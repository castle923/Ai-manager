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
                 + "raise RuntimeError('live_source_executed')\n")
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
        self.assertEqual(output.getvalue().count('__PHASE_SKIPPED__'), 3)
        self.assertTrue(all(namespace[name] is False for name in (
            'USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU', 'USER_CONFIRMED_FREE_T4',
            'USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT', 'ALLOW_RUNTIME_DOWNLOAD',
            'ALLOW_MODEL_DOWNLOAD', 'ALLOW_MODEL_EXECUTION')))
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


if __name__ == '__main__':
    unittest.main()
