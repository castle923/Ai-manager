"""Fresh synthetic workspaces: configuration transaction and server generations."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import sqlite3
import unittest
from unittest.mock import Mock, patch
import urllib.request
import urllib.error

from ai_manager.auth import AUTH_URL, TOKEN_URL
from ai_manager.config import SettingsStore
from ai_manager.desktop import DesktopBridge
from ai_manager.drive_setup import ConfigurationChange, configuration
from ai_manager.local_mode import NoDriveAuth
from ai_manager.server import create_application


class DriveSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root/'fresh'
        self.settings = SettingsStore(self.home).initialize_local()
        self.client = self.root/'client.json'
        self.allowlist = self.root/'allowlist.json'
        self.client.write_text(json.dumps({'installed': dict(client_id='new.apps.googleusercontent.com',client_secret='synthetic-not-a-real-secret',auth_uri=AUTH_URL,token_uri=TOKEN_URL)}))
        self.allowlist.write_text(json.dumps(dict(accounts={'A':'new-a@example.invalid','B':'new-b@example.invalid'},roots=[dict(account='A',id='NEW_ROOT',alias='NEW') ])))
        self.bridge = None

    def tearDown(self):
        if self.bridge:
            self.bridge._close()
        self.temp.cleanup()

    def start_bridge(self):
        bridge = self.bridge = DesktopBridge(self.home, self.root, self.root)
        bridge._guard_ready = True
        bridge._start_application()
        bridge._window = Mock()
        bridge._window.get_current_url.side_effect = lambda: bridge._application.url
        return bridge

    def configure(self, bridge):
        with patch('ai_manager.desktop.open_oauth_browser', side_effect=AssertionError('OAuth must be user-triggered')), patch('requests.sessions.Session.request', side_effect=AssertionError('outbound forbidden')):
            return bridge.configure_drive(str(self.client), str(self.allowlist))

    def test_configuration_rejects_unofficial_endpoints_and_does_not_write_home(self):
        before = (self.home/'settings.json').read_bytes()
        data=json.loads(self.client.read_text()); data['installed']['token_uri']='https://untrusted.invalid/token'
        self.client.write_text(json.dumps(data))
        with self.assertRaises(Exception): configuration(str(self.client), str(self.allowlist))
        self.assertEqual((self.home/'settings.json').read_bytes(), before)
        self.assertFalse((self.home/'credentials').exists())

    def test_validation_read_swap_restore_cannot_bind_a_different_client_payload(self):
        before=(self.home/'settings.json').read_bytes()
        swapped=json.loads(self.client.read_text())['installed']
        swapped['client_id']='swapped.apps.googleusercontent.com'
        with patch('ai_manager.drive_setup.client_config',return_value=swapped):
            with self.assertRaisesRegex(ValueError,'original_changed'):
                configuration(str(self.client),str(self.allowlist))
        self.assertEqual((self.home/'settings.json').read_bytes(),before)
        self.assertFalse(list(self.home.glob('settings-before-drive-*')))

    def test_transaction_has_exclusive_original_backup_and_compare_before_rollback(self):
        before=(self.home/'settings.json').read_bytes()
        change=ConfigurationChange(self.home,before,configuration(str(self.client),str(self.allowlist)))
        try:
            with self.assertRaisesRegex(ValueError,'busy'):
                ConfigurationChange(self.home,before,change.settings)
            change.apply()
            self.assertEqual(change.backup.read_bytes(),before)
            (self.home/'settings.json').write_bytes(b'new concurrent owner edit')
            with self.assertRaisesRegex(ValueError,'rollback_conflict'):
                change.rollback()
            self.assertEqual((self.home/'settings.json').read_bytes(),b'new concurrent owner edit')
        finally: change.close()

    def test_same_workspace_configuration_preserves_databases_and_rotates_authority(self):
        bridge=self.start_bridge(); old=bridge._application
        before=(self.home/'settings.json').read_bytes()
        dbs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in self.home.glob('*.sqlite3')}
        with urllib.request.urlopen(old.url+'api/session') as response: stale=json.load(response)['csrf']
        result=self.configure(bridge)
        self.assertEqual(result['status'],'configured',result)
        self.assertEqual((self.home/result['backup']).read_bytes(),before)
        self.assertNotEqual(bridge._application.url,old.url)
        self.assertTrue(old.closed)
        self.assertEqual(dbs,{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in self.home.glob('*.sqlite3')})
        self.assertNotEqual(SettingsStore(self.home).load().get('mode'),'local')
        request=urllib.request.Request(bridge._application.url+'api/action',data=b'{"action":"scan","account":"A"}',headers={'Content-Type':'application/json','X-AiManager-CSRF':stale},method='POST')
        with self.assertRaises(urllib.error.HTTPError) as failure: urllib.request.urlopen(request)
        self.assertEqual(failure.exception.code,403)
        bridge._window.get_current_url.side_effect=None;bridge._window.get_current_url.return_value=old.url
        self.assertEqual(bridge.prepare_runtime(),{'status':'denied'})

    def test_native_call_queued_before_transition_cannot_enter_new_generation(self):
        bridge=self.start_bridge();real_lock=bridge._mutation_lock
        attempted=threading.Event();result={}
        class ObservedLock:
            def __enter__(self):
                attempted.set();real_lock.acquire();return self
            def __exit__(self,*args):real_lock.release()
        bridge._mutation_lock=ObservedLock()
        with patch.object(bridge._runtime,'start',return_value={'status':'running'}) as start:
            with real_lock:
                queued=threading.Thread(target=lambda:result.update(call=bridge.prepare_runtime()))
                queued.start();self.assertTrue(attempted.wait(2))
                configured=self.configure(bridge)
                self.assertEqual(configured['status'],'configured')
            queued.join(5)
            self.assertFalse(queued.is_alive())
            self.assertEqual(result['call'],{'status':'denied'})
            start.assert_not_called()

    def test_queued_work_and_each_native_preparation_block_without_settings_change(self):
        bridge=self.start_bridge();before=(self.home/'settings.json').read_bytes()
        with patch.object(bridge._application.inference,'_runs',return_value=[{'status':'queued'}]):
            self.assertEqual(self.configure(bridge)['error'],'workspace_busy')
        for name in ('_model_thread',):
            with patch.object(bridge,name,Mock(is_alive=Mock(return_value=True))):
                self.assertEqual(self.configure(bridge)['error'],'workspace_busy')
        for runtime in (bridge._runtime,bridge._task_runtime):
            with patch.object(runtime,'thread',Mock(is_alive=Mock(return_value=True))):
                self.assertEqual(self.configure(bridge)['error'],'workspace_busy')
        self.assertEqual((self.home/'settings.json').read_bytes(),before)
        self.assertFalse(list(self.home.glob('settings-before-drive-*')))

    def test_post_gate_blocks_after_quiesce_even_if_not_yet_started(self):
        bridge=self.start_bridge(); app=bridge._application
        with urllib.request.urlopen(app.url+'api/session') as response: token=json.load(response)['csrf']
        with app.mutation_lock:
            outcome=[]
            thread=threading.Thread(target=lambda:outcome.append(app.quiesce()));thread.start();thread.join(2)
            self.assertEqual(outcome,[False])
        self.assertTrue(app.quiesce())
        request=urllib.request.Request(app.url+'api/action',data=b'{"action":"runtime_check","account":"B"}',headers={'Content-Type':'application/json','X-AiManager-CSRF':token},method='POST')
        with self.assertRaises(urllib.error.HTTPError) as failure: urllib.request.urlopen(request)
        self.assertEqual(failure.exception.code,409)
        app.resume_requests()

    def test_post_arriving_during_busy_check_is_rejected_after_gate_commits(self):
        bridge=self.start_bridge();app=bridge._application
        with urllib.request.urlopen(app.url+'api/session') as response:token=json.load(response)['csrf']
        checking,release=threading.Event(),threading.Event();result={}
        def busy():
            checking.set();self.assertTrue(release.wait(5));return False
        def post():
            request=urllib.request.Request(app.url+'api/preferences',data=b'{}',headers={'Content-Type':'application/json','X-AiManager-CSRF':token},method='POST')
            try:
                with urllib.request.urlopen(request,timeout=5) as response:result['post']=response.status
            except urllib.error.HTTPError as failure:result['post']=failure.code
        with patch.object(app,'_busy',side_effect=busy):
            first=threading.Thread(target=lambda:result.update(quiesced=app.quiesce()));first.start()
            self.assertTrue(checking.wait(2));second=threading.Thread(target=post);second.start()
            release.set();first.join(5);second.join(5)
        self.assertEqual(result,{'quiesced':True,'post':409})
        app.resume_requests()

    def test_validation_admission_reads_all_batches_without_changing_database(self):
        bridge=self.start_bridge();validation=bridge._application.validation
        validation.home.mkdir()
        database=validation.home/'validation-control.sqlite3'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE batches(id INTEGER PRIMARY KEY,status TEXT)')
            db.executemany('INSERT INTO batches VALUES (?,?)',[(i,'pending' if i==0 else 'succeeded')for i in range(151)])
        before=database.read_bytes()
        self.assertTrue(validation.has_pending_work())
        self.assertFalse(bridge._application.quiesce())
        self.assertEqual(database.read_bytes(),before)
        database.write_bytes(b'new synthetic invalid sqlite')
        with self.assertRaises(sqlite3.DatabaseError):validation.has_pending_work()

    def test_failed_local_reconstruction_keeps_mutators_denied_but_safe_status_visible(self):
        bridge=self.start_bridge();before=(self.home/'settings.json').read_bytes()
        with patch('ai_manager.desktop.create_application',side_effect=RuntimeError('synthetic failure')):
            result=self.configure(bridge)
        self.assertEqual(result['error'],'drive_setup_recovery_requires_restart')
        self.assertEqual((self.home/'settings.json').read_bytes(),before)
        self.assertTrue(bridge._transitioning)
        self.assertFalse(bridge._trusted())
        self.assertEqual(bridge.prepare_runtime(),{'status':'denied'})
        self.assertEqual(bridge.drive_setup_status()['error'],'drive_setup_recovery_requires_restart')

    def test_settings_edit_before_apply_is_preserved_without_creating_backup(self):
        before=(self.home/'settings.json').read_bytes()
        change=ConfigurationChange(self.home,before,configuration(str(self.client),str(self.allowlist)))
        replacement=before+b'\n'
        (self.home/'settings.json').write_bytes(replacement)
        try:
            with self.assertRaisesRegex(ValueError,'settings_changed'):change.apply()
            self.assertEqual((self.home/'settings.json').read_bytes(),replacement)
            self.assertFalse(list(self.home.glob('settings-before-drive-*')))
        finally:change.close()

    def test_new_server_failure_rolls_back_settings_and_preserves_databases(self):
        bridge=self.start_bridge(); before=(self.home/'settings.json').read_bytes()
        dbs={p.name:p.read_bytes()for p in self.home.glob('*.sqlite3')}
        real=create_application
        def construct(*args,**kwargs):
            if args[1].get('mode')!='local': raise RuntimeError('synthetic construction failure')
            return real(*args,**kwargs)
        with patch('ai_manager.desktop.create_application',side_effect=construct):result=self.configure(bridge)
        self.assertEqual(result['error'],'drive_setup_failed_local_preserved',result)
        self.assertEqual((self.home/'settings.json').read_bytes(),before)
        self.assertEqual(dbs,{p.name:p.read_bytes()for p in self.home.glob('*.sqlite3')})
        self.assertFalse((self.home/'credentials').exists())
        self.assertTrue(bridge._trusted())

    def test_navigation_failure_closes_new_generation_and_restores_local(self):
        bridge=self.start_bridge();before=(self.home/'settings.json').read_bytes()
        bridge._window.load_url.side_effect=[RuntimeError('synthetic navigation failure'),None]
        result=self.configure(bridge)
        self.assertEqual(result['error'],'drive_setup_failed_local_preserved',result)
        self.assertEqual((self.home/'settings.json').read_bytes(),before)
        self.assertEqual(bridge._window.load_url.call_count,2)
        self.assertTrue(bridge._trusted())
        self.assertFalse((self.home/'credentials').exists())

    def test_existing_credentials_or_drive_settings_are_never_upgraded(self):
        bridge=self.start_bridge();before=(self.home/'settings.json').read_bytes()
        credentials=self.home/'credentials';credentials.mkdir();(credentials/'preserve').write_bytes(b'synthetic encrypted state')
        self.assertEqual(self.configure(bridge)['error'],'drive_setup_failed_local_preserved')
        self.assertEqual((credentials/'preserve').read_bytes(),b'synthetic encrypted state')
        self.assertEqual((self.home/'settings.json').read_bytes(),before)
        self.assertFalse(list(self.home.glob('settings-before-drive-*')))

    def test_application_construction_failure_releases_all_created_owners(self):
        with patch('ai_manager.registry.Registry',side_effect=ValueError('synthetic failure')):
            with self.assertRaises(ValueError):create_application(self.home,self.settings,NoDriveAuth())
        app=create_application(self.home,self.settings,NoDriveAuth())
        try:
            self.assertTrue(app.inference.owner.handle)
            self.assertTrue(app.tasks.owner.handle)
        finally:app.close()

    def test_picker_cancellation_and_foreign_origin_do_not_register_or_prepare(self):
        bridge=self.start_bridge();before={p.name:p.read_bytes()for p in self.home.glob('*.sqlite3')}
        bridge._window.create_file_dialog.return_value=None
        self.assertEqual(bridge.choose_model_directory(),{'status':'cancelled'})
        bridge._window.create_file_dialog.return_value=[str(self.root)]
        self.assertEqual(bridge.choose_model_directory(),{'status':'selected','path':str(self.root)})
        self.assertEqual(before,{p.name:p.read_bytes()for p in self.home.glob('*.sqlite3')})
        bridge._window.get_current_url.side_effect=None;bridge._window.get_current_url.return_value='https://foreign.invalid/'
        bridge._window.create_file_dialog.reset_mock()
        self.assertEqual(bridge.choose_model_directory(),{'status':'denied'})
        self.assertEqual(self.configure(bridge),{'status':'denied'})
        bridge._window.create_file_dialog.assert_not_called()
