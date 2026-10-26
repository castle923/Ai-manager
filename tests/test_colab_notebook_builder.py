"""Synthetic packet fixtures only; no private inputs or live notebook execution."""
import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/colab/build_llama_watchdog_notebook.py'
spec = importlib.util.spec_from_file_location('notebook_builder', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NotebookBuilderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='notebook-builder-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.r02 = self.root / 'r02'; self.r02.mkdir()
        self.output = self.root / 'packet'
        self.guard = self.root / 'guard.py'; self.guard.write_bytes(b'# synthetic guard\n')
        self.original = self.root / 'original.ipynb'
        assets = {
            'llama_t4_meta.py': ('# ' + m.OLD_GUARD_SHA + '\n').encode(),
            'model-manifest.json': json.dumps(dict(revision='0e9e39f249a16976918f6564b8830bc894c89659',
                files=[dict(path=str(i), size=16_069_722_660 if i == 0 else 1) for i in range(10)])).encode(),
        }
        payload = {name: dict(sha256=m.digest(raw), compressed_b64=base64.b64encode(zlib.compress(raw)).decode())
                   for name, raw in assets.items()}
        setup = ('USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True\n# Diagnostic-only\n'
                 + 'PAYLOADS=' + repr(payload) + '\n'
                 + "raise RuntimeError('live_source_executed')\nMETA_RESULT=subprocess.run([])\n")
        self.original.write_text(json.dumps(dict(cells=[{}, dict(source=setup.splitlines(True))])), encoding='utf8')
        replacements = {}
        for key, (filename, _) in m.R02_INPUTS.items():
            raw = ("controlled_attempt='cache-safe-r02 after r01 load-stage memory-floor stop'\n"
                   if key == 'llama_worker.py' else '# synthetic helper\n').encode()
            (self.r02 / filename).write_bytes(raw)
            replacements[key] = (filename, m.digest(raw))
        for name, value in [('ORIGINAL_SHA', m.digest(self.original.read_bytes())),
                            ('GUARD_SHA', m.digest(self.guard.read_bytes())),
                            ('R02_INPUTS', replacements)]:
            p = patch.object(m, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(m.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 601_000_000_000})())
        p.start(); self.addCleanup(p.stop)

    def build(self):
        result = m.build_packet(self.original, self.r02, self.guard, self.output)
        notebook = json.loads((self.output / 'upload' / m.NAME).read_text(encoding='utf8'))
        return result, notebook

    def test_default_run_all_is_stdlib_only_and_skips_all_live_phases(self):
        _, notebook = self.build()
        import builtins
        original_import = builtins.__import__
        denied = {'torch', 'transformers', 'subprocess', 'getpass', 'socket', 'requests', 'pip'}
        def checked_import(name, *args, **kwargs):
            if name.split('.')[0] in denied:
                self.fail('live import attempted: ' + name)
            return original_import(name, *args, **kwargs)
        namespace = {}
        output = io.StringIO()
        with patch('builtins.__import__', side_effect=checked_import), \
             patch('builtins.open', side_effect=AssertionError('file IO attempted')), \
             contextlib.redirect_stdout(output):
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    exec(compile(''.join(cell['source']), '<offline-cell>', 'exec'), namespace)
        self.assertIn('__OFFLINE_PACKET_VALIDATED__', output.getvalue())
        self.assertEqual(output.getvalue().count('__PHASE_SKIPPED__'), 4)
        self.assertEqual(output.getvalue().count('__RESULT_CHECK_SKIPPED__'), 1)
        self.assertTrue(all(namespace[name] is False for name in (
            'USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU', 'USER_CONFIRMED_FREE_T4',
            'USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT', 'ALLOW_RUNTIME_DOWNLOAD',
            'ALLOW_FULL_PREFLIGHT', 'ALLOW_MODEL_DOWNLOAD', 'ALLOW_MODEL_EXECUTION')))
        self.assertNotIn('ROOT', namespace)

    def test_packet_shape_empty_outputs_ids_and_exact_guard_bytes(self):
        result, notebook = self.build()
        ids = [cell['id'] for cell in notebook['cells']]
        self.assertEqual(len(ids), len(set(ids)))
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                ast.parse(''.join(cell['source']))
                self.assertIsNone(cell['execution_count'])
                self.assertEqual(cell['outputs'], [])
        source = ''.join(notebook['cells'][1]['source'])
        payloads = ast.literal_eval(m.assignment(source, 'PAYLOADS').value)
        actual = zlib.decompress(base64.b64decode(payloads['llama_watchdog.py']['compressed_b64']))
        self.assertEqual(actual, self.guard.read_bytes())
        self.assertEqual(result['canonical_watchdog_sha256'], m.GUARD_SHA)

    def test_tampered_payload_fails_before_phase_controls(self):
        _, notebook = self.build()
        source = ''.join(notebook['cells'][1]['source'])
        payloads = ast.literal_eval(m.assignment(source, 'PAYLOADS').value)
        payloads['llama_watchdog.py']['compressed_b64'] = base64.b64encode(zlib.compress(b'# tampered')).decode()
        source = m.replace_assignment(source, 'PAYLOADS', 'PAYLOADS=' + repr(payloads))
        with self.assertRaises(AssertionError):
            exec(compile(source, '<synthetic>', 'exec'), {})

    def test_input_hash_mismatch_does_not_create_output(self):
        self.guard.write_bytes(b'# changed')
        with self.assertRaisesRegex(ValueError, 'source_hash_mismatch'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_output_is_exclusive_and_existing_files_unchanged(self):
        self.build()
        target = self.output / 'upload' / m.NAME
        before = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'new_absolute_output_required'):
            self.build()
        self.assertEqual(target.read_bytes(), before)

    def test_disk_reserve_includes_all_serialized_files_and_allowance(self):
        self.build()
        serialized_bytes=sum(p.stat().st_size for p in self.output.rglob('*') if p.is_file())
        threshold=m.MINIMUM_FREE_BYTES+serialized_bytes+m.FILESYSTEM_ALLOWANCE_BYTES
        self.output=self.root/'boundary-pass'
        with patch.object(m.shutil,'disk_usage',return_value=type('Disk',(),{'free':threshold})()):
            self.build()
        self.output=self.root/'boundary-fail'
        with patch.object(m.shutil,'disk_usage',return_value=type('Disk',(),{'free':threshold-1})()):
            with self.assertRaisesRegex(ValueError,'C_reserve_not_met'):self.build()
        self.assertFalse(self.output.exists())

    def test_oversized_packet_is_rejected_before_creating_output(self):
        with patch.object(m,'INTRO','x'*(2*1024**2)),patch.object(m.shutil,'disk_usage',
                return_value=type('Disk',(),{'free':m.MINIMUM_FREE_BYTES+m.FILESYSTEM_ALLOWANCE_BYTES+1024**2})()):
            with self.assertRaisesRegex(ValueError,'C_reserve_not_met'):self.build()
        self.assertFalse(self.output.exists())

    def test_readonly_helper_tamper_is_rejected_before_output(self):
        with patch.object(m,'RESULT_HELPER_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'source_hash_mismatch'):self.build()
        self.assertFalse(self.output.exists())

    def test_fresh_execution_flow_has_no_resume_state_and_preserves_guards(self):
        self.assertNotIn('ORIGINAL_SUMMARY', m.EXECUTE)
        self.assertNotIn('RESUME_', m.EXECUTE)
        self.assertLess(m.EXECUTE.index('hint_exact_downloaded_shards'), m.EXECUTE.index('memory_sample'))
        self.assertLess(m.EXECUTE.index('memory_sample'), m.EXECUTE.index('run_owned'))
        for contract in ('timeout_seconds=600', 'handshake_seconds=240', 'interval_seconds=.2',
                         'os_floor_bytes=2*1024**3', 'hard_rss_cap_bytes=8*1024**3',
                         "open('x')", 'exist_ok=False'):
            self.assertIn(contract, m.EXECUTE)
        for forbidden in ('getpass', 'download_fixed', 'pip'):
            self.assertNotIn(forbidden, m.EXECUTE)

    def test_live_gate_checks_precede_side_effect_sources(self):
        for source, flag in [(m.DOWNLOAD, 'ALLOW_MODEL_DOWNLOAD'), (m.EXECUTE, 'ALLOW_MODEL_EXECUTION')]:
            with self.subTest(flag=flag), self.assertRaises(AssertionError):
                exec(compile(source, '<disabled-phase>', 'exec'), {flag: False})
        with self.assertRaisesRegex(AssertionError, 'runtime_download_disabled'):
            result, nb = self.build()
            runtime_cell = ''.join(nb['cells'][4]['source'])
            live = ast.literal_eval(m.assignment(runtime_cell, 'LIVE_SOURCE').value)
            exec(compile(live, '<disabled-runtime>', 'exec'), {'ALLOW_RUNTIME_DOWNLOAD': False})

    def test_controls_preserve_run_context_for_normal_stage_flag_changes(self):
        namespace = {name: object() for name in (
            'ROOT', 'DOWNLOAD', 'MODEL', 'WORK', 'FRESH_META', 'FRESH_META_TIME',
            'RUNTIME_CONTEXT', 'DOWNLOAD_CONTEXT')}
        exec(m.CONTROLS, namespace)
        self.assertTrue(all(name in namespace for name in (
            'ROOT', 'DOWNLOAD', 'MODEL', 'WORK', 'FRESH_META', 'FRESH_META_TIME',
            'RUNTIME_CONTEXT', 'DOWNLOAD_CONTEXT')))

    def test_failed_runtime_cannot_reuse_previous_download_or_timestamp(self):
        _, notebook = self.build()
        namespace = dict(ALLOW_RUNTIME_DOWNLOAD=True,
            USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
            USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True,
            ROOT='old', DOWNLOAD={'status': 'completed'}, FRESH_META_TIME=123,
            RUNTIME_CONTEXT=('old',), DOWNLOAD_CONTEXT=('old',), PAYLOADS={})
        with self.assertRaisesRegex(RuntimeError, 'live_source_executed'):
            exec(''.join(notebook['cells'][4]['source']), namespace)
        for name in ('DOWNLOAD', 'FRESH_META_TIME', 'RUNTIME_CONTEXT', 'DOWNLOAD_CONTEXT'):
            self.assertNotIn(name, namespace)

    def test_execution_rejects_mixed_context_before_model_assignment(self):
        namespace = dict(ALLOW_MODEL_EXECUTION=True,
            USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
            USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True,
            DOWNLOAD=dict(status='completed', file_count=10, total_bytes=16_069_722_669,
                          full_weight_SHA_verified=True, model_path='/content/llama-t4-int8-old/model'),
            ROOT=Path('/content/llama-t4-int8-new'), pathlib=__import__('pathlib'))
        with self.assertRaisesRegex(AssertionError, 'runtime_context_missing_or_changed'):
            exec(m.EXECUTE, namespace)
        self.assertNotIn('MODEL', namespace)

    def ready_namespace(self):
        root = Path('/content/llama-t4-int8-synthetic')
        namespace = dict(ALLOW_MODEL_DOWNLOAD=True, ALLOW_MODEL_EXECUTION=True,
            USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
            USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True,
            ROOT=root, PY=root/'venv/bin/python', META=root/'metadata-proof.json',
            FRESH_META_TIME=100, FRESH_META={'status': 'INT8_preflight_candidate'},
            PAYLOADS={'test.py': {'sha256': 'synthetic'}}, env=lambda offline: {},
            json=json, pathlib=__import__('pathlib'), load_reviewed=lambda *args: None,
            DOWNLOAD=dict(status='completed', file_count=10, total_bytes=16_069_722_669,
                          full_weight_SHA_verified=True, model_path=str(root/'model')))
        namespace['RUNTIME_CONTEXT'] = eval(m.CONTEXT_VALUE, namespace)
        namespace['DOWNLOAD_CONTEXT'] = (namespace['RUNTIME_CONTEXT'], namespace['load_reviewed'])
        return namespace

    def test_bound_execution_prefix_accepts_normal_control_stage_changes(self):
        namespace = self.ready_namespace()
        context = namespace['RUNTIME_CONTEXT']
        exec(m.CONTROLS, namespace)
        self.assertEqual(namespace['RUNTIME_CONTEXT'], context)
        for name in ('ALLOW_MODEL_EXECUTION', 'USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU',
                     'USER_CONFIRMED_FREE_T4', 'USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT'):
            namespace[name] = True
        exec(m.EXECUTE[:m.EXECUTE.index('WORK=')], namespace)
        self.assertEqual(namespace['MODEL'], namespace['ROOT']/'model')

    def test_execution_blocks_swapped_root_timestamp_metadata_payload_and_helpers(self):
        changes = {'ROOT': Path('/content/llama-t4-int8-other'), 'FRESH_META_TIME': 101,
            'FRESH_META': {'status': 'stopped'}, 'PAYLOADS': {'test.py': {'sha256': 'changed'}},
            'env': lambda offline: {}, 'load_reviewed': lambda *args: None,
            'DOWNLOAD_CONTEXT': None}
        for name,value in changes.items():
            with self.subTest(name=name):
                namespace = self.ready_namespace();namespace[name] = value
                with self.assertRaisesRegex(AssertionError, 'context_missing_or_changed'):
                    exec(m.EXECUTE, namespace)
                self.assertNotIn('MODEL', namespace)

    def test_download_failure_invalidates_old_proof_before_reuse(self):
        namespace = self.ready_namespace()
        namespace['time'] = type('Clock', (), {'monotonic': lambda: 701})
        with self.assertRaisesRegex(AssertionError, 'fresh_preflight_expired_before_token_prompt'):
            exec(m.DOWNLOAD, namespace)
        self.assertNotIn('DOWNLOAD', namespace)
        self.assertNotIn('DOWNLOAD_CONTEXT', namespace)
        with self.assertRaisesRegex(AssertionError, 'download_context_missing_or_changed'):
            exec(m.EXECUTE, namespace)


class SourcePinTests(unittest.TestCase):
    def test_canonical_guard_pin_and_original_input_binding_are_distinct(self):
        source = SOURCE.read_text(encoding='utf-8')
        declared = ast.literal_eval(m.assignment(source, 'GUARD_SHA').value)
        self.assertEqual(declared, hashlib.sha256((SOURCE.parent/'llama_watchdog.py').read_bytes()).hexdigest())
        self.assertEqual(ast.literal_eval(m.assignment(source, 'OLD_GUARD_SHA').value),
                         'e708957971410a3594d9174e11b15cd401cbf9971f75924c9c94407478b19b14')

    def test_readonly_helper_raw_pin_matches_LF_source(self):
        source=SOURCE.read_text(encoding='utf-8')
        declared=ast.literal_eval(m.assignment(source,'RESULT_HELPER_SHA').value)
        raw=(SOURCE.parent/'file_result_check.py').read_bytes()
        self.assertNotIn(b'\r',raw)
        self.assertEqual(declared,hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
