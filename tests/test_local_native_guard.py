"""Native local setup is a fresh-workspace operation behind the existing guard."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ai_manager.config import SettingsStore
from ai_manager.desktop import DesktopBridge


class NativeLocalSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / 'fresh-local'
        SettingsStore(self.home)

    def tearDown(self):
        self.temp.cleanup()

    def bridge(self):
        bridge = DesktopBridge(self.home, self.base, self.base)
        bridge._guard_ready = True
        bridge._setup_url = 'http://127.0.0.1:54321/'
        bridge._window = Mock()
        bridge._window.get_current_url.return_value = bridge._setup_url
        return bridge

    def test_untrusted_missing_guard_foreign_and_already_app_cannot_initialize(self):
        for kind in ('guard', 'foreign', 'application'):
            bridge = self.bridge()
            if kind == 'guard': bridge._guard_ready = False
            elif kind == 'foreign': bridge._window.get_current_url.return_value = 'https://foreign.invalid/'
            else: bridge._application = Mock(url='http://127.0.0.1:54322/')
            with patch('ai_manager.desktop.SettingsStore') as settings:
                self.assertEqual(bridge.initialize_local(), {'status': 'denied'})
                settings.assert_not_called()
            self.assertFalse((self.home/'settings.json').exists())

    def test_existing_settings_never_overwritten(self):
        store = SettingsStore(self.home)
        store.initialize_local()
        before = store.path.read_bytes()
        bridge = self.bridge()
        self.assertEqual(bridge.initialize_local()['status'], 'failed')
        self.assertEqual(store.path.read_bytes(), before)
        self.assertIsNone(bridge._application)
        bridge._window.load_url.assert_not_called()

    def test_trusted_fresh_setup_starts_local_server_without_oauth_or_network(self):
        bridge = self.bridge()
        with patch('ai_manager.desktop.SecretStore') as secrets, patch('ai_manager.desktop.DesktopAuth') as auth, \
                patch('requests.sessions.Session.request', side_effect=AssertionError('outbound forbidden')), \
                patch('ai_manager.desktop.open_oauth_browser', side_effect=AssertionError('browser forbidden')):
            try:
                self.assertEqual(bridge.initialize_local(), {'status': 'initialized'})
                self.assertEqual(SettingsStore(self.home).load()['mode'], 'local')
                bridge._window.load_url.assert_called_once_with(bridge._application.url)
                secrets.assert_not_called()
                auth.assert_not_called()
            finally:
                bridge._close()
        self.assertFalse((self.home/'credentials').exists())
