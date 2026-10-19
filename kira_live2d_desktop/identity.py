"""Desktop identity helpers."""
import hashlib

def parse_binding(value):
    if not value:
        return None
    parts = value.strip().split(':', 2)
    if len(parts) != 3 or parts[1] != 'dm' or not parts[0] or not parts[2]:
        raise ValueError('绑定身份必须是完整私聊会话，例如 QQ实例名:dm:用户ID')
    return parts[0], parts[2]

def recipient_id(binding):
    return hashlib.sha256(binding.encode('utf-8')).hexdigest()[:20] if binding else 'local'

