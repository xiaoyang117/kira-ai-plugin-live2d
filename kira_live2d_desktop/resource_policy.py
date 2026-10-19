"""Per-model allow/deny settings shared by prompts, tools and manual tests."""
import json


def read_policy(raw):
    policy = {'expressions_enabled': True, 'motions_enabled': True,
              'disabled_expressions': [], 'disabled_motions': [],
              'enabled_expressions': [], 'enabled_motions': [],
              'appearance_expressions': [], 'appearance_motions': []}
    if raw == '':
        return policy
    if not isinstance(raw, str) or len(raw) > 262144:
        raise ValueError('表情动作禁用设置格式无效')
    try:
        values = json.loads(raw)
    except ValueError:
        raise ValueError('表情动作禁用设置必须是 JSON 对象') from None
    if not isinstance(values, dict) or set(values) - set(policy):
        raise ValueError('表情动作禁用设置包含未知字段')
    for key, value in values.items():
        if key.endswith('_enabled'):
            if type(value) is not bool:
                raise ValueError('表情动作开关必须是布尔值')
        elif (not isinstance(value, list) or len(value) > 4096 or any(
                not isinstance(name, str) or not name.strip() or len(name) > 2048
                or any(ord(char) < 32 for char in name) for name in value)):
            raise ValueError('禁用列表必须是有效名称数组，最多 4096 项')
        policy[key] = value
    return policy


def allowed(policy, section, name):
    if section == 'expressions' and name in ('恢复默认', 'neutral'):
        name = '默认'
    return policy[section + '_enabled'] and name not in policy['disabled_' + section]


def apply_analysis(policy, analysis):
    """Unknown purposes default off; explicit user choices survive rescans."""
    result = {key: list(value) if isinstance(value, list) else value for key, value in policy.items()}
    for section in ('expressions', 'motions'):
        disabled = result['disabled_' + section]
        enabled = set(result['enabled_' + section])
        for name, info in analysis.get(section, {}).items():
            if info.get('uncertain') and not info.get('appearance') and name not in result.get('appearance_'+section,[]) and name not in enabled and name not in disabled:
                disabled.append(name)
    return result


def apply_appearance(analysis, policy):
    """User-confirmed mixed outfit expressions are excluded from emotional gestures."""
    result={section:dict(entries) for section,entries in analysis.items()}
    for section in ('expressions','motions'):
        for name in policy.get('appearance_'+section,[]):
            if name in result.get(section,{}):
                result[section][name]={**result[section][name],'appearance':True,'uncertain':True,
                    'summary':'手动标记：含换装，普通情绪回应不要自动使用'}
    return result
