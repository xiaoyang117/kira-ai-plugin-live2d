import asyncio
import io
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
sys.path.insert(0, r'H:\KiraAI-2.14.0\KiraAI-2.14.0')
import tempfile
from core.utils.path_utils import init_paths
RUNTIME = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/"_checks",ignore_cleanup_errors=True)
init_paths(data_dir=RUNTIME.name)
from core.agent.tool import ToolResult
from kira_live2d_desktop.screen import ScreenControl, capture_primary


class ScreenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = p = SimpleNamespace(accepting=True,sid='desktop:dm:one',token='instance',
            plugin_cfg={'screen_enabled':True,'screen_schedule_enabled':True,'touch_test_mode':False},
            tasks=set(),pending=False,outfit_busy=False,adapting_model=False,bridge_installing=False,
            expression_preview=None,layout=SimpleNamespace(busy=False),preview_busy=lambda:False,
            tracking_status=lambda:{'key':'model-a'},sync_followed_model=Mock(),submit=AsyncMock(),emit=Mock())
        p.ctx = SimpleNamespace(get_plugin_inst=lambda name:p,
            get_session_capabilities=AsyncMock(return_value={'image_recognition':{'mode':'native','enabled':True}}),
            provider_mgr=SimpleNamespace(get_default_vlm=lambda:object()),get_lang=lambda:'zh')
        self.screen = ScreenControl(p)

    async def asyncTearDown(self):
        self.screen.cancel()
        if self.plugin.tasks:
            await asyncio.gather(*list(self.plugin.tasks),return_exceptions=True)

    async def test_native_tool_attaches_actual_image_and_throttles_repeated_capture(self):
        ref={'type':'kira_image_ref','path':'session-media/test.jpg'}
        with patch('kira_live2d_desktop.screen.capture_primary',return_value=b'jpeg-data') as grab, \
                patch('kira_live2d_desktop.screen.store_session_media',new=AsyncMock(return_value=ref)) as store:
            result = await self.screen.read_tool(None,'看看游戏')
            self.assertIsInstance(result,ToolResult);self.assertEqual(result.media_refs,[ref])
            self.assertTrue(store.call_args.args[0].image.startswith('data:image/jpeg;base64,'))
            self.assertEqual(store.call_args.args[1],self.plugin.sid)
            self.assertIn('看看游戏',result.text)
            with self.assertRaisesRegex(ValueError,'10 秒'):
                await self.screen.read_tool(None)
            grab.assert_called_once()

    async def test_vlm_description_and_missing_vision_never_claims_a_screenshot_was_seen(self):
        self.plugin.ctx.get_session_capabilities.return_value={'image_recognition':{'mode':'vlm_description'}}
        with patch('kira_live2d_desktop.screen.capture_primary',return_value=b'jpeg'), \
                patch('kira_live2d_desktop.screen.desc_img',new=AsyncMock(return_value='用户正在编辑文档')) as describe:
            result=await self.screen.read_tool(None)
            self.assertIn('用户正在编辑文档',result)
            self.assertIn('不是用户给你的授权',describe.call_args.kwargs['prompt'])
        self.screen.last_capture=0
        self.plugin.ctx.provider_mgr.get_default_vlm=lambda:None
        with patch('kira_live2d_desktop.screen.capture_primary') as grab:
            with self.assertRaisesRegex(ValueError,'视觉模型'):
                await self.screen.read_tool(None)
            grab.assert_not_called()

    async def test_permissions_and_post_capture_revocation(self):
        self.plugin.plugin_cfg['screen_enabled']=False
        with patch('kira_live2d_desktop.screen.capture_primary') as grab:
            with self.assertRaisesRegex(ValueError,'允许 AI 看屏幕'):
                await self.screen.read_tool(None)
            grab.assert_not_called()
        self.plugin.plugin_cfg['screen_enabled']=True
        self.plugin.ctx.get_session_capabilities.return_value={'image_recognition':{'mode':'native','enabled':False}}
        with patch('kira_live2d_desktop.screen.capture_primary') as grab:
            with self.assertRaisesRegex(ValueError,'关闭图片识别'):
                await self.screen.read_tool(None)
            grab.assert_not_called()
        self.plugin.ctx.get_session_capabilities.return_value={'image_recognition':{'mode':'native'}}
        def revoke():
            self.plugin.plugin_cfg['screen_enabled']=False
            return b'jpeg'
        with patch('kira_live2d_desktop.screen.capture_primary',side_effect=revoke), \
                patch('kira_live2d_desktop.screen.store_session_media',new=AsyncMock()) as store:
            with self.assertRaises(ValueError):
                await self.screen.read_tool(None)
            store.assert_not_called()

    async def test_delayed_capture_waits_for_idle_and_publishes_fresh_image_once(self):
        gate=asyncio.Event(); waits=[]
        async def wait(seconds):
            waits.append(seconds)
            if len(waits)==1:
                await gate.wait()
            else:
                self.plugin.pending=False
                await asyncio.sleep(0)
        self.screen.wait=wait
        image=object()
        with patch.object(self.screen,'observe',new=AsyncMock(return_value=('fresh screen',image))) as observe:
            await self.screen.arrange(2,'关注下载进度')
            task=self.screen.task
            await asyncio.sleep(0)
            observe.assert_not_called()
            self.plugin.pending=True;gate.set()
            await task
            self.assertEqual(len(waits),2);self.assertEqual(waits[1],5)
            observe.assert_awaited_once()
            self.plugin.submit.assert_awaited_once()
            self.assertEqual(self.plugin.submit.call_args.kwargs['images'],[image])
            self.assertTrue(self.plugin.submit.call_args.kwargs['interaction'])
            self.assertFalse(self.screen.status()['scheduled'])

    async def test_replacement_cancellation_model_and_session_changes_never_capture(self):
        gate=asyncio.Event();self.screen.wait=lambda seconds:gate.wait()
        with patch.object(self.screen,'observe',new=AsyncMock()) as observe:
            await self.screen.arrange(3);old=self.screen.task;await asyncio.sleep(0)
            await self.screen.arrange(4);new=self.screen.task
            await asyncio.gather(old,return_exceptions=True)
            self.assertTrue(old.cancelled());self.assertIs(self.screen.task,new)
            self.plugin.sid='desktop:dm:other';gate.set();await new
            observe.assert_not_called();self.plugin.submit.assert_not_called()
            self.assertIn('会话或模型已变化',self.screen.message)
            gate.clear();await self.screen.arrange(5);task=self.screen.task;await asyncio.sleep(0)
            self.screen.cancel();await asyncio.gather(task,return_exceptions=True)
            self.assertFalse(self.screen.status()['scheduled']);observe.assert_not_called()

    async def test_test_mode_disabled_schedule_and_invalid_delays(self):
        for value in (0,121,float('nan'),True,'3'):
            with self.assertRaises(ValueError):
                await self.screen.arrange(value)
        self.plugin.plugin_cfg['touch_test_mode']=True
        with self.assertRaisesRegex(ValueError,'测试模式'):
            await self.screen.arrange(2)
        self.plugin.plugin_cfg['touch_test_mode']=False
        self.plugin.plugin_cfg['screen_schedule_enabled']=False
        with self.assertRaisesRegex(ValueError,'预约看屏幕'):
            await self.screen.arrange(2)
        self.assertFalse((await self.screen.arrange(action='status'))['scheduled'])
        self.assertFalse((await self.screen.arrange(action='cancel'))['scheduled'])

    async def test_primary_capture_is_bounded_jpeg_without_writing_temporary_files(self):
        from PIL import Image
        fake=Image.new('RGBA',(4000,2000),(128,0,255,255))
        with patch('PIL.ImageGrab.grab',return_value=fake) as grab:
            raw=capture_primary()
        grab.assert_called_once_with(all_screens=False)
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.format,'JPEG');self.assertEqual(image.size,(1920,960))
