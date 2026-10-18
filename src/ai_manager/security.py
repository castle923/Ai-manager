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


def _system_tool(name):
    """Resolve only the Windows system tools used for private directory ACLs."""
    if name not in ('whoami.exe', 'icacls.exe'):
        raise ValueError('Unsupported private storage tool')
    buffer = ctypes.create_unicode_buffer(32768)
    function = ctypes.windll.kernel32.GetSystemDirectoryW
    function.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    function.restype = wintypes.UINT
    length = function(buffer, len(buffer))
    if not length or length >= len(buffer) or not Path(buffer.value).is_absolute():
        raise RuntimeError('Cannot identify Windows system directory')
    return str(Path(buffer.value) / name)


def protect_directory(directory):
    """Restrict private state to current Windows user and SYSTEM."""
    from .config import private_home
    directory = private_home(directory)
    directory.mkdir(parents=True, exist_ok=True)
    empty = not any(directory.iterdir())
    if os.name != "nt":
        raise RuntimeError("Windows private storage required")
    from .external_process import run_external
    hidden = dict(stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    identity = run_external([_system_tool('whoami.exe'), "/user", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, check=True, timeout=10, **hidden)
    sid = next(csv.reader(io.StringIO(identity.stdout)))[1]
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise RuntimeError("Cannot identify current Windows user")
    # Reapplying inheritable ACLs to a populated workspace can propagate to all
    # descendants. Read the actual protected DACL first; never trust a marker.
    if directory_is_private(directory, sid):
        return
    if not empty:
        raise RuntimeError('Existing private storage ACL verification failed')
    result = run_external([_system_tool('icacls.exe'), str(directory), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                          capture_output=True, timeout=30, **hidden)
    if result.returncode:
        raise RuntimeError("Cannot protect private storage")
    if not directory_is_private(directory, sid):
        raise RuntimeError("Cannot verify private storage")


def private_acl_contract(protected, owner, rules, sid):
    """Only the exact current-user/SYSTEM full-control directory ACL is ready."""
    return (protected is True and owner == sid and len(rules) == 2
        and {rule[0] for rule in rules} == {sid, 'S-1-5-18'}
        and all(kind == 0 and flags == 3 and mask == 0x1F01FF
            for _, kind, flags, mask in rules))


def directory_is_private(directory, sid):
    """Inspect the DACL with Win32 APIs; do not mutate ACLs or enumerate children."""
    if os.name != 'nt':
        return False
    from .config import private_home
    directory = private_home(directory)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.c_void_p
    advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
        ctypes.POINTER(pointer), pointer, ctypes.POINTER(pointer), pointer, ctypes.POINTER(pointer)]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.IsValidSecurityDescriptor.argtypes = [pointer]
    advapi.IsValidSecurityDescriptor.restype = wintypes.BOOL
    advapi.IsValidAcl.argtypes = [pointer]
    advapi.IsValidAcl.restype = wintypes.BOOL
    advapi.IsValidSid.argtypes = [pointer]
    advapi.IsValidSid.restype = wintypes.BOOL
    advapi.GetLengthSid.argtypes = [pointer]
    advapi.GetLengthSid.restype = wintypes.DWORD
    advapi.GetSecurityDescriptorControl.argtypes = [pointer, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
    class AclSize(ctypes.Structure):
        _fields_ = [('count', wintypes.DWORD), ('used', wintypes.DWORD), ('free', wintypes.DWORD)]
    advapi.GetAclInformation.argtypes = [pointer, pointer, wintypes.DWORD, ctypes.c_int]
    advapi.GetAclInformation.restype = wintypes.BOOL
    advapi.GetAce.argtypes = [pointer, wintypes.DWORD, ctypes.POINTER(pointer)]
    advapi.GetAce.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(pointer)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    descriptor, owner, dacl = pointer(), pointer(), pointer()
    def sid_text(value):
        text = pointer()
        if not advapi.IsValidSid(value) or not advapi.ConvertSidToStringSidW(value, ctypes.byref(text)):
            raise OSError('private_acl_read_failed')
        try:
            return ctypes.cast(text, ctypes.c_wchar_p).value
        finally:
            kernel.LocalFree(text)
    try:
        if advapi.GetNamedSecurityInfoW(str(directory), 1, 5, ctypes.byref(owner), None,
                ctypes.byref(dacl), None, ctypes.byref(descriptor)) or not dacl:
            return False
        if not advapi.IsValidSecurityDescriptor(descriptor) or not advapi.IsValidAcl(dacl):
            return False
        control, revision = wintypes.WORD(), wintypes.DWORD()
        size = AclSize()
        if (not advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision))
                or not advapi.GetAclInformation(dacl, ctypes.byref(size), ctypes.sizeof(size), 2)
                or size.count != 2):
            return False
        rules = []
        for index in range(size.count):
            ace = pointer()
            if not advapi.GetAce(dacl, index, ctypes.byref(ace)):
                return False
            header = ctypes.string_at(ace, 4)
            ace_size = int.from_bytes(header[2:4], 'little')
            if header[0] != 0 or ace_size < 20:
                return False
            if not advapi.IsValidSid(ace.value + 8) or advapi.GetLengthSid(ace.value + 8) > ace_size - 8:
                return False
            mask = ctypes.cast(ace.value + 4, ctypes.POINTER(wintypes.DWORD)).contents.value
            rules.append((sid_text(ace.value + 8), header[0], header[1], mask))
        return private_acl_contract(bool(control.value & 0x1000), sid_text(owner), rules, sid)
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)


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
