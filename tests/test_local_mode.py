"""Explicit local workspaces never acquire Drive authority or touch credentials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from ai_manager.auth import AuthError
from ai_manager.config import SettingsStore, validate
from ai_manager.desktop import DesktopBridge
from ai_manager.local_mode import NoDriveAuth
from ai_manager.server import create_application
from ai_manager.validation_contracts import ContractError


class LocalModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / 'fresh-local'
        self.settings = SettingsStore(self.home).initialize_local()

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_schema_no_fake_account_or_client_and_no_overwrite(self):
        self.assertEqual(SettingsStore(self.home).load(), self.settings)
        for change in ({'version': 1}, {'version': 2.0}, {'mode':'typo'}, {'accounts': {'A': 'fake'}}, {'client_path': 'fake'},
                       {'allowlist': [{'account': 'A', 'id': 'fake'}]}, {'sources': [{}]}):
            with self.assertRaises(ValueError): validate(self.settings | change)
        before = (self.home / 'settings.json').read_bytes()
        with self.assertRaises(FileExistsError): SettingsStore(self.home).initialize_local()
        self.assertEqual((self.home / 'settings.json').read_bytes(), before)
        self.assertFalse((self.home / 'credentials').exists())
        with self.assertRaises(ValueError): validate({'accounts': {}, 'allowlist': []})

    def test_no_drive_auth_has_no_credential_store_and_denies_every_method(self):
        auth = NoDriveAuth()
        self.assertFalse(hasattr(auth, 'store'))
        for method in ('connect', 'access', 'disconnect'):
            with self.assertRaisesRegex(AuthError, 'drive_setup_required'):
                getattr(auth, method)('A')

    def test_desktop_local_start_never_constructs_oauth_or_credentials(self):
        bridge = DesktopBridge(self.home, self.home, self.home)
        with patch('ai_manager.desktop.SecretStore') as secrets, patch('ai_manager.desktop.DesktopAuth') as auth, \
                patch('requests.sessions.Session.request', side_effect=AssertionError('network forbidden')), \
                patch('ai_manager.desktop.open_oauth_browser', side_effect=AssertionError('browser forbidden')):
            bridge._start_application()
            bridge._close()
            secrets.assert_not_called()
            auth.assert_not_called()
        self.assertFalse((self.home / 'credentials').exists())

    def test_malformed_drive_client_still_fails_instead_of_local_fallback(self):
        bridge = DesktopBridge(self.home, self.home, self.home)
        drive = {'accounts': {'A': 'a@example.invalid', 'B': 'b@example.invalid'},
                 'allowlist': [{'account': 'A', 'id': 'ROOT'}], 'client_path': str(self.home/'missing.json')}
        with patch('ai_manager.desktop.SettingsStore') as settings:
            settings.return_value.load.return_value = drive
            with self.assertRaises(FileNotFoundError): bridge._start_application()
        self.assertIsNone(bridge._application)

    def test_local_http_state_remote_denials_and_local_registry_are_independent(self):
        auth = NoDriveAuth()
        app = create_application(self.home, self.settings, auth)
        url = app.start().rstrip('/')
        try:
            csrf = requests.get(url+'/api/session', timeout=5).json()['csrf']
            headers = {'X-AiManager-CSRF': csrf}
            status = requests.get(url+'/api/status', timeout=5).json()
            self.assertEqual(status['accounts'], {})
            self.assertEqual(status['drive']['configuration'], 'not_configured')
            prefs = requests.get(url+'/api/preferences', timeout=5).json()['workspace']
            self.assertEqual(prefs['accounts'], {})
            with patch.object(auth, 'connect', side_effect=AssertionError('connect forbidden')), \
                    patch.object(auth, 'access', side_effect=AssertionError('access forbidden')), \
                    patch.object(auth, 'disconnect', side_effect=AssertionError('disconnect forbidden')), \
                    patch('ai_manager.inventory.Inventory.scan', side_effect=AssertionError('scan forbidden')), \
                    patch('ai_manager.preparation.Preparation._official_content', side_effect=AssertionError('download forbidden')):
                for action in ('connect', 'refresh', 'scan', 'disconnect', 'prepare'):
                    response = requests.post(url+'/api/action', json={'action': action, 'account': 'B'}, headers=headers, timeout=5)
                    self.assertEqual(response.status_code, 409, (action, response.text))
                    self.assertEqual(response.json()['error'], 'drive_setup_required')
            self.assertEqual(requests.get(url+'/api/status', timeout=5).json()['task']['status'], 'idle')
            self.assertEqual(requests.get(url+'/api/history', timeout=5).json()['total'], 0)
            remote_plan = dict(roots=[],action='validate_control_plan',runtimes={},wall_seconds=30,source='drive',drive_scope=0)
            response = requests.post(url+'/api/validation/plan',json=remote_plan,headers=headers,timeout=5)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(response.json()['error'],'drive_setup_required')
            self.assertFalse((self.home/'validation').exists())
            body = dict(metadata=dict(name='새 로컬 등록', type='음성 합성', description='', version_label='초안', tags=[], notes=''), artifact=dict(adapter_id='', revision=''), references=[])
            response = requests.post(url+'/api/registry', json=body, headers=headers, timeout=5)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(requests.post(url+'/api/action', json={'action':'scan','account':'B'}, headers={'Origin':'https://foreign.invalid'}, timeout=5).status_code, 403)
        finally:
            app.close()
        self.assertFalse((self.home / 'credentials').exists())

    def test_remote_prepare_and_all_validation_provider_paths_fail_before_effects(self):
        from ai_manager.preparation import Preparation, PreparationError
        from ai_manager.validation_ui import ValidationUI
        from ai_manager.validation_drive import authenticated_provider
        with self.assertRaisesRegex(PreparationError, 'drive_setup_required'):
            Preparation(self.home, self.settings, NoDriveAuth()).prepare()
        self.assertFalse((self.home/'preparations').exists())
        ui = ValidationUI(self.home, self.settings, NoDriveAuth())
        self.assertEqual(ui.scopes()['drive_scopes'], [])
        for operation in (lambda: ui.provider(0), lambda: ui.reobserve_drive({'account':'A','root_id':'old'})):
            with self.assertRaisesRegex(ContractError, 'drive_setup_required'): operation()
        with patch('ai_manager.security.SecretStore') as secrets, patch('requests.Session') as session:
            with self.assertRaisesRegex(ContractError, 'drive_setup_required'):
                authenticated_provider(self.home, 'A', 'ROOT')
            secrets.assert_not_called()
            session.assert_not_called()

    def test_old_drive_plan_authority_is_refused_before_grant_or_batch_effects(self):
        from ai_manager.validation_ui import ValidationUI
        ui = ValidationUI(self.home, self.settings, NoDriveAuth())
        store = Mock()
        store.plan.return_value = {'plan': {'observation': {'kind': 'drive_live_readonly'}}}
        cases = [('approve', dict(plan_id='p',plan_sha256='s',confirmed=True,action='run_cpu_probe')),
                 ('start', dict(plan_id='p',approval_id='a')),
                 ('recover', dict(plan_id='p',batch_id='b')),
                 ('approve_resume', dict(plan_id='p',batch_id='b',plan_sha256='s',confirmed=True)),
                 ('resume', dict(plan_id='p',batch_id='b',resume_approval_id='r')),
                 ('supersede', dict(plan_id='p',plan_sha256='s'))]
        with patch.object(ui, 'store', return_value=store):
            for method, payload in cases:
                with self.assertRaisesRegex(ContractError, 'drive_setup_required'):
                    getattr(ui, method)(payload)
        store.consume.assert_not_called()
        store.approve.assert_not_called()
        store.status.assert_not_called()
        store.transaction.assert_not_called()

    def test_local_mode_module_bytes_are_bound_to_approval_code_hash(self):
        from ai_manager.validation_store import control_code_sha, CODE_FILES
        self.assertIn('local_mode.py', CODE_FILES)
        original_read = Path.read_bytes
        baseline = control_code_sha()
        def changed(path):
            raw = original_read(path)
            return raw + b'\n# new local mode control bytes\n' if path.name == 'local_mode.py' else raw
        with patch.object(Path, 'read_bytes', changed):
            self.assertNotEqual(control_code_sha(), baseline)

    def test_cli_remote_commands_fail_before_scan_and_never_create_credentials(self):
        from ai_manager.cli import main
        with patch('ai_manager.cli.SecretStore') as secrets, patch('ai_manager.cli.AuthManager') as auth, \
                patch('ai_manager.inventory.Inventory.scan', side_effect=AssertionError('scan forbidden')):
            for command in ('connect', 'refresh', 'disconnect', 'scan', 'prepare'):
                argv = ['ai-manager', '--home', str(self.home), command] + ([] if command == 'prepare' else ['A'])
                with patch('sys.argv', argv), self.assertRaises(SystemExit) as result:
                    main()
                self.assertEqual(result.exception.code, 1)
            secrets.assert_not_called()
            auth.assert_not_called()
