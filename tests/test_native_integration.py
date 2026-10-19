"""Native-only plugin regression tests using KiraAI's real loader, no GUI/paid LLM."""
import asyncio,importlib,json,socket,sys,tempfile,time,types,unittest
from dataclasses import fields
from pathlib import Path
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,r'H:\KiraAI-2.14.0\KiraAI-2.14.0')
from core.utils.path_utils import init_paths
RUNTIME=tempfile.TemporaryDirectory(dir=ROOT/'_checks',ignore_cleanup_errors=True);init_paths(data_dir=RUNTIME.name)
from core.plugin import PluginContext,PluginManager
from core.adapter import AdapterManager
from core.adapter.context import AdapterContext
from core.adapter.adapter_info import AdapterInfo
from core.adapter.builtin.webchat.webchat import WebChatAdapter
from core.adapter.capabilities import IMCapability
from core.webchat.store import WebChatStore
from core.webchat.service import WebChatService
from core.chat.message_elements import Text,Image
from core.chat import MessageChain
from core.agent.func_tool_manager import FuncToolManager
from aiohttp import ClientSession

class NativeIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        init_paths(data_dir=RUNTIME.name)
        import core.plugin.manager as manager_module
        for name,value in [('PLUGIN_CONFIG_DIR',Path(RUNTIME.name)/'config/plugins'),('PLUGIN_STATE_FILE',Path(RUNTIME.name)/'config/plugins.json')]:
            setting=patch.object(manager_module,name,value);setting.start();self.addCleanup(setting.stop)
        self.queue=asyncio.Queue()
        cfg=Path(RUNTIME.name)/'config/plugins/kira-ai-plugin-live2d.json';cfg.parent.mkdir(parents=True,exist_ok=True)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        # Keep an old renderer setting deliberately: it must never start ViewerEX.
        cfg.write_text(json.dumps({'renderer_mode':'viewerex','viewer_url':'ws://invalid.invalid/api','shell_connection_mode':'local','bridge_port':self.port,'native_model_path':str(ROOT/'models/Yayoi_Sakura_ViewerEX/Yayoi_Sakura.model3.json'),'touch_test_mode':True}),encoding='utf-8')
        for name,path in [('plugins',ROOT),('plugins.kira_live2d_desktop',ROOT/'kira_live2d_desktop')]:
            module=types.ModuleType(name);module.__path__=[str(path)];sys.modules[name]=module
        self.native=importlib.import_module('plugins.kira_live2d_desktop.native_shell.client')
        start=patch.object(self.native.NativeClient,'start',new=AsyncMock());start.start();self.addCleanup(start.stop)
        self.ctx=PluginContext(**{f.name:None for f in fields(PluginContext)})
        self.ctx.config={};self.ctx.provider_mgr=SimpleNamespace(get_default_tts=lambda:object())
        self.ctx.tool_mgr=FuncToolManager({});self.ctx.adapter_mgr=AdapterManager({},self.queue)
        self.ctx.event_bus=SimpleNamespace(publish=self.queue.put)
        self.store=WebChatStore(Path(RUNTIME.name)/('webchat-'+str(self.port)));await self.store.initialize()
        await self.store.set_setting('profile',{'nickname':'网页用户','peer_nickname':'Kira','description':''})
        self.web_adapter=WebChatAdapter(AdapterContext(info=AdapterInfo(True,'builtin-webchat','webchat','webchat'),event_queue=self.queue),self.store)
        await self.ctx.adapter_mgr.register_builtin_adapter(self.web_adapter)
        self.web_cap=self.web_adapter.get_capability(IMCapability);self.web_original=self.web_cap.publish
        self.service=WebChatService(self.web_adapter,SimpleNamespace(update_session=AsyncMock()))
        self.manager=PluginManager(self.ctx);self.ctx.plugin_mgr=self.manager
        await self.manager.load_plugin_from_dir(ROOT/'kira_live2d_desktop',auto_install=False)
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d');self.assertIsNotNone(self.plugin)
        self.client=ClientSession();self.headers={'Authorization':'Bearer '+self.plugin.token}
        self.url=f'http://127.0.0.1:{self.port}'
        self.plugin.viewer.process=SimpleNamespace(poll=lambda:0)
        self.plugin.viewer.ready=True;self.plugin.viewer.heartbeat=time.monotonic()
        # No process is launched in integration tests. Only UI/transport tests render.
        self.plugin.viewer.process=SimpleNamespace(poll=lambda:None,wait=lambda:0)
        self.plugin.viewer.send=AsyncMock(return_value=1);self.plugin.viewer.request=AsyncMock(return_value={})
    async def asyncTearDown(self):
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d') or self.plugin
        if self.plugin.viewer:self.plugin.viewer.process=None
        await self.manager.terminate('kira-ai-plugin-live2d');await self.client.close()
    def request(self,body):return SimpleNamespace(body=AsyncMock(return_value=json.dumps(body).encode()),json=AsyncMock(return_value=body))
    async def test_native_only_load_and_authenticated_feedback(self):
        self.assertTrue(self.plugin.native_mode)
        self.assertIsInstance(self.plugin.viewer,self.native.NativeClient)
        settings=await self.plugin.settings_get()
        for key in ('renderer_mode','viewer_url','model_index','auto_ai_control','model_path'):self.assertNotIn(key,settings['config'])
        async with self.client.post(self.url+'/native/feedback',json={'ready':True}) as r:self.assertEqual(r.status,401)
        for path in ('/viewer/event',):
            async with self.client.post(self.url+path,json={},headers=self.headers) as r:self.assertEqual(r.status,404)
        self.assertTrue(settings['model_tracking']['following'])
        self.assertIn('drag_preview',settings['event_bridge']['features'])
        await self.plugin.native_debug(self.request({'revision':self.plugin.config_revision()}))
        self.plugin.viewer.request.assert_awaited_with('debug',enabled=True)
    async def test_native_drag_feedback_user_events_test_mode_and_repeat(self):
        from kira_live2d_desktop.interaction import drag_key
        source={'area':'ArtMesh1','parameter':'ParamA','name':'cloth','enabled':True}
        source['id']=drag_key(source['area'],source['parameter'],source['name'])
        profile=self.plugin.model_profile();profile['drag_candidates']=[source]
        self.plugin.model_profile=lambda *a:profile
        self.plugin.plugin_cfg['drag_events']=json.dumps({source['id']:{'max':'提起裙摆'}})
        self.plugin.submit=AsyncMock()
        async def send(nonce,**kw):
            data={'kind':'drag',**source,'phase':'max','nonce':nonce,'gesture':'gesture1',**kw}
            async with self.client.post(self.url+'/native/feedback',json={'drag':data,'key':self.plugin.tracking_status()['key']},headers=self.headers) as response:self.assertEqual(response.status,200,await response.text())
        await send('first');self.assertEqual(len(self.plugin.interactions),1);self.plugin.submit.assert_not_awaited()
        await send('second');self.assertEqual(len(self.plugin.interactions),1)
        self.plugin.plugin_cfg['touch_test_mode']=False;self.plugin.plugin_cfg['drag_repeat_boundaries']=True
        await send('third');self.assertEqual(len(self.plugin.interactions),2);self.plugin.submit.assert_awaited_once()
        self.assertIn('提起裙摆',self.plugin.submit.call_args.args[0])
        self.plugin.submit.reset_mock();self.plugin.plugin_cfg['drag_events']=''
        await send('fourth',gesture='newgesture');self.plugin.submit.assert_not_awaited()
    async def test_builtin_chat_routes_once_and_persists_both_directions(self):
        request_id='test-web-message'
        await self.service.submit(request_id,'从网页发来')
        event=await asyncio.wait_for(self.queue.get(),2)
        self.assertEqual(event.session.sid,self.plugin.sid)
        self.assertEqual(event.adapter.name,'kira_desktop')
        self.assertEqual(event.message.chain[0].text,'从网页发来')
        await self.service.submit(request_id,'从网页发来')
        self.assertTrue(self.queue.empty(),'A retry must not generate another AI turn')
        result=await self.plugin.deliver(self.plugin.recipient,MessageChain([Text('网页回复')]))
        self.assertTrue(result.ok)
        rows=(await self.store.list_messages())['messages']
        self.assertEqual([r['direction'] for r in rows],['incoming','outgoing'])
        self.assertEqual(rows[0]['id'],request_id)
        self.assertEqual(rows[1]['id'],result.message_id)
        self.assertEqual(rows[1]['chain'][0]['text'],'网页回复')
        self.assertEqual(self.plugin.input_mode,'web')

    async def test_desktop_and_interaction_visible_in_builtin_history_and_reload(self):
        await self.plugin.submit('桌面发来',request_id='desktop-example')
        await self.queue.get()
        self.plugin.pending=False;await self.plugin.webchat.finish()
        await self.plugin.submit('换上新衣服',interaction=True) # Test mode skips all interaction messages.
        self.plugin.plugin_cfg['touch_test_mode']=False
        await self.plugin.submit('换上新衣服',interaction=True)
        await self.queue.get()
        await self.plugin.deliver(self.plugin.recipient,MessageChain([Text('好看吗')]))
        rows=(await self.store.list_messages())['messages']
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[1]['chain'][0]['type'],'notice')
        reopened=WebChatStore(self.store.root)
        self.assertEqual((await reopened.list_messages())['messages'],rows)
        self.assertFalse(self.plugin.adapter.info.config['allow_file_tools'])

    async def test_web_continuous_send_uses_native_event_queue_and_stop_restores_builtin(self):
        self.plugin.pending=True
        await self.service.submit('native-1','第一条')
        await self.service.submit('native-2','第二条')
        # Native WebChat publishes immediately even during an AI reply. Kira owns
        # batching/consecutive-message behavior; the plugin adds no wait or queue.
        self.assertEqual(self.queue.qsize(),2)
        first,second=self.queue.get_nowait(),self.queue.get_nowait()
        self.assertEqual([first.message.chain[0].text,second.message.chain[0].text],['第一条','第二条'])
        self.assertEqual(first.session.sid,second.session.sid)
        await self.plugin.webchat.close()
        self.assertEqual(self.web_cap.publish,self.web_original)
        request=await self.store.latest_request();self.assertEqual(request['status'],'interrupted')
        self.web_cap.receive_message('restored',MessageChain([Text('正常网页')]),{'nickname':'用户','peer_nickname':'Kira'})
        restored=await asyncio.wait_for(self.queue.get(),2)
        self.assertEqual(restored.adapter.name,'webchat')

    async def test_native_web_attachments_binding_and_batch_completion(self):
        from PIL import Image as PILImage
        image_path=self.store.root/'input.png';PILImage.new('RGB',(8,8),'blue').save(image_path)
        self.plugin.plugin_cfg.update(continue_bound_session=True,binding_session='qq:dm:12345')
        await self.service.submit('attachment','',[Image(str(image_path))])
        image_event=self.queue.get_nowait()
        self.assertEqual(image_event.session.sid,'webchat:dm:admin')
        self.assertEqual(image_event.message.sender.user_id,'admin')
        self.assertEqual(image_event.message.self_id,'webchat')
        self.assertIsInstance(image_event.message.chain[0],Image)
        await self.service.submit('next-turn','下一条')
        next_event=self.queue.get_nowait()
        await self.plugin.failed(image_event,ValueError('test failure'))
        self.assertTrue(self.plugin.pending,'Finishing one batch must preserve the next accepted input')
        self.assertEqual((await self.store.latest_request())['status'],'sent')
        await self.plugin.finished(next_event)
        self.assertFalse(self.plugin.pending)

    async def test_shared_webchat_route_uses_native_context_and_delivers_once_without_binding(self):
        from core.workflow.src.im.message_delivery import MessageDeliveryService
        self.plugin.plugin_cfg.update(continue_bound_session=True,binding_session='')
        self.assertEqual(self.plugin.sid,self.web_adapter.SID)
        await self.service.submit('native-context','接着网页聊')
        event=self.queue.get_nowait()
        self.assertEqual(event.session.sid,'webchat:dm:admin')
        self.assertEqual(event.message.message_id,'native-context')
        self.assertEqual(event.adapter.name,'webchat')
        self.assertEqual(event.message.sender.nickname,'网页用户')
        service=MessageDeliveryService(None,self.ctx.adapter_mgr,None)
        self.plugin.reply_route.enter(event)
        try:
            result=await service.send_message_chain(event.session.sid,MessageChain([Text('接续网页上下文的回复')]))
        finally:self.plugin.reply_route.leave()
        self.assertTrue(result.ok)
        self.plugin.viewer.send.assert_awaited()
        rows=(await self.store.list_messages())['messages']
        self.assertEqual(len(rows),2,'Reply must appear once in native web chat')
        self.assertEqual(rows[1]['id'],result.message_id)
        await self.plugin.finished(event)
        await self.plugin.submit('桌面继续',request_id='desktop-native-context')
        desktop=self.queue.get_nowait()
        self.assertEqual(desktop.session.sid,'webchat:dm:admin')
        self.assertEqual(desktop.message.sender.user_id,'admin')
        self.assertIsNotNone(await self.store.get_message(desktop.message.message_id))
        self.plugin.plugin_cfg['continue_bound_session']=False
        self.assertEqual(self.plugin.sid,self.plugin.transport_sid)

    async def test_save_and_reload_webchat_context_without_selected_user(self):
        values=self.plugin.configuration();values.update(continue_bound_session=True,binding_session='',nickname='')
        await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertTrue(self.plugin.use_webchat_session)
        self.assertEqual(self.plugin.sid,'webchat:dm:admin')
        self.assertEqual(self.plugin.binding(),None)

    async def test_retained_desktop_history_import_once_with_original_timestamps(self):
        def record(identity,direction,text,timestamp):
            return SimpleNamespace(id=identity,platform_message_id=identity,direction=direction,chain=MessageChain([Text(text)]),sender_name='旧用户',timestamp=timestamp,status='sent')
        old_out=record('old-out','outgoing','旧回复',200)
        old_in=record('old-in','incoming','旧消息',100)
        self.ctx.message_history=SimpleNamespace(list_messages=AsyncMock(side_effect=[SimpleNamespace(messages=[old_out],next_cursor='older'),SimpleNamespace(messages=[old_in],next_cursor=None)]))
        await self.plugin.webchat.import_history()
        rows=(await self.store.list_messages())['messages']
        self.assertEqual([r['timestamp'] for r in rows],[100,200])
        self.assertEqual([r['chain'][0]['text'] for r in rows],['旧消息','旧回复'])
        await self.plugin.webchat.import_history()
        self.assertEqual(self.ctx.message_history.list_messages.await_count,2)
        self.assertEqual(len((await self.store.list_messages())['messages']),2)

    async def test_save_reloads_preserves_native_path_and_model_preferences(self):
        values=self.plugin.configuration();values['bubble_seconds']=18
        old_data_dir=self.plugin.data_dir
        result=await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(result['config']['bubble_seconds'],18)
        self.assertTrue(self.plugin.native_mode);self.assertTrue(self.plugin.tracking_status()['following'])
        store=json.loads((old_data_dir/'model-settings.json').read_text(encoding='utf-8'))
        self.assertEqual(store['models'][self.plugin.tracking_status()['key']]['settings']['bubble_seconds'],18)


    async def test_model_import_and_switch_restores_separate_settings(self):
        from starlette.requests import Request
        from kira_live2d_desktop.tests.test_model_library import model_files
        import io,zipfile
        files=model_files('LibraryPet');buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            for name,value in files.items():archive.writestr(name,value)
        boundary='ModelImportBoundary'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="paths"\r\n\r\n["test.zip"]\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="test.zip"\r\nContent-Type: application/zip\r\n\r\n').encode()+buffer.getvalue()+f'\r\n--{boundary}--\r\n'.encode()
        async def receive():return {'type':'http.request','body':body,'more_body':False}
        request=Request({'type':'http','method':'POST','path':'/model/import','headers':[(b'content-type',f'multipart/form-data; boundary={boundary}'.encode())]},receive)
        result=await self.plugin.import_model(request);target=result['imported'][0]
        self.assertTrue(any(item['path']==target for item in result['model_library']))
        values=self.plugin.configuration();original=values['native_model_path'];values['bubble_seconds']=47
        await self.plugin.settings_save(self.request({'revision':self.plugin.config_revision(),'config':values}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        values=self.plugin.configuration();values['native_model_path']=target
        await self.plugin.settings_save(self.request({'revision':self.plugin.config_revision(),'config':values}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(self.plugin.plugin_cfg['native_model_path'],target)
        self.assertNotEqual(self.plugin.plugin_cfg['bubble_seconds'],47,'A new model must not inherit the previous settings')
        values=self.plugin.configuration();values['bubble_seconds']=21
        await self.plugin.settings_save(self.request({'revision':self.plugin.config_revision(),'config':values}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        values=self.plugin.configuration();values['native_model_path']=original
        await self.plugin.settings_save(self.request({'revision':self.plugin.config_revision(),'config':values}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(self.plugin.plugin_cfg['bubble_seconds'],47)
        values=self.plugin.configuration();values['native_model_path']=target
        await self.plugin.settings_save(self.request({'revision':self.plugin.config_revision(),'config':values}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(self.plugin.plugin_cfg['bubble_seconds'],21)

    async def test_settings_does_not_query_unused_full_chat_session_history(self):
        previous=self.ctx.session_mgr
        sessions=AsyncMock(side_effect=AssertionError('unrelated history queried'))
        self.ctx.session_mgr=SimpleNamespace(get_sessions=sessions)
        try:
            result=await self.plugin.settings_get()
            self.assertIn('status',result)
            sessions.assert_not_called()
        finally:self.ctx.session_mgr=previous

    async def test_ai_copy_toggle_preserves_selected_model_identity_and_preferences(self):
        before=self.plugin.configuration();key=self.plugin.tracking_status()['key']
        values=dict(before);values['ai_control_copy_enabled']=False
        result=await self.plugin.settings_save(self.request({'revision':self.plugin.config_revision(),'config':values}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertFalse(result['config']['ai_control_copy_enabled'])
        self.assertEqual(self.plugin.tracking_status()['key'],key)
        for field in ('native_model_path','model_overrides','resource_policy','drag_events','outfits'):
            self.assertEqual(result['config'][field],before[field])


    async def test_select_model_restarts_and_ready_feedback_discovers_new_resources(self):
        from kira_live2d_desktop.tests.test_model_library import model_files,uploads
        from plugins.kira_live2d_desktop.model_library import ModelLibrary
        files=model_files('AutoReady')
        target=ModelLibrary(self.plugin.data_dir).import_files(uploads(files),list(files))[0]
        before=self.native.NativeClient.start.await_count
        result=await self.plugin.select_model(self.request({'path':target,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(self.native.NativeClient.start.await_count,before+1)
        self.assertEqual(result['config']['native_model_path'],target)
        self.assertFalse(result['status']['viewer_connected'])
        self.assertEqual(len(self.plugin.model_profile()['motions']),0)
        motion={'Version':3,'Meta':{'Duration':1,'Fps':30},'Curves':[{'Target':'Parameter','Id':'ParamAngleX','Segments':[0,0,0,1,10]}]}
        (Path(target).parent/'wave.motion3.json').write_text(json.dumps(motion),encoding='utf-8')
        self.plugin.viewer.generation='new-instance';self.plugin.viewer.process=SimpleNamespace(poll=lambda:None)
        await self.plugin.viewer.feedback(SimpleNamespace(json=AsyncMock(return_value={'ready':True,'generation':'new-instance'})))
        self.assertTrue(self.plugin.viewer.connected)
        self.assertTrue(self.plugin.model_profile()['motions'],'New motion was not discovered after ready')
        settings=await self.plugin.settings_get();self.assertTrue(settings['status']['viewer_connected'])
        self.assertTrue(settings['motions'])



    async def test_action_round_limits_validate_and_survive_reload(self):
        from fastapi import HTTPException
        values=self.plugin.configuration()
        for key,bad in [('action_agent_max_steps',0),('action_agent_max_motions',33),('action_agent_max_expressions',-1),('action_agent_max_steps',True)]:
            with self.assertRaises(HTTPException) as result:
                await self.plugin.settings_save(self.request({'config':{**values,key:bad},'revision':self.plugin.config_revision()}))
            self.assertEqual(result.exception.status_code,422)
        values.update(action_agent_max_steps=12,action_agent_max_motions=5,action_agent_max_expressions=0)
        await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(self.plugin.action_agent.limits(),{'steps':12,'motions':5,'expressions':0})
        self.assertEqual((await self.plugin.settings_get())['config']['action_agent_max_motions'],5)

    async def test_delivery_does_not_feed_or_wait_for_action_agent(self):
        self.plugin.plugin_cfg['touch_test_mode']=False
        entered=asyncio.Event();release=asyncio.Event()
        async def decide(messages):
            entered.set();await release.wait();return {'tool':'finish'}
        self.plugin.action_agent.ask=AsyncMock(side_effect=decide)
        self.plugin.action_agent.observe('user','请做动作')
        await asyncio.wait_for(entered.wait(),.5)
        generation=self.plugin.action_agent.generation
        await asyncio.wait_for(self.plugin.deliver(self.plugin.recipient,MessageChain([Text('第一句')])),.3)
        await asyncio.wait_for(self.plugin.deliver(self.plugin.recipient,MessageChain([Text('第二句')])),.3)
        self.assertEqual(self.plugin.action_agent.generation,generation)
        self.plugin.action_agent.ask.assert_awaited_once()
        payload=json.loads(self.plugin.action_agent.ask.call_args.args[0][1].content)
        self.assertEqual(payload['event']['text'],'请做动作')
        self.assertNotIn('第一句',json.dumps(payload,ensure_ascii=False))
        self.assertNotIn('第二句',json.dumps(payload,ensure_ascii=False))
        self.assertFalse(self.plugin.action_agent.round.done())
        release.set()
        await asyncio.wait_for(asyncio.shield(self.plugin.action_agent.round),.3)

    async def test_manual_outfit_category_survives_save_and_reaches_action_agent(self):
        data=await self.plugin.settings_get()
        name=next(name for name,info in data['resource_analysis']['expressions'].items() if not info['appearance'])
        values=self.plugin.configuration()
        values['resource_policy']=json.dumps({'appearance_expressions':[name],'enabled_expressions':[name]})
        await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        result=await self.plugin.settings_get()
        self.assertTrue(result['resource_analysis']['expressions'][name]['appearance'])
        self.assertIn('手动标记',result['resource_analysis']['expressions'][name]['summary'])
        self.assertIn(name,result['expressions'])
        self.assertTrue(self.plugin.action_agent.resources()['expressions'][name]['appearance'])

    async def test_remote_mode_auth_bundle_single_peer_and_disable(self):
        import uuid,zipfile
        values=self.plugin.configuration();values['shell_connection_mode']='remote'
        await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d');viewer=self.plugin.viewer
        viewer.generation=uuid.uuid4().hex
        await viewer.launch()
        self.assertIsNone(viewer.process,'Remote mode must not launch a host renderer')
        self.assertTrue(viewer.bundle.is_file())
        headers={'Authorization':'Bearer '+self.plugin.remote_token};peer=uuid.uuid4().hex
        async with self.client.post(self.url+'/native/connect',json={'client_id':peer}) as r:self.assertEqual(r.status,401)
        async with self.client.post(self.url+'/native/connect',headers=headers,json={'client_id':peer}) as r:
            self.assertEqual(r.status,200,await r.text());metadata=await r.json()
        async with self.client.get(self.url+metadata['bundle_url'],headers=headers) as r:
            self.assertEqual(r.status,200);body=await r.read();self.assertTrue(body.startswith(b'PK'))
        async with self.client.post(self.url+'/native/connect',headers=headers,json={'client_id':uuid.uuid4().hex}) as r:self.assertEqual(r.status,409)
        async with self.client.post(self.url+'/native/feedback',headers=headers,json={'generation':viewer.generation,'client_id':peer,'ready':True}) as r:self.assertEqual(r.status,200)
        self.assertTrue(viewer.connected)
        async with self.client.get(self.url+'/native/commands',headers=headers,params={'generation':viewer.generation,'client_id':uuid.uuid4().hex}) as r:self.assertTrue((await r.json())['obsolete'])
        async with self.client.post(self.url+'/native/disconnect',headers=headers,json={'client_id':peer}) as r:self.assertEqual(r.status,200)
        self.assertFalse(viewer.connected)
        original_key=self.plugin.remote_token
        settings=await self.plugin.settings_get();self.assertTrue(settings['remote_shell']['enabled'])
        values=self.plugin.configuration();values['shell_connection_mode']='disabled'
        await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        async with self.client.get(self.url+'/status',headers={'Authorization':'Bearer '+original_key}) as r:self.assertEqual(r.status,401)
        self.assertEqual(self.plugin.remote_token,'')

    async def test_unselected_mode_ignores_legacy_flag_and_stays_stopped_after_save(self):
        config_path=Path(RUNTIME.name)/'config/plugins/kira-ai-plugin-live2d.json'
        legacy=json.loads(config_path.read_text(encoding='utf-8'));legacy.pop('shell_connection_mode',None)
        config_path.write_text(json.dumps(legacy),encoding='utf-8')
        self.manager.plugin_configs['kira-ai-plugin-live2d'].pop('shell_connection_mode',None)
        self.plugin.plugin_cfg.pop('shell_connection_mode',None)
        self.native.NativeClient.start.reset_mock()
        with patch.object(self.native,'ensure_runtime',side_effect=AssertionError('Unexpected runtime download')):
            await self.manager.update_plugin_config('kira-ai-plugin-live2d',{'remote_shell_enabled':True})
            self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
            self.assertIsInstance(self.plugin.viewer,self.native.InactiveNativeClient)
            self.assertFalse(self.plugin.viewer.connected)
            self.assertIsNone(self.plugin.viewer.task)
            self.assertIsNone(self.plugin.viewer.process)
            self.assertEqual(self.plugin.remote_token,'')
            settings=await self.plugin.settings_get()
            self.assertEqual(settings['config']['shell_connection_mode'],'disabled')
            self.assertFalse(settings['remote_shell']['enabled'])
            headers={'Authorization':'Bearer '+self.plugin.token}
            async with self.client.post(self.url+'/native/connect',headers=headers,json={}) as r:self.assertEqual(r.status,404)
            async with self.client.post(self.url+'/native/feedback',headers=headers,json={'ready':True}) as r:
                self.assertEqual(r.status,202)
            self.assertFalse(self.plugin.viewer.connected)
            values=self.plugin.configuration();values['bubble_seconds']=21
            await self.plugin.settings_save(self.request({'config':values,'revision':self.plugin.config_revision()}))
            self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
            await self.plugin.select_model(self.request({'path':values['native_model_path'],'revision':self.plugin.config_revision()}))
            self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
            await self.manager.init_plugin('kira-ai-plugin-live2d')
            self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
            self.assertIsInstance(self.plugin.viewer,self.native.InactiveNativeClient)
            self.native.NativeClient.start.assert_not_awaited()

    async def test_mode_selector_starts_only_selected_transport_and_rejects_stale_changes(self):
        await self.plugin.select_shell_mode(self.request({'mode':'disabled','revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.native.NativeClient.start.reset_mock()
        old_revision=self.plugin.config_revision()
        await self.plugin.select_shell_mode(self.request({'mode':'local','revision':old_revision}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(type(self.plugin.viewer),self.native.NativeClient)
        self.native.NativeClient.start.assert_awaited_once()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            await self.plugin.select_shell_mode(self.request({'mode':'remote','revision':old_revision}))
        self.assertEqual(error.exception.status_code,409)
        for mode in ('invalid',True,[],None):
            with self.assertRaises(HTTPException) as error:
                await self.plugin.select_shell_mode(self.request({'mode':mode,'revision':self.plugin.config_revision()}))
            self.assertEqual(error.exception.status_code,422)
        await self.plugin.select_shell_mode(self.request({'mode':'remote','revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        from plugins.kira_live2d_desktop.native_shell.remote_server import RemoteNativeClient
        self.assertIsInstance(self.plugin.viewer,RemoteNativeClient)
        self.assertGreaterEqual(len(self.plugin.remote_token),32)
        await self.manager.init_plugin('kira-ai-plugin-live2d')
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertEqual(self.plugin.shell_connection_mode,'remote')
        await self.plugin.select_shell_mode(self.request({'mode':'disabled','revision':self.plugin.config_revision()}))
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        self.assertIsInstance(self.plugin.viewer,self.native.InactiveNativeClient)
        with self.assertRaises(HTTPException):
            await self.plugin.restart_native_shell(self.request({'revision':self.plugin.config_revision()}))

    async def test_websocket_push_ack_chat_and_operation_allowlist(self):
        import uuid
        from aiohttp import WSServerHandshakeError
        viewer=self.plugin.viewer;viewer.generation=uuid.uuid4().hex
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect(self.url+'/native/ws?generation='+viewer.generation)
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect(self.url+'/native/ws?generation=old',headers=self.headers)
        async with self.client.ws_connect(self.url+'/native/ws?generation='+viewer.generation,headers=self.headers) as wire:
            self.assertEqual((await wire.receive_json())['type'],'connected')
            await wire.send_json({'type':'feedback','data':{'ready':True}})
            viewer.send=self.native.NativeClient.send.__get__(viewer)
            started=time.monotonic();sent=asyncio.create_task(viewer.send(13300,{'expId':0}))
            packet=await asyncio.wait_for(wire.receive_json(),1)
            self.assertLess(time.monotonic()-started,.8)
            self.assertEqual(packet['command']['msg'],13300)
            await wire.send_json({'type':'feedback','data':{'msgId':packet['command']['msgId'],'result':{}}})
            await asyncio.wait_for(sent,1)
            await wire.send_json({'type':'rpc','id':'mode','path':'/input','body':{'mode':'desktop'}})
            self.assertEqual((await wire.receive_json())['status'],200)
            await wire.send_json({'type':'rpc','id':'input','path':'/message','body':{'text':'WebSocket 输入','request_id':'ws-test'}})
            response=await asyncio.wait_for(wire.receive_json(),2)
            self.assertEqual(response['status'],202,response)
            event=self.queue.get_nowait();self.assertEqual(event.message.chain[0].text,'WebSocket 输入')
            await wire.send_json({'type':'rpc','id':'forbidden','path':'/action','body':{}})
            response=await wire.receive_json();self.assertIn('error',response)
        await asyncio.sleep(.05)
        self.assertIsNone(viewer.socket)
        self.assertFalse(viewer.ready)

    async def test_select_mode_without_model_defers_download_until_model_is_available(self):
        await self.manager.update_plugin_config('kira-ai-plugin-live2d',{'native_model_path':'','model_path':''})
        self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
        for mode in ('local','remote','disabled'):
            await self.plugin.select_shell_mode(self.request({'mode':mode,'revision':self.plugin.config_revision()}))
            self.plugin=self.manager.get_plugin_inst('kira-ai-plugin-live2d')
            self.assertEqual(self.plugin.shell_connection_mode,mode)
            if mode!='disabled':
                with patch.object(self.native,'ensure_runtime',side_effect=AssertionError('Download without a model')):
                    await self.plugin.viewer.launch()
                self.assertIn('请先导入',self.plugin.viewer.last_error)
            self.assertIsNone(self.plugin.viewer.process)

if __name__=='__main__':unittest.main()
