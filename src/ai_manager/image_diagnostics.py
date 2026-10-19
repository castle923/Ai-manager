"""Opt-in, bounded structural diagnostics. Never serialize exception messages.

No traceback source, locals, prompt, request, URL, path, device name or env dump
is collected. The private run directory remains subject to its owner's ACL;
0600 is applied on POSIX and does not claim to install a Windows ACL.
"""
import importlib.metadata
import builtins
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

MAX_BYTES = 128 * 1024
MAX_EVENTS = 64
STAGES = frozenset(('input_validation', 'runtime_import', 'runtime_check', 'memory_preflight',
    'loading', 'component_import', 'offload_setup', 'transformer_load', 'text_encoder_load',
    'vae_load', 'vae_offload', 'processor_load', 'scheduler_load', 'pipeline_construct',
    'pipeline_configure', 'loading_synchronize', 'prompt_recheck', 'inference',
    'inference_synchronize', 'output_validation', 'output_publish', 'metrics', 'complete'))
LIBRARIES = ('torch', 'torchvision', 'transformers', 'diffusers', 'accelerate', 'safetensors', 'Pillow', 'psutil')
KNOWN_VERSIONS = {'torch': '2.9.1+cu128', 'torchvision': '0.24.1+cu128', 'transformers': '5.17.0',
    'accelerate': '1.12.0', 'safetensors': '0.8.0', 'Pillow': '11.3.0', 'psutil': '7.2.2'}


def _module(value):
    root = value.split('.')[0]
    # Only static categories are emitted: dotted module names may themselves
    # contain dynamically supplied private values.
    return root if root in ('builtins', 'torch', 'torchvision', 'transformers', 'diffusers',
        'accelerate', 'safetensors', 'ai_manager', 'importlib') else 'external'


def _exception_type(error):
    cls = type(error)
    for name in ('Exception', 'RuntimeError', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
                 'AttributeError', 'ImportError', 'ModuleNotFoundError', 'OSError', 'FileNotFoundError',
                 'FileExistsError', 'PermissionError', 'MemoryError', 'NotImplementedError', 'AssertionError'):
        if cls is getattr(builtins, name):
            return name
    if cls is importlib.metadata.PackageNotFoundError:
        return 'PackageNotFoundError'
    # Fixed official names only; a user-controlled exception class name is
    # never copied to the log even if its __module__ impersonates a library.
    if _module(cls.__module__) == 'torch' and cls.__name__ in ('OutOfMemoryError', 'CUDAOutOfMemoryError'):
        return cls.__name__
    return 'ExternalError'


def exception_structure(error):
    """Keep type and chained stacks, dropping arbitrary message text entirely."""
    chain, seen = [], set()
    while error is not None and id(error) not in seen and len(chain) < 6:
        seen.add(id(error))
        module = _module(type(error).__module__)
        name = _exception_type(error)
        frames, tb = [], error.__traceback__
        while tb is not None:
            # Module + line identifies fixed source without leaking host paths,
            # arbitrary source text, function defaults or local variables.
            frames.append(dict(module=_module(tb.tb_frame.f_globals.get('__name__', '')),
                               line=tb.tb_lineno))
            tb = tb.tb_next
        chain.append(dict(type=name, module=module, frames=frames[-16:], message_omitted=True))
        following = error.__cause__
        relation = 'cause'
        if following is None and not error.__suppress_context__:
            following, relation = error.__context__, 'context'
        chain[-1]['next'] = relation if following is not None else None
        error = following
    return chain


class ImageDiagnostics:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.stage = 'input_validation'
        self.enabled = os.environ.get('AI_MANAGER_IMAGE_DIAGNOSTICS') == '1'
        self.events = self.bytes = 0
        self.stream = None
        if self.enabled:
            try:
                for part in (self.directory, *self.directory.parents):
                    info = part.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                        raise OSError('unsafe diagnostic directory')
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                fd = os.open(self.directory / 'image-diagnostics.jsonl', flags, 0o600)
                self.stream = os.fdopen(fd, 'wb')
            except Exception:
                self.enabled = False

    def emit(self, event, **values):
        if not self.enabled or self.events >= MAX_EVENTS:
            return
        try:
            data = (json.dumps(dict(schema=1, event=event, stage=self.stage,
                    monotonic_seconds=round(time.monotonic(), 3), **values), ensure_ascii=True) + '\n').encode('ascii')
            if len(data) > 16384 or self.bytes + len(data) > MAX_BYTES:
                return
            self.stream.write(data)
            self.stream.flush()
            self.events += 1
            self.bytes += len(data)
        except Exception:
            self.enabled = False

    def mark(self, stage):
        self.stage = stage if stage in STAGES else 'loading'
        if self.enabled:
            self.emit('stage', resources=self.resources())

    def resources(self):
        result = {}
        # Snapshot calls must never allocate tensors, synchronize a device or
        # mask the original error (including a partially imported runtime).
        try:
            psutil = sys.modules.get('psutil')
            if psutil:
                result['process_rss_bytes'] = int(psutil.Process().memory_info().rss)
                result['ram_available_bytes'] = int(psutil.virtual_memory().available)
        except Exception:
            pass
        try:
            torch = sys.modules.get('torch')
            if torch and torch.cuda.is_initialized():
                free, total = torch.cuda.mem_get_info(0)
                result.update(gpu_free_bytes=int(free), gpu_total_bytes=int(total),
                    gpu_allocated_bytes=int(torch.cuda.memory_allocated(0)),
                    gpu_reserved_bytes=int(torch.cuda.memory_reserved(0)))
        except Exception:
            pass
        try:
            import shutil
            result['disk_free_bytes'] = int(shutil.disk_usage(self.directory).free)
        except Exception:
            pass
        return result

    def runtime(self):
        if not self.enabled:
            return
        packages = {}
        for name in LIBRARIES:
            try:
                version = importlib.metadata.version(name)
                packages[name] = (KNOWN_VERSIONS[name] if name in KNOWN_VERSIONS and version == KNOWN_VERSIONS[name]
                    else 'source_hash_checked_separately' if name == 'diffusers' else 'unexpected')
            except Exception:
                packages[name] = 'unavailable'
        self.emit('runtime', packages=packages)

    def placement(self, component, model):
        if not self.enabled:
            return
        counts = {'cpu': 0, 'disk': 0, 'cuda': 0, 'meta': 0, 'other': 0}
        try:
            mapping = getattr(model, 'hf_device_map', {})
            for device in mapping.values():
                key = 'cuda' if type(device) is int or (isinstance(device, str) and re.fullmatch(r'cuda(?::[0-9]+)?', device)) else device
                counts[key if isinstance(key, str) and key in counts else 'other'] += 1
            self.emit('placement', component=component, device_map_counts=counts)
        except Exception:
            pass

    def failure(self, error, public_code):
        try:
            self.emit('failure', public_code=public_code, exceptions=exception_structure(error), resources=self.resources())
        except Exception:
            # Even malformed exception objects and diagnostic I/O failures must
            # leave the worker's stable result and exit status unchanged.
            pass

    def close(self):
        try:
            if self.stream:
                self.stream.close()
        except Exception:
            pass
