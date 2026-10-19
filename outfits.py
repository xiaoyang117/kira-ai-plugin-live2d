"""User-selected model resources for manual outfit changes."""
import json
import re


def read_outfits(raw):
    if not isinstance(raw, str) or len(raw) > 131072:
        raise ValueError('换装配置格式无效或过长')
    try:
        rows = json.loads(raw) if raw.strip() else []
    except ValueError:
        raise ValueError('换装配置必须是有效 JSON') from None
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError('最多配置 128 个换装项')
    result, ids = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'name', 'expression', 'motion', 'event'}:
            raise ValueError('换装配置字段不完整')
        entry = {}
        for key, limit in [('id',32),('name',80),('expression',200),('motion',200),('event',300)]:
            value = row[key]
            if not isinstance(value, str) or len(value) > limit or any(ord(c)<32 for c in value):
                raise ValueError('换装名称最多 80 字，事件最多 300 字，不能含控制字符')
            entry[key] = value.strip()
        if not re.fullmatch(r'[0-9a-f]{24,32}',entry['id']) or entry['id'] in ids:
            raise ValueError('换装项标识无效或重复')
        ids.add(entry['id'])
        if not entry['name'] or not (entry['expression'] or entry['motion']):
            raise ValueError('换装项需要名称，并至少选择一个表情或动作')
        result.append(entry)
    return result


def outfit_expression_indices(profile, entry):
    """Resolve actual expression resources, including those inside a motion event."""
    from .model_profile import load_profile, read_json
    from pathlib import Path
    path = profile.get('load_path')
    if not path or profile.get('format') not in ('Cubism 3', '模型配置'):
        return None
    data = read_json(Path(path))
    refs = data.get('FileReferences', data)
    automatic = load_profile(path)
    indices = []
    motion = profile.get('motions', {}).get(entry.get('motion'))
    if motion and motion['type'] == 0:
        groups = refs.get('Motions', refs.get('motions', data.get('Motions', {})))
        if isinstance(groups, dict):
            for group, rows in groups.items():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    name = row.get('Name', row.get('name'))
                    if motion['mtn'] != f'{group}:{name}':
                        continue
                    expression = row.get('Expression', row.get('expression'))
                    if expression in automatic['expressions']:
                        indices.append(automatic['expressions'][expression])
    explicit = profile.get('expressions', {}).get(entry.get('expression'))
    if explicit is not None and explicit not in indices:
        indices.append(explicit)
    return indices
