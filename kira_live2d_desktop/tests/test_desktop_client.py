import importlib.util
from importlib.machinery import SourceFileLoader
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


path = Path(__file__).resolve().parents[1] / 'desktop' / 'client.pyw'
spec = importlib.util.spec_from_loader('desktop_client', SourceFileLoader('desktop_client', str(path)))
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class DesktopConnectionTests(unittest.TestCase):
    def panel(self):
        panel = client.DesktopPanel.__new__(client.DesktopPanel)
        panel.root = Mock()
        panel.input = Mock()
        panel.outfit_button = Mock()
        panel.commands, panel.results = queue.Queue(), queue.Queue()
        panel.stop = threading.Event()
        panel.pending = panel.sending = panel.connected = False
        panel.input_active = True
        panel.refresh_outfits = Mock()
        return panel

    def test_outfit_menu_uses_custom_popup_and_root_owner(self):
        root = Mock()
        root.winfo_screenwidth.return_value = 1920
        root.winfo_screenheight.return_value = 1080
        with patch.object(client.tk,'Canvas'), patch.object(client.tk,'PhotoImage'), patch.object(client.tk,'Button'), \
                patch.object(client.tk,'Frame'), patch.object(client.tk,'Label'), \
                patch.object(client.tk,'Text'), patch.object(client,'OutfitMenu') as menu, \
                patch.object(client.threading,'Thread'), \
                patch.object(client.DesktopPanel,'register_hotkey'):
            panel=client.DesktopPanel(root,Path('unused.json'))
        menu.assert_called_once_with(root)
        self.assertIs(panel.outfit_menu,menu.return_value)

    def outfit_panel(self):
        panel = self.panel()
        del panel.refresh_outfits
        panel.outfit_signature = panel.outfit_revision = None
        panel.outfit_menu, panel.outfit_label, panel.outfit_bar = Mock(), Mock(), Mock()
        panel.outfit_bar.winfo_manager.return_value = 'pack'
        panel.outfit_button.cget.return_value = 'disabled'
        return panel

    def test_unchanged_poll_preserves_open_menu_and_hover_state(self):
        panel = self.outfit_panel()
        status = {'outfits': [{'id': 'one', 'name': 'Dress', 'available': True}],
            'outfit_revision': 'rev1', 'viewer_connected': True}
        panel.refresh_outfits(status)
        panel.outfit_button.configure.assert_called_once_with(state='normal')
        panel.outfit_button.configure.reset_mock()
        panel.outfit_button.cget.return_value = 'active'
        for _ in range(5):
            panel.refresh_outfits(status)
        panel.outfit_button.configure.assert_not_called()
        panel.outfit_menu.delete.assert_called_once_with(0, 'end')
        panel.outfit_menu.add_command.assert_called_once()
        panel.connected = True
        panel.outfit_menu.add_command.call_args.kwargs['command']()
        command, payload = panel.commands.get_nowait()
        self.assertEqual(command, '/outfit')
        self.assertEqual((payload['id'], payload['revision']), ('one', 'rev1'))
        self.assertTrue(panel.sending)
        panel.change_outfit('one', 'rev1')
        self.assertTrue(panel.commands.empty(), 'Repeated clicks must not duplicate a request')

    def test_outfit_refresh_still_blocks_busy_or_unavailable_choices(self):
        panel = self.outfit_panel()
        status = {'outfits': [{'id': 'one', 'name': 'Dress', 'available': True}],
            'outfit_revision': 'rev1', 'viewer_connected': True}
        panel.refresh_outfits(status)
        panel.outfit_button.cget.return_value = 'normal'
        panel.pending = True
        panel.refresh_outfits(status)
        self.assertFalse(panel.outfit_ready)
        panel.outfit_button.configure.assert_called_with(state='disabled')
        panel.connected = True
        panel.change_outfit('one', 'rev1')
        self.assertTrue(panel.commands.empty())
        panel.pending = False
        status['outfits'][0]['available'] = False
        status['outfit_revision'] = 'rev2'
        panel.refresh_outfits(status)
        self.assertFalse(panel.outfit_ready)
        panel.outfit_menu.add_command.assert_called_with(label='Dress（不可用）',
            state='disabled', command=unittest.mock.ANY)

    def test_ui_exception_keeps_polling_and_recovers(self):
        panel = self.panel()
        status = {'pending': False, 'input_mode': 'desktop'}
        panel.refresh_outfits.side_effect = [ValueError('bad status'), None]
        panel.results.put(('poll', status))
        with self.assertLogs(client.logger, level='ERROR'):
            panel.drain()
        self.assertFalse(panel.connected)
        self.assertEqual(panel.root.after.call_count, 1)
        panel.results.put(('poll', status))
        panel.drain()
        self.assertTrue(panel.connected)
        self.assertEqual(panel.root.after.call_count, 2)
        self.assertIn('输入', panel.root.title.call_args.args[0])

    def test_offline_preserves_input_and_blocks_sends(self):
        panel = self.panel()
        panel.input.get.return_value = 'unsent draft'
        panel.results.put(('error', ('HTTP Error 401: Unauthorized', None)))
        panel.drain()
        panel.send()
        self.assertTrue(panel.commands.empty())
        panel.input.delete.assert_not_called()
        self.assertIn('401', panel.root.title.call_args.args[0])
        panel.results.put(('poll', {'pending': False}))
        panel.drain()
        panel.send()
        self.assertEqual(panel.commands.get_nowait()[1]['text'], 'unsent draft')

    def test_worker_rereads_rotated_credentials_after_failure(self):
        panel = self.panel()
        with tempfile.TemporaryDirectory() as folder:
            panel.config_path = Path(folder) / 'desktop-client.json'
            panel.config_path.write_text(json.dumps({'url': 'http://127.0.0.1:1', 'token': 'old'}))
            tokens = []
            def request(config, path, data=None):
                tokens.append('Bearer '+config['token'])
                if len(tokens) == 1:
                    panel.config_path.write_text(json.dumps({'url': 'http://127.0.0.1:1', 'token': 'new'}))
                    raise ConnectionError('reload')
                panel.stop.set()
                return {"pending": False}

            transport = Mock()
            transport.call.side_effect = request
            # Avoid the retry delay while retaining the worker's real loop.
            panel.stop.wait = Mock()
            with patch.object(client, 'BridgeConnection', return_value=transport), self.assertLogs(client.logger):
                panel.worker()
            transport.close.assert_called_once()
            self.assertEqual(tokens, ['Bearer old', 'Bearer new'])
            self.assertEqual(panel.results.get_nowait()[0], 'error')
            self.assertEqual(panel.results.get_nowait()[0], 'poll')


    def test_poll_failure_after_confirmed_outfit_does_not_report_send_failure(self):
        panel=self.outfit_panel();panel.connected=True
        command=('/outfit',{'id':'dress','request_id':'one','revision':'rev'})
        panel.commands.put(command)
        with tempfile.TemporaryDirectory() as folder:
            panel.config_path=Path(folder)/'desktop-client.json'
            panel.config_path.write_text(json.dumps({'url':'http://127.0.0.1:1','token':'test'}))
            def call(config,path,data=None):
                if path=='/outfit':return {'sent':True,'name':'Dress','event_sent':False}
                panel.stop.set();raise TimeoutError('timed out')
            transport=Mock();transport.call.side_effect=call
            with patch.object(client,'BridgeConnection',return_value=transport),self.assertLogs(client.logger):panel.worker()
            with patch.object(client.messagebox,'showwarning') as warning:panel.drain()
            warning.assert_not_called()
            self.assertFalse(panel.sending)
            self.assertEqual([call.args[1] for call in transport.call.call_args_list],['/outfit','/status'])


class BridgeConnectionTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_call()

            def do_POST(self):
                self.handle_call()

            def handle_call(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                requests.append((self.client_address[1], self.command, self.path, self.headers.get('Authorization'), body))
                if self.path == '/drop':
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                    return
                if self.path == '/outfit':
                    import time
                    time.sleep(3.2)
                denied = self.headers.get('Authorization') == 'Bearer bad'
                raw = json.dumps({'error': 'expired'} if denied else {'pending': False}).encode()
                self.send_response(401 if denied else 200)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.transport = client.BridgeConnection()
        self.config = {'url': 'http://127.0.0.1:'+str(self.server.server_port), 'token': 'old'}

    def tearDown(self):
        self.transport.close()
        self.server.shutdown()
        self.server.server_close()

    def test_polls_and_post_reuse_connection_and_refresh_token(self):
        for _ in range(6):
            self.assertEqual(self.transport.call(self.config, '/status'), {'pending': False})
        self.config['token'] = 'new'
        self.transport.call(self.config, '/message', {'text': 'hello'})
        self.assertEqual(len({r[0] for r in self.requests}), 1)
        self.assertEqual(self.requests[-1][1:4], ('POST', '/message', 'Bearer new'))

    def test_slow_outfit_succeeds_and_reused_connection_restores_poll_timeout(self):
        self.transport.call(self.config,'/status')
        self.transport.call(self.config,'/outfit',{'id':'dress'})
        self.assertEqual(self.transport.connection.sock.gettimeout(),30)
        self.transport.call(self.config,'/status')
        self.assertEqual(self.transport.connection.sock.gettimeout(),3)
        self.assertEqual(len({row[0] for row in self.requests}),1)
        self.assertEqual(sum(row[1]=='POST' for row in self.requests),1)

    def test_unauthorized_recovers_on_next_poll(self):
        self.config['token'] = 'bad'
        with self.assertRaisesRegex(RuntimeError, 'expired'):
            self.transport.call(self.config, '/status')
        self.assertIsNone(self.transport.connection)
        self.config['token'] = 'new'
        self.assertFalse(self.transport.call(self.config, '/status')['pending'])

    def test_failed_post_is_not_replayed(self):
        with self.assertRaises((OSError, client.http.client.HTTPException)):
            self.transport.call(self.config, '/drop', {'text': 'send once'})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][1], 'POST')
        self.assertFalse(self.transport.call(self.config, '/status')['pending'])
        self.assertEqual(len(self.requests), 2)


if __name__ == '__main__':
    unittest.main()
