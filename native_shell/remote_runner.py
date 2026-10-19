"""Standalone Qt client, independent of the KiraAI installation."""
import hashlib
import json
import os
from pathlib import Path
import threading
import sys
import time
import urllib.request
import uuid
import faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(20)
print('[启动] 正在加载窗口组件…',flush=True)
sys.path.insert(0,str(Path(__file__).resolve().parent))
from PySide6.QtCore import Signal,Qt,QTimer
from PySide6.QtGui import QSurfaceFormat,QFont
from PySide6.QtWidgets import QApplication,QDialog,QFormLayout,QLineEdit,QPushButton,QLabel,QPlainTextEdit,QVBoxLayout,QHBoxLayout,QFrame,QWidget,QStackedWidget,QButtonGroup,QScrollArea
import live2d
print('[启动] 正在加载桌宠组件…',flush=True)
from window import Window,Network
from remote_model import unpack_model_bundle,MAX_SIZE
from glass_theme import STYLE,surface,install

ROOT=Path(os.environ.get('KIRA_REMOTE_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'KiraLive2DRemote')))

class InputDialog(QDialog):
    result=Signal(bool,str,str)
    def __init__(self,controller):
        super().__init__();self.controller=controller;self.setWindowTitle('Kira 桌宠 · 输入')
        self.setStyleSheet(STYLE);self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        surface(self)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose,False)
        layout=QFormLayout(self);layout.setContentsMargins(22,20,22,20);layout.setSpacing(14)
        self.text=QPlainTextEdit();self.text.setPlaceholderText('输入消息…')
        self.status=QLabel('');self.status.setWordWrap(True);self.send=QPushButton('发送')
        self.send.setObjectName('primary')
        layout.addRow(self.text);layout.addRow(self.status);layout.addRow(self.send)
        self.send.clicked.connect(self.submit);self.result.connect(self.sent);self.resize(460,210)
    def submit(self):
        text=self.text.toPlainText().strip()
        if not text:return
        self.send.setEnabled(False);url,key=self.controller.address,self.controller.key
        def work():
            wire=self.controller.network
            try:
                wire.request('/input',{'mode':'desktop'})
                wire.request('/message',{'text':text,'request_id':'remote-'+uuid.uuid4().hex})
                self.result.emit(True,'已发送',text)
            except Exception as exc:self.result.emit(False,'发送未完成：'+str(exc),text)
            finally:pass
        threading.Thread(target=work,daemon=True).start()
    def sent(self,ok,message,text):
        self.send.setEnabled(True);self.status.setText(message)
        if ok and self.text.toPlainText().strip()==text:self.text.clear()

class Controller(QDialog):
    prepared=Signal(dict)
    progress=Signal(str)
    offline=Signal(object,str)
    def __init__(self):
        super().__init__();ROOT.mkdir(parents=True,exist_ok=True)
        self.setWindowTitle('Kira Live2D · 远程连接');self.setStyleSheet(STYLE)
        surface(self)
        self.setFont(QFont('Microsoft YaHei UI',10));self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose,False)
        self.worker_stop=None;self.window=None;self.network=None;self.thread=None
        self.client_id=uuid.uuid4().hex;self.address='';self.key='';self.input=InputDialog(self)
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(188)
        navigation=QVBoxLayout(sidebar);navigation.setContentsMargins(16,28,16,20);navigation.setSpacing(6)
        brand=QLabel('Kira Live2D');brand.setObjectName('brand');navigation.addWidget(brand)
        caption=QLabel('独立端设置');caption.setObjectName('caption');navigation.addWidget(caption);navigation.addSpacing(24)
        pages=QStackedWidget();group=QButtonGroup(self);group.setExclusive(True)
        for index,title in enumerate(('连接设置','桌宠互动')):
            button=QPushButton(title);button.setObjectName('navigation');button.setCheckable(True);button.setChecked(index==0)
            group.addButton(button);navigation.addWidget(button);button.clicked.connect(lambda checked=False,i=index:pages.setCurrentIndex(i))
        navigation.addStretch();note=QLabel('由独立端连接 KiraAI');note.setObjectName('caption');navigation.addWidget(note)
        layout.addWidget(sidebar);layout.addWidget(pages,1)
        connection=QWidget();connection.setObjectName('settingsPage');form=QVBoxLayout(connection);form.setContentsMargins(30,28,30,28);form.setSpacing(14)
        heading=QLabel('连接设置');heading.setObjectName('headline');form.addWidget(heading)
        description=QLabel('连接电脑上的 KiraAI，同步模型与桌宠互动。');description.setObjectName('caption');description.setWordWrap(True);form.addWidget(description);form.addSpacing(8)
        self.address_field=QLineEdit();self.address_field.setPlaceholderText('http://KiraAI电脑IP:18765')
        self.key_field=QLineEdit();self.key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.status=QLabel('填写插件设置页提供的地址与访问密钥。');self.status.setWordWrap(True)
        self.connect_button=QPushButton('连接');self.disconnect_button=QPushButton('断开');self.chat_button=QPushButton('打开输入窗口')
        self.connect_button.setObjectName('primary')
        for title,description,field in (('连接地址','填写运行 KiraAI 的电脑地址',self.address_field),('访问密钥','与插件远程连接设置中的密钥一致',self.key_field)):
            card=QFrame();card.setObjectName('settingsCard');row=QVBoxLayout(card);row.setContentsMargins(18,14,18,16);row.setSpacing(7)
            label=QLabel(title);label.setObjectName('section');row.addWidget(label)
            hint=QLabel(description);hint.setObjectName('caption');hint.setWordWrap(True);row.addWidget(hint);row.addWidget(field);form.addWidget(card)
        self.status.setMinimumHeight(34);form.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(self.disconnect_button);actions.addWidget(self.connect_button);form.addLayout(actions);form.addStretch()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(connection);pages.addWidget(scroll)
        interaction=QWidget();interaction.setObjectName('settingsPage');tools=QVBoxLayout(interaction);tools.setContentsMargins(30,28,30,28);tools.setSpacing(16)
        heading=QLabel('桌宠互动');heading.setObjectName('headline');tools.addWidget(heading)
        card=QFrame();card.setObjectName('settingsCard');cardLayout=QVBoxLayout(card);cardLayout.setContentsMargins(18,18,18,18)
        hint=QLabel('连接后可打开独立输入窗口。模型的右键菜单、换装、位置调整和互动方式保持不变。');hint.setWordWrap(True);cardLayout.addWidget(hint);cardLayout.addSpacing(12);cardLayout.addWidget(self.chat_button);tools.addWidget(card);tools.addStretch();pages.addWidget(interaction)
        self.connect_button.clicked.connect(self.connect_remote);self.disconnect_button.clicked.connect(self.disconnect_remote)
        self.chat_button.clicked.connect(self.input.show);self.prepared.connect(self.load_model);self.progress.connect(self.status.setText);self.offline.connect(self.connection_offline)
        try:
            data=json.loads((ROOT/'connection.json').read_text(encoding='utf-8'))
            self.address_field.setText(data.get('url',''));self.key_field.setText(data.get('token',''))
        except (OSError,ValueError,TypeError):pass
        self.resize(800,570);self.setMinimumSize(660,460)
    def connect_remote(self):
        self.disconnect_remote()
        self.address=self.address_field.text().strip().rstrip('/');self.key=self.key_field.text().strip()
        from urllib.parse import urlsplit
        parsed=urlsplit(self.address)
        if parsed.scheme not in ('http','https') or not parsed.hostname or not self.key:
            self.status.setText('请填写有效的 HTTP/HTTPS 地址和访问密钥');return
        (ROOT/'connection.json').write_text(json.dumps({'url':self.address,'token':self.key}),encoding='utf-8')
        self.client_id=uuid.uuid4().hex
        stop=threading.Event();self.worker_stop=stop
        self.connect_button.setEnabled(False);self.status.setText('正在连接并同步模型…')
        self.thread=threading.Thread(target=self.monitor,args=(stop,self.address,self.key,self.client_id),daemon=True);self.thread.start()
    def monitor(self,stop,address,key,client_id):
        wire=Network({'url':address,'token':key});previous=None
        try:
            while not stop.is_set():
                try:
                    started=time.time();active=self.network if self.network and self.network.config.get('client_id')==client_id and self.network.socket is not None else wire;meta=active.request('/native/connect',{'client_id':client_id})
                    clock_offset=meta.get('server_time',time.time())-(started+time.time())/2
                    if meta.get('protocol')!=1:raise ValueError('远程壳版本不兼容，请下载更新的远程壳')
                    for field,length in (('generation',32),('bundle_hash',64)):
                        if not isinstance(meta.get(field),str) or len(meta[field])!=length or any(c not in '0123456789abcdef' for c in meta[field]):raise ValueError('远程连接信息无效')
                    if meta['bundle_url']!='/native/model/'+meta['bundle_hash'] or not isinstance(meta.get('key'),str) or len(meta['key'])>96 or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in meta['key']):raise ValueError('远程模型信息无效')
                    stamp=(meta['generation'],meta['bundle_hash'])
                    if stamp!=previous:
                        self.progress.emit('正在下载或校验当前模型…')
                        archive=ROOT/(meta['bundle_hash']+'.zip')
                        if not archive.is_file() or self.digest(archive)!=meta['bundle_hash']:
                            temporary=archive.with_suffix('.'+client_id+'.download')
                            request=urllib.request.Request(address+meta['bundle_url'],headers={'Authorization':'Bearer '+key})
                            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                            with opener.open(request,timeout=60) as response,temporary.open('wb') as dest:
                                total=0
                                while chunk:=response.read(1024*1024):
                                    if stop.is_set():return
                                    total+=len(chunk)
                                    if total>MAX_SIZE:raise ValueError('模型下载过大')
                                    dest.write(chunk)
                            if self.digest(temporary)!=meta['bundle_hash']:raise ValueError('模型下载校验失败，请重新连接')
                            temporary.replace(archive)
                        if stop.is_set():return
                        model,aliases=unpack_model_bundle(archive,ROOT/'models'/meta['bundle_hash'])
                        preferences=ROOT/'preferences'/meta['key'];preferences.mkdir(parents=True,exist_ok=True)
                        config={'url':address,'token':key,'generation':meta['generation'],'key':meta['key'],'id':0,
                            'client_id':client_id,'model':model,'preferences':str(preferences/'window.json'),
                            'remote_motion_paths':aliases,'remote_managed':True,'audio_cache':str(ROOT/'audio'),
                            'clock_offset':clock_offset,'monitor_id':id(stop)}
                        if stop.is_set():return
                        self.prepared.emit(config);previous=stamp
                    stop.wait(3)
                except Exception as exc:
                    if stop.is_set():return
                    if any(code in str(exc) for code in ('HTTP 401','HTTP 404','HTTP 409')):
                        previous=None;self.offline.emit(stop,'远程模式未开启、密钥无效或已有其他壳连接；正在等待恢复')
                    self.progress.emit('连接暂未就绪：'+str(exc)+'；正在重试');stop.wait(3)
        finally:
            try:wire.request('/native/disconnect',{'client_id':client_id})
            except Exception:pass
            wire.close_transport()
    @staticmethod
    def digest(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as data:
            while chunk:=data.read(1024*1024):h.update(chunk)
        return h.hexdigest()
    def load_model(self,config):
        if self.worker_stop is None or self.worker_stop.is_set() or config['monitor_id']!=id(self.worker_stop):return
        self.retire_window()
        self.network=Network(config);self.window=Window(config,self.network)
        self.network.command.connect(self.window.command);self.window.remote_input_requested.connect(self.input.show)
        self.window.remote_closed.connect(self.model_closed)
        self.window.show();threading.Thread(target=self.network.run,daemon=True).start()
        self.status.setText('模型已同步；右键模型可调试或打开输入窗口')
    def connection_offline(self,stop,message):
        if stop is not self.worker_stop:return
        if self.network:self.network.stopped.set()
        self.retire_window();self.input.hide();self.status.setText(message)

    def model_closed(self,server_requested):
        if server_requested:
            old=self.window;self.window=None;self.input.hide()
            if old:self.release_window(old)
        else:self.disconnect_remote();self.show()
    def release_window(self,old):
        old.makeCurrent();old.model=None;live2d.glRelease();old.doneCurrent();old.deleteLater()
    def retire_window(self):
        old=self.window;self.window=None
        if old:
            old.remote_server_shutdown=True;old.close()
            self.release_window(old)

    def disconnect_remote(self):
        if self.worker_stop:self.worker_stop.set();self.worker_stop=None
        if self.network:self.network.stopped.set()
        self.retire_window()
        self.connect_button.setEnabled(True);self.status.setText('已断开，可修改连接信息')
    def closeEvent(self,event):
        self.disconnect_remote();self.input.close();event.accept();QApplication.quit()

def main():
    print('[启动] 正在初始化连接窗口…',flush=True)
    fmt=QSurfaceFormat();fmt.setAlphaBufferSize(8);fmt.setDepthBufferSize(24);fmt.setStencilBufferSize(8);fmt.setVersion(2,1)
    QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);install(app);live2d.init();live2d.setLogLevel(2)
    controller=Controller();controller.show();controller.raise_();controller.activateWindow()
    print(f'[启动] 窗口平台：{app.platformName()}；窗口句柄：{int(controller.winId())}；可见：{controller.isVisible()}',flush=True)
    QTimer.singleShot(1000,lambda: print(f'[启动] 窗口状态：可见={controller.isVisible()}，位置={controller.geometry().getRect()}',flush=True))
    faulthandler.cancel_dump_traceback_later()
    print('[启动] 连接窗口已显示',flush=True)
    app.exec();live2d.dispose()
if __name__=='__main__':main()
