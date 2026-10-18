import json
import builtins
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_manager.startup_diagnostics import StartupDiagnostics


class StartupDiagnosticsTests(unittest.TestCase):
    def test_opt_in_and_secret_metadata_omission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            StartupDiagnostics().failed(ValueError('SECRET token URL account input'))
            self.assertEqual(list(root.iterdir()), [])
            diagnostics = StartupDiagnostics(root)
            diagnostics.enter('configure_runtime')
            Secret = type('SECRET_API_KEY', (Exception,), {'__module__':'builtins'})
            try:
                try:
                    raise ImportError('SECRET token cookie URL')
                except ImportError as error:
                    raise Secret('SECRET input') from error
            except Exception as error:
                diagnostics.failed(error)
            diagnostics.close()
            data = next(root.iterdir()).read_text('utf8')
            self.assertNotIn('SECRET', data)
            record = json.loads(data.splitlines()[1])
            self.assertEqual(record['exceptions'][0]['kind'], 'ExternalError')
            self.assertEqual(record['exceptions'][1]['kind'], 'ImportError')
            self.assertEqual(record['stage'], 'configure_runtime')
            self.assertNotIn(str(root), data)

    def test_bounded_io_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as temporary:
            diagnostics = StartupDiagnostics(temporary)
            with patch('ai_manager.startup_diagnostics.os.write', side_effect=OSError('SECRET')):
                diagnostics.failed(ValueError('original'))
            for _ in range(200):
                diagnostics.enter('start_webview')
            diagnostics.close()
            path = next(Path(temporary).iterdir())
            self.assertLessEqual(path.stat().st_size, 16384)
            self.assertLessEqual(len(path.read_text().splitlines()),32)

    def test_injected_builtin_attribute_does_not_become_a_label(self):
        import ai_manager.startup_diagnostics as module
        Secret = type('OtherError', (Exception,), {})
        with tempfile.TemporaryDirectory() as temporary, patch.object(builtins, 'SECRET_SENTINEL', Secret, create=True):
            importlib.reload(module)
            diagnostics = module.StartupDiagnostics(temporary)
            diagnostics.failed(Secret('omitted'))
            diagnostics.close()
            data = next(Path(temporary).iterdir()).read_text()
            self.assertNotIn('SECRET_SENTINEL',data)
            self.assertIn('ExternalError',data)
        importlib.reload(module)


if __name__ == '__main__':
    unittest.main()
