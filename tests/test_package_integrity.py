"""Synthetic package binding negatives; no existing deployment artifacts."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from ai_manager import package_integrity as package
from ai_manager.validation_contracts import ContractError


class PackageIntegrityTests(unittest.TestCase):
    def test_loaded_code_must_match_recorded_raw_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);module=root/'_internal/ai_manager/package_integrity.py';module.parent.mkdir(parents=True)
            module.write_bytes(Path(package.__file__).read_bytes());exe=root/'AiManager.exe';exe.write_bytes(b'new synthetic EXE')
            files={'src/ai_manager/package_integrity.py':hashlib.sha256(module.read_bytes()).hexdigest()}
            provenance=dict(version='0.16.5',source_commit='a'*40,source_files=files)
            source=root/'SOURCE-PROVENANCE.json';source.write_text(json.dumps(provenance),'utf8')
            manifest=dict(version='0.16.5',source_files=files,files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (exe,source)})
            (root/'DESKTOP-MANIFEST.json').write_text(json.dumps(manifest),'utf8')
            with patch.object(package,'__file__',str(module)),patch.object(package.sys,'frozen',True,create=True),patch.object(package.sys,'executable',str(exe)):
                self.assertEqual(package.verify_frozen(full=True)['source_commit'],'a'*40)
                loader=types.SimpleNamespace(get_code=lambda name:compile('x=1','other.py','exec'))
                with patch.object(package.importlib.util,'find_spec',return_value=types.SimpleNamespace(loader=loader)):
                    with self.assertRaisesRegex(ContractError,'import_source_mismatch'):package.verify_frozen()
                module.write_bytes(b'changed')
                with self.assertRaisesRegex(ContractError,'source_integrity'):package.verify_frozen()
                module.unlink()
                with self.assertRaisesRegex(ContractError,'source_integrity'):package.verify_frozen()

    def test_code_binding_rejects_required_lock_missing(self):
        from ai_manager.validation_store import control_code_sha
        original=Path.is_file
        with patch.object(Path,'is_file',lambda p:False if p.name=='requirements-runtime.lock' else original(p)):
            with self.assertRaisesRegex(ContractError,'code_unavailable'):control_code_sha()
