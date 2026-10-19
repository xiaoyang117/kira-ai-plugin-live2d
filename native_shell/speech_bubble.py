"""Non-activating, translucent speech balloon following the desktop pet."""
import json
import time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QRectF,QPoint,Signal
from PySide6.QtGui import QColor,QFont,QPainter,QPainterPath,QPen,QTextDocument,QTextOption,QAbstractTextDocumentLayout,QLinearGradient
from glass_theme import surface
from PySide6.QtWidgets import QWidget,QApplication


class SpeechBubble(QWidget):
    position_changed=Signal()
    def __init__(self, owner):
        super().__init__(owner,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.owner=owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose,False)
        surface(self)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.offset=None;self.drag_anchor=None;self.drag_time=0.;self.debug_preview=False
        preferences=getattr(owner,'preferences',None)
        self.preferences=Path(preferences).with_name(Path(preferences).stem+'-bubble.json') if preferences else None
        try:
            saved=json.loads(self.preferences.read_text(encoding='utf-8')) if self.preferences else {}
            if type(saved.get('dx')) is int and type(saved.get('dy')) is int:
                self.offset=QPoint(saved['dx'],saved['dy'])
        except (OSError,ValueError,TypeError,AttributeError,OverflowError):pass
        self.document=QTextDocument(self)
        font=QFont('Microsoft YaHei UI');font.setPixelSize(18)
        self.document.setDefaultFont(font);self.document.setDocumentMargin(0)
        option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document.setDefaultTextOption(option)
        self.document.setDefaultStyleSheet('body { color:#e1e6ef; }')
        self.started=0.;self.duration=0.
        self.timer=QTimer(self);self.timer.timeout.connect(self.follow);self.timer.setInterval(40)

    def set_debug(self,on):
        on=bool(on)
        if on==self.debug_preview:return
        self.debug_preview=on
        if on:self.display('这是回复文本框的位置预览。\n按住这里拖动，或在调试面板调整位置。',120000)
        else:
            if self.drag_anchor is not None:self.store_position()
            self.hide();self.timer.stop()

    def show_message(self,text,duration_ms):
        if not self.debug_preview:self.display(text,duration_ms)

    def display(self,text,duration_ms):
        if not self.owner.isVisible():
            self.hide();self.timer.stop();return
        area=(self.owner.screen() or QApplication.primaryScreen()).availableGeometry()
        width=max(120,min(420,area.width()-32))
        self.document.setPlainText(str(text)[:2000])
        self.document.setTextWidth(width-44)
        # Keep short replies compact while allowing longer replies to wrap.
        width=max(180,min(width,round(self.document.idealWidth())+44))
        self.document.setTextWidth(width-44)
        height=max(70,min(round(self.document.size().height())+40,area.height()-32,720))
        self.resize(width,height)
        self.duration=max(.5,min(120.,float(duration_ms)/1000))
        self.started=time.monotonic();self.follow();self.show();self.timer.start()
        self.update()

    def follow(self):
        if not self.owner.isVisible() or (not self.debug_preview and self.drag_anchor is None and time.monotonic()-self.started>=self.duration):
            self.hide();self.timer.stop();return
        if self.drag_anchor is not None:
            self.update();return
        area=(self.owner.screen() or QApplication.primaryScreen()).availableGeometry()
        pet=self.owner.frameGeometry()
        if self.offset is not None:
            self.move(self.bounded_position(pet.topLeft()+self.offset));self.update();return
        left=pet.left()-self.width()-12;right=pet.right()+12
        place_left=left>=area.left() or right+self.width()>area.right()
        x=left if place_left else right
        x=max(area.left()+8,min(x,area.right()-self.width()-7))
        y=max(area.top()+8,min(pet.top()+round(pet.height()*.12),area.bottom()-self.height()-7))
        self.move(x,y);self.update()

    def bounded_position(self,position):
        screen=QApplication.screenAt(position+QPoint(self.width()//2,self.height()//2)) or self.owner.screen() or QApplication.primaryScreen()
        area=screen.availableGeometry()
        return QPoint(max(area.left()+8,min(position.x(),area.right()-self.width()-7)),
                      max(area.top()+8,min(position.y(),area.bottom()-self.height()-7)))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag_anchor=event.globalPosition().toPoint()-self.pos()
            self.drag_time=time.monotonic()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept();return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag_anchor is not None:
            self.move(self.bounded_position(event.globalPosition().toPoint()-self.drag_anchor))
            event.accept();return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.drag_anchor is not None:
            self.store_position()
            self.started+=time.monotonic()-self.drag_time
            self.drag_anchor=None;self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept();return
        super().mouseReleaseEvent(event)

    def store_position(self):
        self.offset=self.pos()-self.owner.frameGeometry().topLeft()
        self.save_position()

    def save_position(self):
        if self.preferences:
            data={'dx':self.offset.x(),'dy':self.offset.y()} if self.offset is not None else {}
            try:self.preferences.write_text(json.dumps(data),encoding='utf-8')
            except OSError as exc:print('回复文本框位置保存失败：',exc,flush=True)

    def set_position(self,x,y):
        self.move(self.bounded_position(QPoint(int(x),int(y))))
        self.store_position()

    def reset_position(self):
        self.offset=None;self.save_position();self.follow()

    def moveEvent(self,event):
        super().moveEvent(event);self.position_changed.emit()

    def hideEvent(self,event):
        self.drag_anchor=None;self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hideEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body=QRectF(1,1,self.width()-2,self.height()-2)
        path=QPainterPath();path.addRoundedRect(body,8,8)
        fill=QLinearGradient(0,0,self.width(),self.height())
        fill.setColorAt(0,QColor(45,45,45,230));fill.setColorAt(1,QColor(38,38,38,225))
        painter.setPen(QPen(QColor(100,100,100,155),1));painter.setBrush(fill);painter.drawPath(path)
        text_rect=body.adjusted(21,17,-21,-17)
        overflow=max(0.,self.document.size().height()-text_rect.height())
        elapsed=time.monotonic()-self.started
        progress=max(0.,min(1.,(elapsed-1.2)/max(.5,self.duration-2.)))
        painter.setClipRect(text_rect);painter.translate(text_rect.left(),text_rect.top()-overflow*progress)
        # Plain text only: model output never becomes HTML or external content.
        context=QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(context.palette.ColorRole.Text,QColor('#e1e6ef'))
        self.document.documentLayout().draw(painter,context)

    def closeEvent(self,event):
        self.timer.stop();event.accept()
