"""New synthetic contracts only; these tests do not load Llama or use a GPU."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'ai_manager' / 'llm_worker.py'
SPEC = importlib.util.spec_from_file_location('llm_worker_contract', SOURCE)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class Tensor:
    def __init__(self, ids):
        self.ids = ids
        self.shape = (1, len(ids))

    def to(self, device):
        return self

    def __getitem__(self, key):
        return Tensor(self.ids[key[1]])

    def tolist(self):
        return self.ids


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        self.run.mkdir()
        self.model = self.root / 'model'
        self.model.mkdir()
        for name, data in {
            'config.json': {'model_type': 'llama', 'architectures': ['LlamaForCausalLM']},
            'tokenizer_config.json': {}, 'tokenizer.json': {},
            'model.safetensors.index.json': {'weight_map': {'x': 'model-00001-of-00001.safetensors'}},
        }.items():
            (self.model / name).write_text(json.dumps(data), 'utf8')
        (self.model / 'model-00001-of-00001.safetensors').write_bytes(b'synthetic-not-a-model')
        self.data = '이번 실행에서 새로 만든 한국어 입력'.encode('utf8')
        self.request = dict(run_id='new-contract-run', input_sha256=hashlib.sha256(self.data).hexdigest(),
            parameters=dict(worker.PARAMETERS), model_path=str(self.model),
            input_metadata=dict(bytes=len(self.data), sha256=hashlib.sha256(self.data).hexdigest()))
        (self.run / 'input.txt').write_bytes(self.data)

    def test_integrity_and_parameter_boundary(self):
        self.assertIn('한국어', worker.validate_request(self.request, self.run))
        (self.run / 'input.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '^input_changed$'):
            worker.validate_request(self.request, self.run)
        self.request['parameters']['do_sample'] = 0
        with self.assertRaisesRegex(ValueError, '^request_invalid$'):
            worker.validate_request(self.request, self.run)

    def test_empty_utf8_and_size_rejected(self):
        for data in (b' ', b'\xff', b'\x00', b'x' * 8193):
            (self.run / 'input.txt').write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.request.update(input_sha256=digest, input_metadata={'bytes': len(data), 'sha256': digest})
            with self.assertRaises(ValueError):
                worker.validate_request(self.request, self.run)

    def test_manifest_traversal_and_remote_code_rejected(self):
        self.assertEqual(worker.validate_model(str(self.model)), self.model)
        (self.model / 'model.safetensors.index.json').write_text(
            json.dumps({'weight_map': {'x': '../other.safetensors'}}), 'utf8')
        with self.assertRaisesRegex(ValueError, '^model_invalid$'):
            worker.validate_model(str(self.model))

    def test_finish_reason_is_actual_stop(self):
        self.assertEqual(worker.finish_reason([10, 2], [2, 3]), 'eos')
        self.assertEqual(worker.finish_reason([10] * 64, [2]), 'length')
        with self.assertRaisesRegex(ValueError, '^generation_timeout$'):
            worker.finish_reason([10], [2])
        with self.assertRaisesRegex(ValueError, '^output_invalid$'):
            worker.finish_reason([], [2])

    def fake_runtime(self, count=4, cuda=False):
        self.load_kwargs = {}
        self.generate_kwargs = {}
        tensor = Tensor(list(range(count)))
        tokenizer = SimpleNamespace(pad_token_id=None,
            apply_chat_template=lambda *a, **k: {'input_ids': tensor, 'attention_mask': tensor},
            decode=lambda ids, **k: '새 응답')
        def load_model(*args, **kwargs):
            self.load_kwargs.update(kwargs)
            return model
        def generate(**kwargs):
            self.generate_kwargs.update(kwargs)
            return Tensor(list(range(count)) + [88, 2])
        model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=1024),
            generation_config=SimpleNamespace(eos_token_id=[2, 3]),
            device='cpu', hf_device_map={'': 'cpu'}, generate=generate)
        model.eval = lambda: model
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda,
            set_device=lambda _: None, reset_peak_memory_stats=lambda _: None,
            synchronize=lambda _: None, max_memory_allocated=lambda _: 123,
            get_device_name=lambda _: 'synthetic CUDA fixture', mem_get_info=lambda _: (8*1024**3,8*1024**3)),
            manual_seed=lambda _: None, float16='float16', inference_mode=contextlib.nullcontext)
        transformers = SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: tokenizer),
            LlamaForCausalLM=SimpleNamespace(from_pretrained=load_model))
        return patch.dict('sys.modules', {'torch': torch, 'transformers': transformers, 'psutil': SimpleNamespace(virtual_memory=lambda:SimpleNamespace(available=32*1024**3))})

    def test_offline_cpu_contract_new_response_and_budgets(self):
        phases = []
        with self.fake_runtime(), patch.object(worker.importlib.metadata, 'version', return_value='fixture'):
            metrics = worker.generate(self.request, self.run, phases.append)
        response = json.loads((self.run / 'response.json').read_text('utf8'))
        self.assertEqual(response, dict(text='새 응답', finish_reason='eos', input_tokens=4,
            generated_tokens=2, parameters=worker.PARAMETERS))
        self.assertEqual((self.run / 'response.txt').read_text('utf8'), '새 응답')
        self.assertEqual(phases, ['loading', 'running', 'validating'])
        self.assertTrue(metrics['cpu_fallback'])
        self.assertEqual(self.load_kwargs['max_memory'], {'cpu': '4GiB'})
        for key in ('local_files_only', 'use_safetensors', 'low_cpu_mem_usage', 'offload_state_dict'):
            self.assertIs(self.load_kwargs[key], True)
        self.assertIs(self.load_kwargs['trust_remote_code'], False)
        self.assertEqual(self.load_kwargs['offload_folder'], str(self.run / 'offload'))
        self.assertEqual(self.generate_kwargs['max_new_tokens'], 64)
        self.assertFalse(self.generate_kwargs['do_sample'])
        with self.assertRaisesRegex(ValueError, '^output_exists$'):
            worker.validate_request(self.request, self.run)

    def test_token_limit_before_model_loading(self):
        with self.fake_runtime(count=257):
            with self.assertRaisesRegex(ValueError, '^input_token_limit$'):
                worker.generate(self.request, self.run, lambda _: None)
        self.assertEqual(self.load_kwargs, {})
        self.assertFalse((self.run / 'response.json').exists())

    def test_cuda_budget_fixture_does_not_claim_gpu_execution(self):
        with self.fake_runtime(cuda=True), patch.object(worker.importlib.metadata, 'version', return_value='fixture'):
            metrics = worker.generate(self.request, self.run, lambda _: None)
        self.assertEqual(self.load_kwargs['max_memory'], {0: '3GiB', 'cpu': '4GiB'})
        self.assertTrue(metrics['cuda_available'])
        # The synthetic dispatcher selected CPU, even though CUDA was available.
        self.assertTrue(metrics['cpu_fallback'])
        self.assertEqual(metrics['placement_devices'], ['cpu'])

    def test_main_failure_has_sanitized_result(self):
        self.request['parameters']['seed'] = 1
        path = self.run / 'request.json'
        path.write_text(json.dumps(self.request), 'utf8')
        with contextlib.redirect_stderr(io.StringIO()) as captured:
            self.assertEqual(worker.main([str(path)]), 1)
        result = json.loads((self.run / 'result.json').read_text('utf8'))
        self.assertEqual(result, dict(run_id=self.request['run_id'], input_sha256=self.request['input_sha256'],
            status='failed', error='request_invalid'))
        self.assertEqual(captured.getvalue(), 'request_invalid\n')
        self.assertFalse((self.run / 'response.txt').exists())


if __name__ == '__main__':
    unittest.main()
