"""Small Windows desktop chat panel; only Python's standard library is required."""
import argparse
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox
import http.client
from urllib.parse import urlsplit
import uuid

logger = logging.getLogger('kira.desktop')


def configure_logging(config_path):
    try:
        handler = RotatingFileHandler(Path(config_path).with_name('desktop-client.log'),
            maxBytes=262144, backupCount=1, encoding='utf-8')
    except OSError:
        return
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class BridgeConnection:
    """Reuse one direct connection; never automatically replay a POST."""
    def __init__(self):
        self.connection = None
        self.endpoint = None

    def close(self):
        if self.connection is not None:
            self.connection.close()
        self.connection = None
        self.endpoint = None

    def call(self, config, path, data=None):
        url = urlsplit(config['url'])
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Invalid desktop bridge URL')
        endpoint = (url.scheme, url.hostname, url.port)
        # Outfit changes can wait for motion, expression and wardrobe acknowledgements.
        timeout = 30 if path == '/outfit' else 3
        if endpoint != self.endpoint or self.connection is None:
            self.close()
            factory = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
            self.connection = factory(url.hostname, url.port, timeout=timeout)
            self.endpoint = endpoint
        self.connection.timeout = timeout
        if self.connection.sock is not None:
            self.connection.sock.settimeout(timeout)
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
        try:
            self.connection.request('GET' if data is None else 'POST', url.path.rstrip('/')+path,
                body=body, headers={'Authorization': 'Bearer '+config['token'], 'Content-Type': 'application/json'})
            response = self.connection.getresponse()
            raw = response.read()
            if response.status >= 400:
                message = 'HTTP %s: %s' % (response.status, response.reason)
                try:
                    message = json.loads(raw).get('error', message)
                except (ValueError, AttributeError):
                    pass
                raise RuntimeError(message)
            return json.loads(raw)
        except Exception:
            self.close()
            raise


class OutfitMenu:
    """Nonblocking rounded popup, independent of Windows' native menu styling."""
    def __init__(self, root):
        self.root, self.entries, self.popup = root, [], None

    def delete(self, first, last=None):
        self.unpost()
        self.entries.clear()

    def add_command(self, **entry):
        self.entries.append(entry)

    def cget(self, key):
        if key in ('bg', 'background'):
            return '#141820'
        raise KeyError(key)

    def invoke(self, index):
        entry = self.entries[index]
        if entry.get('state') == 'disabled':
            return
        self.unpost()
        entry['command']()

    def unpost(self):
        if self.popup is not None:
            self.popup.withdraw()

    def post(self, x, y):
        if not self.entries:
            return
        if self.popup is not None:
            self.popup.destroy()
        popup = self.popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        popup.configure(bg='#010203')
        try:
            popup.attributes('-transparentcolor', '#010203')
        except tk.TclError:
            pass
        width = max(190, min(340, max(len(e['label']) for e in self.entries)*14+40))
        height = min(8,len(self.entries))*36+24
        x = max(0,min(int(x),self.root.winfo_screenwidth()-width))
        y = int(y)
        if y+height > self.root.winfo_screenheight()-12:
            y = self.root.winfo_rooty()-height-8
        y = max(0,y)
        popup.geometry('%dx%d+%d+%d' % (width,height,x,y))
        border = tk.Canvas(popup,bg='#010203',highlightthickness=0)
        border.pack(fill='both',expand=True)
        r=22
        border.create_polygon([r,2,width-r,2,width-2,2,width-2,r,width-2,height-r,
            width-2,height-2,width-r,height-2,r,height-2,2,height-2,2,height-r,2,r,2,2],
            smooth=True,splinesteps=24,fill='#141820',outline='#2b4b7c',width=2)
        content = tk.Canvas(popup,bg='#141820',highlightthickness=0)
        content.place(x=12,y=12,width=width-24,height=height-24)
        rows = tk.Frame(content,bg='#141820')
        content.create_window(0,0,anchor='nw',window=rows,width=width-24)
        def scroll(event):
            if len(self.entries)>8:
                content.yview_scroll(-1 if event.delta>0 else 1,'units')
            return 'break'
        content.bind('<MouseWheel>',scroll)
        for index,entry in enumerate(self.entries):
            button=tk.Button(rows,text=entry['label'],anchor='w',relief='flat',
                bg='#141820',fg='#e1e6ef',activebackground='#203b65',
                activeforeground='#e1e6ef',disabledforeground='#626d7d',
                borderwidth=0,font=('Microsoft YaHei UI',11),padx=10,pady=5,
                state=entry.get('state','normal'),cursor='hand2',
                command=lambda selected=index:self.invoke(selected))
            button.pack(fill='x')
            button.bind('<MouseWheel>',scroll)
            button.bind('<Enter>',lambda event,b=button:b.configure(bg='#203b65') if str(b.cget('state'))!='disabled' else None)
            button.bind('<Leave>',lambda event,b=button:b.configure(bg='#141820'))
        rows.update_idletasks()
        content.configure(scrollregion=content.bbox('all'),yscrollincrement=36)
        popup.bind('<Escape>',lambda event:self.unpost())
        def lost_focus(event):
            def check():
                try:
                    focused=popup.focus_displayof()
                    if focused is None or focused.winfo_toplevel()!=popup:
                        self.unpost()
                except tk.TclError:
                    pass
            popup.after_idle(check)
        popup.bind('<FocusOut>',lost_focus)
        popup.focus_force()


class DesktopPanel:
    def __init__(self, root, config_path):
        self.root, self.config_path = root, config_path
        self.commands, self.results = queue.Queue(), queue.Queue()
        self.stop = threading.Event()
        self.pending = False
        self.input_active = True
        self.sending = False
        self.connected = False
        self.hotkey_registered = False
        self.outfit_signature = None
        self.outfit_ready = False
        self.outfit_revision = None
        root.title('Kira 桌宠 · 输入')
        root.geometry('446x168+%d+%d' % (max(0, root.winfo_screenwidth()-476), max(0, root.winfo_screenheight()-238)))
        root.minsize(320, 150)
        root.attributes('-topmost', True)
        root.configure(bg='#010203')
        # Transparent corners leave the desktop visible around the rounded panel.
        root.overrideredirect(True)
        try:
            root.attributes('-transparentcolor', '#010203')
        except tk.TclError:
            pass
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.canvas = tk.Canvas(root, bg='#010203', highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill='both', expand=True)
        self.input = tk.Text(root, width=1, height=3, wrap='word',
            font=('Microsoft YaHei UI', 12), relief='flat', borderwidth=0,
            bg='#141820', fg='#e1e6ef', insertbackground='#e1e6ef',
            selectbackground='#28476f', highlightthickness=0, padx=0, pady=0,
            undo=True)
        self.placeholder = tk.Label(root, text='输入消息...', bg='#141820', fg='#757d89',
            font=('Microsoft YaHei UI', 12), anchor='nw', cursor='xterm')
        self.placeholder.bind('<Button-1>', lambda event: self.activate_input())
        self.input.bind('<FocusIn>', lambda event: self.activate_input())
        self.input.bind('<Button-1>', lambda event: self.activate_input())
        self.input.bind('<<Modified>>', self.text_changed)
        self.outfit_bar = tk.Frame(root, bg='#141820')
        self.outfit_icon = tk.PhotoImage(file=str(Path(__file__).parent/'icons'/'outfit.png'))
        self.outfit_button = tk.Button(self.outfit_bar, image=self.outfit_icon, command=self.toggle_outfits,
            relief='flat', borderwidth=0,
            bg='#141820', fg='#8993a3', activebackground='#202b3d',
            activeforeground='#d7e2f6', disabledforeground='#4e5663',
            padx=5, pady=5, cursor='hand2', state='disabled')
        self.outfit_menu = OutfitMenu(root)
        self.outfit_button.pack(side='left')
        self.outfit_label = tk.Label(root, text='', bg='#141820', fg='#8791a2',
            anchor='w', font=('Microsoft YaHei UI', 9))
        self.canvas.tag_bind('send', '<Button-1>', lambda event: self.send())
        self.canvas.tag_bind('close', '<Button-1>', lambda event: self.hide())
        self.canvas.tag_bind('close', '<Enter>', lambda event: self.canvas.configure(cursor='hand2'))
        self.canvas.tag_bind('close', '<Leave>', lambda event: self.canvas.configure(cursor=''))
        self.canvas.bind('<ButtonPress-1>', self.move_start)
        self.canvas.bind('<B1-Motion>', self.move_window)
        self.canvas.bind('<Configure>', self.draw_panel)
        self.canvas.bind('<Button-3>', lambda event: self.hide())
        self.update_placeholder()
        self.input.bind('<Return>', self.enter)
        self.input.bind('<Shift-Return>', lambda e: None)
        root.bind('<Escape>', lambda e: self.hide())
        root.bind('<Control-Return>', self.enter)
        self.register_hotkey()
        threading.Thread(target=self.worker, daemon=True, name='desktop-connection').start()
        root.after(100, self.drain)
        self.input.focus_set()

    def draw_panel(self, event=None):
        width, height = self.root.winfo_width(), self.root.winfo_height()
        if width < 30 or height < 30:
            return
        self.canvas.delete('panel')
        x0, y0, x1, y1, radius = 3, 3, width-3, height-3, 30
        points = [x0+radius,y0,x1-radius,y0,x1,y0,x1,y0+radius,
                  x1,y1-radius,x1,y1,x1-radius,y1,x0+radius,y1,
                  x0,y1,x0,y1-radius,x0,y0+radius,x0,y0]
        self.canvas.create_polygon(points, smooth=True, splinesteps=24,
            fill='#141820', outline='#2b4b7c', width=2, tags='panel')
        self.canvas.tag_lower('panel')
        self.input.place(x=28,y=25,width=width-80,height=height-91)
        self.outfit_bar.place(x=24,y=height-58,height=38)
        self.outfit_label.place(x=72,y=height-48,width=max(0,width-162),height=20)
        self.canvas.delete('close')
        cx, cy = width-26, 23
        self.canvas.create_oval(cx-11,cy-11,cx+11,cy+11,fill='#141820',outline='',tags='close')
        self.canvas.create_line(cx-4,cy-4,cx+4,cy+4,fill='#8993a3',width=2,tags='close')
        self.canvas.create_line(cx-4,cy+4,cx+4,cy-4,fill='#8993a3',width=2,tags='close')
        self.canvas.delete('send')
        cx, cy = width-43, height-39
        self.canvas.create_oval(cx-20,cy-20,cx+20,cy+20,fill='#203b65',outline='',tags='send')
        self.canvas.create_line(cx,cy+8,cx,cy-8,fill='#a8c7f6',width=2,tags='send')
        self.canvas.create_line(cx-7,cy-1,cx,cy-8,cx+7,cy-1,fill='#a8c7f6',width=2,tags='send')
        self.update_placeholder()

    def update_placeholder(self):
        if self.input.get('1.0','end-1c'):
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=29,y=25)
            self.placeholder.lift()

    def text_changed(self, event=None):
        if self.input.edit_modified():
            self.input.edit_modified(False)
            self.update_placeholder()

    def activate_input(self):
        if not self.input_active:
            self.input_active = True
            self.commands.put(('/input', {'mode': 'desktop'}))
        self.input.focus_set()

    def move_start(self, event):
        if not {'send','close'}.intersection(self.canvas.gettags('current')):
            self.move_anchor = (event.x_root-self.root.winfo_x(), event.y_root-self.root.winfo_y())
        else:
            self.move_anchor = None

    def move_window(self, event):
        if getattr(self, 'move_anchor', None):
            x, y = self.move_anchor
            self.root.geometry('%+d%+d' % (event.x_root-x,event.y_root-y))

    def toggle_outfits(self):
        popup=self.outfit_menu.popup
        if popup is not None and popup.winfo_viewable():
            self.outfit_menu.unpost()
        else:
            self.outfit_menu.post(self.root.winfo_rootx()+24,self.root.winfo_rooty()+self.root.winfo_height()+6)

    def hide(self):
        # Closing this panel preserves the draft and never stops the native model.
        self.outfit_menu.unpost()
        self.root.withdraw()


    def enter(self, event=None):
        self.send()
        return 'break'

    def send(self):
        text = self.input.get('1.0', 'end-1c').strip()
        if not text or not self.connected or self.sending or self.pending or not self.input_active:
            return
        if len(text) > 4000:
            messagebox.showinfo('消息太长', '每条消息最多 4000 字。', parent=self.root)
            return
        self.sending = True
        self.commands.put(('/message', {'text': text, 'request_id': uuid.uuid4().hex}))

    def refresh_outfits(self, status):
        outfits = status.get('outfits', [])
        revision = status.get('outfit_revision')
        signature = json.dumps([outfits,revision],ensure_ascii=False,sort_keys=True)
        if signature != self.outfit_signature:
            if self.outfit_revision != revision:
                self.outfit_label.configure(text='')
            self.outfit_revision = revision
            self.outfit_signature = signature
            self.outfit_menu.delete(0,'end')
            for entry in outfits:
                self.outfit_menu.add_command(label=entry['name']+('（不可用）' if not entry['available'] else ''),
                    state='normal' if entry['available'] else 'disabled',
                    command=lambda value=entry['id'],version=revision:self.change_outfit(value,version))
        self.outfit_ready = bool(outfits and any(row['available'] for row in outfits)
            and status.get('viewer_connected') and status.get('model_following',True)
            and self.input_active and not self.pending and not self.sending and not status.get('outfit_busy'))
        # Leave Tk's hover/posted state alone when availability has not changed.
        if (str(self.outfit_button.cget('state')) != 'disabled') != self.outfit_ready:
            self.outfit_button.configure(state='normal' if self.outfit_ready else 'disabled')

    def change_outfit(self, outfit_id, revision):
        if not self.connected or not self.outfit_ready or self.sending or self.pending or not self.input_active:
            return
        self.sending = True
        self.outfit_button.configure(state='disabled')
        self.commands.put(('/outfit',{'id':outfit_id,'revision':revision,'request_id':uuid.uuid4().hex}))

    def worker(self):
        transport = BridgeConnection()
        last_error = None
        try:
            while not self.stop.is_set():
                command = None
                try:
                    command = self.commands.get(timeout=0.5)
                except queue.Empty:
                    pass
                try:
                    config = json.loads(self.config_path.read_text(encoding='utf-8'))
                    show_request = self.config_path.with_suffix('.show')
                    if show_request.exists():
                        show_request.unlink()
                        self.results.put(('show', None))
                    if command:
                        reply = transport.call(config, command[0], command[1])
                        self.results.put(('sent', (command, reply)))
                        command = None  # Later polling errors must not invalidate an acknowledged send.
                    status = transport.call(config, '/status')
                    self.results.put(('poll', status))
                    if last_error is not None:
                        logger.info('桌面输入连接已恢复')
                        last_error = None
                except Exception as exc:
                    error = str(exc)
                    if error != last_error:
                        logger.warning('桌面输入连接异常：%s', error)
                        last_error = error
                    self.results.put(('error', (str(exc), command)))
                    self.stop.wait(1.5)
        finally:
            transport.close()

    def connection_error(self, error):
        self.connected = False
        self.root.title('Kira 桌宠 · 连接未就绪 · '+str(error).replace('\n', ' ')[:90])
        self.outfit_ready = False
        if hasattr(self, 'canvas'):
            self.outfit_label.configure(text='连接未就绪')
        self.outfit_button.configure(state='disabled')

    def drain(self):
        try:
            while True:
                kind, payload = self.results.get_nowait()
                if kind == 'sent':
                    command, reply = payload
                    if command[0] == '/message':
                        if self.input.get('1.0', 'end-1c').strip() == command[1]['text']:
                            self.input.delete('1.0', 'end')
                            if hasattr(self, 'placeholder'):
                                self.update_placeholder()
                        self.sending = False
                        self.pending = True
                    elif command[0] == '/outfit':
                        self.sending = False
                        self.pending = reply.get('event_sent',False)
                        self.outfit_label.configure(text='已请求：'+reply.get('name',''))
                        if reply.get('warning'):
                            messagebox.showwarning('换装事件未送达',reply['warning'][:300],parent=self.root)
                elif kind == 'poll':
                    status = payload
                    self.pending = status['pending']
                    self.input_active = status.get('input_mode', 'desktop') == 'desktop'
                    self.refresh_outfits(status)
                    self.input.configure(state='normal')
                    self.root.title('Kira 桌宠 · '+('网页输入中' if not self.input_active else '正在回复…' if self.pending else '输入'))
                    self.connected = True
                    if hasattr(self, 'canvas'):
                        self.outfit_label.configure(text='正在回复…' if self.pending else '点击输入以切回桌面' if not self.input_active else '')
                elif kind == 'show':
                    self.commands.put(('/input', {'mode': 'desktop'}))
                    self.input_active = True
                    self.root.deiconify()
                    self.root.lift()
                    self.input.focus_force()
                elif kind == 'hotkey_error':
                    self.root.title('Kira 桌宠 · 输入（快捷键被占用）')
                elif kind == 'error':
                    error, command = payload
                    self.connection_error(error)
                    if command:
                        self.sending = False
                        messagebox.showwarning('发送未完成', error[:300], parent=self.root)
        except queue.Empty:
            pass
        except Exception as exc:
            logger.exception('桌面输入状态更新失败')
            self.connection_error('状态更新失败：'+str(exc))
        finally:
            if not self.stop.is_set():
                self.root.after(100, self.drain)

    def register_hotkey(self):
        if not hasattr(ctypes, 'windll'):
            return
        def listener():
            user32 = ctypes.windll.user32
            registered = bool(user32.RegisterHotKey(None, 71, 0x0002|0x0001|0x4000, 0x20))
            if not registered:
                self.results.put(('hotkey_error', None))
                return
            try:
                message = wintypes.MSG()
                while not self.stop.is_set():
                    if user32.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                        self.results.put(('show', None))
                    self.stop.wait(0.05)
            finally:
                user32.UnregisterHotKey(None, 71)
        threading.Thread(target=listener, daemon=True, name='desktop-hotkey').start()

    def close(self):
        self.stop.set()
        self.root.destroy()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    configure_logging(Path(args.config))
    root = tk.Tk()
    DesktopPanel(root, Path(args.config))
    root.mainloop()
