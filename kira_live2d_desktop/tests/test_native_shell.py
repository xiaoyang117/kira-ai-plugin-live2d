import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock,patch

from kira_live2d_desktop.native_shell.client import NativeClient,NativeFollower
from kira_live2d_desktop.native_shell.model import prepare_model,soften_motion_breath,normalize_motion_counts
from kira_live2d_desktop.model_follow import MODEL_FIELDS

ROOT=Path(__file__).resolve().parents[2]
MODEL=ROOT/'models/Yayoi_Sakura_ViewerEX/Yayoi_Sakura.model3.json'

class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_ack_errors_and_old_connections(self):
        plugin=SimpleNamespace(on_viewer_event=AsyncMock(),model_index=0)
        client=NativeClient(plugin)
        client.process=SimpleNamespace(poll=lambda:None,wait=lambda:0)
        client.ready=True;client.heartbeat=time.monotonic()
        task=asyncio.create_task(client.send(13300,{'expId':2}))
        packet=json.loads((await client.poll(None)).body)['command']
        self.assertEqual(packet['data']['expId'],2)
        await client.feedback(SimpleNamespace(json=AsyncMock(return_value={'msgId':packet['msgId']})))
        self.assertEqual(await task,packet['msgId'])
        task=asyncio.create_task(client.request('outfit',expressions=[2]))
        packet=json.loads((await client.poll(None)).body)['command']
        await client.feedback(SimpleNamespace(json=AsyncMock(return_value={'msgId':packet['msgId'],'error':'bad expression'})))
        with self.assertRaisesRegex(ValueError,'bad expression'):await task
        await client.feedback(SimpleNamespace(json=AsyncMock(return_value={'event':'Head'})))
        plugin.on_viewer_event.assert_awaited_once_with({'type':0,'id':0,'hitArea':'Head'})
        client.heartbeat=0
        with self.assertRaises(ConnectionError):await client.send(13300,{})
        await client.close()
        self.assertEqual(client.queue.get_nowait()['msg'],'quit')
        self.assertFalse(client.connected)

    async def test_restarted_shell_rejects_old_feedback_and_polls(self):
        plugin=SimpleNamespace(on_viewer_event=AsyncMock(),native_model_ready=Mock(),
            action_agent=SimpleNamespace(offer=Mock()))
        client=NativeClient(plugin);client.generation='new-generation'
        client.process=SimpleNamespace(poll=lambda:None)
        old=await client.feedback(SimpleNamespace(json=AsyncMock(return_value={'generation':'old-generation','ready':True,'event':'Head'})))
        self.assertEqual(old.status,202);self.assertFalse(client.connected)
        plugin.on_viewer_event.assert_not_awaited();plugin.native_model_ready.assert_not_called()
        client.queue.put_nowait({'msg':'current'})
        old_poll=await client.poll(SimpleNamespace(query={'generation':'old-generation'}))
        self.assertTrue(json.loads(old_poll.body)['obsolete']);self.assertEqual(client.queue.qsize(),1)
        for _ in range(2):
            await client.feedback(SimpleNamespace(json=AsyncMock(return_value={'generation':'new-generation','ready':True})))
        self.assertTrue(client.connected);plugin.native_model_ready.assert_called_once_with('new-generation')
        plugin.action_agent.offer.assert_called_once()
        current=await client.poll(SimpleNamespace(query={'generation':'new-generation'}))
        self.assertEqual(json.loads(current.body)['command']['msg'],'current')
        client.process=None;await client.close()

    async def test_poll_started_before_restart_does_not_take_new_shell_command(self):
        client=NativeClient(SimpleNamespace());client.generation='old'
        waiting=asyncio.create_task(client.poll(SimpleNamespace(query={'generation':'old'})))
        await asyncio.sleep(0)
        client.generation='new';client.queue.put_nowait({'msg':'for-new-shell'})
        result=await waiting
        self.assertTrue(json.loads(result.body)['obsolete'])
        self.assertEqual(client.queue.get_nowait()['msg'],'for-new-shell')
        await client.close()

    async def test_start_removes_old_quit_command_and_changes_generation(self):
        client=NativeClient(SimpleNamespace());client.generation='old'
        client.ready=True;client.heartbeat=time.monotonic();client.queue.put_nowait({'msg':'quit'})
        client.launch=AsyncMock()
        await client.start();await client.task
        self.assertNotEqual(client.generation,'old');self.assertTrue(client.queue.empty());self.assertFalse(client.ready)
        await client.close()

    def test_model_preparation_keeps_source_and_compact_expression_indices(self):
        before=hashlib.sha256(MODEL.read_bytes()).digest()
        with tempfile.TemporaryDirectory() as directory:
            model=prepare_model(MODEL,directory)
            raw=Path(model['path']).read_bytes()
            self.assertTrue(raw.endswith(b'\n'))
            data=json.loads(raw)
            self.assertEqual([r['Name'] for r in data['FileReferences']['Expressions']],list(map(str,range(10))))
            for item in model['expressions']:
                self.assertTrue(item['File'].isascii())
                self.assertTrue((Path(model['path']).parent/item['File']).is_file())
            self.assertEqual(len(model['motion_files']),3)
            for file in model['motion_files'].values():self.assertTrue(Path(file).is_file())
            self.assertEqual(hashlib.sha256(MODEL.read_bytes()).digest(),before)

    def test_native_staging_handles_unicode_groups_and_incorrect_motion_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'model';source.mkdir()
            (source/'fake.moc3').write_bytes(b'fixture')
            motion={'Version':3,'Meta':{'Duration':1,'Fps':30,'CurveCount':1,
                'TotalSegmentCount':99,'TotalPointCount':1},'Curves':[
                {'Target':'Parameter','Id':'ParamAngleX','Segments':[0,0,0,1,10]},
                {'Target':'Parameter','Id':'ParamAngleY','Segments':[0,0,0,1,5]}]}
            original=json.dumps(motion).encode();(source/'move.motion3.json').write_bytes(original)
            config={'Version':3,'FileReferences':{'Moc':'fake.moc3','Textures':[],
                'Motions':{'提衣服':[{'File':'move.motion3.json','FadeInTime':.3}],
                           'Idle':[{'File':'move.motion3.json'}]}}}
            path=source/'test.model3.json';path.write_text(json.dumps(config))
            model=prepare_model(path,root/'cache')
            staged=json.loads(Path(model['path']).read_text())
            groups=staged['FileReferences']['Motions']
            self.assertIn('Idle',groups)
            self.assertTrue(all(group.isascii() for group in groups))
            self.assertTrue(all(set(row)=={'File'} for rows in groups.values() for row in rows))
            self.assertIn('提衣服',model['motion_entries'])
            resource=Path(model['path']).parent/groups['Idle'][0]['File']
            adapted=json.loads(resource.read_text())
            self.assertEqual(adapted['Meta']['CurveCount'],2)
            self.assertEqual(adapted['Meta']['TotalSegmentCount'],2)
            self.assertEqual(adapted['Meta']['TotalPointCount'],4)
            self.assertEqual(adapted['Curves'],motion['Curves'])
            self.assertEqual((source/'move.motion3.json').read_bytes(),original)
            resource.write_bytes(b'\xff\xfe') # Invalid UTF-8 in an old cache must also be repaired.
            prepare_model(path,root/'cache')
            self.assertEqual(json.loads(resource.read_text())['Meta']['CurveCount'],2)

    def test_resource_suffixes_are_ascii_and_nonmotions_cannot_be_played(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            (source/'pet.moc3').write_bytes(b'fixture')
            (source/'贴图.自定义.png').write_bytes(b'fixture texture')
            (source/'physics.json').write_text(json.dumps({'PhysicsSettings':[]}))
            (source/'bad.exp3.json').write_text(json.dumps({'Parameters':[7]}))
            good={'Parameters':[{'Id':'ParamA','Value':1,'Blend':'Overwrite'}]}
            (source/'good.exp3.json').write_text(json.dumps(good))
            config={'FileReferences':{'Moc':'pet.moc3','Textures':['贴图.自定义.png'],
                'Expressions':[{'Name':'bad','File':'bad.exp3.json'}, {'Name':'good','File':'good.exp3.json'}],
                'Motions':{'test':[{'Name':'not a motion','File':'physics.json'}]}}}
            path=source/'Pet.model3.json';path.write_text(json.dumps(config))
            model=prepare_model(path,root/'data')
            data=json.loads(Path(model['path']).read_text())
            self.assertTrue(data['FileReferences']['Textures'][0].isascii())
            self.assertEqual(len(model['expressions']),1)
            self.assertEqual(model['expression_names'],{'good':0})
            self.assertFalse(model['motion_files'])
            self.assertFalse(data['FileReferences']['Motions'])
            config['FileReferences']['Textures']={'invalid':'type'}
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError,'Textures'):prepare_model(path,root/'data')

    async def test_cancelled_copy_progress_cannot_replace_new_shell_state(self):
        captured=[];entered=asyncio.Event()
        plugin=SimpleNamespace(data_dir=Path('.'),plugin_cfg={'model_path':str(MODEL)},emit=Mock())
        client=NativeClient(plugin);client.generation='old'
        async def background(func,*args):
            if func.__name__=='ensure_runtime':return Path('python.exe')
            captured.append(args[-1]);entered.set()
            await asyncio.Event().wait()
        with patch('kira_live2d_desktop.native_shell.client.asyncio.to_thread',side_effect=background):
            client.task=asyncio.create_task(client.launch())
            await entered.wait();await client.close()
        client.stopping=False;client.generation='new';client.copy_state={'stage':'prepared','message':'new model'}
        captured[0]({'stage':'error','message':'old model'})
        self.assertEqual(client.copy_state,{'stage':'prepared','message':'new model'})
        plugin.emit.assert_not_called()

    def test_resource_escape_is_rejected_before_native_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'outside.moc3').write_bytes(b'fake')
            model=root/'model';model.mkdir()
            path=model/'test.model3.json';path.write_text(json.dumps({'Version':3,'FileReferences':{'Moc':'../outside.moc3','Textures':[]}}))
            with self.assertRaisesRegex(ValueError,'超出模型目录'):prepare_model(path,root/'cache')

    def test_native_model_settings_follow_model_without_viewerex(self):
        defaults=json.loads((ROOT/'kira_live2d_desktop/schema.json').read_text(encoding='utf-8'))
        defaults={k:v['default'] for k,v in defaults.items() if v['type']!='info'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config={**defaults,'native_model_path':str(MODEL),'model_path':str(MODEL)}
            follower=NativeFollower(root,'ws://127.0.0.1/native',0,{k:defaults[k] for k in MODEL_FIELDS})
            self.assertTrue(follower.refresh(config));key=follower.key
            config['bubble_seconds']=42;follower.save(config)
            other=root/'second.model3.json';other.write_bytes(MODEL.read_bytes())
            config['native_model_path']=str(other)
            self.assertTrue(follower.refresh(config))
            config['native_model_path']=str(MODEL)
            self.assertTrue(follower.refresh(config));self.assertEqual(follower.key,key)
            self.assertEqual(config['bubble_seconds'],42)

class NativeInteractionMath(unittest.TestCase):
    def test_drag_factor_axis_boundary_crossing_and_clamping(self):
        from kira_live2d_desktop.native_shell.behavior import DragGesture,project_vertices
        source={'area':'a','parameter':'p','name':'衣服','axis':1,'factor':-.01}
        drag=DragGesture(source,0,0,1,10,20)
        self.assertEqual(drag.update(10,-180),'max');self.assertEqual(drag.value,1)
        self.assertIsNone(drag.update(10,-200))
        self.assertIsNone(drag.update(10,-30));self.assertEqual(drag.update(10,-180),'max')
        self.assertEqual(drag.update(10,120),'min');self.assertEqual(drag.value,0)
        self.assertEqual(drag.packet('begin')['gesture'],drag.packet('end')['gesture'])
        self.assertNotEqual(drag.packet('max')['nonce'],drag.packet('max')['nonce'])
        identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        self.assertEqual(project_vertices([-1,-1,1,1],identity,400,600),[(0,600),(400,0)])
    def test_motion_counts_rebuilt_without_changing_curves_or_source(self):
        motion={'Meta':{'Duration':3,'Loop':True,'CurveCount':1,'TotalSegmentCount':999,'TotalPointCount':1},
            'Curves':[{'Target':'Parameter','Id':'A','Segments':[0,0,0,1,.5,1,1.2,.7,1.8,.8,2,1]},
                {'Target':'Parameter','Id':'B','Segments':[0,0,2,1,1,3,2,0]}],
            'UserData':[{'Time':1,'Value':'换装'}]}
        original=copy.deepcopy(motion)
        adapted=normalize_motion_counts(motion)
        self.assertEqual(adapted['Meta']['CurveCount'],2)
        self.assertEqual(adapted['Meta']['TotalSegmentCount'],4)
        self.assertEqual(adapted['Meta']['TotalPointCount'],8)
        self.assertEqual(adapted['Meta']['UserDataCount'],1)
        self.assertEqual(adapted['Meta']['TotalUserDataSize'],6)
        self.assertEqual(adapted['Curves'],original['Curves'])
        self.assertEqual(motion,original)
        with self.assertRaisesRegex(ValueError,'不完整'):
            normalize_motion_counts({'Meta':{},'Curves':[{'Target':'Parameter','Id':'P','Segments':[0,0,1,1,1]}]})
        with self.assertRaisesRegex(ValueError,'无效'):
            normalize_motion_counts({'Meta':{},'Curves':[{'Segments':[0,float('nan')]}]})

    def test_breath_attenuation_preserves_times_other_parameters_and_source(self):
        motion={'Curves':[{'Target':'Parameter','Id':'ParamBreath','Segments':[0,0,1,.5,.002,1,.915,1.5,.994]},
                          {'Target':'Parameter','Id':'ParamAngleX','Segments':[0,1,0,1,4]}]}
        original=copy.deepcopy(motion)
        scaled=soften_motion_breath(motion,strength=.25)
        self.assertEqual(motion,original)
        self.assertEqual(scaled['Curves'][1],original['Curves'][1])
        self.assertEqual(scaled['Curves'][0]['Segments'],[0,0,1,.5,.0005,1,.22875,1.5,.2485])
        self.assertEqual(soften_motion_breath({'Curves':[{'Target':'Parameter','Id':'PARAM_BREATH','Segments':[0,1,0,2,.5,2,3,0,3,4,1]}]})['Curves'][0]['Segments'],[0,0,0,2,0,2,3,0,3,4,0])
        self.assertEqual(soften_motion_breath(motion)['Curves'][0]['Segments'],[0,0,1,.5,0,1,0,1.5,0])

    def test_mouse_gaze_smooth_bounded_frame_independent_and_returns_to_center(self):
        from kira_live2d_desktop.native_shell.behavior import MouseGaze
        a,b=MouseGaze(),MouseGaze()
        for _ in range(30):a.step(10000,-10000,(200,100),(300,250),1/30)
        for _ in range(60):b.step(10000,-10000,(200,100),(300,250),1/60)
        self.assertAlmostEqual(a.x,b.x);self.assertAlmostEqual(a.y,b.y)
        self.assertTrue(0<a.x<1 and 0<a.y<1)
        prior=a.x;a.step(-10000,10000,(200,100),(300,250),1/30)
        self.assertTrue(-1<a.x<prior)
        for _ in range(60):a.step(10000,-10000,(200,100),(300,250),1/30,enabled=False)
        self.assertLess(abs(a.x)+abs(a.y),1e-5)
        center=MouseGaze();self.assertEqual(center.step(202,98,(200,100),(300,250),1/30),(0,0))

    def test_drag_candidates_keep_controller_options(self):
        from kira_live2d_desktop.interaction import drag_candidates
        source=drag_candidates({'Controllers':{'ParamHit':{'Items':[{'HitArea':'mesh','Id':'p','Name':'裙','Axis':1,'Factor':-.01,'ReleaseType':3}]}}})[0]
        self.assertEqual((source['axis'],source['factor'],source['release']),(1,-.01,3))
