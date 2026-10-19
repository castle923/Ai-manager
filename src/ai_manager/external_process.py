"""Spawn external tools without inheriting a frozen host's DLL/Python paths."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import threading

_spawn_lock = threading.RLock()


def isolated_environment(environment=None):
    env = dict(os.environ if environment is None else environment)
    for key in list(env):
        if key.upper() in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'VIRTUAL_ENV') or key.startswith('_PYI_') or key == '_MEIPASS2':
            env.pop(key, None)
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        root = Path(bundle).resolve()
        env['PATH'] = os.pathsep.join(part for part in env.get('PATH', '').split(os.pathsep)
                                      if part and not Path(part).resolve().is_relative_to(root))
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


@contextmanager
def _external_dll_search():
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    previous = ctypes.create_unicode_buffer(32768)
    length = kernel.GetDllDirectoryW(len(previous), previous)
    if length >= len(previous) or not kernel.SetDllDirectoryW(None):
        raise OSError('external_process_environment_failed')
    try:
        yield
    finally:
        if not kernel.SetDllDirectoryW(previous.value if length else None):
            raise OSError('host_process_environment_restore_failed')


def spawn_external(args, *, popen=subprocess.Popen, **options):
    options['env'] = isolated_environment(options.get('env'))
    process = None
    try:
        with _spawn_lock, _external_dll_search():
            process = popen(args, **options)
    except BaseException:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=15)
        raise
    return process


def run_external(args, *, capture_output=False, timeout=None, check=False, input=None, **options):
    if capture_output:
        if 'stdout' in options or 'stderr' in options:
            raise ValueError('capture_output_conflicts_with_streams')
        options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input is not None:
        options['stdin'] = subprocess.PIPE
    with spawn_external(args, **options) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except BaseException:
            process.kill()
            process.wait()
            raise
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
