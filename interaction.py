"""Model-declared drag sources and user-authored descriptions."""
import hashlib
import json

PHASES = {'begin': '开始互动', 'end': '松手结束', 'min': '到达最小值', 'max': '到达最大值'}


def drag_key(area, parameter, name):
    return hashlib.sha256(json.dumps([area, parameter, name], ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()[:24]


def drag_candidates(data):
    controllers = data.get('Controllers', {})
    controller = controllers.get('ParamHit', {}) if isinstance(controllers, dict) else {}
    rows = controller.get('Items', []) if isinstance(controller, dict) else []
    if not rows:
        rows = data.get('hit_params', [])
    result = {}
    if not isinstance(rows, list):
        return []
    for item in rows[:128]:
        if not isinstance(item, dict):
            continue
        area, parameter, name = (item.get(upper, item.get(lower, '')) for upper, lower in
            [('HitArea', 'hit_area'), ('Id', 'id'), ('Name', 'name')])
        if not all(isinstance(value, str) and len(value) <= 200 and not any(ord(c)<32 for c in value)
                for value in (area, parameter, name)) or not area or not parameter:
            continue
        key = drag_key(area, parameter, name)
        result[key] = {'id': key, 'area': area, 'parameter': parameter, 'name': name,
            'axis': item.get('Axis',item.get('axis',0)),
            'factor': item.get('Factor',item.get('factor',.01)),
            'release': item.get('ReleaseType',item.get('release_type',0)),
            'enabled': controller.get('Enabled', True) is not False and item.get('Enabled', item.get('enabled', True)) is not False}
    return list(result.values())


def read_events(raw):
    if not isinstance(raw, str) or len(raw) > 32768:
        raise ValueError('拖动事件配置过长或格式无效')
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        raise ValueError('拖动事件必须是有效 JSON') from None
    if not isinstance(data, dict) or len(data) > 128:
        raise ValueError('拖动事件最多 128 组')
    for key, phases in data.items():
        if not isinstance(key, str) or len(key) != 24 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('拖动事件来源无效，请重新读取模型')
        if not isinstance(phases, dict) or set(phases)-PHASES.keys():
            raise ValueError('拖动阶段配置无效')
        for value in phases.values():
            if not isinstance(value, str) or len(value)>300 or any(ord(c)<32 for c in value):
                raise ValueError('事件描述最多 300 字，不能含控制字符')
    return data
