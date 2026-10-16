"""Local, single-owner TTS queue with private immutable inputs and verified WAVs."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import threading
import time
import uuid
import wave

from .preparation import atomic_text, manifest, now, safe_relative

TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}
DEFAULTS = dict(language='Korean', speaker='Sohee', batch_size=1, instruct=None,
                max_text_length=300, timeout_seconds=600, max_new_tokens=1024)


class InferenceError(ValueError):
    pass


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def regular(path, root):
    """Reject symlink/junction/reparse indirections, including all private parents."""
    path, root = Path(path), Path(root)
    if not path.is_relative_to(root):
        raise InferenceError('unsafe_local_path')
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.stat(), 'st_file_attributes', 0) & 0x400):
            raise InferenceError('unsafe_local_path')
        if item == root:
            break
    return path


def validate_wav(path):
    """Decode bounded PCM16 output independently of the inference runtime."""
    try:
        if not Path(path).is_file() or not 44 < Path(path).stat().st_size <= 6_000_000:
            raise ValueError()
        with Path(path).open('rb') as stream:
            header = stream.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WAVE' or struct.unpack('<I', header[4:8])[0] + 8 != Path(path).stat().st_size:
            raise ValueError()
        with wave.open(str(path), 'rb') as reader:
            frames, rate, channels = reader.getnframes(), reader.getframerate(), reader.getnchannels()
            if rate != 24000 or channels != 1 or reader.getsampwidth() != 2 or reader.getcomptype() != 'NONE' or not 0 < frames <= rate * 120:
                raise ValueError()
            data = reader.readframes(frames)
            if len(data) != frames * 2:
                raise ValueError()
        samples = [value[0] / 32768 for value in struct.iter_unpack('<h', data)]
        peak = max(abs(value) for value in samples)
        rms = math.sqrt(sum(value * value for value in samples) / frames)
        clipped = sum(abs(value) >= 32767 / 32768 for value in samples)
        if not math.isfinite(rms) or rms <= 0 or clipped / frames > .01:
            raise ValueError()
        return dict(sha256=digest(path), bytes=Path(path).stat().st_size, sample_rate=rate,
                    channels=channels, frames=frames, duration_seconds=frames / rate, peak=peak, rms=rms, clipped_samples=clipped)
    except (OSError, EOFError, wave.Error, ValueError, ZeroDivisionError):
        raise InferenceError('output_invalid') from None


class FileOwner:
    """OS lock, released by process exit; PID text is never proof of ownership."""
    def __init__(self, path):
        self.handle = None
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = None
        try:
            handle = path.open('a+b')
            if path.stat().st_size == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.handle = handle
        except OSError:
            if handle: handle.close()

    def close(self):
        if self.handle:
            self.handle.close(); self.handle = None


class OwnedChild:
    """Keep a Windows kill-on-close Job Object for this exact spawned worker."""
    def __init__(self, process):
        self.process, self.job = process, None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            class BASIC(ctypes.Structure):
                _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                            ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                            ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                            ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
            class EXTENDED(ctypes.Structure):
                _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                            ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            job = kernel.CreateJobObjectW(None, None)
            info = EXTENDED(); info.BasicLimitInformation.LimitFlags = 0x2000
            if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job, int(process._handle)):
                if job: kernel.CloseHandle(job)
                process.kill(); process.wait()
                raise InferenceError('worker_ownership_failed')
            self.job, self.kernel = job, kernel
            # The process is created suspended so a venv launcher cannot spawn
            # an unowned child before assignment. Resume its original thread.
            class THREADENTRY32(ctypes.Structure):
                _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ThreadID', wintypes.DWORD),
                            ('th32OwnerProcessID', wintypes.DWORD), ('tpBasePri', wintypes.LONG),
                            ('tpDeltaPri', wintypes.LONG), ('dwFlags', wintypes.DWORD)]
            kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
            kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
            kernel.OpenThread.restype = wintypes.HANDLE
            kernel.ResumeThread.argtypes = [wintypes.HANDLE]
            snapshot = kernel.CreateToolhelp32Snapshot(0x4, 0)
            entry = THREADENTRY32(); entry.dwSize = ctypes.sizeof(entry)
            found = False
            try:
                available = kernel.Thread32First(snapshot, ctypes.byref(entry))
                while available:
                    if entry.th32OwnerProcessID == process.pid:
                        thread = kernel.OpenThread(0x2, False, entry.th32ThreadID)
                        if thread:
                            try: found = kernel.ResumeThread(thread) != 0xFFFFFFFF
                            finally: kernel.CloseHandle(thread)
                        break
                    available = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            finally:
                kernel.CloseHandle(snapshot)
            if not found:
                self.stop(); self.close()
                raise InferenceError('worker_ownership_failed')

    def stop(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=15)

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job); self.job = None


class Inference:
    def __init__(self, home, *, timeout=600, popen=subprocess.Popen):
        self.home = Path(home)
        self.base = self.home / 'tts'
        self.base.mkdir(parents=True, exist_ok=True)
        regular(self.base, self.home)
        self.owner = FileOwner(self.base / 'owner.lock')
        self.timeout, self.popen = timeout, popen
        self.lock = threading.RLock()
        self.wake, self.closed = threading.Event(), threading.Event()
        self.cancelled = set()
        self.child = None
        self.active = None
        self.thread = None
        if self.owner.handle:
            # A new owner means no prior worker can still publish a valid success.
            for run in self._runs():
                if run['status'] not in TERMINAL:
                    run.update(status='interrupted', error='process_interrupted', finished_at=now())
                    self._save(run)
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _path(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
            raise InferenceError('run_not_found')
        return regular(self.base / run_id, self.home)

    def _runs(self):
        values = []
        for path in self.base.glob('*/state.json'):
            try:
                value = json.loads(regular(path, self.home).read_text(encoding='utf8'))
                if value['id'] == path.parent.name and re.fullmatch('[a-f0-9]{32}', value['id']):
                    values.append(value)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(values, key=lambda r: r['started_at'], reverse=True)

    def _save(self, run):
        with self.lock:
            atomic_text(self._path(run['id']) / 'state.json', json.dumps(run, ensure_ascii=False, indent=2))

    def _public(self, run):
        result = {key: run.get(key) for key in ('id', 'status', 'started_at', 'finished_at', 'text', 'input_sha256', 'parameters', 'model', 'error', 'metrics', 'output')}
        result['audio_url'] = f"/api/tts/runs/{run['id']}/audio" if run['status'] == 'succeeded' else None
        return result

    def snapshot(self):
        with self.lock:
            m = manifest()
            return dict(supported_model={key: m[key] for key in ('name', 'revision')} | {'id': m['model_id']},
                        defaults=DEFAULTS, runs=[self._public(run) for run in self._runs()], active_run_id=self.active)

    def get(self, run_id):
        with self.lock:
            try:
                run = json.loads((self._path(run_id) / 'state.json').read_text(encoding='utf8'))
                if run['id'] != run_id:
                    raise ValueError()
                return self._public(run)
            except (OSError, KeyError, ValueError):
                raise InferenceError('run_not_found') from None

    def create(self, text):
        if not isinstance(text, str) or not text.strip():
            raise InferenceError('text_required')
        text = text.strip()
        try:
            text.encode('utf8')
        except UnicodeEncodeError:
            raise InferenceError('invalid_request') from None
        if len(text) > DEFAULTS['max_text_length'] or any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise InferenceError('text_too_long' if len(text) > DEFAULTS['max_text_length'] else 'invalid_request')
        with self.lock:
            if not self.owner.handle or self.closed.is_set():
                raise InferenceError('operation_running')
            if sum(run['status'] == 'queued' for run in self._runs()) >= 3:
                raise InferenceError('queue_full')
            run_id = uuid.uuid4().hex
            directory = self._path(run_id); directory.mkdir()
            m = manifest()
            run = dict(id=run_id, status='queued', started_at=now(), finished_at=None, text=text,
                       input_sha256=hashlib.sha256(text.encode('utf8')).hexdigest(),
                       parameters={key: DEFAULTS[key] for key in ('language', 'speaker', 'batch_size', 'instruct', 'max_new_tokens')} | {'seed': int.from_bytes(os.urandom(4), 'little')},
                       model={'id': m['model_id'], 'name': m['name'], 'revision': m['revision'], 'preparation_id': None},
                       error=None, metrics={}, output=None)
            atomic_text(directory / 'input.json', json.dumps({'text': text, 'sha256': run['input_sha256'], 'parameters': run['parameters']}, ensure_ascii=False, indent=2))
            self._save(run); self.wake.set()
            return self._public(run)

    def cancel(self, run_id):
        with self.lock:
            if not self.owner.handle or self.closed.is_set():
                raise InferenceError('operation_running')
            run = self.get(run_id)
            if run['status'] in TERMINAL:
                return run
            self.cancelled.add(run_id)
            run.update(status='cancelled' if run['status'] == 'queued' else 'cancelling', error='cancelled')
            if run['status'] == 'cancelled': run['finished_at'] = now()
            run.pop('audio_url', None)
            self._save(run); self.wake.set()
            return self._public(run)

    def _check_cancel(self, run_id):
        if run_id in self.cancelled or self.closed.is_set():
            raise InferenceError('cancelled')

    def _prepare(self, run):
        from .preparation import Preparation
        prep = Preparation(self.home)
        state = prep._load()
        if state.get('status') != 'ready' or state.get('integrity') != 'matched' or not re.fullmatch('[a-f0-9]{32}', state.get('id', '')):
            raise InferenceError('model_not_ready')
        if prep.environment().get('status') != 'ready':
            raise InferenceError('runtime_not_ready')
        assets = regular(prep.base / state['id'] / 'assets', self.home)
        m = manifest(); verified = []
        for item in m['files']:
            self._check_cancel(run['id'])
            path = regular(assets / safe_relative(item['path']), self.home)
            if not path.is_file() or path.stat().st_size != item['size'] or digest(path) != item['sha256']:
                raise InferenceError('model_integrity_failed')
            verified.append(item)
        actual = {str(path.relative_to(assets)).replace('\\', '/') for path in assets.rglob('*') if path.is_file()}
        if actual != {item['path'] for item in m['files']}:
            raise InferenceError('model_integrity_failed')
        run['model']['preparation_id'] = state['id']
        python = regular(self.home / 'runtime' / 'venv' / 'Scripts' / 'python.exe', self.home)
        if not python.is_file(): raise InferenceError('runtime_not_ready')
        worker = Path(__file__).with_name('tts_worker.py')
        provenance = dict(run_id=run['id'], checked_at=now(), inputs=[dict(item, kind='designated_model_component', local_path=str(assets / safe_relative(item['path'])), source=m['source']) for item in verified],
                          input_sha256=run['input_sha256'], manifest_sha256=digest(Path(__file__).with_name('model_manifest.json')),
                          code_sha256={p.name: digest(p) for p in (Path(__file__), worker)},
                          runtime=prep.environment(), runtime_lock_sha256=digest(self.home / 'runtime' / 'requirements.lock') if (self.home / 'runtime' / 'requirements.lock').is_file() else None,
                          cold_loading=True, timeout_seconds=self.timeout, offline=True)
        directory = self._path(run['id'])
        atomic_text(directory / 'provenance.json', json.dumps(provenance, ensure_ascii=False, indent=2))
        atomic_text(directory / 'request.json', json.dumps(dict(run_id=run['id'], model_path=str(assets), text=run['text'], parameters=run['parameters']), ensure_ascii=False))
        return python, worker

    def _execute(self, run):
        started = time.monotonic(); directory = self._path(run['id']); child = None
        try:
            run['status'] = 'preparing'; self._save(run)
            python, worker = self._prepare(run)
            self._check_cancel(run['id'])
            env = os.environ.copy()
            env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', TOKENIZERS_PARALLELISM='false', HF_HOME=str(directory / 'model-cache'), HF_MODULES_CACHE=str(directory / 'modules-cache'))
            for key in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'): env.pop(key, None)
            with (directory / 'worker.log').open('wb') as log:
                process = self.popen([str(python), str(worker), str(directory / 'request.json')], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, cwd=directory, env=env,
                                     creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == 'nt' else 0)
                child = OwnedChild(process); self.child = child
                while process.poll() is None:
                    self._check_cancel(run['id'])
                    if time.monotonic() - started > self.timeout:
                        raise InferenceError('inference_timeout')
                    progress = directory / 'progress.json'
                    if progress.is_file():
                        try:
                            phase = json.loads(progress.read_text(encoding='utf8'))
                            if phase.get('run_id') == run['id'] and phase.get('status') in {'loading', 'running', 'validating'}:
                                with self.lock:
                                    self._check_cancel(run['id']); run['status'] = phase['status']; self._save(run)
                        except (OSError, json.JSONDecodeError): pass
                    self.closed.wait(.15)
                self._check_cancel(run['id'])
                try:
                    result = json.loads((directory / 'result.json').read_text(encoding='utf8'))
                except (OSError, ValueError):
                    raise InferenceError('worker_crashed') from None
                if result.get('run_id') != run['id'] or result.get('input_sha256') != run['input_sha256']:
                    raise InferenceError('worker_crashed')
                if isinstance(result.get('metrics'), dict):
                    run['metrics'] = result['metrics']
                if process.returncode != 0 or result.get('status') != 'generated':
                    raise InferenceError(result.get('error') if result.get('error') in {'inference_out_of_memory', 'inference_failed', 'output_invalid', 'runtime_not_ready', 'generation_limit_reached'} else 'worker_crashed')
                with self.lock:
                    self._check_cancel(run['id']); run['status'] = 'validating'; self._save(run)
                output = validate_wav(regular(directory / 'output.wav', self.home))
                with self.lock:
                    self._check_cancel(run['id'])
                    run.update(status='succeeded', output=output, metrics=result.get('metrics', {}), finished_at=now())
        except InferenceError as error:
            run.update(status='cancelled' if str(error) == 'cancelled' else 'failed', error=str(error), finished_at=now())
        except Exception:
            run.update(status='failed', error='inference_failed', finished_at=now())
        finally:
            if child:
                child.stop(); child.close()
            self.child = None
            with self.lock:
                # Cancellation wins until the final success publication boundary.
                if run['id'] in self.cancelled:
                    run.update(status='cancelled', error='cancelled', output=None, finished_at=now())
                run['metrics']['total_seconds'] = round(time.monotonic() - started, 3)
                self._save(run)

    def _loop(self):
        while not self.closed.is_set():
            self.wake.wait(.5); self.wake.clear()
            with self.lock:
                queued = [run for run in reversed(self._runs()) if run['status'] == 'queued']
                if not queued: continue
                run = queued[0]; self.active = run['id']
            self._execute(run)
            with self.lock: self.active = None
            self.wake.set()

    def audio(self, run_id):
        with self.lock:
            run = self.get(run_id)
            if run['status'] != 'succeeded': raise InferenceError('run_not_finished')
            path = regular(self._path(run_id) / 'output.wav', self.home)
            if validate_wav(path) != run['output']: raise InferenceError('output_invalid')
            return path.read_bytes()

    def close(self):
        self.closed.set(); self.wake.set()
        if self.thread:
            self.thread.join(20)
        if not self.thread or not self.thread.is_alive(): self.owner.close()
