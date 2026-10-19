"""Keep desktop delivery local while Kira uses the selected conversation key."""
from contextvars import ContextVar
from functools import wraps
from copy import copy
from types import SimpleNamespace

_turn = ContextVar('kira_desktop_reply_turn', default=None)


class DesktopReplyRoute:
    def __init__(self, plugin):
        self.plugin = plugin
        self.original = None

    def install(self):
        from core.workflow.src.im.message_delivery import MessageDeliveryService
        self.original = MessageDeliveryService.send_message_chain
        original = self.original
        plugin = self.plugin

        @wraps(original)
        async def send(service, session, chain, **kwargs):
            event = _turn.get()
            if (event is not None and plugin.accepting and plugin.pending
                    and plugin.is_desktop_session(event) and session == event.session.sid):
                # Only this desktop task's replies are redirected. Other tasks,
                # including simultaneous real-platform replies, keep their route.
                if session != plugin.transport_sid:
                    # A per-call facade keeps outgoing history under the real
                    # conversation without replacing any global adapter entry.
                    async def direct(recipient, message):
                        if recipient != event.session.session_id:
                            raise ValueError('Unexpected desktop reply recipient')
                        return await plugin.deliver(plugin.recipient, message)
                    target = SimpleNamespace(send_direct_message=direct)
                    original_adapter=plugin.ctx.adapter_mgr.get_adapter(event.session.adapter_name)
                    adapter = SimpleNamespace(info=original_adapter.info if original_adapter else plugin.adapter.info,
                        get_capability=lambda capability: target)
                    manager = service.adapter_mgr
                    local = copy(service)
                    local.adapter_mgr = SimpleNamespace(get_adapter=lambda name:
                        adapter if name == event.session.adapter_name else manager.get_adapter(name))
                    return await original(local, session, chain, **kwargs)
            return await original(service, session, chain, **kwargs)

        self.replacement = send
        MessageDeliveryService.send_message_chain = send

    def enter(self, event):
        _turn.set(event)

    def leave(self):
        _turn.set(None)

    def close(self):
        from core.workflow.src.im.message_delivery import MessageDeliveryService
        if self.original and MessageDeliveryService.send_message_chain is self.replacement:
            MessageDeliveryService.send_message_chain = self.original
