"""Windows 11 Settings inspired neutral surfaces shared by the desktop shell."""
import sys
from PySide6.QtCore import QObject,QEvent,QTimer
from PySide6.QtWidgets import QApplication

STYLE='''
QDialog,QWidget#settingsPage { background:#202020; color:#ffffff; }
QFrame#sidebar { background:#202020; border-right:1px solid #303030; }
QFrame#settingsCard { background:#2b2b2b; border:1px solid #363636; border-radius:8px; }
QLabel { background:transparent; color:#d0d0d0; font-size:13px; }
QLabel#headline { color:#ffffff; font-size:28px; font-weight:600; padding:0; }
QLabel#section { color:#ffffff; font-size:14px; font-weight:600; }
QLabel#caption { color:#a6a6a6; font-size:12px; }
QLabel#brand { color:#ffffff; font-size:18px; font-weight:600; }
QLineEdit,QPlainTextEdit,QSpinBox,QComboBox {
 background:#333333; color:#ffffff; border:1px solid #454545;
 border-bottom:1px solid #969696; border-radius:4px; padding:8px;
 selection-background-color:#356b85;
}
QLineEdit:focus,QPlainTextEdit:focus,QSpinBox:focus,QComboBox:focus { border-bottom:2px solid #60cdff; }
QPushButton { background:#353535; color:#ffffff; border:1px solid #484848;
 border-radius:4px; min-height:22px; padding:7px 16px; }
QPushButton:hover { background:#3e3e3e; }
QPushButton:pressed { background:#303030; color:#c2c2c2; }
QPushButton:disabled { background:#2c2c2c; color:#777777; border-color:#383838; }
QPushButton#primary { background:#60cdff; border-color:#60cdff; color:#002b3e; }
QPushButton#primary:hover { background:#78d4ff; }
QPushButton#primary:pressed { background:#55b6e2; }
QPushButton#primary:disabled { background:#3b3b3b; border-color:#414141; color:#848484; }
QPushButton#navigation { text-align:left; background:transparent; border:0; border-left:3px solid transparent; padding:9px 14px; }
QPushButton#navigation:hover { background:#2b2b2b; }
QPushButton#navigation:checked { background:#303030; border-left:3px solid #60cdff; }
QMenu { background:#2c2c2c; color:#ffffff; border:1px solid #454545; border-radius:8px; padding:5px; }
QMenu::item { padding:8px 22px; border-radius:4px; }
QMenu::item:selected { background:#3c3c3c; }
QMenu::separator { height:1px; background:#444444; margin:5px; }
QScrollArea { background:transparent; border:0; }
QScrollBar:vertical { background:transparent; width:7px; margin:2px; }
QScrollBar::handle:vertical { background:#797979; border-radius:3px; min-height:24px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QToolTip { background:#303030; color:#ffffff; border:1px solid #555555; padding:6px; }
'''

def native_glass(widget):
    if sys.platform!='win32':return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd=wintypes.HWND(int(widget.winId()))
        for attribute,value in ((20,1),(33,2)):
            setting=ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,attribute,ctypes.byref(setting),4)
    except (AttributeError,OSError,ValueError,RuntimeError):pass

class _Surface(QObject):
    def eventFilter(self,widget,event):
        if event.type()==QEvent.Type.Show:QTimer.singleShot(0,lambda:native_glass(widget))
        return False

def surface(widget):
    widget._glass_surface=_Surface(widget)
    widget.installEventFilter(widget._glass_surface)

def install(app=None):
    (app or QApplication.instance()).setStyleSheet(STYLE)
