"""Fresh tiny public-library fixtures; never use installed personal runtimes."""
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_manager import runtime_paths, runtime_reuse, task_runtime
from ai_manager.runtime_bootstrap import RuntimeBootstrap
from ai_manager import adapters
from ai_manager.registry import sha
from ai_manager.task_inference import TaskInference


class RuntimeReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.old = self.resources('old')
        self.new = self.resources('new')
        self.instance = '1234567890abcdef'
        self.addCleanup(setattr, runtime_paths, '_DESKTOP_CONTEXT', runtime_paths._DESKTOP_CONTEXT)
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.req = patch.object(task_runtime, 'requirements', side_effect=lambda role: self.new / 'ai_manager' / task_runtime.LOCKS[role])
        self.req.start()
        self.addCleanup(self.req.stop)
        self.probe = patch.object(runtime_reuse, 'fresh_metadata', side_effect=lambda root, base, expected:
            dict(python='3.10.22', base=str(base), packages=expected))
        self.probe_mock = self.probe.start()
        self.addCleanup(self.probe.stop)
        for role in ('tts', *task_runtime.LOCKS):
            self.runtime(role)

    def resources(self, name):
        resources = self.root / name
        (resources / 'ai_manager').mkdir(parents=True)
        for dirname, metadata_name in (('python_runtime', 'python-runtime.json'), ('python_image_runtime', 'python-image-runtime.json')):
            base = resources / dirname
            (base / 'Lib/venv/scripts/nt').mkdir(parents=True)
            (base / 'python.exe').write_bytes(b'fresh fake public base executable')
            (base / 'Lib/venv/scripts/nt/python.exe').write_bytes(b'fresh fake venv launcher')
            (base / 'Lib/library.py').write_text('value = 1\n', 'utf8')
            files = {p.relative_to(base).as_posix(): runtime_reuse.digest(p) for p in base.rglob('*') if p.is_file()}
            metadata = dict(version='3.10.22', archive_sha256='a'*64, python_executable_sha256=files['python.exe'], files=files)
            (resources / metadata_name).write_text(json.dumps(metadata), 'utf8')
        (resources / 'requirements-runtime.lock').write_text('torch==2.9.1+cu128\n', 'utf8')
        for role, filename in task_runtime.LOCKS.items():
            (resources / 'ai_manager' / filename).write_text('torch==2.9.1+cu128\n', 'utf8')
        return resources

    def runtime(self, role):
        root = self.home / ('runtime-' + self.instance) if role == 'tts' else self.home / 'task-runtimes' / role / self.instance
        (root / 'venv/Scripts').mkdir(parents=True)
        base = self.old / ('python_image_runtime' if role == 'qwen-image-2.1' else 'python_runtime')
        (root / 'venv/Scripts/python.exe').write_bytes((base / 'Lib/venv/scripts/nt/python.exe').read_bytes())
        (root / 'venv/pyvenv.cfg').write_text('home = ' + str(base) + '\n', 'utf8')
        metadata = runtime_reuse.read(self.new / ('python-image-runtime.json' if role == 'qwen-image-2.1' else 'python-runtime.json'))
        lock = self.new / 'requirements-runtime.lock' if role == 'tts' else task_runtime.requirements(role)
        marker = dict(requirements_sha256=runtime_reuse.digest(lock), python_archive_sha256=metadata['archive_sha256'])
        record = dict(status='ready', cuda_available=True, packages=task_runtime.versions(role) if role != 'tts' else {'torch': '2.9.1+cu128'})
        if role == 'tts':
            from ai_manager import runtime_probe
            marker.update(python_base=str(base), python_executable_sha256=metadata['python_executable_sha256'], runtime_instance_id=root.name)
            marker_file = root / 'bootstrap-inputs.json'
            record.update(probe_sha256=runtime_reuse.digest(Path(runtime_probe.__file__)), runtime_instance_id=root.name)
            (root / 'bootstrap.json').write_text(json.dumps({'status': 'ready'}), 'utf8')
        else:
            marker.update(adapter_id=role, base_python_path=str(base / 'python.exe'), base_python_sha256=metadata['python_executable_sha256'], python_base_kind='verified_bundled_python')
            marker_file = root / 'setup-inputs.json'
            (root / 'requirements.lock').write_bytes(lock.read_bytes())
            (root / 'installed-packages.json').write_text('{}', 'utf8')
            record.update(adapter_id=role, lock_sha256=runtime_reuse.digest(lock), resolved_packages_sha256=runtime_reuse.digest(root / 'installed-packages.json'))
        marker_file.write_text(json.dumps(marker), 'utf8')
        if role != 'tts':
            record['setup_inputs_sha256'] = runtime_reuse.digest(marker_file)
        (root / 'environment.json').write_text(json.dumps(record), 'utf8')

    def test_identical_side_by_side_base_references_original_without_copy_or_reinstall(self):
        runtime_paths.configure_desktop_runtime(self.new, self.home)
        self.assertEqual(runtime_paths.runtime_directory(self.home).name, 'runtime-' + self.instance)
        self.assertEqual(runtime_paths.python_base(self.home, 'tts', self.new / 'python_runtime'), self.old / 'python_runtime')
        for role in task_runtime.LOCKS:
            self.assertEqual(task_runtime.root(self.home, role).name, self.instance)
        bootstrap = RuntimeBootstrap(self.home, self.new)
        with patch.object(bootstrap, '_prepare') as prepare:
            self.assertEqual(bootstrap.start()['status'], 'ready')
            prepare.assert_not_called()
        self.assertEqual(len(self.probe_mock.mock_calls), 5)
        for _ in range(5):
            runtime_paths.runtime_directory(self.home)
            task_runtime.root(self.home, 'tapir')
            runtime_paths.runtime_dependencies(self.home)
        self.assertEqual(len(self.probe_mock.mock_calls), 5)  # polling does not probe/hash again

    def test_image_lock_changes_only_image_and_tts_lock_only_tts(self):
        original = runtime_reuse.bind(self.new, self.home)
        image = task_runtime.requirements('qwen-image-2.1')
        image.write_text('torch==2.9.1+cu128\ntorchvision==0.24.1+cu128\n', 'utf8')
        changed = runtime_reuse.bind(self.new, self.home)
        self.assertFalse(changed['roles']['qwen-image-2.1']['reused'])
        for role in ('tts', 'tapir', 'whisper-large-v3-turbo', 'llama-3.1-8b-instruct'):
            self.assertEqual(original['roles'][role]['root'], changed['roles'][role]['root'])
        (self.new / 'requirements-runtime.lock').write_text('torch==2.9.2\n', 'utf8')
        final = runtime_reuse.bind(self.new, self.home)
        self.assertFalse(final['roles']['tts']['reused'])
        self.assertEqual(changed['roles']['tapir']['root'], final['roles']['tapir']['root'])

    def test_changed_or_missing_original_base_fails_closed_and_does_not_edit_venv(self):
        config = self.home / ('runtime-' + self.instance) / 'venv/pyvenv.cfg'
        before = config.read_bytes()
        (self.old / 'python_runtime/Lib/library.py').write_text('value = 2\n', 'utf8')
        result = runtime_reuse.bind(self.new, self.home)
        self.assertFalse(result['roles']['tts']['reused'])
        self.assertEqual(config.read_bytes(), before)
        (self.old / 'python_runtime/python.exe').unlink()
        self.assertFalse(runtime_reuse.bind(self.new, self.home)['roles']['tapir']['reused'])

    def test_only_cache_equivalent_to_pinned_source_is_allowed(self):
        base = self.old / 'python_runtime'
        cache = base / 'Lib/__pycache__/library.cpython-310.pyc'
        cache.parent.mkdir()
        source = base / 'Lib/library.py'
        cache.write_bytes(importlib.util.MAGIC_NUMBER + b'\0'*12 + marshal.dumps(compile(source.read_bytes(), str(source), 'exec')))
        self.assertTrue(runtime_reuse.bind(self.new, self.home)['roles']['tts']['reused'])
        cache.write_bytes(importlib.util.MAGIC_NUMBER + b'\0'*12 + marshal.dumps(compile('value = 9', str(source), 'exec')))
        self.assertFalse(runtime_reuse.bind(self.new, self.home)['roles']['tts']['reused'])
        code = compile(source.read_bytes(), str(source), 'exec')
        changed_flags = code.replace(co_flags=code.co_flags ^ 1)
        self.assertNotEqual(changed_flags.co_flags, code.co_flags)
        for changed in (changed_flags, code.replace(co_stacksize=code.co_stacksize + 1)):
            cache.write_bytes(importlib.util.MAGIC_NUMBER + b'\0'*12 + marshal.dumps(changed))
            self.assertFalse(runtime_reuse.bind(self.new, self.home)['roles']['tts']['reused'])
        cache.write_bytes(importlib.util.MAGIC_NUMBER + b'\0'*12)
        self.assertFalse(runtime_reuse.bind(self.new, self.home)['roles']['tts']['reused'])

    def test_old_base_reuse_still_launches_current_worker_and_current_source_provenance(self):
        runtime_paths.configure_desktop_runtime(self.new, self.home)
        model = self.home / 'designated-model'
        model.mkdir()
        component = model / 'config.json'
        component.write_bytes(b'new synthetic designated model component')
        fixture = adapters.manifest('llama-3.1-8b-instruct')
        fixture['files'] = [dict(path='config.json', size=component.stat().st_size, sha256=runtime_reuse.digest(component))]
        manifest = self.home / 'new-manifest.json'
        manifest.write_text(json.dumps(fixture), 'utf8')
        old_worker = self.old / 'ai_manager/llm_worker.py'
        old_worker.write_text('raise RuntimeError("must never be selected")', 'utf8')
        task = TaskInference.__new__(TaskInference)
        task.home, task.base = self.home, self.home / 'task-runs'
        directory = task.base / ('b'*32)
        directory.mkdir(parents=True)
        data = b'Fresh current-candidate provenance fixture.'
        (directory / 'input.txt').write_bytes(data)
        binding = dict(id='a'*32, generation='new-generation', fingerprint='new-fingerprint',
            registered_source=str(model), manifest_sha256=runtime_reuse.digest(manifest), asset_sha256=sha(fixture['files']))
        run = dict(id='b'*32, adapter_id='llama-3.1-8b-instruct', task_type='llm', registry_binding=binding,
            input=dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()), parameters={})
        task._check = lambda _: None
        with patch.object(adapters, 'manifest', return_value=fixture), patch.object(adapters, 'manifest_path', return_value=manifest), \
             patch.object(task_runtime, 'environment', return_value={'status': 'ready'}):
            python, worker = task._prepare(run)
        self.assertNotEqual(worker, old_worker)
        self.assertEqual(worker, Path(task_runtime.__file__).with_name('llm_worker.py'))
        self.assertEqual(python.parent.parent, task_runtime.root(self.home, 'llama-3.1-8b-instruct') / 'venv')
        proof = json.loads((directory / 'provenance.json').read_text('utf8'))
        self.assertEqual(proof['code_sha256']['runtime_reuse.py'], runtime_reuse.digest(Path(runtime_reuse.__file__)))
        self.assertNotEqual(proof['code_sha256']['llm_worker.py'], runtime_reuse.digest(old_worker))

    def test_context_free_legacy_cli_and_explicit_instance_still_work(self):
        runtime_paths._DESKTOP_CONTEXT = None
        os.environ.pop(runtime_paths.INSTANCE_ENV, None)
        self.assertEqual(runtime_paths.runtime_directory(self.home), self.home / 'runtime')
        os.environ[runtime_paths.INSTANCE_ENV] = 'f'*16
        self.assertEqual(task_runtime.root(self.home, 'tapir').name, 'f'*16)


if __name__ == '__main__':
    unittest.main()
