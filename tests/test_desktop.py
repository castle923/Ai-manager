import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from ai_manager.desktop import DesktopBridge, resolve_desktop_home
from ai_manager.desktop_files import save_output
from ai_manager.desktop_install import install_to_new_directory
from ai_manager.runtime_bootstrap import RuntimeBootstrap
from ai_manager.external_process import isolated_environment, spawn_external


class DesktopTests(unittest.TestCase):
    def test_program_update_keeps_existing_default_workspace_without_creating_it(self):
        import os
        with patch.dict(os.environ, {'LOCALAPPDATA':str(self.root)}):
            self.assertEqual(resolve_desktop_home(),self.root/'AiManager'/'desktop-0.15.0')
            self.assertFalse((self.root/'AiManager').exists())
        explicit=self.root/'fresh-explicit-workspace'
        self.assertEqual(resolve_desktop_home(str(explicit)),explicit)
        self.assertFalse(explicit.exists())
    def model_bridge(self):
        bridge = DesktopBridge(self.home, self.root, self.root)
        bridge._guard_ready = True
        bridge._application = Mock(url='http://127.0.0.1:54321/')
        bridge._application.inference.active = None
        bridge._window = Mock()
        bridge._window.get_current_url.return_value = bridge._application.url
        return bridge

    def test_model_direct_path_rejects_invalid_and_untrusted_before_preparation(self):
        bridge = self.model_bridge()
        file = self.root / 'not-folder'; file.write_bytes(b'new synthetic')
        for value in ('relative', '', str(file), str(self.root/'missing'), str(self.root/'..'/'escape'), 7, 'C:\\bad\npath'):
            bridge._model_state = {'status':'ready','source_directory':'old-synthetic-folder'}
            result = bridge.prepare_model('qwen3-tts-1.7b-customvoice', value)
            self.assertEqual(result['error'], 'model_folder_absolute_directory_required')
            self.assertEqual(bridge.model_status(),result)
            self.assertNotIn('source_directory',result)
        bridge._window.get_current_url.return_value = 'https://foreign.invalid/'
        self.assertEqual(bridge.prepare_model('qwen3-tts-1.7b-customvoice', str(self.root)), {'status':'denied'})
        self.assertIsNone(bridge._model_thread)
        bridge._window.create_file_dialog.assert_not_called()

    def test_model_native_dialog_malformed_return_never_starts_preparation(self):
        bridge = self.model_bridge()
        for selected in (str(self.root), [str(self.root), str(self.root)], [7]):
            bridge._model_state = {'status':'ready','source_directory':'old-synthetic-folder'}
            bridge._window.create_file_dialog.return_value = selected
            result = bridge.prepare_model('qwen3-tts-1.7b-customvoice')
            self.assertEqual(result['error'], 'model_folder_selection_invalid')
            self.assertEqual(bridge.model_status(),result)
        self.assertIsNone(bridge._model_thread)

    def test_model_direct_path_matches_visible_model_and_records_without_picker(self):
        bridge = self.model_bridge()
        source = self.root/'지정 모델 새 원본'; source.mkdir()
        state = {'status':'ready','files_verified':1,'preflight':{'component':'config.json','expected_bytes':3,'observed_bytes':3}}
        with patch('ai_manager.desktop.SettingsStore') as store, patch('ai_manager.desktop.SecretStore'), patch('ai_manager.desktop.DesktopAuth'), patch('ai_manager.preparation.Preparation') as preparation:
            store.return_value.load.return_value = {'synthetic_secret':'must-not-return'}
            preparation.return_value.prepare_local.return_value = state
            bridge.prepare_model('qwen3-tts-1.7b-customvoice', str(source))
            bridge._model_thread.join(5)
            self.assertFalse(bridge._model_thread.is_alive())
            self.assertEqual(preparation.call_args.kwargs['model_id'], 'qwen3-tts-1.7b-customvoice')
            self.assertEqual(preparation.return_value.prepare_local.call_args.args[0], source.resolve())
        result = bridge.model_status()
        self.assertEqual(result['source_directory'], str(source.resolve()))
        self.assertEqual(result['model_id'], 'qwen3-tts-1.7b-customvoice')
        self.assertNotIn('must-not-return', json.dumps(result))
        bridge._window.create_file_dialog.assert_not_called()

    def test_first_component_size_failure_retains_private_source_and_exact_stat(self):
        from ai_manager.preparation import Preparation, PreparationError
        source = self.root/'new synthetic model';source.mkdir()
        original = source/'README.md';original.write_bytes(b'new bytes')
        manifest = {'name':'synthetic/new','revision':'new-test','source':'https://example.invalid/new','files':[{'path':'README.md','size':27,'sha256':'0'*64}]}
        prep = Preparation(self.home, {'sources':[]})
        with patch('ai_manager.preparation.manifest', return_value=manifest), self.assertRaisesRegex(PreparationError,'size_mismatch'):
            prep.prepare_local(source)
        state = prep.snapshot()['preparation']
        self.assertEqual(state['preflight'], {'component':'README.md','expected_bytes':27,'observed_bytes':9})
        self.assertEqual(state['source_directory'], str(source))
        self.assertEqual(state['files_verified'],0)
        provenance = json.loads((prep.base/state['id']/'inputs.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['source_directory'],str(source))
        self.assertEqual(provenance['files'],[])
        self.assertNotIn('new bytes',json.dumps(state)+json.dumps(provenance))
        self.assertEqual(original.read_bytes(),b'new bytes')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'fresh-home'
        self.home.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def inference(self):
        value = Mock()
        value.owner.handle = True
        value.closed = threading.Event()
        value.get.return_value = {'status': 'succeeded'}
        value.audio.return_value = b'new synthetic output bytes for this test'
        return value

    def test_save_new_file_hash_and_existing_destination_unchanged(self):
        inference = self.inference()
        output = self.root / '한글 새 음성.wav'
        result = save_output(inference, 'a' * 32, output)
        self.assertEqual(result['sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            save_output(inference, 'a' * 32, output)
        self.assertEqual(output.read_bytes(), inference.audio.return_value)

    def test_save_publish_race_does_not_replace_competing_file(self):
        output = self.root / 'race.wav'
        import ai_manager.desktop_files as files
        original = files.safe_destination
        checks = 0
        def checked(value):
            nonlocal checks
            result = original(value)
            checks += 1
            if checks == 2:
                output.write_bytes(b'competing new user file')
            return result
        with patch.object(files, 'safe_destination', checked), self.assertRaises(FileExistsError):
            save_output(self.inference(), 'a' * 32, output)
        self.assertEqual(output.read_bytes(), b'competing new user file')
        self.assertFalse(list(self.root.glob('.ai-manager-*')))

    def test_save_rejects_wrong_id_owner_failed_run_and_traversal(self):
        inference = self.inference()
        for run_id in ('../escape', None):
            with self.assertRaises(ValueError):
                save_output(inference, run_id, self.root / 'unused.wav')
        inference.owner.handle = False
        with self.assertRaises(ValueError):
            save_output(inference, 'a' * 32, self.root / 'unused.wav')
        inference.owner.handle = True
        inference.get.return_value = {'status': 'cancelled'}
        with self.assertRaises(ValueError):
            save_output(inference, 'a' * 32, self.root / 'unused.wav')
        self.assertFalse((self.root / 'unused.wav').exists())

    def test_bridge_untrusted_origin_and_missing_guard_are_denied(self):
        bridge = DesktopBridge(self.home, self.root, self.root)
        bridge._window = Mock()
        bridge._application = Mock(url='http://127.0.0.1:54321/')
        bridge._window.get_current_url.return_value = 'http://127.0.0.1:54321/'
        self.assertFalse(bridge._trusted())
        bridge._guard_ready = True
        self.assertTrue(bridge._trusted())
        for url in ('https://foreign.invalid/', 'http://127.0.0.1:54322/', 'http://127.0.0.1:54321/?secret=anything', 'file:///app.html'):
            bridge._window.get_current_url.return_value = url
            self.assertEqual(bridge.save_audio('a' * 32), {'status': 'denied'})
        bridge._window.create_file_dialog.assert_not_called()

    def test_bridge_cancelled_dialog_never_requests_or_saves_audio(self):
        bridge = DesktopBridge(self.home, self.root, self.root)
        bridge._guard_ready = True
        bridge._window = Mock()
        bridge._window.get_current_url.return_value = 'http://127.0.0.1:54321/'
        bridge._window.create_file_dialog.return_value = None
        bridge._application = Mock(url='http://127.0.0.1:54321/', inference=self.inference())
        self.assertEqual(bridge.save_audio('a' * 32), {'status': 'cancelled'})
        bridge._application.inference.audio.assert_not_called()
        self.assertFalse(list(self.root.glob('*.wav')))

    def test_setup_is_a_fixed_loopback_origin_and_host_origin_guards_apply(self):
        import requests
        bridge = DesktopBridge(self.home, self.root, self.root)
        bridge._start_setup()
        try:
            bridge._window = Mock()
            bridge._guard_ready = True
            bridge._window.get_current_url.return_value = bridge._setup_url
            self.assertTrue(bridge._trusted(setup=True))
            self.assertEqual(requests.get(bridge._setup_url, timeout=3).status_code, 200)
            self.assertEqual(requests.get(bridge._setup_url, headers={'Host': 'foreign.invalid'}, timeout=3).status_code, 403)
            self.assertEqual(requests.get(bridge._setup_url, headers={'Origin': 'https://foreign.invalid'}, timeout=3).status_code, 403)
            for value in ('about:blank', 'data:text/html,anything', bridge._setup_url + '?anything=1'):
                bridge._window.get_current_url.return_value = value
                self.assertFalse(bridge._trusted(setup=True))
        finally:
            bridge._close()
            bridge._close()

    def test_visible_setup_path_entry_is_absolute_json_only_and_never_returns_content(self):
        bridge = DesktopBridge(self.home, self.root, self.root)
        bridge._guard_ready = True
        bridge._setup_url = 'http://127.0.0.1:54321/'
        bridge._window = Mock()
        bridge._window.get_current_url.return_value = bridge._setup_url
        original = self.root / 'new-original.json'
        original.write_text('{"synthetic_private_value":"do-not-return"}')
        result = bridge.set_setup_path('client', str(original))
        self.assertEqual(result, {'status': 'selected', 'kind': 'client', 'filename': original.name})
        self.assertNotIn('do-not-return', json.dumps(result))
        self.assertEqual(bridge.set_setup_path('client', 'relative.json')['status'], 'failed')
        self.assertEqual(bridge.set_setup_path('arbitrary', str(original))['status'], 'denied')

    def test_install_visible_parent_path_reports_existing_target_without_writes(self):
        import sys
        package = self.package()
        parent = self.root / 'new-user-install'
        parent.mkdir()
        target = parent / 'AiManager-0.17.0'
        target.mkdir()
        bridge = DesktopBridge(self.home, self.root, package)
        bridge._guard_ready = True
        bridge._setup_url = 'http://127.0.0.1:54321/'
        bridge._window = Mock()
        bridge._window.get_current_url.return_value = bridge._setup_url
        with patch.object(sys, 'frozen', True, create=True):
            result = bridge.install(str(parent))
        self.assertEqual(result['error'], 'installation_destination_exists')
        self.assertIn(str(target), result['message'])
        self.assertFalse(list(target.iterdir()))
        status = json.loads((self.home / 'host-status.json').read_text())
        self.assertTrue(status['installation_target_preexisted'])
        self.assertEqual(status['installation_error'], 'installation_destination_exists')

    def package(self):
        package = self.root / 'portable'
        package.mkdir()
        (package / 'AiManager.exe').write_bytes(b'new synthetic executable placeholder')
        manifest = {'version': '0.17.0', 'files': {'AiManager.exe': hashlib.sha256((package / 'AiManager.exe').read_bytes()).hexdigest()}}
        (package / 'DESKTOP-MANIFEST.json').write_text(json.dumps(manifest))
        return package

    def test_install_manifest_files_only_new_target_no_overwrite_overlap(self):
        package = self.package()
        (package / 'unlisted-private.txt').write_bytes(b'must not be copied')
        target = self.root / '새 설치 공백'
        self.assertEqual(install_to_new_directory(package, target, self.home)['status'], 'installed')
        self.assertFalse((target / 'unlisted-private.txt').exists())
        for destination in (target, package / 'recursive', self.home / 'nested'):
            with self.assertRaises(ValueError):
                install_to_new_directory(package, destination, self.home)

    def test_install_tampered_source_creates_no_target(self):
        package = self.package()
        (package / 'AiManager.exe').write_bytes(b'changed bytes')
        with self.assertRaises(ValueError):
            install_to_new_directory(package, self.root / 'new-target', self.home)
        self.assertFalse((self.root / 'new-target').exists())

    def test_runtime_full_base_hash_rejects_modified_library_before_process(self):
        base = self.root / 'python_runtime'
        base.mkdir()
        (base / 'python.exe').write_bytes(b'synthetic python')
        (base / 'python310.dll').write_bytes(b'synthetic library original')
        metadata = {'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in base.iterdir()}, 'python_executable_sha256': hashlib.sha256((base / 'python.exe').read_bytes()).hexdigest(), 'archive_sha256': 'a' * 64}
        (self.root / 'python-runtime.json').write_text(json.dumps(metadata))
        (base / 'python310.dll').write_bytes(b'tampered library')
        runtime = RuntimeBootstrap(self.home, self.root)
        with patch.object(runtime, '_run') as execute:
            runtime._prepare()
            execute.assert_not_called()
        self.assertEqual(runtime.snapshot()['error'], 'bundled_python_integrity_failed')
        self.assertFalse((self.home / 'runtime/venv').exists())

    def test_external_environment_removes_frozen_and_user_python_paths(self):
        import sys
        environment = {'PATH': str(self.root / 'bundle/bin') + ';C:\\Windows\\System32', 'PYTHONHOME': 'old', 'PYTHONPATH': 'old', '_PYI_ARCHIVE_FILE': 'old', 'HF_HUB_OFFLINE': '1'}
        with patch.object(sys, '_MEIPASS', str(self.root / 'bundle'), create=True):
            result = isolated_environment(environment)
        self.assertNotIn('PYTHONHOME', result)
        self.assertNotIn('PYTHONPATH', result)
        self.assertNotIn('_PYI_ARCHIVE_FILE', result)
        self.assertEqual(result['PATH'], 'C:\\Windows\\System32')
        self.assertEqual(result['HF_HUB_OFFLINE'], '1')
        self.assertEqual(environment['PYTHONHOME'], 'old')

    def test_spawn_restores_original_dll_path_even_if_process_creation_fails(self):
        import sys
        kernel = Mock()
        def previous_path(length, buffer):
            buffer.value = 'C:\\safe-bundle'
            return len(buffer.value)
        kernel.GetDllDirectoryW.side_effect = previous_path
        kernel.SetDllDirectoryW.return_value = 1
        with patch.object(sys, 'frozen', True, create=True), patch('ctypes.WinDLL', return_value=kernel), self.assertRaises(OSError):
            spawn_external(['synthetic-do-not-execute'], popen=Mock(side_effect=OSError('synthetic spawn failure')))
        self.assertEqual(kernel.SetDllDirectoryW.call_args_list[0].args, (None,))
        self.assertEqual(kernel.SetDllDirectoryW.call_args_list[-1].args, ('C:\\safe-bundle',))

    def test_spawn_cleans_created_child_if_dll_restore_fails(self):
        import sys
        kernel = Mock()
        kernel.GetDllDirectoryW.return_value = 0
        kernel.SetDllDirectoryW.side_effect = [1, 0]
        process = Mock()
        process.poll.return_value = None
        with patch.object(sys, 'frozen', True, create=True), patch('ctypes.WinDLL', return_value=kernel), self.assertRaises(OSError):
            spawn_external(['synthetic-do-not-execute'], popen=Mock(return_value=process))
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=15)

    def test_dangling_junction_is_rejected_before_resolving(self):
        import os
        import subprocess
        from ai_manager.config import private_home
        from ai_manager.desktop_files import safe_destination
        from ai_manager.inference import regular
        if os.name != 'nt':
            self.skipTest('Windows reparse boundary')
        junction = self.root / 'dangling-junction'
        subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(junction), str(self.root / 'missing-target')], capture_output=True, check=True)
        try:
            self.assertTrue(junction.lstat().st_file_attributes & 0x400)
            self.assertFalse(junction.exists())
            bridge = self.model_bridge()
            self.assertEqual(bridge.prepare_model('qwen3-tts-1.7b-customvoice', str(junction))['error'], 'model_folder_absolute_directory_required')
            self.assertIsNone(bridge._model_thread)
            for operation in (lambda: private_home(junction / 'child'), lambda: safe_destination(junction / 'child'), lambda: regular(junction / 'child', self.root)):
                with self.assertRaises(ValueError):
                    operation()
        finally:
            os.rmdir(junction)

    def test_setup_close_concurrent_calls_detach_owned_server_exactly_once(self):
        bridge = DesktopBridge(self.home, self.root, self.root)
        entered, release = threading.Event(), threading.Event()
        server = Mock()
        def shutdown():
            entered.set()
            release.wait(3)
        server.shutdown.side_effect = shutdown
        bridge._setup_server, bridge._setup_thread = server, Mock()
        thread = bridge._setup_thread
        errors = []
        def close():
            try: bridge._close_setup()
            except Exception as error: errors.append(type(error).__name__)
        first, second = threading.Thread(target=close), threading.Thread(target=close)
        first.start()
        self.assertTrue(entered.wait(2))
        second.start()
        second.join(1)
        self.assertFalse(second.is_alive())
        release.set()
        first.join(2)
        self.assertFalse(errors)
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        thread.join.assert_called_once_with(5)

    def test_desktop_close_concurrent_call_cleans_runtime_and_application_once(self):
        bridge = DesktopBridge(self.home, self.root, self.root)
        entered, release = threading.Event(), threading.Event()
        bridge._runtime = Mock()
        bridge._runtime.close.side_effect = lambda: (entered.set(), release.wait(3))
        bridge._application = Mock()
        first = threading.Thread(target=bridge._close)
        first.start()
        self.assertTrue(entered.wait(2))
        second = threading.Thread(target=bridge._close)
        second.start(); second.join(1)
        self.assertFalse(second.is_alive())
        release.set();first.join(2)
        bridge._runtime.close.assert_called_once()
        bridge._application.close.assert_called_once()

    def test_runtime_instance_is_deterministic_and_new_base_ignores_old_ready(self):
        import os
        from ai_manager.runtime_paths import configure_desktop_runtime, runtime_directory, INSTANCE_ENV
        from ai_manager.preparation import Preparation
        for name in ('install-five', 'install-six'):
            resources = self.root / name
            resources.mkdir();(resources/'python_runtime').mkdir()
            (resources/'python-runtime.json').write_text(json.dumps({'archive_sha256':'a'*64}))
            (resources/'requirements-runtime.lock').write_text('synthetic-public-lock==1')
        old = self.home/'runtime';old.mkdir();(old/'environment.json').write_text(json.dumps({'status':'ready','blockers':[]}))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(INSTANCE_ENV, None)
            self.assertEqual(runtime_directory(self.home),old)
            first=configure_desktop_runtime(self.root/'install-five')
            self.assertEqual(configure_desktop_runtime(self.root/'install-five'),first)
            root=runtime_directory(self.home)
            self.assertNotEqual(root,old)
            self.assertEqual(Preparation(self.home,{'allowlist':[]},Mock()).environment()['status'],'unverified')
            (root/'venv/Scripts').mkdir(parents=True)
            (root/'venv/Scripts/python.exe').write_bytes(b'synthetic-not-executed')
            (root/'environment.json').write_text((old/'environment.json').read_text())
            self.assertEqual(Preparation(self.home,{'allowlist':[]},Mock()).environment()['blockers'],['runtime_record_invalid'])
            second=configure_desktop_runtime(self.root/'install-six')
            self.assertNotEqual(first,second)
            self.assertNotEqual(runtime_directory(self.home),root)
        self.assertTrue((old/'environment.json').exists())


if __name__ == '__main__':
    unittest.main()
