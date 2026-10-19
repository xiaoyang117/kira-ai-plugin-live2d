import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kira_live2d_desktop.ai_copy import make_copy,prepare_render_model
from kira_live2d_desktop.model_profile import load_profile
from kira_live2d_desktop.lpk_engine import ensure_engine,engine_ready


class AIControlCopyTests(unittest.TestCase):
    def test_reversible_copy_preserves_mappings_drag_idle_and_original_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            motion={'Version':3,'Meta':{'Duration':1,'Fps':30,'Loop':False,'UserDataCount':1,'TotalUserDataSize':4},
                    'Curves':[{'Target':'Parameter','Id':'ParamA','Segments':[0,0,0,1,1]}],
                    'UserData':[{'Time':0,'Value':'play original sound'}]}
            (source/'pet.moc3').write_bytes(b'MOC3 fixture');(source/'voice.wav').write_bytes(b'audio')
            (source/'wave.motion3.json').write_text(json.dumps(motion),encoding='utf-8')
            original={'Version':3,'FileReferences':{'Moc':'pet.moc3','Textures':[],
                'Motions':{'Idle':[{'File':'wave.motion3.json'}],
                'Text':[{'Name':'TextAnimation','File':'wave.motion3.json'}],
                'TapBody':[{'Name':'Wave','File':'wave.motion3.json','Sound':'voice.wav','Text':'native text','Command':'original event'}]}},
                'Controllers':{'ParamTrigger':{'Enabled':True},'ParamHit':{'Items':[{'HitArea':'Body','Id':'ParamA','Name':'drag','Axis':1,'Factor':0.1,'ReleaseType':3,'MinMtn':'old'}]}},
                'HitAreas':[{'Name':'Body','Id':'Body'}]}
            entry=source/'Pet.model3.json';entry.write_text(json.dumps(original),encoding='utf-8')
            before={str(path):path.read_bytes() for path in source.iterdir() if path.is_file()}
            result=make_copy(entry,root/'data');self.assertFalse(result['reused'])
            copied=Path(result['model_path']);data=json.loads(copied.read_text(encoding='utf-8'))
            self.assertEqual(Path(result['backup_path']).read_bytes(),entry.read_bytes())
            self.assertFalse((copied.parent/'voice.wav').exists())
            self.assertNotIn('ParamTrigger',data['Controllers'])
            drag=data['Controllers']['ParamHit']['Items'][0];self.assertNotIn('MinMtn',drag);self.assertEqual(drag['Factor'],0.1)
            self.assertEqual(data['FileReferences']['Motions']['Idle'],original['FileReferences']['Motions']['Idle'])
            self.assertNotIn('Sound',data['FileReferences']['Motions']['TapBody'][0])
            self.assertNotIn('Text',data['FileReferences']['Motions']['TapBody'][0])
            cleaned=json.loads((copied.parent/'wave.motion3.json').read_text(encoding='utf-8'))
            self.assertNotIn('UserData',cleaned);self.assertEqual(cleaned['Curves'],motion['Curves'])
            self.assertEqual(set(load_profile(str(entry))['motions']),set(load_profile(str(copied))['motions']))
            self.assertEqual(load_profile(str(entry))['drag_candidates'],load_profile(str(copied))['drag_candidates'])
            self.assertTrue(make_copy(entry,root/'data')['reused'])
            runtime,state,preferences=prepare_render_model(entry,root/'data',True)
            self.assertEqual(runtime['original'],str(entry.resolve()))
            self.assertIn(str((source/'wave.motion3.json').resolve()),runtime['motion_files'])
            self.assertEqual(state['stage'],'prepared')
            normal,disabled,normal_preferences=prepare_render_model(entry,root/'data',False)
            self.assertEqual(disabled['stage'],'disabled');self.assertEqual(preferences,normal_preferences)
            self.assertEqual(normal['original'],runtime['original'])
            self.assertEqual(before,{str(path):path.read_bytes() for path in source.iterdir() if path.is_file()})

    def test_authored_initial_part_visibility_survives_command_cleaning(self):
        from kira_live2d_desktop.native_shell.initial_pose import initial_part_opacities
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            (source/'pet.moc3').write_bytes(b'MOC3 fixture')
            motion={'Version':3,'Meta':{'Duration':1,'Fps':30},'Curves':[
                {'Target':'PartOpacity','Id':'PartHand01','Segments':[0,1,0,1,1]},
                {'Target':'PartOpacity','Id':'PartHand02','Segments':[0,0,0,1,0]}]}
            (source/'body.json').write_text(json.dumps(motion))
            idle={'Version':3,'Meta':{'Duration':1,'Fps':30},'Curves':[
                {'Target':'Parameter','Id':'ParamA','Segments':[0,0,0,1,0]}]}
            (source/'idle.json').write_text(json.dumps(idle))
            original={'Version':3,'FileReferences':{'Moc':'pet.moc3','Textures':[],
                'Motions':{'Idle':[{'File':'idle.json','Command':'start_mtn Body:Default;launch something'}],
                    'Body':[{'Name':'Other','File':'idle.json'},
                            {'Name':'Default','File':'body.json','Command':'start_mtn Idle'}]}}}
            entry=source/'pet.model3.json';entry.write_text(json.dumps(original))
            before=entry.read_bytes();expected={'PartHand01':1.,'PartHand02':0.}
            self.assertEqual(initial_part_opacities(entry),expected)
            normal,_,_=prepare_render_model(entry,root/'data',False)
            copied,state,_=prepare_render_model(entry,root/'data',True)
            self.assertEqual(normal['initial_parts'],expected)
            self.assertEqual(copied['initial_parts'],expected)
            cleaned=json.loads(Path(state['model_path']).read_text(encoding='utf8'))
            self.assertNotIn('Command',cleaned['FileReferences']['Motions']['Idle'][0])
            self.assertEqual(entry.read_bytes(),before)
            original['FileReferences']['Pose']='own.pose3.json'
            self.assertEqual(initial_part_opacities(entry,original),{})
            original['FileReferences'].pop('Pose')
            original['FileReferences']['Motions']['Idle'][0]['Command']='delete_files Body:Default'
            self.assertEqual(initial_part_opacities(entry,original),{})

    def test_copy_failure_keeps_original_model_loadable(self):
        from kira_live2d_desktop.tests.test_model_library import model_files
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            for name,value in model_files().items():
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            with patch('kira_live2d_desktop.ai_copy.make_copy',side_effect=ValueError('copy failure')):
                model,state,_=prepare_render_model(source/'Pet.model3.json',root/'data',True)
            self.assertEqual(state['stage'],'error');self.assertTrue(Path(model['path']).is_file())
            self.assertEqual(model['original'],str((source/'Pet.model3.json').resolve()))


class OnDemandEngineTests(unittest.TestCase):
    def test_first_download_cached_reuse_and_integrity_check(self):
        raw=b'pinned engine fixture';digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory,patch('kira_live2d_desktop.lpk_engine.ASSETS',{'Core/engine.py':('https://example.invalid/engine',digest)}):
            with patch('kira_live2d_desktop.lpk_engine.urlopen',side_effect=lambda *a,**k:io.BytesIO(raw)) as download:
                self.assertFalse(engine_ready(directory));ensure_engine(directory)
                self.assertTrue(engine_ready(directory));ensure_engine(directory);self.assertEqual(download.call_count,1)
            (Path(directory)/'Core/engine.py').write_bytes(b'corrupted')
            with patch('kira_live2d_desktop.lpk_engine.urlopen',return_value=io.BytesIO(b'wrong content')):
                with self.assertRaisesRegex(ValueError,'校验失败'):ensure_engine(directory)
            self.assertFalse(engine_ready(directory))


class LpkUnicodeTests(unittest.TestCase):
    def test_unpack_worker_uses_utf8_for_unicode_names_under_legacy_locale(self):
        import os
        import subprocess
        import zipfile
        from kira_live2d_desktop.lpk_engine import unpack_lpk
        real_run=subprocess.run
        title='アリス・マーガトロイド😀'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);engine=root/'engine';(engine/'Core').mkdir(parents=True)
            (engine/'Core/lpk_loader.py').write_text(
                'from pathlib import Path\nimport sys\nclass LpkLoader:\n'
                ' def __init__(self,*args):pass\n'
                ' def extract(self,output):\n'
                '  assert sys.stdout.encoding.lower().replace("-", "") == "utf8"\n'
                '  assert sys.stderr.encoding.lower().replace("-", "") == "utf8"\n'
                '  name='+repr(title)+'\n'
                '  print(name, flush=True)\n'
                '  print(name, file=sys.stderr, flush=True)\n'
                '  (Path(output)/(name+".txt")).write_text(name,encoding="utf8")\n',encoding='utf8')
            package=root/'pet.lpk'
            with zipfile.ZipFile(package,'w') as archive:
                archive.writestr('config.mlve',json.dumps({'type':'STD2_0','list':[]}))
            def run(command,**kwargs):
                self.assertEqual(command[1:4],['-I','-X','utf8'])
                return real_run(command,env={**os.environ,'PYTHONIOENCODING':'cp936','PYTHONUTF8':'0'},**kwargs)
            with patch('kira_live2d_desktop.lpk_engine.ensure_engine',return_value=engine),patch('kira_live2d_desktop.lpk_engine.subprocess.run',side_effect=run):
                unpack_lpk(package,root/'output',root)
            self.assertEqual((root/'output'/(title+'.txt')).read_text(encoding='utf8'),title)
            self.assertEqual((root/'output-unpack.log').read_text(encoding='utf8').count(title),2)
