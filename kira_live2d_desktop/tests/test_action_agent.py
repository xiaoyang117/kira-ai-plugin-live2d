import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock,patch
sys.path.insert(0,r'H:\KiraAI-2.14.0\KiraAI-2.14.0')
from core.utils.path_utils import init_paths
ROOT=Path(__file__).resolve().parents[2]
RUNTIME=tempfile.TemporaryDirectory(dir=ROOT/'_checks',ignore_cleanup_errors=True)
init_paths(data_dir=RUNTIME.name)
from kira_live2d_desktop.action_agent import ActionAgent
from kira_live2d_desktop.motion_analysis import catalog,add_discovered,discovered,curve_values
from kira_live2d_desktop.model_profile import load_profile

MODEL=ROOT/'models/Yayoi_Sakura_ViewerEX/Yayoi_Sakura.model3.json'

class AnalysisTests(unittest.TestCase):
    def test_names_curves_and_appearance_are_distinguished_without_renaming(self):
        profile=load_profile(str(MODEL));before=dict(profile['motions'])
        data=catalog(profile)
        self.assertIn('头部上下转动',data['motions']['点头']['summary'])
        self.assertIn('点头',data['motions']['点头']['tags'])
        self.assertIsNotNone(data['motions']['点头']['duration'])
        self.assertTrue(data['expressions']['摘帽子']['appearance'])
        self.assertEqual(profile['motions'],before)
        self.assertEqual(curve_values([0,0,0,1,2,1,1.2,3,1.8,4,2,5]),[0.,2.,3.,4.,5.])
    def test_large_named_motion_catalog_reads_model_once_per_operation(self):
        from kira_live2d_desktop import motion_analysis as analysis
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'wave.motion3.json').write_text(json.dumps({'Meta':{'Duration':1},
                'Curves':[{'Target':'Parameter','Id':'ParamAngleX','Segments':[0,0,0,1,10]}]}))
            path=root/'pet.model3.json'
            path.write_text(json.dumps({'FileReferences':{'Moc':'pet.moc3','Textures':[],
                'Motions':{f'Wave{group}':[{'Name':str(i),'File':'wave.motion3.json'} for i in range(group*100,(group+1)*100)] for group in range(2)}}}))
            profile=load_profile(str(path))
            with patch.object(analysis,'read_json',wraps=analysis.read_json) as read:
                discovered=analysis.add_discovered(profile)
                self.assertLessEqual(read.call_count,2)
            self.assertEqual(set(discovered['motions']),set(profile['motions']))
            with patch.object(analysis,'read_json',wraps=analysis.read_json) as read:
                result=analysis.catalog(profile)
                self.assertLessEqual(read.call_count,2)
            self.assertEqual(len(result['motions']),200)
            self.assertIn('头部左右转动',result['motions']['Wave1:199']['summary'])

    def test_unreferenced_motion_discovery_and_manual_mapping_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);model=base/'sample.model3.json'
            model.write_text(json.dumps({'Version':3,'FileReferences':{'Moc':'fake.moc3','Textures':[]}}))
            motion=base/'happy.motion3.json';motion.write_text(json.dumps({'Meta':{'Duration':1},'Curves':[{'Target':'Parameter','Id':'ParamAngleY','Segments':[0,0,0,1,10]}]}))
            discovered.cache_clear()
            profile=add_discovered(load_profile(str(model)))
            self.assertEqual(len(profile['motions']),1)
            name=next(iter(profile['motions']));self.assertIn('happy',name)
            (base/'fake.moc3').write_bytes(b'fake native resource for preparation only')
            from kira_live2d_desktop.native_shell.model import prepare_model
            prepared=prepare_model(model,base/'runtime')
            self.assertIn(str(motion),prepared['motion_files'])
            custom=json.dumps({'motions':{'我的动作':{'type':1,'mtn':str(motion)}}})
            self.assertEqual(list(add_discovered(load_profile(str(model),custom),custom)['motions']),['我的动作'])

class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        profile=load_profile(str(MODEL))
        self.client=SimpleNamespace(chat=AsyncMock())
        self.plugin=p=SimpleNamespace(native_mode=True,plugin_cfg={'action_agent_enabled':True},accepting=True,
            viewer=SimpleNamespace(connected=True),sid='native:dm:one',token='instance',
            tracking_status=lambda:{'key':'model-a'},outfit_busy=False,adapting_model=False,
            preview_busy=lambda:False,expression_preview=None,layout=SimpleNamespace(busy=False),bridge_installing=False,
            current_outfit=None,model_profile=lambda:profile,expression_map=lambda:profile['expressions'],
            motion_map=lambda:profile['motions'],default_expression_enabled=lambda:True,
            expression=AsyncMock(),motion=AsyncMock())
        p.ctx=SimpleNamespace(get_plugin_inst=lambda name:p,get_default_llm_client=lambda:self.client)
        self.agent=ActionAgent(p)
    async def wait_state(self,state):
        async with asyncio.timeout(2):
            while self.agent.state!=state:await asyncio.sleep(.005)

    def job(self):
        return {'kind':'user','text':'请点点头','generation':self.agent.generation,
            'target':(self.plugin.sid,'model-a',self.plugin.token)}
    async def asyncTearDown(self):await self.agent.close()
    async def test_resource_filter_reads_each_live_allowlist_once_for_large_models(self):
        catalog={'expressions':{f'exp{i}':{} for i in range(200)},
                 'motions':{f'move{i}':{} for i in range(200)}}
        self.plugin.expression_map=Mock(return_value={'exp1':1})
        self.plugin.motion_map=Mock(return_value={'move2':{'type':0,'mtn':'Wave'}})
        with patch('kira_live2d_desktop.action_agent.catalog',return_value=catalog):
            resources=self.agent.resources()
        self.plugin.expression_map.assert_called_once()
        self.plugin.motion_map.assert_called_once()
        self.assertEqual(set(resources['expressions']),{'exp1','默认'})
        self.assertEqual(set(resources['motions']),{'move2'})
        self.plugin.motion_map.return_value={}
        with patch('kira_live2d_desktop.action_agent.catalog',return_value=catalog):
            self.assertFalse(self.agent.resources()['motions'])

    async def test_real_request_loop_uses_tool_feedback_without_chatting(self):
        self.client.chat.side_effect=[SimpleNamespace(text_response=json.dumps({'tool':'motion','name':'点头'},ensure_ascii=False),tool_calls=[]),
            SimpleNamespace(text_response='{"tool":"finish","next_check_seconds":null}',tool_calls=[])]
        await self.agent.run(self.job())
        self.plugin.motion.assert_awaited_once_with('点头');self.plugin.expression.assert_not_called()
        self.assertEqual(self.client.chat.await_count,2)
        request=self.client.chat.call_args.args[0]
        self.assertIn('工具结果',request.messages[-1].content)
        self.assertIsNone(request.tools)
    async def test_appearance_disabled_unknown_and_duplicate_controls_never_execute(self):
        self.agent.ask=AsyncMock(side_effect=[{'tool':'expression','name':'摘帽子'},
            {'tool':'motion','name':'不存在'},{'tool':'motion','name':'点头'}, {'tool':'motion','name':'点头'},{'tool':'finish'}])
        await self.agent.run(self.job())
        self.plugin.expression.assert_not_called();self.plugin.motion.assert_awaited_once_with('点头')
    async def test_stale_model_decisions_and_disabled_policy_are_rechecked(self):
        async def stale(messages):
            self.plugin.token='new-instance'
            return {'tool':'motion','name':'点头'}
        self.agent.ask=stale
        with self.assertRaisesRegex(ValueError,'替换旧决策'):await self.agent.run(self.job())
        self.plugin.motion.assert_not_called()
        self.plugin.token='instance'
        async def disable(messages):
            self.plugin.motion_map=lambda:{}
            return {'tool':'motion','name':'点头'}
        self.agent.ask=AsyncMock(side_effect=[disable])
        # A resource disabled while the request is running must not reach the model.
        self.agent.ask=disable
        await self.agent.run(self.job());self.plugin.motion.assert_not_called()
    async def test_event_supersedes_inflight_request_and_close_cancels_loop(self):
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def decide(messages):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        self.agent.ask=decide
        await self.agent.start();self.agent.offer('user','旧消息')
        await asyncio.wait_for(entered.wait(),2)
        self.agent.offer('assistant','新回复')
        await asyncio.wait_for(cancelled.wait(),2)
        await self.agent.close()
        self.plugin.expression.assert_not_called();self.plugin.motion.assert_not_called()
        self.assertIsNone(self.agent.task)
    async def test_timer_wait_is_cancelled_by_manual_preview_reset(self):
        self.agent.next_due=__import__('time').time()+.1
        self.agent.latest=None
        self.agent.run=AsyncMock()
        await self.agent.start();await asyncio.sleep(.02)
        self.agent.reset('手动预览')
        await asyncio.sleep(.2)
        self.agent.run.assert_not_called();self.assertIsNone(self.agent.next_due)

    async def test_test_mode_pauses_agent_and_explains_status(self):
        self.plugin.plugin_cfg['touch_test_mode']=True
        self.agent.offer('user','测试动作')
        self.assertIsNone(self.agent.latest)
        self.assertEqual(self.agent.status()['state'],'paused')
        self.assertIn('测试模式',self.agent.status()['message'])

    async def test_multiple_motions_wait_in_order_and_keep_context(self):
        names=['动作一','动作二','动作三','动作四']
        resources={'expressions':{},'motions':{name:{'duration':1,'uncertain':False} for name in names}}
        self.agent.resources=lambda:resources
        self.agent.history.extend([{'kind':'user','text':'先挥手再点头'},{'kind':'assistant','text':'好的'}])
        self.agent.recent.append({'tool':'motion','name':'旧动作'})
        seen=[]
        async def wait(job,deadline):seen.append(self.plugin.motion.await_count);self.agent.guard(job)
        self.agent.wait_for_motion=wait
        self.agent.ask=AsyncMock(side_effect=[*[{'tool':'motion','name':name} for name in names],{'tool':'motion','name':'动作一'},{'tool':'finish'}])
        await self.agent.run(self.job())
        self.assertEqual([call.args[0] for call in self.plugin.motion.await_args_list],names)
        self.assertEqual(seen,[0,1,2,3])
        payload=json.loads(self.agent.ask.call_args_list[0].args[0][1].content)
        self.assertEqual(payload['conversation'][-1]['text'],'好的')
        self.assertEqual(payload['recent_actions'][0]['name'],'旧动作')
    async def test_policy_changes_during_sequence_wait_prevent_followup(self):
        resources={'expressions':{},'motions':{'one':{'duration':1},'two':{'duration':1}}}
        self.agent.resources=lambda:resources
        async def wait(job,deadline):
            if self.plugin.motion.await_count:resources['motions'].pop('two',None)
        self.agent.wait_for_motion=wait
        self.agent.ask=AsyncMock(side_effect=[{'tool':'motion','name':'one'},{'tool':'motion','name':'two'},{'tool':'finish'}])
        await self.agent.run(self.job())
        self.plugin.motion.assert_awaited_once_with('one')
    async def test_reset_interrupts_sequence_before_second_motion(self):
        self.agent.resources=lambda:{'expressions':{},'motions':{'one':{'duration':10},'two':{'duration':1}}}
        self.agent.ask=AsyncMock(side_effect=[{'tool':'motion','name':'one'},{'tool':'motion','name':'two'}])
        waiting=asyncio.Event()
        original=self.agent.wait_for_motion
        async def wait(job,deadline):
            if self.plugin.motion.await_count:waiting.set()
            await original(job,deadline)
        self.agent.wait_for_motion=wait
        self.agent.round=asyncio.create_task(self.agent.run(self.job()))
        await asyncio.wait_for(waiting.wait(),3)
        self.agent.reset('手动预览')
        await asyncio.gather(self.agent.round,return_exceptions=True)
        self.plugin.motion.assert_awaited_once_with('one')

    async def test_real_sequence_respects_requested_display_interval(self):
        import time
        stamps=[]
        async def motion(name):stamps.append((name,time.monotonic()))
        self.plugin.motion=AsyncMock(side_effect=motion)
        self.agent.resources=lambda:{'expressions':{},'motions':{'one':{'duration':1},'two':{'duration':1}}}
        self.agent.ask=AsyncMock(side_effect=[{'tool':'motion','name':'one','hold_seconds':.3},{'tool':'motion','name':'two'},{'tool':'finish'}])
        await self.agent.run(self.job())
        self.assertEqual([name for name,stamp in stamps],['one','two'])
        self.assertGreaterEqual(stamps[1][1]-stamps[0][1],.29)

    async def test_custom_round_limits_are_enforced_and_sent_to_model(self):
        self.plugin.plugin_cfg.update(action_agent_max_steps=3,action_agent_max_motions=1,action_agent_max_expressions=0)
        self.agent.resources=lambda:{'expressions':{'face':{}},'motions':{'one':{},'two':{}}}
        self.agent.ask=AsyncMock(side_effect=[{'tool':'expression','name':'face'},{'tool':'motion','name':'one'},{'tool':'motion','name':'two'},{'tool':'finish'}])
        await self.agent.run(self.job())
        self.assertEqual(self.agent.ask.await_count,3)
        self.plugin.expression.assert_not_called();self.plugin.motion.assert_awaited_once_with('one')
        payload=json.loads(self.agent.ask.call_args_list[0].args[0][1].content)
        self.assertEqual(payload['round_limits'],{'steps':3,'motions':1,'expressions':0})
    async def test_kira_context_limit_is_dynamic_and_keeps_native_chunks(self):
        manager=SimpleNamespace(max_memory_length=2,get_session=AsyncMock(return_value=SimpleNamespace(content=[
            [{'role':'user','content':'removed'}],
            [{'role':'user','content':'previous'},{'role':'assistant','content':'answer'}],
            [{'role':'user','content':[{'type':'text','text':'current'},{'type':'image_url','image_url':{'url':'private image'}}]}]])))
        self.plugin.ctx.session_mgr=manager
        result=await self.agent.conversation_context()
        manager.get_session.assert_awaited_once_with(self.plugin.sid)
        self.assertEqual([item['text'] for item in result],['previous','answer','current'])
        self.assertEqual(self.agent.history.maxlen,4)
        manager.max_memory_length=1
        self.assertEqual(await self.agent.conversation_context(),[{'kind':'user','text':'current'}])
        self.assertEqual(self.agent.history.maxlen,2)
        manager.get_session.return_value=SimpleNamespace(content=[])
        self.agent.history.append({'kind':'user','text':'stale local event'})
        self.agent.resources=lambda:{'expressions':{'默认':{}},'motions':{}}
        self.agent.ask=AsyncMock(return_value={'tool':'finish'})
        await self.agent.run(self.job())
        payload=json.loads(self.agent.ask.call_args.args[0][1].content)
        self.assertEqual(payload['conversation'],[])
        self.assertNotIn('stale local event',json.dumps(payload))

    async def test_input_starts_decision_without_main_reply(self):
        called=asyncio.Event()
        async def decide(messages):
            called.set();return {'tool':'finish'}
        self.agent.ask=decide
        self.plugin.ctx.persona_mgr=SimpleNamespace(get_persona=AsyncMock(return_value=SimpleNamespace(content='温柔、喜欢点头')))
        self.agent.ask=AsyncMock(side_effect=decide)
        await self.agent.start();self.agent.observe('user','你好')
        await asyncio.wait_for(called.wait(),.3)
        payload=json.loads(self.agent.ask.call_args.args[0][1].content)
        self.assertEqual(payload['event'],{'kind':'user','text':'你好'})
        self.assertEqual(payload['persona'],'温柔、喜欢点头')
        self.plugin.ctx.persona_mgr.get_persona.return_value.content='活泼'
        called.clear()
        self.agent.observe('interaction','摸头')
        await asyncio.wait_for(called.wait(),1)
        payload=json.loads(self.agent.ask.call_args.args[0][1].content)
        self.assertEqual(payload['persona'],'活泼')

    async def test_new_input_cancels_old_round_without_waiting_for_main(self):
        entered=asyncio.Event();canceled=asyncio.Event();second=asyncio.Event()
        async def decide(messages):
            payload=json.loads(messages[1].content)
            if payload['event']['text']=='旧输入':
                entered.set()
                try:await asyncio.Event().wait()
                finally:canceled.set()
            second.set();return {'tool':'finish'}
        self.agent.ask=decide
        await self.agent.start();self.agent.observe('user','旧输入')
        await asyncio.wait_for(entered.wait(),.3)
        self.agent.observe('user','新输入')
        await asyncio.wait_for(second.wait(),.3)
        self.assertTrue(canceled.is_set())
        self.assertEqual(self.agent.generation,2)
        self.plugin.motion.assert_not_awaited()

    async def test_fsm_pause_resume_disconnect_error_and_close(self):
        entered=asyncio.Event()
        async def ask(messages):
            entered.set();await asyncio.Event().wait()
        self.agent.ask=ask
        await self.agent.start();self.agent.observe('user','回复')
        await asyncio.wait_for(entered.wait(),1)
        self.plugin.plugin_cfg['touch_test_mode']=True
        self.assertEqual(self.agent.status()['state'],'paused')
        await asyncio.sleep(.02)
        self.assertEqual(self.agent.state,'paused')
        self.plugin.plugin_cfg['touch_test_mode']=False
        self.assertEqual(self.agent.status()['state'],'idle')
        self.assertIsNone(self.agent.latest)
        self.plugin.viewer.connected=False
        self.assertEqual(self.agent.status()['state'],'disconnected')
        self.plugin.viewer.connected=True
        self.assertEqual(self.agent.status()['state'],'idle')
        self.agent.ask=AsyncMock(return_value={'tool':'finish','next_check_seconds':10})
        self.agent.observe('user','恢复回复');await self.wait_state('scheduled')
        self.assertEqual(self.agent.state,'scheduled')
        await self.agent.close();self.assertEqual(self.agent.status()['state'],'stopped')
        self.plugin.motion.assert_not_awaited()

    async def test_fsm_tracks_holding_and_manual_control_wait(self):
        release=asyncio.Event()
        async def decide(messages):
            if len(messages)==2:return {'tool':'motion','name':'点头','hold_seconds':.3}
            if len(messages)==4:return {'tool':'motion','name':'two','hold_seconds':.3}
            return {'tool':'finish'}
        self.agent.resources=lambda:{'motions':{'点头':{'duration':.1},'two':{'duration':.1}},'expressions':{}}
        self.agent.ask=decide
        await self.agent.start();self.agent.observe('user','点头然后继续')
        await self.wait_state('holding')
        self.assertEqual(self.agent.state,'holding')
        await asyncio.sleep(.4)
        self.assertEqual(self.agent.state,'idle')
        transitions=self.agent.status()['transitions']
        self.assertIn('holding',[t['to'] for t in transitions])
        self.assertEqual(self.plugin.motion.await_count,2)
        self.plugin.outfit_busy=True
        self.agent.observe('user','等换装')
        await self.wait_state('blocked')
        self.assertEqual(self.agent.state,'blocked')
        self.plugin.outfit_busy=False
        await asyncio.sleep(.65)
        self.assertEqual(self.agent.state,'idle')

    async def test_multiple_json_decisions_do_not_abort_or_bypass_feedback(self):
        self.client.chat.side_effect=[
            SimpleNamespace(text_response='{"tool":"motion","name":"点头"}\n{"tool":"expression","name":"默认"}\n{"tool":"finish"}',tool_calls=[]),
            SimpleNamespace(text_response='{"tool":"finish"}',tool_calls=[])]
        await self.agent.run(self.job())
        self.plugin.motion.assert_awaited_once_with('点头')
        self.plugin.expression.assert_not_awaited()
        self.assertEqual(self.client.chat.await_count,2)
        self.assertIn('工具结果',self.client.chat.call_args.args[0].messages[-1].content)

    async def test_decision_parser_rejects_trailing_prose_lists_and_broken_fences(self):
        from kira_live2d_desktop.action_agent import parse_action_command
        self.assertEqual(parse_action_command('```json\n{"tool":"finish"}\n{"tool":"motion","name":"x"}\n```'),{'tool':'finish'})
        for raw in ('{"tool":"finish"} prose','[{"tool":"finish"}]','```json\n{"tool":"finish"}',''):
            with self.assertRaises(ValueError):parse_action_command(raw)
