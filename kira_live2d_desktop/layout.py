"""Opt-in model placement through the authenticated local companion."""
import asyncio
import json
import math
import time
import uuid



def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'数值必须在 {low} 到 {high} 之间')
    return float(value)


def snapshot(value):
    if not isinstance(value, dict):
        raise ValueError('未读到模型大小和位置')
    return {'x': number(value.get('x'), -1000, 1000),
            'y': number(value.get('y'), -1000, 1000),
            'scale': number(value.get('scale'), .01, 4)}


class LayoutControl:
    def __init__(self, plugin):
        self.plugin = plugin
        self.lock = asyncio.Lock()
        self.command = None
        self.future = None
        self.inspection = None
        self.baselines = {}
        self.storage_error = ''
        self.message = ''

    @property
    def busy(self):
        return self.lock.locked()

    def initialize(self):
        self.file = self.plugin.data_dir/'layout-baselines.json'
        if not self.file.exists():
            return
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
            if data.get('version') != 1 or not isinstance(data.get('models'), dict) or len(data['models']) > 1000:
                raise ValueError('Unsupported layout baselines')
            self.baselines = {key: snapshot(value) for key, value in data['models'].items()}
        except (OSError, ValueError, TypeError, AttributeError):
            self.storage_error = '大小与位置备份不可读取，已保留原文件；本次不调整模型'

    def save_baseline(self, key, value):
        models = {**self.baselines, key: snapshot(value)}
        if len(models) > 1000:
            raise ValueError('大小与位置备份已达到上限')
        temporary = self.file.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps({'version': 1, 'models': models}, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.file)
        finally:
            temporary.unlink(missing_ok=True)
        self.baselines = models

    def status(self):
        key = self.plugin.tracking_status()['key']
        return {'enabled': self.plugin.plugin_cfg.get('ai_layout_enabled', False) is True,
                'busy': self.busy, 'can_restore': key in self.baselines and not self.storage_error,
                'message': self.storage_error or self.message}

    def close(self):
        if self.future is not None and not self.future.done():
            self.future.set_exception(ConnectionError('桌宠正在停止，本次调整已停止等待'))

    def require_outfit(self):
        if not self.plugin.viewer.connected:raise ValueError(self.plugin.viewer.last_error)

    async def outfit(self,indices):
        if indices is None:return
        self.require_outfit()
        await self.plugin.viewer.request('outfit',expressions=indices)

    async def execute(self, action='adjust', x=None, y=None, scale=None, *, require_enabled=True, expected_key=None):
        plugin = self.plugin
        plugin.sync_followed_model()
        key = plugin.tracking_status()['key']
        if expected_key is not None and expected_key != key:
            raise ValueError('模型已切换，本轮不再调整大小和位置')
        if require_enabled and plugin.plugin_cfg.get('ai_layout_enabled', False) is not True:
            raise ValueError('允许 AI 调整大小和位置未开启')
        if self.storage_error:
            raise ValueError(self.storage_error)
        if action not in ('adjust', 'restore', 'get'):
            raise ValueError('操作仅支持 adjust、restore 或 get')
        if x is not None: x = number(x, 5, 95)
        if y is not None: y = number(y, 5, 95)
        if scale is not None: scale = number(scale, 50, 150)
        if action == 'adjust' and x is None and y is None and scale is None:
            raise ValueError('请至少指定位置或大小')
        if self.busy or plugin.adapting_model or plugin.outfit_busy or plugin.preview_busy() or plugin.bridge_installing:
            raise ValueError('请等模型切换、预览或调整结束')
        if not plugin.accepting or not plugin.viewer.connected or not plugin.tracking_status()['following']:
            raise ValueError('大小与位置控制需要原生壳连接并加载模型')
        if getattr(plugin.viewer,'debug_active',False):raise ValueError('调试中，请关闭调试面板后再调整大小与位置')
        if action == 'restore' and key not in self.baselines:
            raise ValueError('当前模型还没有 AI 调整前的大小和位置备份')
        if plugin.native_mode:
            async with self.lock:
                current=await plugin.viewer.request('inspect')
                if action=='get':return current
                if key not in self.baselines:
                    self.save_baseline(key,{'x':current['x']/10,'y':current['y']/10,'scale':current['scale']})
                if action=='restore':
                    base=self.baselines[key]
                    result=await plugin.viewer.request('layout',geometry={'x':base['x']*10,'y':base['y']*10,'w':450*base['scale'],'h':650*base['scale']})
                else:
                    result=await plugin.viewer.request('layout',**{k:v for k,v in [('x',x),('y',y),('scale',scale*self.baselines[key]['scale'] if scale is not None else None)] if v is not None})
                self.message='独立壳大小与位置已更新'
                return result
