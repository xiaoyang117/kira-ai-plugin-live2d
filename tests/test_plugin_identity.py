import json
from pathlib import Path
import tempfile
import unittest
from kira_live2d_desktop.plugin_identity import PLUGIN_ID, LEGACY_ID, migrate_legacy_identity


class PluginIdentityTests(unittest.TestCase):
    def test_migration_retains_absolute_model_paths_and_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / 'config'
            config_dir.mkdir()
            old_data = root / 'plugin_data' / LEGACY_ID
            old_data.mkdir(parents=True)
            (old_data / 'model-settings.json').write_text('{"models":{}}')
            (old_data / 'remote-access-key.txt').write_text('test-key-not-for-use')
            previous = {'shell_connection_mode': 'remote', 'native_model_path': str(old_data / 'model.json')}
            old_file = config_dir / (LEGACY_ID + '.json')
            old_file.write_text(json.dumps(previous))
            defaults = {'shell_connection_mode': 'disabled', 'native_model_path': ''}
            config = dict(defaults)
            new_data = old_data.parent / PLUGIN_ID
            selected = migrate_legacy_identity(config, new_data, config_dir, defaults)
            self.assertEqual(selected, old_data)
            self.assertEqual(config, previous)
            self.assertEqual(json.loads(old_file.read_text()), previous)
            config['shell_connection_mode'] = 'disabled'
            self.assertEqual(migrate_legacy_identity(config, new_data, config_dir, defaults), old_data)
            self.assertEqual(config['shell_connection_mode'], 'disabled')
            self.assertEqual((old_data / 'remote-access-key.txt').read_text(), 'test-key-not-for-use')

    def test_custom_new_config_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / (LEGACY_ID + '.json')).write_text('{"port":1234}')
            (root / 'data' / LEGACY_ID).mkdir(parents=True)
            config = {'port': 5678}
            new_data = root / 'data' / PLUGIN_ID
            self.assertEqual(migrate_legacy_identity(config, new_data, root, {'port': 18765}), new_data)
            self.assertEqual(config, {'port': 5678})

    def test_fresh_install_keeps_default_disabled_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {'shell_connection_mode': 'disabled'}
            new_data = root / 'data' / PLUGIN_ID
            self.assertEqual(migrate_legacy_identity(config, new_data, root, config.copy()), new_data)
            self.assertEqual(config['shell_connection_mode'], 'disabled')
