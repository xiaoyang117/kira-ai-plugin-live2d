"""Native Qt/OpenGL window. Runs only in the isolated rendering process."""
import argparse
import ctypes
import json
import math
from pathlib import Path
import queue
import sys
import threading
import time
import http.client
import urllib.parse

from PySide6.QtCore import Qt,QTimer,Signal,QObject,QPointF,QRectF,QLocale
from PySide6.QtGui import QSurfaceFormat,QAction,QIcon,QPixmap,QColor,QPainter,QPen,QPolygonF,QCursor,QFont,QBitmap,QRegion
from PySide6.QtWidgets import QApplication,QMenu,QSystemTrayIcon,QToolTip,QDialog,QFormLayout,QSpinBox,QLabel,QPushButton,QComboBox,QScrollArea,QVBoxLayout,QWidget
from PySide6.QtOpenGLWidgets import QOpenGLWidget
import live2d
from behavior import DragGesture,project_vertices,MouseGaze
from win_input import PassthroughMenuHook
from part_motion import PartMotion
from speech_bubble import SpeechBubble
from socket_wire import SocketWire,RPC_PATHS
from glass_theme import install,surface

class Network(QObject,SocketWire):
    command=Signal(dict)
    def __init__(self,config):
        super().__init__();self.config=config;self.outgoing=queue.Queue();self.stopped=threading.Event();self.render_ready=False;self.last_ready_report=0
        self.transport=threading.local();self.init_socket()
    def post(self,data):
        if data.get('ready') is True:self.render_ready=True
        if data.get('error') and 'msgId' not in data:self.render_ready=False
        self.outgoing.put(data)
    def request(self,path,data=None,*,binary=False):
        if not binary and self.socket is not None and path.split("?",1)[0] in RPC_PATHS:return self.socket_rpc(path,data)
        generation=self.config.get('generation')
        if generation:
            if data is None:path+='?generation='+generation
            else:data={**data,'generation':generation}
        peer=self.config.get('client_id')
        if peer:
            if data is None:path+=('&' if '?' in path else '?')+'client_id='+peer
            else:data={**data,'client_id':peer}
        body=json.dumps(data).encode() if data is not None else None
        url=urllib.parse.urlsplit(self.config['url'])
        connection=getattr(self.transport,'connection',None)
        if connection is None:
            cls=http.client.HTTPSConnection if url.scheme=='https' else http.client.HTTPConnection
            connection=cls(url.hostname,url.port,timeout=5)
            self.transport.connection=connection
        try:
            connection.request('POST' if body is not None else 'GET',url.path.rstrip('/')+path,body=body,headers={
                'Authorization':'Bearer '+self.config['token'],'Content-Type':'application/json'})
            response=connection.getresponse();content=response.read(64*1024*1024+1)
            if len(content)>64*1024*1024:raise ValueError('远程响应过大')
            if response.will_close:self.close_transport()
            if response.status>=400:raise ConnectionError('原生接口返回 HTTP '+str(response.status))
            return content if binary else json.loads(content)
        except Exception:
            # Do not replay POST requests: an interaction may already be accepted.
            self.close_transport();raise

    def close_transport(self):
        connection=getattr(self.transport,'connection',None)
        if connection is not None:connection.close();self.transport.connection=None

    def run(self):
        self.run_socket()

class Window(QOpenGLWidget):
    remote_closed=Signal(bool)
    remote_input_requested=Signal()
    def __init__(self,config,network,smoke=None):
        super().__init__();self.config=config;self.network=network;self.smoke=smoke
        self.model=None;self.ready=False;self.drag_start=None;self.moving=False
        self.debug=False;self.debug_dialog=None;self.drag=None;self.drag_started=False;self.held={};self.held_initial={};self.drag_returns={};self.drag_restore=None;self.parameter_preview=None
        self.alpha_mask=None;self.last_mask=0;self.input_transparent=False;self.debug_shapes=[];self.last_debug_shape=0
        self.gaze=MouseGaze();self.gaze_anchor=None;self.gaze_radius=None;self.gaze_values=(0.,0.)
        self.part_motion=None;self.native_motion_refs={};self.wardrobe=[];self.extra_motions={};self.voice_started=0;self.bubble_until=0
        self.voice_envelope={};self.text_lip_until=0;self.mouth_value=0.;self.mouth_ids=[]
        self.setWindowTitle('Kira Live2D 独立桌宠')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True);self.resize(450,650)
        area=QApplication.primaryScreen().availableGeometry()
        self.move(area.right()-self.width()-35,area.bottom()-self.height())
        self.preferences=Path(config.get('preferences',Path(config['model']['path']).parent/'window.json'))
        try:
            geometry=json.loads(self.preferences.read_text(encoding='utf-8'))
            w=max(200,min(1200,int(geometry['w'])));h=round(w*650/450)
            self.resize(w,h)
            x=max(area.left(),min(area.right()-w,int(geometry['x'])))
            y=max(area.top(),min(area.bottom()-h,int(geometry['y'])))
            self.move(x,y)
        except (OSError,ValueError,KeyError,TypeError):pass
        self.frame_pending=True;self.last_animation_time=None
        self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer);self.timer.timeout.connect(self.advance_frame)
        self.timer.start(33)
        self.tray=QSystemTrayIcon(self)
        icon=QPixmap(32,32);icon.fill(QColor('#7261dc'));self.tray.setIcon(QIcon(icon))
        menu=QMenu()
        menu.addAction('打开输入窗口',self.open_input)
        self.pass_action=menu.addAction('鼠标穿透');self.pass_action.setCheckable(True)
        self.passthrough_menu=PassthroughMenuHook(self.passthrough_menu_point,
            lambda point:QTimer.singleShot(0,lambda:self.show_passthrough_menu(point)))
        self.pass_action.toggled.connect(self.passthrough)
        menu.addAction('调试：位置、大小与交互框',lambda:self.set_debug(True))
        menu.addAction('恢复默认大小',lambda:self.set_geometry(self.x(),self.y(),450))
        menu.addAction('关闭桌宠',self.close)
        self.tray.setContextMenu(menu);self.tray.setToolTip('Kira Live2D · 透明处自动穿透；右键或托盘打开调试')
        self.tray.show()
        self.speech_bubble=SpeechBubble(self)
        self.input_timer=QTimer(self);self.input_timer.timeout.connect(self.update_input_region);self.input_timer.start(25)
    def advance_frame(self):
        # Qt can repaint for framebuffer reads, exposure and composition as well as
        # our animation timer. Only timer frames may advance SDK/physics state.
        self.frame_pending=True
        self.update()

    def passthrough(self,on):
        if on and not self.passthrough_menu.start():
            self.pass_action.setChecked(False)
            QToolTip.showText(QCursor.pos(),'无法启用右键菜单保护，未开启鼠标穿透')
            return
        if not on:self.passthrough_menu.stop()
        self.update_input_region()
    def passthrough_menu_point(self):
        if (not self.ready or not self.isVisible() or not self.pass_action.isChecked()
                or self.debug or QApplication.activePopupWidget() is not None):return None
        point=QCursor.pos();local=self.mapFromGlobal(point)
        image=self.alpha_mask
        if image is None or image.isNull() or not (0<=local.x()<self.width() and 0<=local.y()<self.height()):return None
        x=min(image.width()-1,int(local.x()*image.width()/max(1,self.width())))
        y=min(image.height()-1,int(local.y()*image.height()/max(1,self.height())))
        return point if image.pixelColor(x,y).alpha()>12 else None
    def show_passthrough_menu(self,point):
        if self.ready and self.isVisible() and self.pass_action.isChecked():
            self.tray.contextMenu().popup(point)
    def set_input_transparent(self,on):
        if self.input_transparent==on:return
        user32=ctypes.windll.user32;handle=int(self.winId())
        style=user32.GetWindowLongW(handle,-20)
        user32.SetWindowLongW(handle,-20,style|0x20 if on else style & ~0x20)
        self.input_transparent=on
    def update_input_region(self):
        if not self.ready:return
        # Use rendered alpha, so large invisible hit meshes never swallow clicks.
        # Refresh away from paintGL to avoid recursive rendering.
        if not self.debug and time.monotonic()-self.last_mask>.15:
            self.last_mask=time.monotonic();self.alpha_mask=self.grabFramebuffer()
            if self.gaze_anchor is None:self.locate_gaze_anchor()
        cursor=self.mapFromGlobal(QCursor.pos())
        inside=0<=cursor.x()<self.width() and 0<=cursor.y()<self.height()
        visible=True
        if inside and self.alpha_mask is not None and not self.alpha_mask.isNull():
            image=self.alpha_mask
            px=min(image.width()-1,int(cursor.x()*image.width()/max(1,self.width())))
            py=min(image.height()-1,int(cursor.y()*image.height()/max(1,self.height())))
            visible=image.pixelColor(px,py).alpha()>12
        locked=self.drag_start is not None or self.debug
        self.set_input_transparent(self.pass_action.isChecked() or (not locked and (not inside or not visible)))
    def locate_gaze_anchor(self):
        image=self.alpha_mask
        if image is None or image.isNull():return
        rect=QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
        if rect.isEmpty():return
        sx=self.width()/image.width();sy=self.height()/image.height()
        self.gaze_anchor=(rect.center().x()*sx,(rect.top()+rect.height()*.18)*sy)
        self.gaze_radius=(max(self.width()*.8,rect.width()*sx*2),max(self.height()*.5,rect.height()*sy*.6))
        # Prefer an explicitly declared head/face hit mesh when available.
        ids=self.model.GetDrawableIds()
        for area in self.config['model']['hit_areas']:
            name=area.get('Name','').casefold()
            ident=area.get('Id','')
            if not any(word in name for word in ('head','face','头','脸')) or ident not in ids:continue
            points=project_vertices(self.model.GetDrawableVertices(ids.index(ident)),self.model.GetMvp(),self.width(),self.height())
            if points:
                xs,ys=zip(*points)
                self.gaze_anchor=((min(xs)+max(xs))*.5,(min(ys)+max(ys))*.5)
                break

    def update_gaze(self,delta):
        cursor=self.mapFromGlobal(QCursor.pos())
        anchor=self.gaze_anchor or (self.width()*.5,self.height()*.25)
        radius=self.gaze_radius or (self.width()*.8,self.height()*.5)
        enabled=self.isVisible() and not (self.debug or self.drag_start is not None or self.parameter_preview or self.drag_returns)
        x,y=self.gaze.step(cursor.x(),cursor.y(),anchor,radius,delta,enabled)
        self.gaze_values=(x,y)
        size=min(self.width(),self.height())
        # SDK Drag converts window pixels into scene-space: supply a small virtual
        # displacement around scene center, rather than raw desktop coordinates.
        self.model.Drag(self.width()*.5+size*.20*x,self.height()*.5-size*.15*y)

    def open_input(self):
        if self.config.get('remote_managed'):self.remote_input_requested.emit()
        else:self.network.post({'open_input':True})

    def update_gaze_eyes(self):
        # Eyes respond a little more than the head, without exaggerated body sway.
        for names,value in [(('ParamEyeBallX','PARAM_EYE_BALL_X'),self.gaze_values[0]),
                            (('ParamEyeBallY','PARAM_EYE_BALL_Y'),self.gaze_values[1])]:
            for ident in names:
                if ident in self.parameters:
                    self.model.SetParamById(ident,self.model.GetParamValueById(ident)+value*.25)
                    break

    def save_geometry(self):
        try:self.preferences.write_text(json.dumps({'x':self.x(),'y':self.y(),'w':self.width(),'h':self.height()}),encoding='utf-8')
        except OSError:pass
    def set_geometry(self,x,y,width):
        width=max(200,min(1200,int(width)));height=round(width*650/450)
        area=self.screen().availableGeometry()
        self.resize(width,height)
        self.move(max(area.left()-width+60,min(area.right()-60,int(x))),max(area.top(),min(area.bottom()-60,int(y))))
        self.alpha_mask=None;self.save_geometry()
    def set_debug(self,on):
        self.debug=bool(on)
        self.speech_bubble.set_debug(self.debug)
        if self.debug:
            self.pass_action.setChecked(False);self.set_input_transparent(False)
            if self.debug_dialog is None:self.debug_dialog=DebugPanel(self)
            self.debug_dialog.sync();self.debug_dialog.show();self.debug_dialog.raise_()
        elif self.debug_dialog:self.debug_dialog.hide()
        self.network.post({'debug':self.debug});self.update()
    def source_hit(self,source,x,y):
        area=source['area']
        for entry in self.config['model']['hit_areas']:
            if area in (entry.get('Name'),entry.get('Id')):
                return self.model.IsAreaHit(entry.get('Name',''),x,y)
        ids=self.model.GetDrawableIds()
        return area in ids and self.model.IsDrawableHit(ids.index(area),x,y)
    def drag_event(self,phase):
        if self.drag is None:return
        packet=self.drag.packet(phase)
        if self.debug:
            if self.debug_dialog:self.debug_dialog.event_label.setText(self.drag.source['name']+' / '+self.drag.source['parameter']+' / '+phase+' = '+str(round(self.drag.value,3)))
        else:self.network.post({'drag':packet,'key':self.config['key']})
    def update_parameter_overrides(self):
        for ident,state in list(self.drag_returns.items()):
            if self.drag is not None and self.drag.source['parameter']==ident:
                continue
            progress=max(0.,min(1.,(time.monotonic()-state['start'])/.35))
            value=state['target']+(state['from']-state['target'])*(1-progress)**3
            self.model.SetParamById(ident,value)
            if progress>=1:
                self.model.SetSaveParamById(ident,state['target'])
                self.drag_returns.pop(ident,None);self.held_initial.pop(ident,None)
        if self.parameter_preview:
            state=self.parameter_preview;elapsed=time.monotonic()-state['start']
            low=state['min'];high=state['max']
            if elapsed<.5:value=low
            elif elapsed<2.5:value=low+(high-low)*(elapsed-.5)/2
            elif elapsed<3:value=high
            else:
                value=state['original'];self.parameter_preview=None
                self.network.post({'preview':{'nonce':state['nonce'],'stage':'done','message':'预览完成，已恢复原值'}})
            self.model.SetParamById(state['parameter'],value)
            # Restore the saved parameter too: Update loads it again next frame.
            if self.parameter_preview is None:self.model.SetSaveParamById(state['parameter'],value)
        for ident,value in self.held.items():self.model.SetParamById(ident,value)
        if self.drag:self.model.SetParamById(self.drag.source['parameter'],self.drag.value)
    def draw_debug(self):
        # Same MVP and drawable vertices as the SDK, in logical window pixels.
        if time.monotonic()-self.last_debug_shape>.1:
            self.last_debug_shape=time.monotonic();self.debug_shapes=[]
            ids=self.model.GetDrawableIds();matrix=self.model.GetMvp()
            rows=[(a.get('Id',''),a.get('Name',''),'touch') for a in self.config['model']['hit_areas']]
            rows.extend((c['area'],c['name']+' / '+c['parameter'],'drag') for c in self.config['model'].get('drag_candidates',[]))
            seen=set()
            for ident,label,kind in rows:
                if ident not in ids or (ident,label) in seen:continue
                seen.add((ident,label));points=project_vertices(self.model.GetDrawableVertices(ids.index(ident)),matrix,self.width(),self.height())
                if points:
                    xs,ys=zip(*points);self.debug_shapes.append((ident,label,kind,QRectF(min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys))))
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),QColor(38,43,61,28))
        painter.setPen(QPen(QColor('#b5a8ff'),2));painter.drawRect(self.rect().adjusted(1,1,-2,-2))
        selected=self.debug_dialog.sources.currentData() if self.debug_dialog else ''
        for ident,label,kind,rect in self.debug_shapes:
            if selected and ident!=selected:continue
            painter.setPen(QPen(QColor('#ffbb44') if kind=='drag' else QColor('#54e7b6'),2))
            painter.drawRect(rect)
            if selected:painter.drawText(QPointF(12,46),label+' ['+ident+']')
        painter.setPen(QColor('white'));painter.drawText(12,22,'调试模式 · 拖空白移动 · 滚轮缩放 · 关闭面板退出')
        painter.end()
    def initializeGL(self):
        try:
            live2d.glInit();self.model=live2d.Model()
            print('正在加载原生模型：',self.config['model']['path'],flush=True)
            self.model.LoadModelJson(Path(self.config['model']['path']).as_posix())
            print('原生模型已加载',flush=True)
            native_data=json.loads(Path(self.config['model']['path']).read_text(encoding='utf-8-sig'))['FileReferences']
            self.native_motion_refs=native_data.get('Motions',{})
            if not native_data.get('Pose'):
                self.part_motion=PartMotion(self.model.GetPartIds(),self.config['model'].get('initial_parts',{}))
            parts={ident:index for index,ident in enumerate(self.model.GetPartIds())}
            for ident,opacity in self.config['model'].get('initial_parts',{}).items():
                if ident in parts:self.model.SetPartOpacity(parts[ident],opacity)
            self.model.Resize(self.width(),self.height())
            self.model.SetAutoBlink(True)
            self.parameters=set(self.model.GetParamIds())
            settings=json.loads(Path(self.config['model']['path']).read_text(encoding='utf-8-sig'))
            self.mouth_ids=list(dict.fromkeys(ident for group in settings.get('Groups',[]) if group.get('Name')=='LipSync' for ident in group.get('Ids',[]) if ident in self.parameters))
            if not self.mouth_ids:self.mouth_ids=[ident for ident in ('ParamMouthOpenY','PARAM_MOUTH_OPEN_Y') if ident in self.parameters]
            self.idle_group=next((name for name,count in self.model.GetMotionGroups().items() if count and name.casefold() in ('idle','standby')),None)
            # Breathing is disabled, including SDK-generated head/body sway.
            # Keep other authored idle behavior and blinking available.
            self.model.SetAutoBreath(False)
            print('待机动作组：',self.idle_group or '无','呼吸效果：关闭',flush=True)
            self.expression_parameters=[]
            base=Path(self.config['model']['path']).parent
            for entry in self.config['model']['expressions']:
                self.expression_parameters.append(json.loads((base/entry['File']).read_text(encoding='utf-8-sig'))['Parameters'])
        except Exception as exc:self.fail(exc)
    def fail(self,exc):
        print('原生渲染异常：',repr(exc),flush=True)
        self.timer.stop();self.network.post({'error':str(exc)})
        QToolTip.showText(self.pos(),'模型加载失败：'+str(exc))
        if self.smoke:QApplication.exit(2)
    def resizeGL(self,w,h):
        self.gaze_anchor=None;self.gaze_radius=None
        print('模型窗口尺寸已调整：',w,h,'调试模式：','开启' if self.debug else '关闭',flush=True)
        if self.model:self.model.Resize(w,h)
    def paintGL(self):
        if not self.model:return
        try:
            live2d.clearBuffer()
            if self.frame_pending:
                self.frame_pending=False
                if self.idle_group and self.model.IsMotionFinished():
                    self.model.StartMotion(self.idle_group,0,1)
                    if self.part_motion:
                        entry=self.native_motion_refs[self.idle_group][0]
                        self.part_motion.start(Path(self.config['model']['path']).parent/entry['File'])
                now=time.monotonic()
                delta=1/30 if self.last_animation_time is None else max(.001,min(.1,now-self.last_animation_time))
                self.last_animation_time=now
                self.update_gaze(delta)
                self.model.Update(delta)
                if self.part_motion:
                    self.part_motion.advance(delta);self.part_motion.apply(self.model)
                self.update_gaze_eyes()
                for index in self.wardrobe:
                    for item in self.expression_parameters[index]:
                        ident=item.get('Id');value=float(item.get('Value',0))
                        if ident not in self.parameters:continue
                        blend=item.get('Blend','Add')
                        if blend=='Add':value+=self.model.GetParamDefaultById(ident)
                        elif blend=='Multiply':value*=self.model.GetParamDefaultById(ident)
                        self.model.SetParamById(ident,value)
                mouth=-1.
                if self.voice_started:
                    buffer=ctypes.create_unicode_buffer(64)
                    ctypes.windll.winmm.mciSendStringW('status kira_voice mode',buffer,64,None)
                    if buffer.value=='playing':
                        levels=self.voice_envelope.get('levels',[])
                        if levels:
                            ctypes.windll.winmm.mciSendStringW('status kira_voice position',buffer,64,None)
                            index=int(buffer.value or 0)//max(10,int(self.voice_envelope.get('step_ms',40)))
                            mouth=float(levels[index]) if index<len(levels) else 0.
                        else:mouth=.15+.45*abs(math.sin((now-self.voice_started)*13))
                    else:self.voice_started=0
                elif now<self.text_lip_until:mouth=0. if now%1.1>.9 else .18+.43*abs(math.sin(now*12))
                animate=mouth>=0 or self.mouth_value>.005
                self.mouth_value+=(max(0.,mouth)-self.mouth_value)*(1-math.exp(-delta/.055))
                if animate:
                    for ident in self.mouth_ids:
                        rest=self.model.GetParamDefaultById(ident);maximum=self.model.GetParamMaxById(ident)
                        self.model.SetParamById(ident,rest+(maximum-rest)*min(1,self.mouth_value))
                self.update_parameter_overrides()
            self.model.Draw()
            if self.debug:self.draw_debug()
            if not self.ready:
                self.ready=True;self.network.post({'ready':True})
                if self.smoke:QTimer.singleShot(1800,self.finish_smoke)
        except Exception as exc:self.fail(exc)
    def finish_smoke(self):
        try:
            self.grabFramebuffer().save(self.smoke)
            print('原生渲染测试通过 NATIVE_SMOKE_OK',self.model.GetParamCount(),len(self.model.GetExpressions()),flush=True)
            if len(self.expression_parameters)>6:
                self.expression(6)
                QTimer.singleShot(450,self.smoke_expression)
            else:self.close()
        except Exception as exc:print('原生渲染测试失败 SMOKE_FAILED',repr(exc),flush=True);QApplication.exit(2)
    def smoke_expression(self):
        self.grabFramebuffer().save(str(Path(self.smoke).with_stem('native-expression')))
        self.model.ResetExpressions()
        paths=list(self.config['model'].get('motion_files',{}))
        if paths:
            self.play_file(Path(paths[0]))
            QTimer.singleShot(500,self.smoke_motion)
        else:self.close()
    def smoke_motion(self):
        self.grabFramebuffer().save(str(Path(self.smoke).with_stem('native-motion')))
        print('原生动作测试通过 NATIVE_ACTION_SMOKE_OK',flush=True)
        self.close()
    def expression(self,index):
        index=int(index)
        if not 0<=index<len(self.expression_parameters):raise ValueError('表情编号无效')
        self.model.SetExpression(str(index))
    def motion(self,spec):
        target=spec.get('mtn','')
        if spec.get('type')==1:target=self.config.get('remote_motion_paths',{}).get(target,target)
        if spec.get('type')==1:
            path=Path(target).resolve()
            source=Path(self.config['model']['original']).parent
            if not path.is_relative_to(source) or not path.is_file():raise ValueError('动作文件不存在或不属于当前模型')
            self.play_file(path);return
        group,sep,name=target.partition(':')
        rows=self.config['model']['motion_entries'].get(group,[])
        entries=[r for r in rows if isinstance(r,dict) and (not sep or r.get('Name',r.get('name'))==name)]
        if not entries:raise ValueError('动作事件不存在：'+target)
        item=entries[0];used=False
        expression=item.get('Expression',item.get('expression'))
        if expression in self.config['model']['expression_names']:
            self.expression(self.config['model']['expression_names'][expression]);used=True
        if item.get('File'):
            path=(Path(self.config['model']['original']).parent/item['File']).resolve()
            self.play_file(path);used=True
        if not used:raise ValueError('此事件没有可播放的动作或表情')
    def play_file(self,path):
        source=Path(self.config['model']['original']).parent
        if not path.is_relative_to(source) or not path.is_file():raise ValueError('动作文件不属于当前模型')
        key=str(path)
        if key not in self.extra_motions:
            group='KiraMotion'+str(len(self.extra_motions));staged=self.config['model']['motion_files'].get(key)
            if not staged:raise ValueError('动作文件未载入独立壳，请重新识别模型并保存')
            index=self.model.LoadExtraMotion(group,Path(staged).as_posix())
            self.extra_motions[key]=(group,index)
        group,index=self.extra_motions[key];self.model.StartMotion(group,index,3)
        if self.part_motion:self.part_motion.start(self.config['model']['motion_files'][key])
    def audio_stop(self):
        ctypes.windll.winmm.mciSendStringW('close kira_voice',None,0,None);self.voice_started=0
    def command(self,packet):
        if packet['msg']=='quit':self.remote_server_shutdown=True;self.close();return
        result={};error=None
        try:
            if packet.get('expires',time.time()+self.config.get('clock_offset',0)+1)<time.time()+self.config.get('clock_offset',0):raise ValueError('控制请求已过期，未执行旧命令')
            if not self.ready:raise ValueError('模型仍在加载')
            command=packet['msg'];data=packet.get('data')
            if command==13300:self.expression(data['expId'])
            elif command==13302:self.model.ResetExpressions()
            elif command==13200:self.motion(data)
            elif command==11000:
                self.speech_bubble.show_message(data['text'],data.get('duration',5000))
                if not self.voice_started:self.text_lip_until=time.monotonic()+min(data.get('duration',5000)/1000,max(.8,min(18,len(data['text'])*.11+.5)))
            elif command==13501:self.audio_stop()
            elif command==13500:
                self.audio_stop();path=str(data['sound']);self.voice_envelope=data.get('lip_sync') or {};self.text_lip_until=0
                if data.get('type')!=0 or '"' in path or not Path(path).is_file():raise ValueError('独立壳音频文件无效')
                status=ctypes.windll.winmm.mciSendStringW('open "'+path+'" alias kira_voice',None,0,None)
                if status:raise ValueError('音频格式不受 Windows 播放器支持')
                ctypes.windll.winmm.mciSendStringW('set kira_voice time format milliseconds',None,0,None)
                ctypes.windll.winmm.mciSendStringW('play kira_voice',None,0,None);self.voice_started=time.monotonic()
            elif command=='control':result=self.control(data)
            elif command=='remote_input':self.open_input()
            elif command==10000:pass
            else:raise ValueError('独立壳暂不支持此控制指令：'+str(command))
        except Exception as exc:error=str(exc)
        self.network.post({'msgId':packet.get('msgId'),'result':result,'error':error})
    def control(self,data):
        operation=data['operation']
        if operation=='debug':
            self.set_debug(data.get('enabled',True));return {'enabled':self.debug}
        if operation=='drag_preview':
            if self.drag or self.parameter_preview or self.drag_returns:raise ValueError('请等拖动回弹或预览结束')
            source=next((s for s in self.config['model'].get('drag_candidates',[]) if s['id']==data.get('source') and s['enabled']),None)
            if source is None or source['parameter'] not in self.parameters:raise ValueError('当前模型没有此拖动参数')
            ident=source['parameter']
            if ident in self.held:raise ValueError('请先释放此拖动参数再预览')
            self.parameter_preview={'parameter':ident,'start':time.monotonic(),'original':self.model.GetParamValueById(ident),'min':self.model.GetParamMinById(ident),'max':self.model.GetParamMaxById(ident),'nonce':data['nonce']}
            return {}
        if operation=='outfit':
            indices=data['expressions']
            if not isinstance(indices,list) or any(type(i)is not int or not 0<=i<len(self.expression_parameters) for i in indices):raise ValueError('换装表情无效')
            self.wardrobe=indices;return {}
        if operation in ('layout','inspect'):
            area=QApplication.primaryScreen().availableGeometry()
            if operation=='layout':
                if self.debug:raise ValueError('调试中，请关闭调试面板后再调整')
                if 'geometry' in data:
                    g=data['geometry'];self.resize(int(g['w']),int(g['h']));self.move(int(g['x']),int(g['y']))
                else:
                    old_w,old_h=self.width(),self.height()
                    old_x=(self.x()-area.x())/max(1,area.width()-old_w)*100
                    old_y=(self.y()-area.y())/max(1,area.height()-old_h)*100
                    factor=float(data.get('scale',self.width()/450*100))/100
                    self.resize(round(450*factor),round(650*factor))
                    self.move(round(area.x()+(area.width()-self.width())*float(data.get('x',old_x))/100),
                        round(area.y()+(area.height()-self.height())*float(data.get('y',old_y))/100))
            if operation=='layout':self.save_geometry()
            return {'x':self.x(),'y':self.y(),'w':self.width(),'h':self.height(),'scale':self.width()/450,'mouth':self.mouth_value,'mouth_parameters':len(self.mouth_ids)}
        raise ValueError('独立壳不支持此操作')
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:self.tray.contextMenu().exec(event.globalPosition().toPoint());return
        if event.button()!=Qt.MouseButton.LeftButton or not self.ready:return
        self.drag_start=event.globalPosition().toPoint();self.window_start=self.pos();self.moving=False;self.drag=None;self.drag_started=False
        x,y=event.position().x(),event.position().y()
        if not self.parameter_preview:
            for source in self.config['model'].get('drag_candidates',[]):
                if source['enabled'] and source['parameter'] in self.parameters and self.source_hit(source,x,y):
                    ident=source['parameter'];self.held.pop(ident,None)
                    self.drag=DragGesture(source,self.model.GetParamValueById(ident),self.model.GetParamMinById(ident),self.model.GetParamMaxById(ident),x,y)
                    prior=self.drag_returns.get(ident)
                    self.drag_restore=prior['target'] if prior else self.drag.start
                    self.held_initial[ident]=self.drag_restore;break
        alt=bool(event.modifiers()&Qt.KeyboardModifier.AltModifier)
        self.moving=alt or (self.debug and self.drag is None)
        if self.moving:self.drag=None
        self.set_input_transparent(False)
    def mouseMoveEvent(self,event):
        if self.moving and self.drag_start is not None:
            self.move(self.window_start+event.globalPosition().toPoint()-self.drag_start)
            if self.debug_dialog:self.debug_dialog.sync()
        elif self.drag:
            if not self.drag_started:
                if abs(event.position().x()-self.drag.x)+abs(event.position().y()-self.drag.y)<4:return
                self.drag_started=True;self.drag_event('begin')
            phase=self.drag.update(event.position().x(),event.position().y(),self.width()/450)
            if phase:self.drag_event(phase)
        # Gaze is updated from the global cursor on animation frames, including
        # transparent pixels and positions outside this window.
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        if self.drag:
            if self.drag_started:self.drag_event('end')
            ident=self.drag.source['parameter']
            target=self.drag_restore if self.drag_restore is not None else self.drag.start
            self.held.pop(ident,None)
            self.model.SetSaveParamById(ident,target)
            if abs(self.drag.value-target)>1e-6:
                self.drag_returns[ident]={'from':self.drag.value,'target':target,'start':time.monotonic()}
            else:
                self.drag_returns.pop(ident,None);self.held_initial.pop(ident,None)
        if not (self.drag and self.drag_started) and self.drag_start is not None and not self.moving and (event.globalPosition().toPoint()-self.drag_start).manhattanLength()<8 and self.ready:
            x,y=event.position().x(),event.position().y();area=''
            for candidate in self.config['model']['hit_areas']:
                if self.model.IsAreaHit(candidate.get('Name',''),x,y):area=candidate.get('Name','');break
            if not area:
                parts=self.model.HitPart(x,y,True)
                if parts:area=str(parts[0])
            if self.debug:
                if self.debug_dialog:self.debug_dialog.event_label.setText('点击：'+(area or '无命中区域'))
            elif area:self.network.post({'event':area})
        self.drag=None;self.drag_restore=None;self.drag_start=None;self.moving=False;self.save_geometry()
    def wheelEvent(self,event):
        # Ordinary scrolling must never resize the pet. Transparent pixels already
        # pass the original wheel event to the application underneath.
        if not self.debug:event.ignore();return
        factor=1.08 if event.angleDelta().y()>0 else 1/1.08
        self.set_geometry(self.x(),self.y(),round(self.width()*factor))
        if self.debug_dialog:self.debug_dialog.sync()
    def closeEvent(self,event):
        self.speech_bubble.close()
        self.passthrough_menu.stop();self.network.stopped.set();self.timer.stop();self.input_timer.stop();self.audio_stop();self.tray.hide()
        if self.debug_dialog:self.debug_dialog.hide()
        try:self.preferences.write_text(json.dumps({'x':self.x(),'y':self.y(),'w':self.width(),'h':self.height()}),encoding='utf-8')
        except OSError:pass
        event.accept()
        if self.config.get('remote_managed'):self.remote_closed.emit(bool(getattr(self,'remote_server_shutdown',False)))
        else:QApplication.quit()

class DebugPanel(QDialog):
    def __init__(self,window):
        super().__init__();self.window=window;self.syncing=False
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose,False)
        surface(self)
        self.setWindowTitle('Live2D 调试：位置、大小与交互框')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setFont(QFont('Microsoft YaHei UI',10))
        self.setStyleSheet("""
            QDialog { background:#202020; color:#ffffff; }
            QLabel { color:#d0d0d0; background:transparent; }
            QSpinBox, QComboBox {
                background:#333333; color:#ffffff; border:1px solid #454545;
                border-radius:4px; min-height:36px; padding:0 32px 0 10px;
                selection-background-color:#3e3e3e; selection-color:#ffffff;
            }
            QSpinBox:focus, QComboBox:focus { border-color:#60cdff; }
            QSpinBox::up-button, QSpinBox::down-button {
                subcontrol-origin:border; width:26px; background:#3a3a3a;
                border-left:1px solid #454545;
            }
            QSpinBox::up-button { subcontrol-position:top right; border-top-right-radius:6px; }
            QSpinBox::down-button { subcontrol-position:bottom right; border-bottom-right-radius:6px; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background:#484848; }
            QSpinBox::up-arrow { image:url("__ICONS__/chevron-up.png"); width:10px; height:7px; }
            QSpinBox::down-arrow { image:url("__ICONS__/chevron-down.png"); width:10px; height:7px; }
            QComboBox::down-arrow { image:url("__ICONS__/chevron-down.png"); width:10px; height:7px; }
            QComboBox::drop-down { width:26px; border:0; }
            QComboBox QAbstractItemView {
                background:#333333; color:#ffffff; border:1px solid #454545;
                selection-background-color:#3e3e3e; padding:4px;
            }
            QPushButton {
                background:#353535; color:#ffffff; border:1px solid #555555;
                border-radius:4px; min-height:36px; padding:2px 12px;
            }
            QPushButton:hover { background:#3e3e3e; }
            QPushButton:pressed { background:#303030; }
            QPushButton:focus { border-color:#60cdff; }
        """.replace("__ICONS__",Path(__file__).with_name("icons").as_posix()))
        outer=QVBoxLayout(self);outer.setContentsMargins(12,12,12,12)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border:0; background:#202020; } QScrollArea > QWidget > QWidget { background:#202020; }')
        content=QWidget();scroll.setWidget(content);outer.addWidget(scroll)
        layout=QFormLayout(content)
        layout.setContentsMargins(20,18,20,20)
        layout.setVerticalSpacing(12);layout.setHorizontalSpacing(18)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        hint=QLabel('绿色：模型声明的点击框；橙色：拖动网格的包围框。\n实际拖动按网格三角形命中，框内透明处可能不命中。\n调试期间不触发 AI；退出后透明处自动穿透。\n示例文本框可直接拖动，退出调试自动保存。')
        hint.setWordWrap(True);layout.addRow(hint)
        self.x=QSpinBox();self.y=QSpinBox();self.width=QSpinBox()
        self.bubble_x=QSpinBox();self.bubble_y=QSpinBox()
        self.bubble_x.setRange(-30000,30000);self.bubble_y.setRange(-30000,30000)
        self.x.setRange(-30000,30000);self.y.setRange(-30000,30000);self.width.setRange(200,1200)
        for label,widget in [('横向位置',self.x),('纵向位置',self.y),('宽度（高度等比）',self.width),('文本框横向位置',self.bubble_x),('文本框纵向位置',self.bubble_y)]:
            widget.setMinimumHeight(38);widget.setSuffix(' px')
            widget.setLocale(QLocale.c());widget.lineEdit().setLocale(QLocale.c())
            widget.lineEdit().setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly|Qt.InputMethodHint.ImhNoPredictiveText)
            numeric_font=QFont('Consolas',11)
            widget.setFont(numeric_font)
            widget.lineEdit().setFont(numeric_font)
            widget.lineEdit().setStyleSheet('QLineEdit { background:transparent; color:#ffffff; border:0; padding:0; margin:0; font-family:Consolas; font-size:15px; }')
            widget.lineEdit().setMinimumHeight(widget.fontMetrics().height()+6)
            layout.addRow(label,widget);widget.valueChanged.connect(self.apply_bubble if widget in (self.bubble_x,self.bubble_y) else self.apply)
        self.sources=QComboBox();self.sources.addItem('显示全部交互框','')
        for a in window.config['model']['hit_areas']:self.sources.addItem('点击 · '+a.get('Name','')+' · '+a.get('Id',''),a.get('Id',''))
        for c in window.config['model'].get('drag_candidates',[]):self.sources.addItem('拖动 · '+c['name']+' · '+c['parameter']+' · '+c['area'],c['area'])
        layout.addRow('交互框',self.sources)
        self.event_label=QLabel('在模型上点击或拖动，核对实际命中。');self.event_label.setWordWrap(True);layout.addRow(self.event_label)
        reset=QPushButton('释放拖动参数（恢复开始前值）');reset.clicked.connect(self.release);layout.addRow(reset)
        reset_bubble=QPushButton('恢复文本框默认位置');reset_bubble.clicked.connect(self.window.speech_bubble.reset_position);layout.addRow(reset_bubble)
        done=QPushButton('保存位置大小并退出调试');done.clicked.connect(self.close);outer.addWidget(done)
        self.window.speech_bubble.position_changed.connect(self.sync_bubble)
        self.setMinimumWidth(480)
        self.resize(540,min(740,window.screen().availableGeometry().height()-60))
    def release(self):
        for ident,value in self.window.held_initial.items():self.window.model.SetSaveParamById(ident,value)
        self.window.held.clear();self.window.held_initial.clear();self.window.drag_returns.clear();self.event_label.setText('已恢复拖动前参数')
    def sync(self):
        self.syncing=True
        self.x.setValue(self.window.x());self.y.setValue(self.window.y());self.width.setValue(self.window.width())
        self.syncing=False
        self.sync_bubble()
    def sync_bubble(self):
        previous=self.syncing;self.syncing=True
        self.bubble_x.setValue(self.window.speech_bubble.x());self.bubble_y.setValue(self.window.speech_bubble.y())
        self.syncing=previous
    def apply_bubble(self):
        if not self.syncing:self.window.speech_bubble.set_position(self.bubble_x.value(),self.bubble_y.value())
    def apply(self):
        if not self.syncing:self.window.set_geometry(self.x.value(),self.y.value(),self.width.value())
    def closeEvent(self,event):
        self.window.save_geometry();self.window.set_debug(False);event.accept()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--smoke-output')
    args=parser.parse_args();config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    fmt=QSurfaceFormat();fmt.setAlphaBufferSize(8);fmt.setDepthBufferSize(24);fmt.setStencilBufferSize(8);fmt.setVersion(2,1);QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication([])
    install(app)
    # The pet is a Qt Tool window. Closing its last ordinary configuration dialog
    # must not make Qt terminate the rendering process. Pet close/quit is explicit.
    app.setQuitOnLastWindowClosed(False)
    live2d.init();live2d.setLogLevel(2)
    network=Network(config);window=Window(config,network,args.smoke_output);network.command.connect(window.command)
    if not args.smoke_output:threading.Thread(target=network.run,daemon=True).start()
    window.show();result=app.exec()
    network.stopped.set()
    if window.model:
        window.makeCurrent();window.model=None;live2d.glRelease();window.doneCurrent()
    live2d.dispose();sys.exit(result)

if __name__=='__main__':main()
