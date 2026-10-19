"""Keep a right-click escape menu for the manually click-through pet on Windows."""
import ctypes
import sys


class PassthroughMenuHook:
    def __init__(self,hit_test,open_menu):
        self.hit_test,self.open_menu=hit_test,open_menu
        self.handle=None;self.callback=None;self.suppress_up=False;self.user32=None

    def start(self):
        if self.handle:return True
        if sys.platform!='win32':return False
        user32=ctypes.WinDLL('user32',use_last_error=True)
        kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
        callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,ctypes.c_size_t,ctypes.c_ssize_t)
        user32.SetWindowsHookExW.argtypes=[ctypes.c_int,callback_type,ctypes.c_void_p,ctypes.c_uint]
        user32.SetWindowsHookExW.restype=ctypes.c_void_p
        user32.CallNextHookEx.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_size_t,ctypes.c_ssize_t]
        user32.CallNextHookEx.restype=ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes=[ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype=ctypes.c_bool
        kernel32.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
        kernel32.GetModuleHandleW.restype=ctypes.c_void_p
        self.user32=user32
        self.callback=callback_type(self.dispatch)
        self.handle=user32.SetWindowsHookExW(14,self.callback,kernel32.GetModuleHandleW(None),0)
        if not self.handle:self.callback=None
        return bool(self.handle)

    def dispatch(self,code,message,data):
        try:
            if code>=0:
                if message==0x0205 and self.suppress_up:  # WM_RBUTTONUP
                    self.suppress_up=False;return 1
                if message==0x0204:  # WM_RBUTTONDOWN
                    point=self.hit_test()
                    if point is not None:
                        self.suppress_up=True;self.open_menu(point);return 1
        except Exception as exc:
            print('鼠标穿透右键菜单异常：',repr(exc),flush=True)
        return self.user32.CallNextHookEx(self.handle,code,message,data)

    def stop(self):
        if self.handle:
            self.user32.UnhookWindowsHookEx(self.handle)
            self.handle=None
        self.callback=None;self.suppress_up=False
