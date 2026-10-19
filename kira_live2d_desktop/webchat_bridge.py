"""Use KiraAI's built-in chat UI without changing the desktop session identity."""
import json
import aiosqlite
from core.adapter.capabilities import IMCapability
from core.chat.message_elements import Text
from core.chat.message_history import serialize_message_chain
from core.plugin import logger


class WebChatBridge:
    def __init__(self, plugin):
        self.plugin = plugin
        self.store = self.capability = self.original = self.receiver = None
        self.profile = {}
        self.active = {}
        self.closed = False

    async def start(self):
        adapter = self.plugin.ctx.adapter_mgr.get_adapter('webchat')
        if adapter is None or not hasattr(adapter, 'store'):
            logger.warning('[Live2D] 内置网页聊天未启用，桌面输入仍可使用')
            return
        self.store = adapter.store
        self.profile = await self.store.get_setting('profile') or {}
        self.capability = adapter.get_capability(IMCapability)
        self.original = self.capability.publish
        self.receiver = self.publish
        self.capability.publish = self.receiver
        try:
            await self.import_history()
        except Exception:
            logger.exception('[Live2D] 旧桌宠记录导入网页聊天失败，下次启动重试')

    def publish(self, event):
        """Keep native receive/batching; only attach the existing desktop session route."""
        if self.closed or not self.plugin.accepting:
            raise ValueError('unavailable')
        message_id, chain = event.message.message_id, event.message.chain
        self.profile={'nickname':event.message.sender.nickname,'peer_nickname':event.message.bot.nickname}
        text = '\n'.join(e.text for e in chain if isinstance(e, Text))
        routed = self.plugin.message_event(text, request_id=message_id, chain_override=chain)
        routed.supported_elements = event.supported_elements
        self.plugin.set_input_mode('web')
        self.original(routed)
        self.active[routed.message.message_id] = message_id
        self.plugin.pending = True
        self.plugin.emit('user', text=text)
        self.plugin.action_agent.observe('user', text)

    async def incoming(self, message, text):
        if self.store is None:
            return
        identity = message.message_id if self.plugin.use_webchat_session else 'desktop-in:' + message.message_id
        elements = await serialize_message_chain(message.chain, archive_root=self.store.media_dir)
        await self.store.accept(identity, text, message.sender.nickname, elements)
        self.active[message.message_id] = identity

    async def outgoing(self, chain):
        if self.store is None:
            return None
        profile = await self.store.get_setting('profile')
        return await self.store.append_reply(chain, (profile or {}).get('peer_nickname', 'Kira'))

    async def finish(self, event=None, failed=False):
        # Consecutive native inputs can belong to different batches. Completing one
        # batch must not mark the following batch as finished/failed.
        if event is None:
            keys = list(self.active)
        else:
            messages = getattr(event, 'messages', None)
            if messages is None:
                messages = [getattr(event, 'message', None)]
            keys = [getattr(message, 'message_id', None) for message in messages]
        identities = [self.active.pop(key) for key in keys if key in self.active]
        if self.store is not None and failed:
            for identity in identities:
                await self.store.finish(identity, 'failed')

    async def close(self):
        self.closed = True
        if self.capability and self.capability.publish is self.receiver:
            self.capability.publish = self.original
        if self.store:
            for identity in self.active.values():
                await self.store.finish(identity, 'interrupted')
        self.active.clear()

    async def import_history(self):
        """Once per desktop identity, backfill its retained archive with stable IDs."""
        history = getattr(self.plugin.ctx, 'message_history', None)
        if history is None:
            return
        sid = self.plugin.transport_sid
        marker = 'desktop-history-v1:' + sid
        if await self.store.get_setting(marker):
            return
        records, cursor = [], None
        while True:
            page = await history.list_messages(sid, cursor=cursor, limit=200)
            records.extend(page.messages)
            cursor = page.next_cursor
            if not cursor:
                break
        records.reverse()
        async with self.store.lock, aiosqlite.connect(self.store.path) as db:
            await db.execute('BEGIN IMMEDIATE')
            for record in records:
                if record.status == 'failed':
                    continue
                elements = await serialize_message_chain(record.chain, archive_root=self.store.media_dir)
                identity = ('desktop-in:' + str(record.platform_message_id)) if record.direction == 'incoming' else ('desktop-archive:' + record.id)
                body = self.store.message(identity, record.direction, record.sender_name or 'Kira', elements)
                body['timestamp'] = record.timestamp
                await db.execute('INSERT OR IGNORE INTO messages (id, body) VALUES (?, ?)',
                                 (identity, json.dumps(body, ensure_ascii=False)))
            await db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (marker, 'true'))
            await db.commit()
