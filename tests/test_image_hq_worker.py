"""New CPU-only HQ contracts; no weights, inference quality or GPU evidence."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from ai_manager import image_hq_worker as hq
from ai_manager import image_safe
from tests.test_image_worker import png_bytes


class HQTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        data = hq.PROMPT.encode('utf8')
        (self.directory / 'input.txt').write_bytes(data)
        self.request = dict(profile=hq.PROFILE, parameters=dict(hq.PARAMETERS), run_id='new_hq_cpu_fixture',
            model_path=str(self.directory / 'model'), input_sha256=hashlib.sha256(data).hexdigest(),
            input_metadata=dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        self.request_path = self.directory / 'request.json'
        self.request_path.write_text(json.dumps(self.request), 'utf8')
        self.torch = types.SimpleNamespace(bfloat16='bf16', cuda=types.SimpleNamespace(
            mem_get_info=lambda _: (75 * hq.GIB, 80 * hq.GIB),
            is_available=lambda: True, is_bf16_supported=lambda: True,
            reset_peak_memory_stats=lambda: None, synchronize=lambda: None,
            max_memory_allocated=lambda: 300, max_memory_reserved=lambda: 400), manual_seed=lambda _: None)
        self.psutil = types.SimpleNamespace(virtual_memory=lambda: types.SimpleNamespace(available=100 * hq.GIB),
            Process=lambda: types.SimpleNamespace(memory_info=lambda: types.SimpleNamespace(rss=100)))

    def test_exact_profile_and_prompt_do_not_relax_existing_smoke(self):
        self.assertEqual(hq.validate_request(self.request, self.directory), hq.PROMPT)
        self.assertEqual(image_safe.PARAMETERS['width'], 512)
        self.assertEqual(image_safe.PARAMETERS['num_inference_steps'], 4)
        self.assertEqual(image_safe.MAX_PNG_BYTES, 2 * 1024 * 1024)
        for changed in ({'width': 4096}, {'num_inference_steps': 41}, {'seed': 43},
                        {'num_images_per_prompt': True}, {'true_cfg_scale': 1}, {'negative_prompt': ''}, {'use_kv_cache': False}):
            request = {**self.request, 'parameters': {**hq.PARAMETERS, **changed}}
            with self.assertRaisesRegex(ValueError, 'input_parameters_invalid'):
                hq.validate_request(request, self.directory)
        with self.assertRaisesRegex(ValueError, 'input_parameters_invalid'):
            hq.validate_request({**self.request, 'profile': 'arbitrary'}, self.directory)

    def test_resource_preflight_fails_closed_for_gpu_ram_and_disk(self):
        with patch.object(hq.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=100 * hq.GIB)):
            hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic(), initial=True)
            for free, total in ((69 * hq.GIB, 80 * hq.GIB), (75 * hq.GIB, 77 * hq.GIB)):
                self.torch.cuda.mem_get_info = lambda _, free=free, total=total: (free, total)
                with self.assertRaisesRegex(ValueError, 'memory_budget_unavailable'):
                    hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic(), initial=True)
            self.torch.cuda.mem_get_info = lambda _: (75 * hq.GIB, 80 * hq.GIB)
            self.psutil.virtual_memory = lambda: types.SimpleNamespace(available=63 * hq.GIB)
            with self.assertRaisesRegex(ValueError, 'memory_budget_unavailable'):
                hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic(), initial=True)
        with patch.object(hq.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, 'memory_budget_unavailable'):
                hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic(), initial=True)

    def test_runtime_guard_and_walltime_fail_without_retry(self):
        self.torch.cuda.mem_get_info = lambda _: (3 * hq.GIB, 80 * hq.GIB)
        with self.assertRaisesRegex(ValueError, 'resource_limit_reached'):
            hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic())
        with self.assertRaisesRegex(ValueError, 'generation_timeout'):
            hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic() - 1501)
        self.torch.cuda.mem_get_info = lambda _: (75 * hq.GIB, 80 * hq.GIB)
        self.psutil.Process = lambda: types.SimpleNamespace(memory_info=lambda: types.SimpleNamespace(rss=65 * hq.GIB))
        with self.assertRaisesRegex(ValueError, 'resource_limit_reached'):
            hq.resources(self.torch, self.psutil, self.directory, hq.time.monotonic())

    def fake_pipeline(self):
        events = []
        class Tensor:
            dtype = 'bf16'
            device = types.SimpleNamespace(type='cpu', index=None)
            def is_floating_point(self): return True
        class Component:
            def __init__(self): self.tensor = Tensor()
            def modules(self): return [self]
            def parameters(self): return [self.tensor]
            def buffers(self): return []
        class Pipeline:
            def __init__(self):
                self.transformer, self.text_encoder, self.vae = Component(), Component(), Component()
            @classmethod
            def from_pretrained(cls, *args, **kwargs): events.append(('load', kwargs)); return cls()
            def to(self, device):
                events.append(('to', device))
                for model in (self.transformer, self.text_encoder, self.vae):
                    model.tensor.device = types.SimpleNamespace(type='cuda', index=0)
                return self
            def set_progress_bar_config(self, **kwargs): pass
        class Processor:
            @classmethod
            def from_pretrained(cls, *args, **kwargs): events.append(('processor', kwargs)); return cls()
        return Pipeline, Processor, events

    def test_full_gpu_loader_is_fresh_unhooked_bf16_and_no_offload_kwargs(self):
        Pipeline, Processor, events = self.fake_pipeline()
        diagnostic = types.SimpleNamespace(mark=lambda _: None)
        with patch.dict(sys.modules, {'transformers': types.SimpleNamespace(Qwen3VLProcessor=Processor),
            'diffusers': types.SimpleNamespace(QwenImage21Pipeline=Pipeline)}):
            pipeline = hq.load_pipeline(self.directory, self.torch, diagnostic, lambda: None)
        self.assertEqual([x[0] for x in events], ['processor', 'load', 'to'])
        self.assertEqual(events[-1][1], 'cuda')
        self.assertEqual(events[1][1]['dtype'], 'bf16')
        self.assertIs(events[1][1]['local_files_only'], True)
        self.assertFalse(any('offload' in key or key == 'device_map' for key in events[1][1]))
        hq.verify_full_gpu(pipeline, self.torch)
        pipeline.transformer._hf_hook = object()
        with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch'):
            hq.verify_unhooked(pipeline)

    def test_cpu_meta_or_wrong_dtype_and_device_map_are_rejected(self):
        Pipeline, _, _ = self.fake_pipeline()
        pipeline = Pipeline()
        with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch'):
            hq.verify_full_gpu(pipeline, self.torch)
        pipeline.to('cuda')
        buffer = types.SimpleNamespace(dtype='float32', device=types.SimpleNamespace(type='cuda', index=0),
            is_floating_point=lambda: True)
        pipeline.text_encoder.buffers = lambda: [buffer]
        hq.verify_full_gpu(pipeline, self.torch)  # official fp32 rotary buffer is valid
        buffer.device = types.SimpleNamespace(type='cpu', index=None)
        with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch'):
            hq.verify_full_gpu(pipeline, self.torch)
        buffer.device = types.SimpleNamespace(type='cuda', index=0)
        pipeline.vae.tensor.dtype = 'float32'
        with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch'):
            hq.verify_full_gpu(pipeline, self.torch)
        pipeline.hf_device_map = {'component': 'cpu'}
        with self.assertRaisesRegex(ValueError, 'runtime_version_mismatch'):
            hq.verify_unhooked(pipeline)

    def test_png_dimensions_and_cap_are_hq_specific(self):
        path = self.directory / 'image.png'
        path.write_bytes(png_bytes(2048, 2048))
        self.assertEqual(image_safe.validate_png(path, 2048, 2048, hq.MAX_PNG_BYTES)['width'], 2048)
        with self.assertRaisesRegex(ValueError, 'output_invalid'):
            image_safe.validate_png(path)
        with path.open('wb') as stream: stream.truncate(hq.MAX_PNG_BYTES + 1)
        with self.assertRaisesRegex(ValueError, 'output_invalid'):
            image_safe.validate_png(path, 2048, 2048, hq.MAX_PNG_BYTES)

    def success_modules(self):
        calls = []
        class Image:
            mode = 'RGB'
            size = (2048, 2048)
            def tobytes(self): return b'\x44' * (2048 * 2048 * 3)
            def save(self, stream, **kwargs): stream.write(png_bytes(2048, 2048))
        class Context:
            def __enter__(self): pass
            def __exit__(self, *args): pass
        class Generator:
            def __init__(self, device): self.device = device
            def manual_seed(self, seed): self.seed = seed; return self
        self.torch.inference_mode = Context
        self.torch.Generator = Generator
        def pipeline(**kwargs):
            calls.append(kwargs)
            callback_values = {}
            self.assertIs(kwargs['callback_on_step_end'](None, 0, None, callback_values), callback_values)
            return types.SimpleNamespace(images=[Image()])
        pil = types.SimpleNamespace(Image=types.SimpleNamespace(frombytes=lambda *args: Image()))
        return calls, pipeline, {'torch': self.torch, 'psutil': self.psutil, 'PIL': pil}

    def test_one_call_one_image_exact_official_parameters_and_metadata(self):
        calls, pipeline, modules = self.success_modules()
        with patch.dict(sys.modules, modules), patch.object(hq, 'check_model_index'), \
             patch.object(hq, 'check_runtime', return_value={}), patch.object(hq, 'load_pipeline', return_value=pipeline), \
             patch.object(hq.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=100 * hq.GIB)):
            self.assertEqual(hq.run(self.request_path), 0)
        self.assertEqual(len(calls), 1)
        value = calls[0]
        for key in ('width', 'height', 'num_inference_steps', 'true_cfg_scale', 'negative_prompt', 'use_kv_cache', 'num_images_per_prompt'):
            self.assertEqual(value[key], hq.PARAMETERS[key])
        self.assertEqual(value['generator'].seed, 42)
        metadata = hq.validate_metadata(self.directory / 'image.json', self.request['input_sha256'])
        self.assertFalse(metadata['conditions']['hardware_recipe_e2e_verified'])
        self.assertFalse(metadata['conditions']['absolute_maximum_quality_claimed'])

    def test_failure_is_not_retried_and_stderr_has_no_private_message(self):
        calls, _, modules = self.success_modules()
        def fail(**kwargs):
            calls.append(kwargs)
            raise RuntimeError('Bearer SECRET_FAKE_COOKIE https://private.invalid/?token=FAKE_SECRET')
        stderr = io.StringIO()
        with patch.dict(sys.modules, modules), patch.object(hq, 'check_model_index'), \
             patch.object(hq, 'check_runtime', return_value={}), patch.object(hq, 'load_pipeline', return_value=fail), \
             patch.object(hq.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=100 * hq.GIB)), contextlib.redirect_stderr(stderr):
            self.assertEqual(hq.run(self.request_path), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(stderr.getvalue(), 'inference_failed\n')
        result = (self.directory / 'result.json').read_text('utf8')
        self.assertNotIn('SECRET', result)
        self.assertEqual(json.loads(result)['status'], 'failed')
        self.assertFalse((self.directory / 'image.png').exists())

    def test_low_resource_run_stops_before_loading_or_calling_pipeline(self):
        self.torch.cuda.mem_get_info = lambda _: (69 * hq.GIB, 80 * hq.GIB)
        with patch.dict(sys.modules, {'torch': self.torch, 'psutil': self.psutil}), \
             patch.object(hq, 'check_model_index'), patch.object(hq, 'check_runtime', return_value={}), \
             patch.object(hq, 'load_pipeline') as load, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hq.run(self.request_path), 1)
            load.assert_not_called()
        self.assertEqual(json.loads((self.directory / 'result.json').read_text('utf8'))['error'], 'memory_budget_unavailable')


if __name__ == '__main__':
    unittest.main()
