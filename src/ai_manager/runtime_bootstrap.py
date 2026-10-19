"""App-local inference runtime built from the packaged complete CPython base."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from .config import private_home
from .inference import FileOwner, OwnedChild
from .preparation import atomic_text
from .external_process import spawn_external
from .runtime_paths import runtime_directory, python_base, reused_runtime


class RuntimeBootstrap:
    def __init__(self, home, resources):
        self.home, self.resources = private_home(home), Path(resources)
        self.root = runtime_directory(self.home)
        self.root.mkdir(exist_ok=True)
        self.root = private_home(self.root)
        self.record = private_home(self.root / 'bootstrap.json')
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread, self.child = None, None
        self.state = {'status': 'not_started', 'stage': 'awaiting_user', 'error': None}
        if self.record.exists():
            previous = json.loads(self.record.read_text(encoding='utf-8'))
            self.state = previous if previous.get('status') in ('ready', 'failed') else {'status': 'interrupted', 'stage': 'retry_available', 'error': 'runtime_setup_interrupted'}

    def snapshot(self):
        with self.lock:
            return dict(self.state, instance_id=self.root.name)

    def _update(self, **values):
        with self.lock:
            self.state.update(values)
            private_home(self.record)
            atomic_text(self.record, json.dumps(self.state, indent=2))

    def start(self):
        with self.lock:
            if self.state.get('status') == 'ready' and reused_runtime(self.home, 'tts'):
                return self.snapshot()
            if self.thread and self.thread.is_alive():
                return self.snapshot()
            if self.cancel.is_set():
                return {'status': 'failed', 'error': 'app_closing'}
            self._update(status='running', stage='verifying_bundled_python', error=None)
            self.thread = threading.Thread(target=self._prepare, daemon=True)
            self.thread.start()
            return self.snapshot()

    def _run(self, args, log):
        if self.cancel.is_set():
            raise ValueError('runtime_setup_cancelled')
        env = os.environ.copy()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_TRUSTED_HOST', 'PIP_CONFIG_FILE'):
            env.pop(key, None)
        env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1')
        process = spawn_external([str(args[0]), '-B', *[str(a) for a in args[1:]]], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   cwd=self.root, env=env, creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == 'nt' else 0)
        try:
            child = OwnedChild(process)
        except Exception:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=15)
            raise
        with self.lock:
            self.child = child
        try:
            while process.poll() is None:
                if self.cancel.wait(.25):
                    child.stop()
                    raise ValueError('runtime_setup_cancelled')
            if process.returncode:
                raise ValueError('runtime_install_failed')
        finally:
            child.close()
            with self.lock:
                self.child = None

    def _prepare(self):
        owner = None
        try:
            owner = FileOwner(private_home(self.root / 'bootstrap-owner.lock'))
            if not owner.handle:
                raise ValueError('runtime_setup_already_owned')
            metadata = json.loads((self.resources / 'python-runtime.json').read_text(encoding='utf-8'))
            python_root = python_base(self.home, 'tts', self.resources / 'python_runtime')
            base = python_root / 'python.exe'
            actual = {p.relative_to(python_root).as_posix() for p in python_root.rglob('*') if p.is_file()}
            if actual != set(metadata['files']):
                raise ValueError('bundled_python_integrity_failed')
            for relative, digest in metadata['files'].items():
                component = private_home(python_root / relative)
                if not component.is_relative_to(python_root) or hashlib.sha256(component.read_bytes()).hexdigest() != digest:
                    raise ValueError('bundled_python_integrity_failed')
            requirements = self.resources / 'requirements-runtime.lock'
            digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
            marker = private_home(self.root / 'bootstrap-inputs.json')
            expected = {'requirements_sha256': digest, 'python_archive_sha256': metadata['archive_sha256'], 'python_executable_sha256': metadata['python_executable_sha256'], 'runtime_instance_id': self.root.name, 'python_base': str(python_root)}
            venv = private_home(self.root / 'venv')
            if marker.exists():
                if json.loads(marker.read_text()) != expected:
                    raise ValueError('runtime_inputs_changed_use_new_home')
            else:
                if venv.exists():
                    raise ValueError('runtime_existing_environment_unowned')
                with marker.open('x', encoding='utf-8') as handle:
                    json.dump(expected, handle)
            with private_home(self.root / 'setup.log').open('ab') as log:
                if not (venv / 'Scripts/python.exe').exists():
                    self._update(stage='creating_app_local_environment')
                    self._run([base, '-I', '-m', 'venv', venv], log)
                python = venv / 'Scripts/python.exe'
                self._update(stage='installing_package_manager')
                self._run([python, '-I', '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple', 'pip==26.2.1'], log)
                self._update(stage='downloading_installing_cuda_runtime')
                self._run([python, '-I', '-m', 'pip', 'install', 'torch==2.9.1', 'torchaudio==2.9.1', '--index-url', 'https://download.pytorch.org/whl/cu128'], log)
                self._update(stage='installing_model_dependencies')
                self._run([python, '-I', '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple', '-r', requirements], log)
                self._update(stage='checking_dependencies')
                self._run([python, '-I', '-m', 'pip', 'check'], log)
            atomic_text(private_home(self.root / 'requirements.lock'), requirements.read_text(encoding='utf-8'))
            self._update(status='ready', stage='ready_for_runtime_check', completed_at=time.time())
        except Exception as error:
            allowed = {'runtime_setup_cancelled', 'runtime_install_failed', 'runtime_setup_already_owned', 'bundled_python_integrity_failed', 'runtime_inputs_changed_use_new_home', 'runtime_existing_environment_unowned'}
            self._update(status='failed', stage='retry_available', error=str(error) if str(error) in allowed else 'runtime_setup_failed')
        finally:
            if owner:
                owner.close()

    def close(self):
        self.cancel.set()
        if self.thread:
            self.thread.join(20)
