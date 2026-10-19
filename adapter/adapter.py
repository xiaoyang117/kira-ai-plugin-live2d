import asyncio
from core.adapter import BaseAdapter, IMCapability, MessageFormatMetadata
from core.adapter.access import ListAccessPolicy
from core.chat.message_utils import KiraIMSentResult

class DesktopIM(IMCapability):
    _SUPPORTED_ELEMENTS = ['text', 'record']
    async def get_message_metadata(self):
        return MessageFormatMetadata(self._supported_elements)
    async def send_direct_message(self, user_id, message):
        if self.adapter.deliver is None:
            return KiraIMSentResult(ok=False, err='Desktop transport is not ready')
        return await self.adapter.deliver(str(user_id), message)
    async def send_group_message(self, group_id, message):
        return KiraIMSentResult(ok=False, err='Desktop supports private chat only')

class DesktopAdapter(BaseAdapter):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.deliver = None
        self.stopped = asyncio.Event()
        self.register_capability(IMCapability, DesktopIM(self))
        self.access.set_policy(capability_type=IMCapability, permission='im.direct.receive',
            policy=ListAccessPolicy.from_lists('deny_list', deny_list=[]))
    async def start(self):
        await self.stopped.wait()
    async def stop(self):
        self.deliver = None
        self.stopped.set()
    def get_client(self):
        return self
