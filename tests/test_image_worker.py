"""Fresh synthetic contracts only; no model weights, CUDA, or network."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib

from ai_manager import image_safe as safe
from ai_manager import image_worker as worker


def png_bytes(width=512, height=512, color=2, interlace=0, raw=None):
    def chunk(name, body):
        return struct.pack('>I', len(body)) + name + body + struct.pack('>I', zlib.crc32(name + body) & 0xffffffff)
    channels = 3 if color == 2 else 4
    raw = raw if raw is not None else (b'\0' + b'\x44' * (width * channels)) * height
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, color, 0, 0, interlace)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class ImageSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(setattr, tempfile, 'tempdir', tempfile.tempdir)

    def prompt(self, text):
        path = self.directory / 'input.txt'
        path.write_bytes(text.encode('utf8'))
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_utf8_character_and_byte_boundaries(self):
        path, digest = self.prompt('한' * 2000)
        self.assertEqual(len(safe.read_prompt(path, digest, {'bytes': 6000, 'sha256': digest})), 2000)
        path, digest = self.prompt('한' * 2001)
        with self.assertRaisesRegex(ValueError, 'input_prompt_invalid'):
            safe.read_prompt(path, digest)
        path, digest = self.prompt('a' * 8193)
        with self.assertRaisesRegex(ValueError, 'input_prompt_invalid'):
            safe.read_prompt(path, digest)

    def test_bad_hash_metadata_and_controls(self):
        path, digest = self.prompt('새로운 입력')
        for sha, metadata in [('0' * 64, None), (digest, {'bytes': 1, 'sha256': digest})]:
            with self.assertRaisesRegex(ValueError, 'input_changed'):
                safe.read_prompt(path, sha, metadata)
        path, digest = self.prompt('hello\x00')
        with self.assertRaisesRegex(ValueError, 'input_prompt_invalid'):
            safe.read_prompt(path, digest)

    def test_parameters_reject_bool_and_unbounded_changes(self):
        self.assertEqual(safe.validate_parameters(dict(safe.PARAMETERS)), safe.PARAMETERS)
        for changed in ({'seed': False}, {'width': 2048}, {'num_inference_steps': 40}, {'custom_pipeline': 'remote'}):
            with self.assertRaisesRegex(ValueError, 'input_parameters_invalid'):
                safe.validate_parameters({**safe.PARAMETERS, **changed})

    def test_png_rgb_rgba_and_bounded_decode(self):
        path = self.directory / 'image.png'
        for color, mode in [(2, 'RGB'), (6, 'RGBA')]:
            path.write_bytes(png_bytes(color=color))
            self.assertEqual(safe.validate_png(path)['mode'], mode)
        for data in [png_bytes(width=32), png_bytes(interlace=1), png_bytes() + b'extra',
                     png_bytes(raw=b'\0' * (4 * 1024 * 1024)), png_bytes()[:-12]]:
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'output_invalid'):
                safe.validate_png(path)
        data = bytearray(png_bytes())
        data[45] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'output_invalid'):
            safe.validate_png(path)

    def test_output_publication_never_overwrites(self):
        path = self.directory / 'image.json'
        worker.publish_bytes(path, b'first')
        with self.assertRaises(FileExistsError):
            worker.publish_bytes(path, b'second')
        self.assertEqual(path.read_bytes(), b'first')

    def request(self):
        path, digest = self.prompt('새로 만든 합성 테스트 입력')
        request = dict(run_id='fresh_synthetic_run', input_sha256=digest,
                       model_path=str(self.directory / 'synthetic-model'), parameters=dict(safe.PARAMETERS),
                       input_metadata=dict(bytes=path.stat().st_size, sha256=digest))
        request_path = self.directory / 'request.json'
        request_path.write_text(json.dumps(request), 'utf8')
        return request_path, request

    def test_worker_rejects_modified_prompt_before_loading(self):
        request_path, _ = self.request()
        (self.directory / 'input.txt').write_text('변경', 'utf8')
        with patch.object(worker, 'load_pipeline') as load:
            self.assertEqual(worker.run(request_path), 1)
            load.assert_not_called()
        result = json.loads((self.directory / 'result.json').read_text('utf8'))
        self.assertEqual(result['error'], 'input_changed')

    def test_worker_synthetic_success_and_cfg_mapping(self):
        request_path, request = self.request()
        class FreshImage:
            mode = 'RGB'
            size = (512, 512)
            def tobytes(self): return b'\x44' * (512 * 512 * 3)
            def save(self, stream, **kwargs): stream.write(png_bytes())
        calls = []
        def pipeline(**kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(images=[FreshImage()])
        class Generator:
            def __init__(self, device): self.device = device
            def manual_seed(self, seed): return self
        class Context:
            def __enter__(self): pass
            def __exit__(self, *args): pass
        torch = types.SimpleNamespace(cuda=types.SimpleNamespace(
            is_available=lambda: True, is_bf16_supported=lambda: True,
            reset_peak_memory_stats=lambda: None, synchronize=lambda: None,
            max_memory_allocated=lambda: 1234, max_memory_reserved=lambda: 2345,
            get_device_name=lambda _: 'synthetic-device'), manual_seed=lambda _: None,
            Generator=Generator, inference_mode=Context)
        psutil = types.SimpleNamespace(Process=lambda: types.SimpleNamespace(
            memory_info=lambda: types.SimpleNamespace(rss=100, peak_wset=200)))
        pil = types.SimpleNamespace(Image=types.SimpleNamespace(frombytes=lambda *args: FreshImage()))
        with patch.dict(sys.modules, {'torch': torch, 'psutil': psutil, 'PIL': pil}), \
             patch.object(worker, 'check_model_index'), patch.object(worker, 'check_runtime', return_value={}), \
             patch.object(worker, 'memory_preflight', return_value={}), patch.object(worker, 'load_pipeline', return_value=pipeline):
            self.assertEqual(worker.run(request_path), 0)
        result = json.loads((self.directory / 'result.json').read_text('utf8'))
        self.assertEqual(result['status'], 'generated')
        self.assertEqual(result['input_sha256'], request['input_sha256'])
        self.assertEqual(calls[0]['true_cfg_scale'], 4.0)
        self.assertEqual(calls[0]['negative_prompt'], '')
        self.assertNotIn('guidance_scale', calls[0])
        metadata = safe.validate_image_metadata(self.directory / 'image.json', request['input_sha256'])
        self.assertFalse(metadata['quality_assessed'])
        self.assertFalse(metadata['conditions']['hardware_recipe_e2e_verified'])
        self.assertFalse(metadata['conditions']['memory_budget_is_os_hard_quota'])

    def test_load_components_local_and_disk_bounded(self):
        model = self.directory / 'synthetic-model'
        model.mkdir()
        (model / 'model_index.json').write_text('{}', 'utf8')
        calls = {}
        def component(name):
            class Component:
                @classmethod
                def from_pretrained(cls, path, **kwargs):
                    calls[name] = kwargs
                    return cls()
                def eval(self): return self
            return Component
        class Pipeline:
            def __init__(self, **kwargs): calls['pipeline'] = kwargs
            def set_progress_bar_config(self, **kwargs): pass
        diffusers = types.SimpleNamespace(QwenImage21Pipeline=Pipeline,
                    QwenImage21Transformer2DModel=component('transformer'),
                    AutoencoderKLQwenImage21=component('vae'), FlowMatchEulerDiscreteScheduler=component('scheduler'))
        transformers = types.SimpleNamespace(Qwen3VLForConditionalGeneration=component('text_encoder'), Qwen3VLProcessor=component('processor'))
        torch = types.SimpleNamespace(bfloat16='bf16', device=lambda value: value)
        accelerate = types.SimpleNamespace(cpu_offload=lambda *args, **kwargs: None)
        with patch.dict(sys.modules, {'diffusers': diffusers, 'transformers': transformers, 'accelerate': accelerate}):
            worker.load_pipeline(model, self.directory, torch)
        for name in ('text_encoder', 'transformer', 'vae', 'processor', 'scheduler'):
            self.assertIs(calls[name]['local_files_only'], True)
        for name in ('text_encoder', 'transformer', 'vae'):
            self.assertIs(calls[name]['use_safetensors'], True)
        for name in ('text_encoder', 'transformer'):
            self.assertEqual(calls[name]['device_map'], 'auto')
            self.assertEqual(calls[name]['max_memory'], worker.PLACEMENT[name])
            self.assertIn('offload_folder', calls[name])
        self.assertNotIn('offload_state_dict', calls['text_encoder'])
        self.assertIs(calls['transformer']['offload_state_dict'], True)
        self.assertIs(calls['text_encoder']['trust_remote_code'], False)


if __name__ == '__main__':
    unittest.main()
