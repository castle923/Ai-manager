"""Fresh CPU failure reproducers; these do not prove model/GPU execution."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from ai_manager import image_diagnostics as diagnostics
from ai_manager import image_worker as worker
from ai_manager.image_safe import PARAMETERS
from ai_manager.task_inference import code_hashes


class ImageDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.secret = 'Bearer fresh-secret Cookie=session-secret https://private.invalid/a?token=signed-secret user@example.invalid C:\\private\\client.json'
        prompt = b'new synthetic prompt not for any GPU run'
        (self.directory / 'input.txt').write_bytes(prompt)
        digest = hashlib.sha256(prompt).hexdigest()
        self.request = self.directory / 'request.json'
        self.request.write_text(json.dumps(dict(run_id='fresh_cpu_failure', input_sha256=digest,
            parameters=PARAMETERS, model_path=str(self.directory / 'model'),
            input_metadata=dict(bytes=len(prompt), sha256=digest))), 'utf8')
        self.torch = types.SimpleNamespace(bfloat16='bf16', device=lambda value: value,
            manual_seed=lambda _: None, cuda=types.SimpleNamespace(is_available=lambda: True,
            is_bf16_supported=lambda: True, reset_peak_memory_stats=lambda: None,
            is_initialized=lambda: False, synchronize=lambda: None))
        self.psutil = types.SimpleNamespace(Process=lambda: types.SimpleNamespace(memory_info=lambda: types.SimpleNamespace(rss=17)),
            virtual_memory=lambda: types.SimpleNamespace(available=29))

    def fake_modules(self, failure_stage):
        secret = self.secret
        def fail():
            try:
                raise KeyError(secret)
            except KeyError as cause:
                raise RuntimeError(secret) from cause
        def component(name):
            class Component:
                @classmethod
                def from_pretrained(cls, *args, **kwargs):
                    if name == failure_stage:
                        fail()
                    return cls()
                def eval(self):
                    return self
                hf_device_map = {'secret-module-name': 0, 'other-name': 'disk'}
            return Component
        class Pipeline:
            def __init__(self, **kwargs):
                if failure_stage == 'pipeline_construct':
                    fail()
            def set_progress_bar_config(self, **kwargs):
                if failure_stage == 'pipeline_configure':
                    fail()
        def cpu_offload(*args, **kwargs):
            if failure_stage == 'vae_offload':
                fail()
        return {'torch': self.torch, 'psutil': self.psutil,
            'diffusers': types.SimpleNamespace(QwenImage21Transformer2DModel=component('transformer_load'),
                AutoencoderKLQwenImage21=component('vae_load'), FlowMatchEulerDiscreteScheduler=component('scheduler_load'),
                QwenImage21Pipeline=Pipeline),
            'transformers': types.SimpleNamespace(Qwen3VLForConditionalGeneration=component('text_encoder_load'),
                Qwen3VLProcessor=component('processor_load')),
            'accelerate': types.SimpleNamespace(cpu_offload=cpu_offload)}

    def run_failure(self, stage, opt_in='1', diagnostic_open_error=False):
        model = self.directory / 'model'
        model.mkdir(exist_ok=True)
        (model / 'model_index.json').write_text('{}', 'utf8')
        stderr = io.StringIO()
        with patch.dict(os.environ, {'AI_MANAGER_IMAGE_DIAGNOSTICS': opt_in}), \
             patch.dict(sys.modules, self.fake_modules(stage)), \
             patch.object(worker, 'check_model_index'), \
             patch.object(worker, 'check_runtime', return_value={}), \
             patch.object(worker, 'memory_preflight', return_value={}), \
             contextlib.redirect_stderr(stderr):
            if diagnostic_open_error:
                with patch.object(diagnostics.os, 'open', side_effect=OSError(self.secret)):
                    code = worker.run(self.request)
            else:
                code = worker.run(self.request)
        return code, json.loads((self.directory / 'result.json').read_text('utf8')), stderr.getvalue()

    def test_every_loading_failure_retains_exact_substage_type_and_cause_without_values(self):
        stages = ('transformer_load', 'text_encoder_load', 'vae_load', 'vae_offload',
            'processor_load', 'scheduler_load', 'pipeline_construct', 'pipeline_configure')
        original = tempfile.tempdir
        for stage in stages:
            with self.subTest(stage=stage):
                # Each subcase owns a fresh run directory; no old outputs feed
                # this run, and the synthetic modules never load real weights.
                prior = self.directory
                self.directory = prior / stage
                self.directory.mkdir()
                self.request = self.directory / 'request.json'
                data = json.loads((prior / 'request.json').read_text('utf8'))
                data['model_path'] = str(self.directory / 'model')
                self.request.write_text(json.dumps(data), 'utf8')
                (self.directory / 'input.txt').write_bytes((prior / 'input.txt').read_bytes())
                code, result, stderr = self.run_failure(stage)
                self.assertEqual((code, result['status'], result['error']), (1, 'failed', 'inference_failed'))
                self.assertEqual(stderr, 'inference_failed\n')
                self.assertEqual(tempfile.tempdir, original)
                text = (self.directory / 'image-diagnostics.jsonl').read_text('utf8')
                event = json.loads(text.splitlines()[-1])
                self.assertEqual((event['event'], event['stage']), ('failure', stage))
                self.assertEqual([x['type'] for x in event['exceptions']], ['RuntimeError', 'KeyError'])
                self.assertEqual(event['exceptions'][0]['next'], 'cause')
                self.assertTrue(event['exceptions'][0]['frames'])
                for value in (self.secret, 'fresh-secret', 'signed-secret', 'session-secret', 'user@example.invalid',
                              str(prior), 'new synthetic prompt', 'secret-module-name'):
                    self.assertNotIn(value, text + stderr + json.dumps(result))
                self.directory = prior
                self.request = prior / 'request.json'

    def test_opt_in_disabled_has_no_diagnostic_file_and_same_result(self):
        code, result, stderr = self.run_failure('processor_load', opt_in='0')
        self.assertEqual((code, result['error'], stderr), (1, 'inference_failed', 'inference_failed\n'))
        self.assertFalse((self.directory / 'image-diagnostics.jsonl').exists())

    def test_io_failure_preserves_result_and_tempdir_cleanup(self):
        original = tempfile.tempdir
        code, result, stderr = self.run_failure('vae_offload', diagnostic_open_error=True)
        self.assertEqual((code, result['error'], stderr), (1, 'inference_failed', 'inference_failed\n'))
        self.assertEqual(tempfile.tempdir, original)
        self.assertNotIn(self.secret, json.dumps(result) + stderr)

    def test_existing_file_is_preserved(self):
        path = self.directory / 'image-diagnostics.jsonl'
        path.write_text('preserved', 'utf8')
        self.run_failure('transformer_load')
        self.assertEqual(path.read_text('utf8'), 'preserved')

    def test_log_bounds_and_private_mode(self):
        with patch.dict(os.environ, {'AI_MANAGER_IMAGE_DIAGNOSTICS': '1'}):
            log = diagnostics.ImageDiagnostics(self.directory)
            for _ in range(500):
                log.mark('processor_load')
            log.close()
        path = self.directory / 'image-diagnostics.jsonl'
        self.assertLessEqual(path.stat().st_size, diagnostics.MAX_BYTES)
        self.assertLessEqual(len(path.read_text('utf8').splitlines()), diagnostics.MAX_EVENTS)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_write_failure_and_exception_format_failure_are_non_fatal(self):
        with patch.dict(os.environ, {'AI_MANAGER_IMAGE_DIAGNOSTICS': '1'}):
            log = diagnostics.ImageDiagnostics(self.directory)
            log.stream.close()
            log.mark('processor_load')
            log.failure(RuntimeError(self.secret), 'inference_failed')
            log.close()
            with patch.object(diagnostics, 'exception_structure', side_effect=ValueError(self.secret)):
                log.failure(RuntimeError(self.secret), 'inference_failed')

    def test_run_provenance_hash_includes_diagnostics_module(self):
        hashes = code_hashes('qwen-image-2.1')
        self.assertEqual(hashes['image_diagnostics.py'], hashlib.sha256(Path(diagnostics.__file__).read_bytes()).hexdigest())

    def test_dynamic_type_and_module_cannot_smuggle_private_values(self):
        for module in ('builtins', 'torch.FAKE_SECRET_SENTINEL', 'private.FAKE_SECRET_SENTINEL'):
            kind = type('ApiKey_FAKE_SECRET_SENTINEL', (Exception,), {'__module__': module})
            value = json.dumps(diagnostics.exception_structure(kind(self.secret)))
            self.assertNotIn('FAKE_SECRET_SENTINEL', value)
            self.assertNotIn(self.secret, value)
            self.assertEqual(json.loads(value)[0]['type'], 'ExternalError')
        namespace = {'__name__': 'torch.FAKE_SECRET_SENTINEL'}
        exec('def raise_error():\n    raise ImportError("private-message")', namespace)
        try:
            namespace['raise_error']()
        except ImportError as error:
            value = json.dumps(diagnostics.exception_structure(error))
        self.assertNotIn('FAKE_SECRET_SENTINEL', value)
        self.assertNotIn('private-message', value)
        with patch.dict(os.environ, {'AI_MANAGER_IMAGE_DIAGNOSTICS': '1'}), \
             patch.object(diagnostics.importlib.metadata, 'version', return_value='FAKE_SECRET_SENTINEL'):
            log = diagnostics.ImageDiagnostics(self.directory)
            log.runtime()
            log.close()
        self.assertNotIn('FAKE_SECRET_SENTINEL', (self.directory / 'image-diagnostics.jsonl').read_text('utf8'))

    def test_missing_vision_backend_stops_before_any_weight_load(self):
        modules = self.fake_modules(None)
        weights = []
        class Weights:
            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                weights.append('unexpected weight load')
                raise AssertionError('weights must not load before processor preflight')
        class Processor:
            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                raise ImportError('AutoVideoProcessor requires torchvision ' + self.secret)
        modules['transformers'].Qwen3VLProcessor = Processor
        modules['diffusers'].QwenImage21Transformer2DModel = Weights
        model = self.directory / 'model'
        model.mkdir()
        with patch.dict(sys.modules, modules):
            with self.assertRaises(ImportError):
                worker.load_pipeline(model, self.directory, self.torch)
        self.assertEqual(weights, [])
        self.assertFalse((self.directory / 'image-offload').exists())

    def test_runtime_gate_requires_exact_matching_torchvision_package(self):
        source = self.directory / 'official_pipeline_fixture.py'
        source.write_bytes(b'new small synthetic source fixture')
        package = types.ModuleType('diffusers')
        pipelines = types.ModuleType('diffusers.pipelines')
        qwen = types.ModuleType('diffusers.pipelines.qwenimage21')
        pipeline = types.ModuleType('diffusers.pipelines.qwenimage21.pipeline_qwenimage21')
        pipeline.__file__ = str(source)
        package.pipelines = pipelines
        pipelines.qwenimage21 = qwen
        qwen.pipeline_qwenimage21 = pipeline
        packages = {'torch': '2.9.1+cu128', 'torchvision': '0.24.1+cu128', 'transformers': '5.17.0',
            'accelerate': '1.12.0', 'safetensors': '0.8.0', 'Pillow': '11.3.0', 'psutil': '7.2.2'}
        def version(name):
            if name not in packages:
                raise worker.importlib.metadata.PackageNotFoundError(name)
            return packages[name]
        modules = {item.__name__: item for item in (package, pipelines, qwen, pipeline)}
        with patch.dict(sys.modules, modules), patch.object(worker, 'PIPELINE_SOURCE_SHA256', hashlib.sha256(source.read_bytes()).hexdigest()), \
             patch.object(worker.importlib.metadata, 'version', side_effect=version):
            self.assertEqual(worker.check_runtime()['torchvision'], '0.24.1+cu128')
            packages['torchvision'] = '0.24.0+cu128'
            with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch'):
                worker.check_runtime()
            del packages['torchvision']
            with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch') as caught:
                worker.check_runtime()
            self.assertIsInstance(caught.exception.__cause__, worker.importlib.metadata.PackageNotFoundError)


if __name__ == '__main__':
    unittest.main()
