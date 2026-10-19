"""Stable public plugin identity and a non-destructive legacy data migration."""
import json
from pathlib import Path
import shutil

PLUGIN_ID = 'kira-ai-plugin-live2d'
LEGACY_ID = 'kira_live2d_desktop'


def migrate_legacy_identity(config, data_dir, config_dir, defaults):
    """Import untouched default configuration once and retain existing asset paths."""
    data_dir = Path(data_dir)
    config_dir = Path(config_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    legacy_data = data_dir.parent / LEGACY_ID
    marker = data_dir / 'legacy-identity.json'
    if marker.is_file():
        state = json.loads(marker.read_text(encoding='utf-8'))
        return legacy_data if state.get('use_legacy_data') and legacy_data.is_dir() else data_dir
    legacy_config = config_dir / (LEGACY_ID + '.json')
    imported = False
    untouched = all(key in defaults and value == defaults[key] for key, value in config.items())
    if legacy_config.is_file() and untouched:
        previous = json.loads(legacy_config.read_text(encoding='utf-8'))
        if not isinstance(previous, dict):
            raise ValueError('旧版 Live2D 配置格式无效，已保留原文件')
        updated = {**config, **previous}
        destination = config_dir / (PLUGIN_ID + '.json')
        config_dir.mkdir(parents=True, exist_ok=True)
        if destination.is_file():
            backup = config_dir / (PLUGIN_ID + '.before-identity-migration.json')
            if not backup.exists():
                shutil.copy2(destination, backup)
        temporary = destination.with_suffix('.migration.tmp')
        temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(destination)
        config.update(updated)
        imported = True
    # Retain the old directory instead of copying large models or breaking absolute paths.
    use_legacy = legacy_data.is_dir() and not any(data_dir.iterdir()) and (imported or not legacy_config.exists())
    marker.write_text(json.dumps({'legacy_id': LEGACY_ID, 'config_imported': imported,
                                 'use_legacy_data': use_legacy}, indent=2), encoding='utf-8')
    return legacy_data if use_legacy else data_dir
