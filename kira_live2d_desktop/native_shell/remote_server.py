"""Remote renderer transport: no GUI/runtime installation on the KiraAI host."""
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import time
import uuid
from aiohttp import web
from .client import NativeClient
from .remote_model import make_model_bundle
from ..ai_copy import prepare_render_model

class RemoteNativeClient(NativeClient):
    def __init__(self,plugin):
        super().__init__(plugin)
        self.peer=None;self.peer_seen=0.;self.bundle=None;self.bundle_hash='';self.media={}
    @property
    def connected(self):return self.ready and self.peer is not None and time.monotonic()-self.heartbeat<12
    async def launch(self):
        generation=self.generation
        try:
            path=self.plugin.plugin_cfg.get('model_path')
            if not path or not Path(path).is_file():
                self.last_error='请先导入并选择模型，选择后会等待远程壳连接'
                return
            self.last_error='正在准备远程模型资源'
            self.copy_state={'stage':'preparing','message':'正在准备远程模型资源','enabled':bool(self.plugin.plugin_cfg.get('ai_control_copy_enabled',True))}
            model,state,_=await asyncio.to_thread(prepare_render_model,self.plugin.plugin_cfg.get('model_path'),self.plugin.data_dir,
                self.plugin.plugin_cfg.get('ai_control_copy_enabled',True))
            bundle,digest=await asyncio.to_thread(make_model_bundle,model,self.plugin.data_dir/'remote-bundles')
            if self.stopping or generation!=self.generation:return
            self.bundle=bundle;self.bundle_hash=digest;self.copy_state=state
            self.last_error='等待远程壳连接'
        except asyncio.CancelledError:raise
        except Exception as exc:
            if not self.stopping and generation==self.generation:
                self.last_error=str(exc);self.plugin.emit('warning',text=self.last_error)
    async def start(self):
        self.peer=None;self.bundle=None
        await super().start()
    async def connect(self,request):
        if not self.bundle or self.stopping:raise web.HTTPServiceUnavailable(text='模型资源尚未准备好，请稍后连接')
        data=await request.json();peer=data.get('client_id','')
        if not isinstance(peer,str) or len(peer)!=32 or any(c not in '0123456789abcdef' for c in peer):raise ValueError('远程壳标识无效')
        if self.peer and self.peer!=peer and time.monotonic()-max(self.peer_seen,self.heartbeat)<(12 if self.ready else 120):
            raise web.HTTPConflict(text='已有远程壳连接，请先断开原壳')
        if self.peer!=peer:
            self.ready=False;self.peer=peer
            while not self.queue.empty():self.queue.get_nowait()
            self.plugin.action_agent.reset('远程壳已连接，等待模型就绪')
        self.peer_seen=time.monotonic()
        return web.json_response({'generation':self.generation,'key':self.plugin.tracking_status()['key'],
            'server_time':time.time(),'bundle_hash':self.bundle_hash,'bundle_url':'/native/model/'+self.bundle_hash,'protocol':1})
    async def disconnect(self,request):
        data=await request.json()
        if data.get('client_id')==self.peer:
            self.peer=None;self.ready=False;self.plugin.action_agent.reset('远程壳已断开')
        return web.json_response({'ok':True})
    async def model_download(self,request):
        if self.bundle is None or request.match_info['digest']!=self.bundle_hash:raise web.HTTPNotFound()
        return web.FileResponse(self.bundle)
    async def media_download(self,request):
        path=self.media.get(request.match_info['name'])
        if path is None or not path.is_file():raise web.HTTPNotFound()
        return web.FileResponse(path)
    async def poll(self,request):
        if not self.peer or request.query.get('client_id')!=self.peer:
            return web.json_response({'command':None,'obsolete':True})
        return await super().poll(request)
    async def feedback(self,request):
        data=await request.json()
        if not self.peer or data.get('client_id')!=self.peer:return web.json_response({'ignored':True},status=202)
        return await super().feedback(request)
    async def send(self,command,data=None):
        if command==13500:
            data=dict(data);path=Path(data['sound']).resolve()
            if not path.is_file() or path.suffix.lower() not in ('.mp3','.ogg','.wav'):raise ValueError('语音资源无效')
            name=uuid.uuid4().hex+path.suffix.lower();self.media[name]=path
            if len(self.media)>32:self.media.pop(next(iter(self.media)))
            data['sound']='remote-audio:'+name
        return await super().send(command,data)
