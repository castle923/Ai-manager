"""Explicit, bounded startup diagnostics without exception text or user data."""
import builtins
import json
import os
from pathlib import Path
import sys
import subprocess
import uuid

STAGES = frozenset(('home', 'configure_runtime', 'bridge', 'import_webview',
    'start_application', 'start_setup', 'create_window', 'start_webview', 'close', 'complete'))
MODULES = ('desktop', 'runtime_paths', 'runtime_reuse', 'runtime_bootstrap', 'server',
    'inference', 'task_inference', 'config', 'security', 'external_process')
KINDS = {BaseException: 'BaseException', Exception: 'Exception', ValueError: 'ValueError',
    TypeError: 'TypeError', KeyError: 'KeyError', IndexError: 'IndexError',
    RuntimeError: 'RuntimeError', OSError: 'OSError', FileNotFoundError: 'FileNotFoundError',
    PermissionError: 'PermissionError', ImportError: 'ImportError', ModuleNotFoundError: 'ModuleNotFoundError',
    AttributeError: 'AttributeError', TimeoutError: 'TimeoutError', EOFError: 'EOFError',
    UnicodeError: 'UnicodeError', UnicodeDecodeError: 'UnicodeDecodeError'}
KINDS.update({subprocess.TimeoutExpired: 'TimeoutExpired', subprocess.CalledProcessError: 'CalledProcessError'})


class StartupDiagnostics:
    def __init__(self, directory=None):
        self.stage = 'home'
        self.fd = None
        self.size = self.events = 0
        if directory is None:
            return
        try:
            from .config import private_home
            directory = private_home(directory)
            directory.mkdir(parents=True, exist_ok=True)
            directory = private_home(directory)
            self.fd = os.open(directory / ('startup-' + uuid.uuid4().hex + '.jsonl'),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except Exception:
            pass

    def enter(self, stage):
        self.stage = stage if stage in STAGES else 'home'
        self._write(dict(event='stage', stage=self.stage))

    def failed(self, error):
        try:
            self._failed(error)
        except Exception:
            pass

    def _failed(self, error):
        chain, seen = [], set()
        while error is not None and id(error) not in seen and len(chain) < 4:
            seen.add(id(error))
            frames, tb = [], error.__traceback__
            while tb is not None and len(frames) < 24:
                category = 'external'
                for name in MODULES:
                    module = sys.modules.get('ai_manager.' + name)
                    if module is not None and tb.tb_frame.f_globals is vars(module):
                        category = name
                        break
                frames.append(dict(module=category, line=tb.tb_lineno))
                tb = tb.tb_next
            chain.append(dict(kind=KINDS.get(type(error), 'ExternalError'), frames=frames))
            error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
        self._write(dict(event='failed', stage=self.stage, exceptions=chain))

    def _write(self, value):
        if self.fd is None or self.events >= 32:
            return
        try:
            data = (json.dumps(value, separators=(',', ':')) + '\n').encode('utf8')
            if self.size + len(data) > 16384:
                return
            os.write(self.fd, data)
            self.size += len(data)
            self.events += 1
        except Exception:
            pass

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None
