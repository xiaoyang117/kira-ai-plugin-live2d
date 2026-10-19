"""Read public model metadata without changing or unpacking model assets."""
import json
import re
import math
from functools import lru_cache
from pathlib import Path

REGIONS = {
    'head': ('头部', '摸了摸你的头'), 'face': ('脸部', '轻轻碰了你的脸'),
    'body': ('身体', '轻轻碰了你的身体'), 'hand': ('手部', '轻轻碰了你的手'),
    'arm': ('手臂', '轻轻碰了你的手臂'), 'leg': ('腿部', '轻轻碰了你的腿'),
    'foot': ('脚部', '轻轻碰了你的脚'), 'hair': ('头发', '摸了摸你的头发'),
    'ear': ('耳朵', '轻轻碰了你的耳朵'), 'tail': ('尾巴', '轻轻碰了你的尾巴'),
    'chest': ('上身', '轻轻碰了你的上身'), 'belly': ('腹部', '轻轻碰了你的腹部'),
    'back': ('背部', '轻轻碰了你的背'), 'unknown': ('未区分', '轻轻碰了你一下'),
}
ALIASES = {
    'head': ('head', '头', '头部', '頭', '頭部'), 'face': ('face', 'cheek', '脸', '脸部', '臉'),
    'body': ('body', '身体', '身體', '身体部位'), 'hand': ('hand', 'lefthand', 'righthand', '手', '左手', '右手'),
    'arm': ('arm', 'leftarm', 'rightarm', '手臂'), 'leg': ('leg', 'leftleg', 'rightleg', '腿', '腿部'),
    'foot': ('foot', 'feet', 'leftfoot', 'rightfoot', '脚', '脚部'), 'hair': ('hair', '头发', '髪'),
    'ear': ('ear', 'ears', '耳朵'), 'tail': ('tail', '尾巴'), 'chest': ('chest', 'bust', '胸', '胸部'),
    'belly': ('belly', 'stomach', '腹部', '肚子'), 'back': ('back', '背', '背部'),
}


def normal(value):
    return re.sub(r'[\s_\-]', '', value).casefold()


def guess_region(value):
    key = normal(value)
    for prefix in ('hitarea', 'hit', 'tap'):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    for region, aliases in ALIASES.items():
        if key in aliases:
            return region
    return 'unknown'


def read_json(path):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('模型配置过大，请选择模型描述文件')
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError('无法读取模型 JSON 配置') from exc
    if not isinstance(data, dict):
        raise ValueError('模型配置必须是 JSON 对象')
    return data


@lru_cache(maxsize=2048)
def model_asset_kind(filename, modified, size):
    """Classify referenced JSON by its contents, independent of its name."""
    try:
        data = read_json(Path(filename))
    except (OSError, ValueError):
        return 'unreadable'
    parameters=data.get('Parameters')
    if isinstance(parameters,list) and parameters:
        if all(isinstance(item,dict) and isinstance(item.get('Id'),str) and item['Id']
                and type(item.get('Value')) in (int,float) and math.isfinite(item['Value'])
                and item.get('Blend','Add') in ('Add','Multiply','Overwrite') for item in parameters):
            return 'expression'
        return 'unknown'
    curves = data.get('Curves')
    if isinstance(curves, list) and curves and all(isinstance(curve, dict)
            and isinstance(curve.get('Id'), str) and isinstance(curve.get('Segments'), list)
            and len(curve['Segments']) >= 2 for curve in curves):
        return 'motion'
    if isinstance(data.get('PhysicsSettings'), list):
        return 'physics'
    return 'unknown'


def expression_asset_valid(filename, modified, size):
    return model_asset_kind(filename, modified, size) == 'expression'


def motion_preview_interval(profile, name):
    """Allow a full local clip to finish before requesting another preview."""
    spec = profile.get('motions', {}).get(name, {})
    filename, speed = None, 1
    try:
        if spec.get('type') == 1:
            filename = Path(spec['mtn'])
        elif profile.get('load_path') and spec.get('type') == 0:
            model = Path(profile['load_path'])
            data = read_json(model)
            refs = data.get('FileReferences', data)
            group, _, target = spec['mtn'].partition(':')
            entries = refs.get('Motions', refs.get('motions', {})).get(group, [])
            entries = [entry for entry in entries if isinstance(entry, dict)
                and (not target or entry.get('Name', entry.get('name')) == target)]
            if len(entries) == 1:
                entry = entries[0]
                resource = entry.get('File', entry.get('file'))
                if resource:
                    filename = model.parent / resource
                speed = float(entry.get('Speed', entry.get('speed', 1)))
        if filename and math.isfinite(speed) and speed > 0:
            data = read_json(filename)
            duration = float(data.get('Meta', {}).get('Duration', 0)) / speed
            if math.isfinite(duration) and duration > 0:
                return max(2, min(120, duration + .5))
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return 8


def read_overrides(raw):
    if not isinstance(raw, str) or len(raw) > 131072:
        raise ValueError('模型映射格式无效或过长')
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        raise ValueError('模型映射必须是有效 JSON') from None
    if not isinstance(data, dict) or set(data) - {'expressions', 'motions', 'touch'}:
        raise ValueError('模型映射只支持 expressions、motions、touch')
    for section in ('expressions', 'motions', 'touch'):
        values = data.setdefault(section, {})
        if not isinstance(values, dict) or len(values) > 512:
            raise ValueError('每组模型映射最多 512 项')
        for name, value in values.items():
            if not isinstance(name, str) or not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
                raise ValueError('模型映射名称不能为空或含控制字符')
            if section == 'expressions':
                if type(value) is not int or not 0 <= value <= 4095:
                    raise ValueError('表情编号必须是 0 到 4095 的整数')
                if name in ('默认', '恢复默认', 'neutral'):
                    raise ValueError('默认表情名称保留给恢复操作')
            elif section == 'motions':
                if isinstance(value, str):
                    spec = {'type': 0, 'mtn': value}
                elif isinstance(value, dict) and set(value) == {'type', 'mtn'}:
                    spec = value
                else:
                    raise ValueError('动作映射需填写动作组或文件目标')
                if type(spec['type']) is not int or spec['type'] not in (0, 1):
                    raise ValueError('动作目标类型无效')
                target = spec['mtn']
                if (not isinstance(target, str) or not target.strip() or len(target) > (2000 if spec['type'] == 1 else 200)
                        or any(ord(c) < 32 for c in target)):
                    raise ValueError('动作目标不能为空或含控制字符')
                if spec['type'] == 1 and not Path(target.strip()).is_absolute():
                    raise ValueError('动作文件需填写完整路径')
            elif (not isinstance(value, str) or not value.strip() or len(value) > 100
                    or any(ord(char) < 32 for char in value)):
                raise ValueError('触摸部位需填写 1 到 100 个字，不能含控制字符')
            elif section == 'touch':
                values[name] = value.strip()
    return data


def unique(mapping, name):
    base = str(name).strip()[:100] or '未命名'
    candidate, suffix = base, 2
    while candidate in mapping or candidate in ('默认', '恢复默认', 'neutral'):
        candidate = f'{base} ({suffix})'
        suffix += 1
    return candidate


def load_profile(value, overrides=''):
    custom = read_overrides(overrides)
    profile = {'format': 'basic', 'name': '当前原生 Live2D 模型', 'load_path': None,
        'expressions': {}, 'motions': {}, 'hit_areas': [], 'warnings': []}
    path, data = None, None
    if value:
        if not isinstance(value, str):
            raise ValueError('模型路径必须是文本')
        path = Path(value)
        if not path.is_absolute() or not path.is_file():
            raise ValueError('模型文件不存在，请填写完整路径；仅连接已加载模型时可留空')
        path = path.resolve()
        profile['name'] = path.stem
        if path.suffix.lower() == '.json':
            data = read_json(path)
            if 'lpkFile' in data or ('file' in data and 'type' in data):
                if data.get('type', 0) != 0:
                    raise ValueError('所选创意工坊项目不是 Live2D 模型')
                profile['name'] = str(data.get('title') or path.parent.name)
                target = data.get('lpkFile') or data.get('file')
                if not isinstance(target, str) or not target:
                    raise ValueError('创意工坊配置没有模型文件')
                path = (path.parent / target).resolve()
                if not path.is_file():
                    raise ValueError('创意工坊模型文件不存在')
                data = read_json(path) if path.suffix.lower() == '.json' else None
        if path.suffix.lower() == '.lpk':
            profile['format'] = 'LPK'
            profile['warnings'].append('LPK 请先解包为普通 Cubism 3 JSON 再使用。')
        elif path.suffix.lower() == '.json' and data is not None:
            parse_model(profile, data, path)
        else:
            raise ValueError('请选择模型 JSON、LPK 或创意工坊 config.json')
    else:
        profile['warnings'].append('请在原生壳设置中选择本地 Cubism 3 JSON 模型。')
    # Explicit lists replace detected lists, preventing obsolete model names from leaking into LPK profiles.
    if custom['expressions']:
        profile['expressions'] = dict(custom['expressions'])
    if custom['motions']:
        profile['motions'] = {name: {'type': value['type'], 'mtn': value['mtn'].strip()} if isinstance(value, dict)
            else {'type': 0, 'mtn': value.strip()} for name, value in custom['motions'].items()}
    profile['touch_overrides'] = custom['touch']
    return profile


def parse_model(profile, data, path):
    from .interaction import drag_candidates
    profile['drag_candidates'] = drag_candidates(data)
    profile['ai_controlled'] = isinstance(data.get('KiraAIAdaptation'), dict)
    refs = data.get('FileReferences', data)
    if not isinstance(refs, dict) or not (refs.get('Moc') or refs.get('model')):
        raise ValueError('这不是可识别的 Live2D 模型描述文件')
    profile['format'] = 'Cubism 3' if 'FileReferences' in data else 'Cubism 2' if 'model' in data else '模型配置'
    profile['load_path'] = str(path)
    extra_motions = []
    recovered_files = set()
    expressions = refs.get('Expressions', refs.get('expressions', data.get('Expressions', [])))
    if isinstance(expressions, list):
        loaded_index = 0
        for index, item in enumerate(expressions[:256]):
            if not isinstance(item, dict):
                continue
            filename = item.get('File', item.get('file', ''))
            name = item.get('Name', item.get('name'))
            if not isinstance(name,str) or not name:name = Path(str(filename)).name.split('.exp')[0] or f'表情 {index}'
            if 'FileReferences' in data:
                try:
                    asset = (path.parent / filename).resolve()
                    stat = asset.stat()
                    kind = model_asset_kind(str(asset), stat.st_mtime_ns, stat.st_size)
                except (OSError, TypeError, ValueError):
                    kind = 'unreadable'
                if kind == 'motion':
                    extra_motions.append((str(name), asset))
                    continue
                if kind == 'physics':
                    profile['warnings'].append(f'表情列表中的物理配置不参与表情编号：{name}')
                    continue
                if kind != 'expression':
                    reason = '文件缺失或无法读取' if kind == 'unreadable' else '内容不符合表情或动作格式'
                    profile['warnings'].append(f'已跳过资源（{reason}）：{name}')
                    continue
            profile['expressions'][unique(profile['expressions'], name)] = loaded_index
            loaded_index += 1
    motions = refs.get('Motions', refs.get('motions', data.get('Motions', {})))
    if isinstance(motions, dict):
        profile['click_groups'] = [key for key in motions if isinstance(key, str) and key.casefold().startswith('tap')][:256]
        adapted = isinstance(data.get('KiraAIAdaptation'), dict) and data['KiraAIAdaptation'].get('mode') != 'native'
        allowed = data['KiraAIAdaptation'].get('motion_labels', {}) if adapted else {}
        allowed = set(allowed.values()) if isinstance(allowed, dict) and all(isinstance(value, str) for value in allowed.values()) else set()
        for group, entries in list(motions.items())[:257 if adapted else 128]:
            if not isinstance(group, str) or not isinstance(entries, list):
                continue
            for item in entries[:128]:
                if not isinstance(item, dict) or len(profile['motions']) >= 512:
                    continue
                name = item.get('Name', item.get('name'))
                if adapted and f'{group}:{name}' not in allowed:
                    continue
                filename = item.get('File', item.get('file'))
                if isinstance(name, str) and name:
                    label = unique(profile['motions'], item.get('KiraAILabel') or f'{group}:{name}')
                    profile['motions'][label] = {'type': 0, 'mtn': f'{group}:{name}'}
                elif isinstance(filename, str) and filename:
                    file = (path.parent / filename).resolve()
                    if not file.is_file():
                        profile['warnings'].append(f'动作文件缺失：{filename}')
                        continue
                    stem = Path(filename).name.split('.motion3')[0].split('.mtn')[0]
                    # Friendly aliases only apply when an actual referenced file exists.
                    label = {'nod': '点头', 'shake': '摇头', 'tilt': '歪头'}.get(stem.casefold(), f'{group}/{stem}')
                    profile['motions'][unique(profile['motions'], label)] = {'type': 1, 'mtn': str(file)}
                else:
                    label = f'{group}（组动作）'
                    profile['motions'].setdefault(label, {'type': 0, 'mtn': group})
    for name, asset in extra_motions:
        key = str(asset).casefold()
        if key in recovered_files:
            profile['warnings'].append(f'同一动作已从表情列表补充到动作映射：{name}')
            continue
        if len(profile['motions']) >= 512:
            profile['warnings'].append(f'动作数量已达上限，未加入：{name}')
            continue
        label = re.sub(r'\.motion3(?:\.json)?$', '', name, flags=re.IGNORECASE) or name
        profile['motions'][unique(profile['motions'], label)] = {'type': 1, 'mtn': str(asset)}
        recovered_files.add(key)
        profile['warnings'].append(f'已将表情列表中的动作加入动作映射：{name}')
    areas = data.get('HitAreas', data.get('hit_areas', refs.get('HitAreas', [])))
    if isinstance(areas, list):
        for item in areas[:256]:
            if not isinstance(item, dict):
                continue
            name, ident = item.get('Name', item.get('name', '')), item.get('Id', item.get('id', ''))
            if not isinstance(name, str) or not isinstance(ident, str):
                continue
            profile['hit_areas'].append({'name': name[:100], 'id': ident[:100]})


def touch_key(value):
    key = normal(value)
    return key[3:] if key.startswith('tap') and len(key) > 3 else key


def click_candidates(profile, observed=()):
    candidates = []
    def add(name, aliases, source):
        aliases = [value for value in [name, *aliases] if isinstance(value, str) and value.strip()
                   and len(value) <= 100 and not any(ord(c) < 32 for c in value)]
        if not aliases:
            return
        keys = {touch_key(value) for value in aliases}
        for item in candidates:
            if keys & {touch_key(value) for value in item['aliases']}:
                item['aliases'] = list(dict.fromkeys([*item['aliases'], *aliases]))
                if source not in item['sources']:
                    item['sources'].append(source)
                return
        if len(candidates) < 256:
            candidates.append({'name': aliases[0], 'aliases': list(dict.fromkeys(aliases)), 'sources': [source]})
    for item in profile.get('hit_areas', []):
        add(item.get('name') or item.get('id'), [item.get('id')], 'declared')
    for group in profile.get('click_groups', []):
        if not isinstance(group, str) or not group.casefold().startswith('tap'):
            continue
        name = re.sub(r'#\d+$', '', group[3:])
        if name:
            add(name, [group], 'motion_group')
    for name in observed:
        add(name, [], 'observed')
    return candidates


def touch_region(profile, area):
    custom = profile.get('touch_overrides', {})
    for key, region in custom.items():
        if area and touch_key(key) == touch_key(area):
            return region
    for item in click_candidates(profile):
        aliases = {touch_key(value) for value in item['aliases']}
        if area and touch_key(area) in aliases:
            for key, region in custom.items():
                if touch_key(key) in aliases:
                    return region
    return 'unknown'
