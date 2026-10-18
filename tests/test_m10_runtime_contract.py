"""Fresh CPU integration counterexamples; no model/runtime installation or GPU."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from ai_manager import adapters, image_safe, image_worker, task_runtime
from ai_manager.task_inference import TaskInference


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def actual_worker_contract(self):
        source = self.home / 'fresh-pipeline.py'
        source.write_bytes(b'new synthetic source; installed-package contract fixture only')
        package = types.ModuleType('diffusers')
        pipelines = types.ModuleType('diffusers.pipelines')
        qwen = types.ModuleType('diffusers.pipelines.qwenimage21')
        pipeline = types.ModuleType('diffusers.pipelines.qwenimage21.pipeline_qwenimage21')
        pipeline.__file__ = str(source)
        package.pipelines, pipelines.qwenimage21, qwen.pipeline_qwenimage21 = pipelines, qwen, pipeline
        versions = dict(torch='2.9.1+cu128', torchvision='0.24.1+cu128', transformers='5.17.0',
            accelerate='1.12.0', safetensors='0.8.0', Pillow='11.3.0', psutil='7.2.2')
        with patch.dict(sys.modules, {m.__name__: m for m in (package, pipelines, qwen, pipeline)}), \
             patch.object(image_worker, 'PIPELINE_SOURCE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest()), \
             patch.object(image_worker.importlib.metadata, 'version', side_effect=lambda name: versions[name]):
            actual = image_worker.check_runtime()
        # The package-version gate is under test, not a mock source's identity.
        actual['pipeline_source_sha256'] = image_worker.PIPELINE_SOURCE_SHA256
        return actual

    def test_actual_worker_probe_matches_app_gate_and_lock_including_torchvision(self):
        actual = self.actual_worker_contract()
        self.assertEqual(actual, task_runtime.versions('qwen-image-2.1'))
        self.assertIn('torchvision==' + actual['torchvision'], task_runtime.requirements('qwen-image-2.1').read_text('utf8'))
        directory = task_runtime.root(self.home, 'qwen-image-2.1')
        (directory / 'venv/Scripts').mkdir(parents=True)
        (directory / 'venv/Scripts/python.exe').write_bytes(b'new non-executable CPU fixture')
        lock = task_runtime.requirements('qwen-image-2.1').read_bytes()
        (directory / 'requirements.lock').write_bytes(lock)
        record = dict(adapter_id='qwen-image-2.1', status='ready', packages=actual,
            cuda_available=True, lock_sha256=hashlib.sha256(lock).hexdigest())
        (directory / 'environment.json').write_text(json.dumps(record), 'utf8')
        self.assertEqual(task_runtime.environment(self.home, 'qwen-image-2.1')['status'], 'ready')
        del record['packages']['torchvision']
        (directory / 'environment.json').write_text(json.dumps(record), 'utf8')
        self.assertEqual(task_runtime.environment(self.home, 'qwen-image-2.1')['status'], 'unverified')

    def test_unverified_advisory_does_not_deny_first_local_attempt_but_runtime_does(self):
        tasks = TaskInference.__new__(TaskInference)
        tasks.home = self.home
        tasks.base = self.home / 'task-runs'
        tasks.base.mkdir()
        tasks.owner = types.SimpleNamespace(handle=True)
        tasks.lock, tasks.closed, tasks.wake = threading.RLock(), threading.Event(), threading.Event()
        with patch.object(task_runtime, 'environment', return_value={'status': 'ready'}):
            catalog = next(item for item in adapters.catalog(self.home) if item['id'] == 'qwen-image-2.1')
            self.assertFalse(catalog['execution_verified'])
            self.assertTrue(catalog['execution_advisories'])
            self.assertEqual(catalog['execution_blockers'], [])
            self.assertEqual(catalog['execution_eligibility'], 'requires_run_preflight')
            self.assertEqual(catalog['memory_requirements'], image_worker.MEMORY_REQUIREMENTS)
            run = tasks.create_registered({'prompt': 'Fresh CPU queue contract, no inference.'}, 'qwen-image-2.1', {})
            self.assertEqual(run['status'], 'queued')
        with patch.object(task_runtime, 'environment', return_value={'status': 'unverified'}):
            with self.assertRaisesRegex(ValueError, 'adapter_runtime_not_ready'):
                tasks.create_registered({'prompt': 'Another fresh CPU queue contract.'}, 'qwen-image-2.1', {})
        self.assertEqual(len(list(tasks.base.glob('*/state.json'))), 1)

    def test_real_worker_resource_gate_stops_before_model_loading(self):
        data = b'Fresh CPU-only resource rejection input'
        digest = hashlib.sha256(data).hexdigest()
        (self.home / 'input.txt').write_bytes(data)
        request = dict(run_id='new_resource_gate', input_sha256=digest, model_path=str(self.home / 'model'),
            parameters=image_safe.PARAMETERS, input_metadata=dict(bytes=len(data), sha256=digest))
        path = self.home / 'request.json'
        path.write_text(json.dumps(request), 'utf8')
        torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True,
            is_bf16_supported=lambda: True, mem_get_info=lambda _: (6 * image_worker.GIB, 8 * image_worker.GIB)))
        psutil = types.SimpleNamespace(virtual_memory=lambda: types.SimpleNamespace(available=64 * image_worker.GIB))
        with patch.dict(sys.modules, {'torch': torch, 'psutil': psutil}), \
             patch.object(image_worker, 'check_model_index'), patch.object(image_worker, 'check_runtime', return_value={}), \
             patch.object(image_worker, 'load_pipeline') as load:
            self.assertEqual(image_worker.run(path), 1)
            load.assert_not_called()
        self.assertEqual(json.loads((self.home / 'result.json').read_text('utf8'))['error'], 'memory_budget_unavailable')


if __name__ == '__main__':
    unittest.main()
