"""WebSocket control channel with independent command dispatch and RPC replies."""
import json
from pathlib import Path
import queue
import threading
import time
import uuid
import websocket

RPC_PATHS=('/status','/events','/input','/message','/outfit','/native/connect')

class SocketWire:
    def init_socket(self):
        self.socket=None;self.rpc_pending={};self.rpc_lock=threading.Lock();self.incoming=queue.Queue()
    def socket_rpc(self,path,data=None):
        ident=uuid.uuid4().hex;event=threading.Event();result={}
        with self.rpc_lock:self.rpc_pending[ident]=(event,result)
        try:
            socket=self.socket
            if socket is None:raise ConnectionError('WebSocket 尚未连接')
            socket.send(json.dumps({'type':'rpc','id':ident,'path':path,'body':data}))
            if not event.wait(30 if path=='/outfit' else 10):raise TimeoutError('WebSocket 请求超时，未自动重发')
            if result.get('error') or result.get('status',200)>=400:raise ConnectionError(result.get('error') or '请求失败')
            return result.get('result',{})
        finally:
            with self.rpc_lock:self.rpc_pending.pop(ident,None)
    def socket_feedback(self):
        while not self.stopped.is_set():
            try:
                try:data=self.outgoing.get(timeout=.1)
                except queue.Empty:data=None
                if data is None and self.render_ready and time.monotonic()-self.last_ready_report>=5:data={'ready':True}
                if data is None:continue
                socket=self.socket
                if socket is None:continue
                socket.send(json.dumps({'type':'feedback','data':data}))
                if data.get('ready'):self.last_ready_report=time.monotonic()
            except Exception:self.stopped.wait(.2)
    def dispatch_socket_commands(self):
        try:
            while not self.stopped.is_set():
                try:command=self.incoming.get(timeout=.2)
                except queue.Empty:continue
                try:
                    if command.get('msg')==13500 and self.config.get('remote_managed'):
                        name=command['data'].get('sound','').removeprefix('remote-audio:')
                        if len(Path(name).stem)!=32 or any(c not in '0123456789abcdef' for c in Path(name).stem) or Path(name).suffix not in ('.mp3','.wav','.ogg') or '/' in name or '\\' in name:raise ValueError('远程语音标识无效')
                        audio=Path(self.config['audio_cache'])/name;audio.parent.mkdir(parents=True,exist_ok=True)
                        audio.write_bytes(self.request('/native/media/'+name,binary=True));command['data']['sound']=str(audio)
                    self.command.emit(command)
                except Exception as error:self.post({'msgId':command.get('msgId'),'error':str(error)})
        finally:self.close_transport()
    def run_socket(self):
        sender=threading.Thread(target=self.socket_feedback,daemon=True);dispatcher=threading.Thread(target=self.dispatch_socket_commands,daemon=True)
        sender.start();dispatcher.start();last_connected=time.monotonic()
        url=self.config['url'].replace('https://','wss://',1).replace('http://','ws://',1).rstrip('/')+'/native/ws?generation='+self.config['generation']
        if self.config.get('client_id'):url+='&client_id='+self.config['client_id']
        try:
            while not self.stopped.is_set():
                socket=None
                try:
                    socket=websocket.create_connection(url,header={'Authorization':'Bearer '+self.config['token']},timeout=3,enable_multithread=True,suppress_origin=True,http_no_proxy=['*'])
                    self.socket=socket;self.last_ready_report=0;last_connected=time.monotonic();socket.settimeout(1)
                    print('WebSocket 已连接',flush=True)
                    while not self.stopped.is_set():
                        try:message=socket.recv()
                        except websocket.WebSocketTimeoutException:continue
                        if not message:raise ConnectionError('WebSocket 已断开')
                        if len(message)>8*1024*1024:raise ValueError('响应过大')
                        packet=json.loads(message)
                        if packet.get('type')=='obsolete':self.stopped.set();self.command.emit({'msg':'quit'});return
                        if packet.get('type')=='command':self.incoming.put(packet['command'])
                        elif packet.get('type')=='response':
                            with self.rpc_lock:
                                pending=self.rpc_pending.get(packet.get('id'))
                                if pending:pending[1].update(packet);pending[0].set()
                except websocket.WebSocketBadStatusException as error:
                    if error.status_code in (401,403,404,409):self.command.emit({'msg':'quit'});return
                except Exception as error:
                    if not self.stopped.is_set():print('WebSocket 连接中断，正在重连：',type(error).__name__,flush=True)
                finally:
                    self.socket=None
                    if socket:socket.close()
                    with self.rpc_lock:
                        for event,result in self.rpc_pending.values():result.update(error='连接已断开，未自动重发');event.set()
                if time.monotonic()-last_connected>120:self.command.emit({'msg':'quit'});return
                self.stopped.wait(1)
        finally:self.stopped.set();sender.join(timeout=1);dispatcher.join(timeout=1)
