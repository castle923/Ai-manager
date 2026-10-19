"""Startup-only, read-only binding to owned public-library environments.

Never copies a venv, rewrites pyvenv.cfg or selects old worker/UI code. Reuse
requires an intact original Python base and a fresh stdlib-only metadata probe.
"""
import hashlib
import json
import importlib.util
import marshal
import os
from pathlib import Path
import re
import subprocess
import types

from .config import private_home


def digest(path):
    return hashlib.sha256(private_home(path).read_bytes()).hexdigest()


def read(path, limit=262144):
    path = private_home(path)
    if not 0 < path.stat().st_size <= limit:
        raise ValueError('runtime_reuse_record_invalid')
    value = json.loads(path.read_text('utf8'))
    if not isinstance(value, dict):
        raise ValueError('runtime_reuse_record_invalid')
    return value


def pins(lock):
    result = {}
    for line in private_home(lock).read_text('utf8').splitlines():
        if re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', line):
            name, version = line.split('==')
            result[name.lower().replace('_', '-')] = version
    return result


def verified_extra_cache(base, relative, files):
    try:
        return _verified_extra_cache(base, relative, files)
    except Exception:
        return False


def _verified_extra_cache(base, relative, files):
    path = private_home(base / relative)
    match = re.fullmatch(r'(.+)\.cpython-310\.pyc', path.name)
    if path.parent.name != '__pycache__' or not match or path.stat().st_size > 2 * 1024 * 1024:
        return False
    source = path.parent.parent / (match[1] + '.py')
    if source.relative_to(base).as_posix() not in files:
        return False
    with path.open('rb') as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if not 16 < len(data) <= 2 * 1024 * 1024 or data[:4] != importlib.util.MAGIC_NUMBER:
        return False
    def normalize(value):
        if isinstance(value, types.CodeType):
            names = ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals', 'co_stacksize',
                'co_flags', 'co_code', 'co_consts', 'co_names', 'co_varnames', 'co_freevars', 'co_cellvars',
                'co_firstlineno', 'co_lnotab', 'co_linetable', 'co_exceptiontable', 'co_name', 'co_qualname')
            return ('code', tuple((name, normalize(getattr(value, name))) for name in names if hasattr(value, name)))
        if isinstance(value, tuple):
            return ('tuple', tuple(normalize(part) for part in value))
        if isinstance(value, frozenset):
            return ('frozenset', frozenset(normalize(part) for part in value))
        return (type(value).__name__, value)
    loaded = marshal.loads(data[16:])
    if not isinstance(loaded, types.CodeType):
        return False
    cached = normalize(loaded)
    expected = normalize(compile(source.read_bytes(), str(source), 'exec', dont_inherit=True, optimize=0))
    # Compare executable fields explicitly, ignoring only the source filename.
    return cached == expected


def fresh_metadata(root, base, expected):
    # -S avoids site/.pth execution; inspect distributions as data only.
    site = private_home(root / 'venv/Lib/site-packages')
    script = ('import importlib.metadata,json,sys; '
        'found={d.metadata["Name"].lower().replace("_","-"):d.version for d in '
        'importlib.metadata.distributions(path=[' + repr(str(site)) + '])}; '
        'print(json.dumps(dict(python=sys.version.split()[0],base=sys.base_prefix,'
        'packages={n:found.get(n) for n in ' + repr(sorted(expected)) + '})))')
    env = dict(os.environ)
    for name in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        env.pop(name, None)
    result = subprocess.run([str(root / 'venv/Scripts/python.exe'), '-I', '-B', '-S', '-c', script],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode or len(result.stdout) > 65536:
        raise ValueError('runtime_reuse_probe_failed')
    value = json.loads(result.stdout)
    if private_home(value['base']) != base or value['packages'] != expected:
        raise ValueError('runtime_reuse_probe_failed')
    return value


def bind(resources, home):
    from . import task_runtime
    resources, home = private_home(resources), private_home(home)
    cache = {}
    selected, diagnostics = {}, []

    def verified_base(base, metadata):
        base = private_home(base)
        key = (str(base), hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest())
        if key not in cache:
            files = metadata['files']
            actual = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
            if set(files) - actual:
                raise ValueError('runtime_reuse_base_missing')
            if any(not verified_extra_cache(base, relative, files) for relative in actual - set(files)):
                raise ValueError('runtime_reuse_base_files_changed')
            for relative, pin in files.items():
                path = private_home(base / relative)
                if not path.is_relative_to(base) or (digest(path) != pin and not verified_extra_cache(base, relative, files)):
                    raise ValueError('runtime_reuse_base_files_changed')
            if digest(base / 'python.exe') != metadata['python_executable_sha256']:
                raise ValueError('runtime_reuse_base_files_changed')
            cache[key] = base
        return cache[key]

    def validate(root, role, metadata, lock, expected_packages):
        root = private_home(root)
        marker_path = root / ('bootstrap-inputs.json' if role == 'tts' else 'setup-inputs.json')
        marker = read(marker_path)
        if marker['requirements_sha256'] != digest(lock) or marker['python_archive_sha256'] != metadata['archive_sha256']:
            raise ValueError('runtime_reuse_lock_changed')
        base = private_home(marker['python_base'] if role == 'tts' else Path(marker['base_python_path']).parent)
        verified_base(base, metadata)
        executable_pin = metadata.get('files', {}).get('Lib/venv/scripts/nt/python.exe')
        if not executable_pin or digest(root / 'venv/Scripts/python.exe') != executable_pin:
            raise ValueError('runtime_reuse_launcher_changed')
        config = private_home(root / 'venv/pyvenv.cfg')
        if config.stat().st_size > 8192:
            raise ValueError('runtime_reuse_base_reference_invalid')
        values = dict(line.split(' = ', 1) for line in config.read_text('utf8').splitlines() if ' = ' in line)
        if private_home(values.get('home', '')) != base:
            raise ValueError('runtime_reuse_base_reference_invalid')
        record = read(root / 'environment.json')
        if record.get('status') != 'ready' or record.get('cuda_available') is not True:
            raise ValueError('runtime_reuse_probe_not_ready')
        if role == 'tts':
            if marker['python_executable_sha256'] != metadata['python_executable_sha256'] or marker['runtime_instance_id'] != root.name:
                raise ValueError('runtime_reuse_marker_invalid')
            from . import runtime_probe
            if record.get('probe_sha256') != digest(Path(runtime_probe.__file__)) or record.get('runtime_instance_id') != root.name:
                raise ValueError('runtime_reuse_probe_changed')
            saved = {name.lower().replace('_', '-'): version for name, version in record.get('packages', {}).items()}
            if any(expected_packages.get(name) != version for name, version in saved.items()) or not saved:
                raise ValueError('runtime_reuse_probe_changed')
        else:
            if marker.get('adapter_id') != role or marker.get('python_base_kind') != 'verified_bundled_python' or marker.get('base_python_sha256') != metadata['python_executable_sha256']:
                raise ValueError('runtime_reuse_marker_invalid')
            if (record.get('adapter_id') != role or record.get('packages') != task_runtime.versions(role)
                    or record.get('setup_inputs_sha256') != digest(marker_path)
                    or record.get('resolved_packages_sha256') != digest(root / 'installed-packages.json')
                    or record.get('lock_sha256') != digest(root / 'requirements.lock')
                    or digest(root / 'requirements.lock') != digest(lock)):
                raise ValueError('runtime_reuse_probe_changed')
        probe = fresh_metadata(root, base, expected_packages)
        if probe['python'] != metadata['version']:
            raise ValueError('runtime_reuse_abi_mismatch')
        return dict(root=root, base=base, reused=True)

    roles = {'tts': (False, resources / 'requirements-runtime.lock')}
    roles.update({role: (role == 'qwen-image-2.1', task_runtime.requirements(role)) for role in task_runtime.LOCKS})
    for role, (image, lock) in roles.items():
        metadata = read(resources / ('python-image-runtime.json' if image else 'python-runtime.json'), 8 * 1024 * 1024)
        base = private_home(resources / ('python_image_runtime' if image else 'python_runtime'))
        identity = dict(role=role, archive=metadata['archive_sha256'], executable=metadata['python_executable_sha256'],
            files=hashlib.sha256(json.dumps(metadata['files'], sort_keys=True).encode()).hexdigest(), lock=digest(lock))
        instance = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        canonical = home / ('runtime-' + instance) if role == 'tts' else home / 'task-runtimes' / role / instance
        candidates = [canonical]
        parent, pattern = (home, 'runtime-*') if role == 'tts' else (home / 'task-runtimes' / role, '*')
        if parent.is_dir():
            candidates.extend(p for p in sorted(parent.glob(pattern)) if re.fullmatch(r'runtime-[a-f0-9]{16}' if role == 'tts' else r'[a-f0-9]{16}', p.name) and p != canonical)
        if len(candidates) > 64:
            raise ValueError('runtime_reuse_candidates_exceeded')
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            try:
                selected[role] = validate(candidate, role, metadata, lock, pins(lock))
                break
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
                allowed = {'runtime_reuse_lock_changed', 'runtime_reuse_base_files_changed', 'runtime_reuse_base_missing', 'runtime_reuse_launcher_changed',
                    'runtime_reuse_base_reference_invalid', 'runtime_reuse_probe_not_ready', 'runtime_reuse_marker_invalid',
                    'runtime_reuse_probe_changed', 'runtime_reuse_probe_failed', 'runtime_reuse_abi_mismatch', 'runtime_reuse_record_invalid'}
                code = str(error)
                diagnostics.append(dict(role=role, code=code if code in allowed else 'existing_runtime_unreadable'))
        if role not in selected:
            # Never reuse or overwrite an incompatible occupied root.
            if canonical.exists():
                fallback = hashlib.sha256((instance + str(base)).encode()).hexdigest()[:16]
                canonical = home / ('runtime-' + fallback) if role == 'tts' else home / 'task-runtimes' / role / fallback
            selected[role] = dict(root=canonical, base=base, reused=False)
    return dict(home=home, roles=selected, diagnostics=diagnostics)
