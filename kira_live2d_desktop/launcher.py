"""Launch the bundled desktop panel, or restore an existing panel on Windows."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys

_process = None


def restore_panel():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(handle, _):
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(handle, title, len(title))
        if title.value.startswith('Kira 桌宠 · '):
            windows.append(handle)
        return True
    callback = callback_type(collect)
    user32.EnumWindows(callback, 0)
    window = windows[0] if windows else None
    if not window:
        return False
    user32.ShowWindowAsync(window, 9)
    user32.SetForegroundWindow(window)
    return True


def open_panel(config_path):
    global _process
    if sys.platform != 'win32':
        raise ValueError('桌面输入窗口目前只支持 Windows')
    config_path = Path(config_path).resolve()
    script = Path(__file__).parent / 'desktop' / 'client.pyw'
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not config_path.is_file():
        raise ValueError('桌宠连接配置尚未就绪，请先重新加载插件')
    if not script.is_file() or not pythonw.is_file():
        raise ValueError('找不到桌面输入程序或 pythonw.exe，请检查插件与 KiraAI 安装')
    config_path.with_suffix('.show').touch()
    if restore_panel():
        return {'state': 'focused'}
    if _process is not None and _process.poll() is None:
        return {'state': 'starting'}
    _process = subprocess.Popen([str(pythonw), str(script), '--config', str(config_path)],
        cwd=str(script.parent), creationflags=subprocess.CREATE_NO_WINDOW)
    return {'state': 'opened'}
