import copy
import json
from pathlib import Path

MODEL_FIELDS = ('model_overrides', 'bubble_seconds', 'voice_enabled', 'voice_prompt',
    'click_enabled', 'click_cooldown', 'touch_test_mode', 'drag_events', 'ai_layout_enabled', 'drag_repeat_boundaries', 'resource_policy', 'outfits', 'ai_control_copy_enabled')


class ModelFollower:
    def __init__(self, data_dir, viewer_url, slot, defaults):
        self.file = Path(data_dir) / 'model-settings.json'
        self.viewer_url, self.slot, self.defaults = viewer_url, slot, defaults
        self.state_file = None
        self.selection = None
        self.valid = False
        self.message = '等待加载原生模型'
        self.models = {}
        self.seen = False
        self.storage_error = None
        if self.file.is_file():
            try:
                content = json.loads(self.file.read_text(encoding='utf-8'))
                if content.get('version') == 1 and isinstance(content.get('models'), dict):
                    if any(not isinstance(item, dict) or not isinstance(item.get('settings'), dict) for item in content['models'].values()):
                        raise ValueError('invalid model settings entries')
                    self.models = content['models']
                else:
                    raise ValueError('unsupported model settings store')
            except (OSError, ValueError, AttributeError):
                self.storage_error = '模型配置存档暂时不可读取，已保留原文件'
                self.message = self.storage_error

    @property
    def key(self):
        return self.selection['key'] if self.selection else ''

    def write(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': 1, 'models': self.models}, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.file)

    def save(self, config):
        if not self.selection:
            return
        old = copy.deepcopy(self.models)
        self.models[self.key] = {'identity': self.selection['identity'],
            'path': self.selection['path'], 'settings': {k: copy.deepcopy(config[k]) for k in MODEL_FIELDS}}
        try:
            self.write()
        except OSError:
            self.models = old
            raise

    def status(self):
        return {'key': self.key, 'following': self.valid and bool(self.selection),
            'message': self.message, 'name': self.selection['name'] if self.selection else ''}
