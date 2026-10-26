import importlib.util
from pathlib import Path
import tempfile
import hashlib
import json
import subprocess
import sys
import importlib.metadata
import importlib.machinery
import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/colab/build_llama_watchdog_notebook.py'
spec = importlib.util.spec_from_file_location('reusable_builder', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RuntimeReuseTests(unittest.TestCase):
    def phases(self, install='INSTALL_CALLS=globals().get("INSTALL_CALLS",0)+1', probe='raise RuntimeError("probe_stopped")'):
        return m.runtime_phases(install, probe)

    def test_repeated_setup_revalidates_and_skips_installer(self):
        with patch.object(m, 'RECHECK_PREPARED', 'assert VALID, "prepared_context_changed"'):
            setup, _ = self.phases()
        ns = dict(ALLOW_RUNTIME_DOWNLOAD=True, VALID=True,
                  USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
                  USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True)
        exec(setup, ns)
        prepared = ns['PREPARED_CONTEXT']
        ns['FRESH_META_TIME'] = 123
        exec(setup, ns)
        self.assertEqual(ns['INSTALL_CALLS'], 1)
        self.assertEqual(ns['PREPARED_CONTEXT'], prepared)
        self.assertEqual(ns['FRESH_META_TIME'], 123)
        ns['VALID'] = False
        with self.assertRaisesRegex(AssertionError, 'prepared_context_changed'):
            exec(setup, ns)
        self.assertNotIn('FRESH_META_TIME', ns)
        self.assertNotIn('PREPARED_CONTEXT', ns)

    def test_incomplete_installation_is_not_automatically_retried(self):
        setup, _ = self.phases('INSTALL_CALLS=globals().get("INSTALL_CALLS",0)+1\nraise RuntimeError("install_failed")')
        ns = dict(ALLOW_RUNTIME_DOWNLOAD=True, USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True,
                  USER_CONFIRMED_FREE_T4=True, USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True)
        with self.assertRaisesRegex(RuntimeError, 'install_failed'):
            exec(setup, ns)
        with self.assertRaisesRegex(AssertionError, 'incomplete_preparation_preserved'):
            exec(setup, ns)
        self.assertEqual(ns['INSTALL_CALLS'], 1)

    def test_probe_failure_preserves_prepared_and_previous_proof(self):
        with tempfile.TemporaryDirectory(prefix='reuse-proof-') as temporary:
            root = Path(temporary)
            old = root / 'fresh-meta-proof.json'
            old.write_bytes(b'old proof preserved')
            with patch.object(m, 'RECHECK_PREPARED', 'assert VALID'):
                _, probe = self.phases()
            ns = dict(ALLOW_FULL_PREFLIGHT=True, ROOT=root, VALID=True,
                      PREPARED_CONTEXT=('ready',), FRESH_META_TIME=123, DOWNLOAD_CONTEXT=('old',),
                      USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
                      USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True)
            with self.assertRaisesRegex(RuntimeError, 'probe_stopped'):
                exec(probe, ns)
            self.assertEqual(ns['PREPARED_CONTEXT'], ('ready',))
            self.assertNotIn('FRESH_META_TIME', ns)
            self.assertNotIn('DOWNLOAD_CONTEXT', ns)
            self.assertEqual(old.read_bytes(), b'old proof preserved')
            self.assertEqual(len(list(root.glob('preflight-*'))), 1)

    def test_probe_disabled_does_not_import_or_touch_files(self):
        _, probe = self.phases()
        with patch('builtins.__import__', side_effect=AssertionError('imported')):
            with self.assertRaisesRegex(AssertionError, 'full_preflight_disabled'):
                exec(probe, dict(ALLOW_FULL_PREFLIGHT=False))

    def test_real_recheck_rejects_changed_context_and_payload_bytes(self):
        with tempfile.TemporaryDirectory(prefix='reuse-context-') as temporary:
            root = Path(temporary) / 'llama-t4-int8-synthetic'
            python = root / 'venv/bin/python'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'not executed')
            metadata = root / 'metadata-proof.json'
            metadata.write_bytes(b'public synthetic metadata')
            active = dict(numpy='2.0.2', transformers='4.57.3', accelerate='1.12.0',
                          huggingface_hub='0.36.2', tokenizers='0.22.2', safetensors='0.8.0',
                          bitsandbytes='0.50.2', torch='2.11.0+cu128')
            ns = dict(ROOT=root, PY=python, META=metadata, json=json, active=active,
                      BASE_INFO={n:{'path':'synthetic/'+n} for n in ('torch','numpy')},
                      PAYLOADS={metadata.name:{'sha256':hashlib.sha256(metadata.read_bytes()).hexdigest()}},
                      env=lambda offline: {})
            ns['PREPARED_CONTEXT'] = eval(m.PREPARED_VALUE, ns)
            source = m.RECHECK_PREPARED.replace("pathlib.Path('/content')", repr(root.parent))
            # Replace only the synthetic content root; production remains /content.
            source = source.replace(repr(root.parent), 'pathlib.Path('+repr(str(root.parent))+')')
            observed = json.dumps(dict(versions=active, origins={n:'synthetic/'+n for n in ('torch','numpy')}))
            with patch.object(sys, 'platform', 'linux'), patch.object(subprocess, 'run', return_value=SimpleNamespace(stdout=observed, stderr='')) as run:
                exec(source, ns)
                self.assertEqual(run.call_count, 1)
                child_code = run.call_args.args[0][-1]
                modules = {n:SimpleNamespace(__version__=active[n], __file__='synthetic/'+n,
                                             __spec__=importlib.machinery.ModuleSpec(n, loader=None, origin='synthetic/'+n))
                           for n in ('torch','numpy')}
                modules['numpy'].__version__ = 'actual-module-version-changed'
                with patch.dict(sys.modules, modules), patch.object(importlib.metadata, 'version', side_effect=active.__getitem__), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(AssertionError):
                        exec(child_code, {})
                for field, changed in [('ROOT', root/'changed'), ('PY', root/'other/python'),
                                       ('env', lambda offline: {}), ('PAYLOADS', {}),
                                       ('active', dict(active, torch='changed'))]:
                    original = ns[field]
                    ns[field] = changed
                    with self.subTest(field=field), self.assertRaisesRegex(AssertionError, 'prepared_context_changed'):
                        exec(source, ns)
                    ns[field] = original
                original_context = ns['PREPARED_CONTEXT']
                ns['ROOT'] = root.parent
                ns['PREPARED_CONTEXT'] = eval(m.PREPARED_VALUE, ns)
                with self.assertRaisesRegex(AssertionError, 'prepared_root_changed'):
                    exec(source, ns)
                ns['ROOT'], ns['PREPARED_CONTEXT'] = root, original_context
                with patch.object(subprocess, 'run', return_value=SimpleNamespace(
                        stdout=json.dumps(dict(versions=dict(active, numpy='changed'),
                                               origins={n:'synthetic/'+n for n in ('torch','numpy')})), stderr='')):
                    with self.assertRaisesRegex(AssertionError, 'prepared_runtime_changed'):
                        exec(source, ns)
                metadata.write_bytes(b'changed metadata')
                with self.assertRaisesRegex(AssertionError, 'prepared_payload_changed'):
                    exec(source, ns)
                self.assertEqual(run.call_count, 1)

    def test_failed_full_probe_clears_partially_assigned_fresh_metadata(self):
        with tempfile.TemporaryDirectory(prefix='reuse-partial-') as temporary:
            with patch.object(m, 'RECHECK_PREPARED', 'assert VALID'):
                _, probe = self.phases(probe='FRESH_META={"status":"stopped"}\nraise RuntimeError("memory_stop")')
            ns = dict(ALLOW_FULL_PREFLIGHT=True, VALID=True, ROOT=Path(temporary),
                      PREPARED_CONTEXT=('ready',), USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True,
                      USER_CONFIRMED_FREE_T4=True, USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True)
            with self.assertRaisesRegex(RuntimeError, 'memory_stop'):
                exec(probe, ns)
            self.assertNotIn('FRESH_META', ns)
            self.assertNotIn('RUNTIME_CONTEXT', ns)
            self.assertEqual(ns['PREPARED_CONTEXT'], ('ready',))

    def test_successful_probe_uses_new_proof_directory_without_reinstall(self):
        with tempfile.TemporaryDirectory(prefix='reuse-success-') as temporary:
            root = Path(temporary)
            old = root / 'fresh-meta-proof.json'
            old.write_bytes(b'old')
            source = 'import json,time\nFRESH_META={"status":"INT8_preflight_candidate"}\nFRESH_META_TIME=time.monotonic()\nwith (PREFLIGHT_DIR/"fresh-meta-proof.json").open("x") as output:json.dump(FRESH_META,output)'
            with patch.object(m, 'RECHECK_PREPARED', 'assert VALID'):
                _, probe = self.phases(probe=source)
            ns = dict(ALLOW_FULL_PREFLIGHT=True, ROOT=root, VALID=True,
                      PREPARED_CONTEXT=('ready',), INSTALL_CALLS=1, DOWNLOAD_CONTEXT=('old',),
                      USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
                      USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True)
            exec(probe, ns)
            first = ns['PREFLIGHT_DIR']
            exec(probe, ns)
            self.assertNotEqual(ns['PREFLIGHT_DIR'], first)
            self.assertEqual(ns['INSTALL_CALLS'], 1)
            self.assertEqual(old.read_bytes(), b'old')
            self.assertEqual(len(list(root.glob('preflight-*/fresh-meta-proof.json'))), 2)
            self.assertNotIn('DOWNLOAD_CONTEXT', ns)
            self.assertEqual(ns['RUNTIME_CONTEXT'], eval(m.CONTEXT_VALUE, ns))

    def test_revalidation_timeout_clears_readiness_without_installation(self):
        with patch.object(m, 'RECHECK_PREPARED', 'raise TimeoutError("probe_timeout")'):
            setup, _ = self.phases()
        ns = dict(ALLOW_RUNTIME_DOWNLOAD=True, PREPARED_CONTEXT=('ready',),
                  INSTALL_CALLS=1, FRESH_META_TIME=123, DOWNLOAD_CONTEXT=('old',),
                  USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU=True, USER_CONFIRMED_FREE_T4=True,
                  USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT=True)
        with self.assertRaisesRegex(TimeoutError, 'probe_timeout'):
            exec(setup, ns)
        self.assertEqual(ns['INSTALL_CALLS'], 1)
        self.assertNotIn('PREPARED_CONTEXT', ns)
        self.assertNotIn('FRESH_META_TIME', ns)
        self.assertNotIn('DOWNLOAD_CONTEXT', ns)
