"""Public source payload must survive installation without a checkout."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from ai_manager import server

ROOT = Path(__file__).resolve().parents[1]


class ColabPackagingTests(unittest.TestCase):
    def test_installed_public_sources_and_notebook_keep_exact_pins(self):
        with tempfile.TemporaryDirectory(prefix='colab-package-') as temporary:
            package = Path(temporary) / 'ai_manager'
            stage = runpy.run_path(str(ROOT / 'scripts/stage_colab_resources.py'))['stage']
            stage(ROOT, package)
            pins = json.loads((package / 'colab_source_pins.json').read_bytes())
            public = package / 'colab_public'
            with patch.object(server, '_HANDOFF_PUBLIC_ROOT', public):
                server._verify_handoff_sources(pins)
            builder = runpy.run_path(str(public / 'scripts/colab/build_llama_handoff.py'))
            metadata = builder['build_bundle'](Path(temporary) / 'notebook')
            self.assertEqual(metadata['source_sha256'], pins)
            for relative in ('src/ai_manager/colab_contract.py',
                             'scripts/colab/llama_handoff_worker.py',
                             'scripts/colab/llama_watchdog.py',
                             'src/ai_manager/adapter_manifest_llama.json'):
                self.assertEqual((public / relative).read_bytes(), (ROOT / relative).read_bytes())

    def test_staging_does_not_overwrite_existing_payload(self):
        with tempfile.TemporaryDirectory(prefix='colab-package-') as temporary:
            stage = runpy.run_path(str(ROOT / 'scripts/stage_colab_resources.py'))['stage']
            package = Path(temporary) / 'ai_manager'
            stage(ROOT, package)
            original = (package / 'colab_source_pins.json').read_bytes()
            # A same-source incremental build is safe and preserves every byte.
            stage(ROOT, package)
            stale = package / 'colab_public/stale.txt'
            stale.write_bytes(b'preserve existing build material')
            with self.assertRaises(FileExistsError):
                stage(ROOT, package)
            self.assertEqual((package / 'colab_source_pins.json').read_bytes(), original)
            self.assertEqual(stale.read_bytes(), b'preserve existing build material')

    def test_conflicting_pins_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='colab-package-') as temporary:
            stage = runpy.run_path(str(ROOT / 'scripts/stage_colab_resources.py'))['stage']
            package = Path(temporary) / 'ai_manager'
            package.mkdir()
            pins = package / 'colab_source_pins.json'
            pins.write_bytes(b'existing material')
            with self.assertRaises(FileExistsError):
                stage(ROOT, package)
            self.assertEqual(pins.read_bytes(), b'existing material')
            self.assertFalse((package / 'colab_public').exists())
