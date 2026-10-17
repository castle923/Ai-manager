"""Current-user Windows DPAPI storage. Never persist plaintext credentials."""
import ctypes
import json
import os
import re
import tempfile
import subprocess
import csv
import io
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path


def protect_directory(directory):
    """Restrict private state to current Windows user and SYSTEM."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        raise RuntimeError("Windows private storage required")
    from .external_process import run_external
    identity = run_external(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True)
    sid = next(csv.reader(io.StringIO(identity.stdout)))[1]
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise RuntimeError("Cannot identify current Windows user")
    result = run_external(["icacls", str(directory), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True)
    if result.returncode:
        raise RuntimeError("Cannot protect private storage")


class SecretStore:
    def __init__(self, directory: Path):
        if os.name != "nt":
            raise RuntimeError("Windows DPAPI is required; no plaintext fallback")
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", key):
            raise ValueError("Invalid credential key")
        return self.directory / (key + ".dpapi")

    @staticmethod
    def _crypt(data: bytes, encrypt: bool) -> bytes:
        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]
        source_buffer = ctypes.create_string_buffer(data)
        source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
        target = Blob()
        crypt = ctypes.windll.crypt32
        if encrypt:
            ok = crypt.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
        else:
            ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
        if not ok:
            raise RuntimeError("Windows credential protection failed")
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            ctypes.windll.kernel32.LocalFree(target.data)

    def put(self, key, value):
        path = self._path(key)
        encrypted = self._crypt(json.dumps(value).encode(), True)
        with tempfile.NamedTemporaryFile(dir=self.directory, prefix=key + "-", suffix=".new", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(encrypted)
        try:
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    @contextmanager
    def lock(self, key):
        """OS advisory lock spans token read, refresh/revoke, and commit."""
        import msvcrt
        path = self._path(key).with_suffix(".lock")
        with path.open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("account_operation_busy") from None
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def get(self, key):
        path = self._path(key)
        return json.loads(self._crypt(path.read_bytes(), False)) if path.exists() else None

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)
