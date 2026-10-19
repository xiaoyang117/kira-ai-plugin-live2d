import asyncio
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid
from aiohttp import web
from ..model_follow import ModelFollower,MODEL_FIELDS
from .runtime import ensure_runtime
from ..ai_copy import prepare_render_model
from ..model_profile import load_profile

class NativeFollower(ModelFollower):
    def refresh(self,config):
        if self.storage_error:return False
        path=str(config.get('native_model_path') or config.get('model_path') or '')
        if not path or not Path(path).is_file():
            self.valid=False;self.message='请在独立壳设置中选择本地 .model3.json 模型';return False
        identity=str(Path(path).resolve()).casefold()
        key='native-'+hashlib.sha256(identity.encode()).hexdigest()
        if self.key==key:
            self.valid=True;return False
        if load_profile(path)['format']!='Cubism 3':
            self.valid=False;self.message='独立壳需要普通 .model3.json 模型';return False
        previous=self.selection
        if previous:self.save(config)
        self.selection={'key':key,'identity':identity,'path':path,'name':Path(path).stem}
        saved=self.models.get(key,{}).get('settings')
        if not saved and (previous or self.models):saved=self.defaults
        if saved:
            for field in MODEL_FIELDS:config[field]=copy.deepcopy(saved.get(field,self.defaults[field]))
        config['model_path']=path
        self.valid=True;self.seen=True;self.message='独立壳直接加载当前 JSON 模型'
        self.save(config)
        return True

class NativeClient:
    def __init__(self,plugin):
        self.plugin=plugin;self.url='ws://127.0.0.1/native'
        self.last_error='正在准备独立壳';self.ready=False;self.heartbeat=0
        self.generation=''
        self.queue=asyncio.Queue(maxsize=64);self.pending={};self.counter=0
        self.task=None;self.process=None;self.stopping=False;self.debug_active=False
        self.socket=None
        self.copy_state={'stage':'idle','message':'等待模型启动','enabled':bool(getattr(plugin,'plugin_cfg',{}).get('ai_control_copy_enabled',True))}
    @property
    def connected(self):
        return self.ready and time.monotonic()-self.heartbeat<12 and self.process is not None and self.process.poll() is None
    async def start(self):
        self.stopping=False;self.ready=False;self.heartbeat=0;self.generation=uuid.uuid4().hex
        while not self.queue.empty():self.queue.get_nowait()
        self.task=asyncio.create_task(self.launch(),name='native-shell-launch')
    async def launch(self):
        generation=self.generation
        def copy_progress(state):
            if not self.stopping and self.generation==generation:self.copy_state=state
        try:
            path=self.plugin.plugin_cfg.get('model_path')
            if not path or not Path(path).is_file():
                self.last_error='请先导入并选择模型，选择后会按当前连接模式启动'
                return
            self.last_error='首次使用正在准备原生渲染组件，完成后自动启动'
            python=await asyncio.to_thread(ensure_runtime,self.plugin.data_dir)
            if self.stopping:return
            self.last_error='正在加载独立壳模型'
            model,copy_state,preferences=await asyncio.to_thread(prepare_render_model,
                self.plugin.plugin_cfg.get('model_path'),self.plugin.data_dir,
                self.plugin.plugin_cfg.get('ai_control_copy_enabled',True),
                copy_progress)
            if self.stopping or self.generation!=generation:return
            self.copy_state=copy_state
            config={'url':f"http://127.0.0.1:{self.plugin.plugin_cfg.get('bridge_port',18765)}",
                'token':self.plugin.token,'model':model,'id':self.plugin.model_index,'preferences':preferences,
                'key':self.plugin.tracking_status()['key'],'generation':self.generation}
            cfg=self.plugin.data_dir/'native-shell.json';cfg.write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
            log_path=self.plugin.data_dir/'native-shell.log'
            if log_path.is_file() and log_path.stat().st_size>4*1024*1024:log_path.replace(log_path.with_suffix('.previous.log'))
            log=log_path.open('ab')
            try:
                self.process=subprocess.Popen([str(python),'-X','utf8','-X','faulthandler','-u',str(Path(__file__).with_name('window.py')),'--config',str(cfg)],
                    stdout=log,stderr=log,cwd=str(Path(__file__).parent),creationflags=subprocess.CREATE_NO_WINDOW)
            finally:log.close()
            self.last_error='等待原生模型渲染完成'
            started=time.monotonic()
            while not self.stopping:
                await asyncio.sleep(1)
                if not self.ready and time.monotonic()-started>45:
                    self.process.terminate()
                    raise RuntimeError('独立壳加载超时，请检查 native-shell.log 或更换模型')
                if self.process.poll() is not None:
                    raise RuntimeError('独立壳已退出（退出码 '+str(self.process.returncode)+'），详情见插件数据目录 native-shell.log')
        except asyncio.CancelledError:raise
        except Exception as exc:
            if self.stopping or self.generation!=generation:return
            self.ready=False;self.last_error=str(exc);self.plugin.emit('warning',text=self.last_error)
    async def close(self):
        self.stopping=True;self.ready=False;self.debug_active=False
        if self.socket is not None and not self.socket.closed:
            try:await self.socket.send_json({'type':'obsolete'})
            except ConnectionError:pass
            await self.socket.close()
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        for future in self.pending.values():
            if not future.done():future.set_exception(ConnectionError('独立壳正在关闭'))
        self.pending.clear()
        if self.process is not None and self.process.poll() is None:
            while not self.queue.empty():self.queue.get_nowait()
            self.queue.put_nowait({'msg':'quit'})
            try:await asyncio.wait_for(asyncio.to_thread(self.process.wait),4)
            except TimeoutError:
                self.process.terminate()
                try:await asyncio.wait_for(asyncio.to_thread(self.process.wait),2)
                except TimeoutError:self.process.kill();await asyncio.to_thread(self.process.wait)
    async def reconnect(self):
        self.ready=False
        await self.close()
        self.stopping=False
        await self.start()
    async def send(self,command,data=None):
        if not self.connected:raise ConnectionError(self.last_error or '独立壳未就绪')
        self.counter+=1;number=self.counter
        future=asyncio.get_running_loop().create_future();self.pending[number]=future
        try:
            self.queue.put_nowait({'msg':command,'msgId':number,'data':data,'expires':time.time()+5})
            result=await asyncio.wait_for(future,6)
            if result.get('error'):raise ValueError(result['error'])
            return number
        finally:self.pending.pop(number,None)
    async def websocket(self,request):
        from .socket_server import serve
        return await serve(self,request)
    async def request(self,operation,**values):
        if not self.connected:raise ConnectionError(self.last_error)
        self.counter+=1;number=self.counter
        future=asyncio.get_running_loop().create_future();self.pending[number]=future
        try:
            self.queue.put_nowait({'msg':'control','msgId':number,'data':{'operation':operation,**values},'expires':time.time()+5})
            result=await asyncio.wait_for(future,6)
            if result.get('error'):raise ValueError(result['error'])
            return result.get('result',{})
        finally:self.pending.pop(number,None)
    async def poll(self,request):
        if self.generation and request.query.get('generation')!=self.generation:
            return web.json_response({'command':None,'obsolete':True})
        self.heartbeat=time.monotonic()
        try:command=await asyncio.wait_for(self.queue.get(),2)
        except TimeoutError:command=None
        if self.generation and request.query.get('generation')!=self.generation:
            if command is not None:self.queue.put_nowait(command)
            return web.json_response({'command':None,'obsolete':True})
        return web.json_response({'command':command})
    async def feedback(self,request):
        data=await request.json()
        if self.stopping or (self.generation and data.get('generation')!=self.generation):
            return web.json_response({'ignored':True},status=202)
        self.heartbeat=time.monotonic()
        if data.get('ready') is True:
            first_ready=not self.ready
            if first_ready and hasattr(self.plugin,'native_model_ready'):self.plugin.native_model_ready(self.generation)
            self.ready=True;self.last_error=''
            if self.copy_state.get('stage')=='prepared':self.copy_state.update(stage='ready',message='正在使用 AI 控制副本；原模型与配置备份已保留')
            if first_ready and hasattr(self.plugin,'action_agent'):self.plugin.action_agent.offer('model_ready','模型已加载，可根据可用资源选择自然表现，不要自动换装')
        if data.get('error') and 'msgId' not in data:
            self.ready=False;self.last_error=str(data['error'])[:500]
        future=self.pending.get(data.get('msgId'))
        if future is not None and not future.done():future.set_result(data)
        if data.get('open_input') is True:
            from ..launcher import open_panel
            self.plugin.set_input_mode('desktop')
            await asyncio.to_thread(open_panel,self.plugin.data_dir/'desktop-client.json')
        if data.get('drag') and isinstance(data['drag'],dict):
            if data.get('key')==self.plugin.tracking_status()['key']:
                await self.plugin.handle_drag(data['drag'])
        if data.get('preview') and isinstance(data['preview'],dict):
            state=data['preview']
            if self.plugin.preview_command and state.get('nonce')==self.plugin.preview_command.get('nonce'):
                self.plugin.preview_state.update(stage=state['stage'],message=state.get('message',''))
        if data.get('debug') is not None:
            self.debug_active=bool(data['debug'])
            if self.debug_active and hasattr(self.plugin,'action_agent'):self.plugin.action_agent.reset('调试模式暂停动作 Agent')
        if data.get('event'):
            await self.plugin.on_viewer_event({'type':0,'id':self.plugin.model_index,'hitArea':str(data['event'])[:100]})
        return web.json_response({'ok':True})


class InactiveNativeClient(NativeClient):
    """Keep configuration available without preparing or starting any renderer."""
    def __init__(self,plugin):
        super().__init__(plugin)
        self.last_error='请选择连接模式后启动桌宠'
        self.copy_state.update(message='选择连接模式并启动模型后，自动准备 AI 控制副本')

    @property
    def connected(self):return False

    async def start(self):
        self.stopping=False
        self.generation=uuid.uuid4().hex

    async def poll(self,request):
        return web.json_response({'command':None,'obsolete':True})

    async def feedback(self,request):
        return web.json_response({'ignored':True},status=202)
