"""Authenticated bidirectional renderer connection; binary assets stay on HTTP."""
import asyncio
import json
from urllib.parse import urlsplit,parse_qs
from aiohttp import web,WSMsgType

class PayloadRequest:
    def __init__(self,data=None,query=None):self.data=data;self.query=query or {}
    async def json(self):return self.data

async def serve(client,request):
    if client.stopping or client.plugin.shell_connection_mode=='disabled':raise web.HTTPConflict(text='桌宠未启动')
    generation=client.generation;peer=request.query.get('client_id','')
    if request.query.get('generation')!=generation:raise web.HTTPConflict(text='模型已更换，请重新连接')
    if hasattr(client,'peer') and (not client.peer or peer!=client.peer):raise web.HTTPConflict(text='远程壳身份已变化')
    socket=web.WebSocketResponse(heartbeat=10,max_msg_size=131072)
    await socket.prepare(request)
    previous=getattr(client,'socket',None);client.socket=socket
    if previous is not None and not previous.closed:await previous.close()
    jobs=set()
    async def rpc(packet):
        ident=packet.get('id')
        if not isinstance(ident,str) or len(ident)>80:return
        try:
            parsed=urlsplit(packet.get('path',''));path=parsed.path
            query={k:v[-1] for k,v in parse_qs(parsed.query).items()}
            routes={'/status':client.plugin.http_status,'/events':client.plugin.http_events,
                    '/input':client.plugin.http_input,'/message':client.plugin.http_message,'/outfit':client.plugin.http_outfit}
            if hasattr(client,'connect'):routes['/native/connect']=client.connect
            if path not in routes or parsed.scheme or parsed.netloc:raise ValueError('此 WebSocket 操作不受支持')
            body=packet.get('body')
            if path=='/native/connect':body={'client_id':peer}
            if client.socket is not socket or generation!=client.generation:raise ConnectionError('连接已变化')
            result=await routes[path](PayloadRequest(body,query))
            await socket.send_json({'type':'response','id':ident,'result':json.loads(result.body),'status':result.status})
        except Exception as error:
            if not socket.closed:await socket.send_json({'type':'response','id':ident,'error':str(error),'status':getattr(error,'status',400)})
    async def sender():
        while not socket.closed:
            command=await client.queue.get()
            if client.socket is not socket or generation!=client.generation:return
            await socket.send_json({'type':'command','command':command})
    output=asyncio.create_task(sender())
    try:
        await socket.send_json({'type':'connected','generation':generation})
        async for message in socket:
            if message.type!=WSMsgType.TEXT:continue
            if client.stopping or client.socket is not socket or generation!=client.generation:break
            try:
                packet=json.loads(message.data)
                if not isinstance(packet,dict):raise ValueError('无效的消息')
                if packet.get('type')=='feedback':
                    data=packet.get('data')
                    if not isinstance(data,dict):raise ValueError('反馈格式无效')
                    await client.feedback(PayloadRequest({**data,'generation':generation,'client_id':peer}))
                elif packet.get('type')=='rpc':
                    if len(jobs)>=16:raise ValueError('请求过多')
                    task=asyncio.create_task(rpc(packet));jobs.add(task);task.add_done_callback(jobs.discard)
                else:raise ValueError('未知消息类型')
            except (ValueError,TypeError,KeyError):await socket.close(code=1008,message=b'Invalid message');break
    finally:
        output.cancel()
        for task in jobs:task.cancel()
        await asyncio.gather(output,*jobs,return_exceptions=True)
        if client.socket is socket:client.socket=None;client.ready=False
        await socket.close()
    return socket
