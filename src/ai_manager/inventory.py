"""Explicit-root inventory with immutable per-scan SQLite observations."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from .drive import Cancelled, Drive, DriveError, FOLDER, SHORTCUT, valid_id

_ACTIVE = set()
_LOCK = threading.RLock()
DENIED_FOLDERS = {".cache", "cache", "caches", "output", "outputs", "results", "result", "runs", "logs", "backup", "backups", ".git", "__pycache__", "node_modules", ".venv"}
WEIGHTS = {".safetensors", ".bin", ".pt", ".pth", ".ckpt", ".gguf", ".onnx", ".h5", ".tflite", ".pb", ".model"}
COMPONENTS = {".vocab", ".merges", ".tiktoken"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def kind(name):
    lower = name.casefold()
    extension = Path(lower).suffix
    if extension in WEIGHTS:
        return "weight_candidate"
    if extension in COMPONENTS or lower in {"config.json", "configuration.json", "generation_config.json", "preprocessor_config.json", "processor_config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json", "vocab.json", "config.yaml", "config.yml", "model.safetensors.index.json", "pytorch_model.bin.index.json", "tokenizer.txt", "vocab.txt", "merges.txt", "added_tokens.txt", "special_tokens.txt"}:
        return "model_component_candidate"
    if lower in {"readme", "readme.md", "readme.txt", "license", "license.md", "license.txt", "notice", "notice.txt"}:
        return "distribution_document_candidate"
    return None


def _alive(pid):
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        code = wintypes.DWORD()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok and code.value == 259)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Inventory:
    def __init__(self, home: Path, session=None, sleep=None):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = self.home / "inventory.sqlite3"
        self.session = session
        self.sleep = sleep
        with self.connect() as db, _LOCK:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY, account TEXT NOT NULL, settings_version INTEGER NOT NULL,
                    settings_json TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL, pid INTEGER NOT NULL, files_count INTEGER NOT NULL DEFAULT 0,
                    folders_count INTEGER NOT NULL DEFAULT 0, excluded_count INTEGER NOT NULL DEFAULT 0,
                    pages_count INTEGER NOT NULL DEFAULT 0, errors_json TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS files (
                    scan_id TEXT NOT NULL REFERENCES scans(scan_id), file_id TEXT NOT NULL,
                    root_alias TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL,
                    metadata_json TEXT NOT NULL, PRIMARY KEY(scan_id,file_id));
                CREATE UNIQUE INDEX IF NOT EXISTS one_running_per_account ON scans(account) WHERE status='running';
            """)
            for row in db.execute("SELECT scan_id,pid FROM scans WHERE status='running'").fetchall():
                if row["scan_id"] not in _ACTIVE and (row["pid"] == os.getpid() or not _alive(row["pid"])):
                    db.execute("UPDATE scans SET status='interrupted',finished_at=?,errors_json=? WHERE scan_id=?",
                               (utcnow(), '["process_interrupted"]', row["scan_id"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def scan(self, settings, account, access, cancel=None):
        if account not in {"A", "B"}:
            raise ValueError("account must be A or B")
        # Freeze approved scope before any network activity or background settings edits.
        snapshot = json.loads(json.dumps(settings))
        roots = [r for r in snapshot.get("allowlist", []) if r.get("account") == account]
        if not roots or any(not valid_id(r.get("id")) or not isinstance(r.get("alias"), str) or not r["alias"] for r in roots):
            raise ValueError("an explicit valid account allowlist is required")
        version = snapshot.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("settings version must be a positive integer")
        scan_id = uuid.uuid4().hex
        with _LOCK, self.connect() as db:
            db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid) VALUES(?,?,?,?,?,'running',?)",
                       (scan_id, account, version, json.dumps(snapshot, ensure_ascii=False), utcnow(), os.getpid()))
            _ACTIVE.add(scan_id)
        counters = dict(files_count=0, folders_count=0, excluded_count=0, pages_count=0)
        errors = []
        status = "complete"
        args = {"session": self.session, "cancel": cancel}
        if self.sleep is not None:
            args["sleep"] = self.sleep
        drive = Drive(access, **args)
        visited = set()
        observed = set()
        try:
            for root in roots:
                drive.check_cancel()
                root_id = root["id"]
                try:
                    metadata = drive.metadata(root_id)
                    if metadata.get("id") != root_id or metadata.get("mimeType") != FOLDER or metadata.get("driveId") or metadata.get("trashed"):
                        raise DriveError("root_not_allowed_folder")
                    queue = deque([(root_id, root["alias"])])
                    while queue:
                        if counters["folders_count"] >= 50000:
                            raise DriveError("folder_limit_reached")
                        folder_id, path = queue.popleft()
                        if folder_id in visited:
                            continue
                        visited.add(folder_id)
                        counters["folders_count"] += 1
                        token = None
                        tokens = set()
                        while True:
                            if counters["pages_count"] >= 100000:
                                raise DriveError("page_limit_reached")
                            drive.check_cancel()
                            page = drive.children(folder_id, token)
                            counters["pages_count"] += 1
                            if page.get("incompleteSearch"):
                                errors.append("incomplete_search")
                            entries = page.get("files")
                            if not isinstance(entries, list):
                                raise DriveError("invalid_files_page")
                            for item in entries:
                                drive.check_cancel()
                                if not isinstance(item, dict):
                                    errors.append("invalid_file_metadata")
                                    continue
                                file_id = item.get("id")
                                name = item.get("name")
                                if not valid_id(file_id) or not isinstance(name, str) or not name or folder_id not in item.get("parents", []):
                                    errors.append("outside_parent_or_invalid_metadata")
                                    continue
                                if item.get("driveId") or item.get("trashed") or item.get("mimeType") == SHORTCUT:
                                    counters["excluded_count"] += 1
                                    continue
                                child_path = path + "/" + name
                                if item.get("mimeType") == FOLDER:
                                    if name.casefold() in DENIED_FOLDERS:
                                        counters["excluded_count"] += 1
                                    elif file_id not in visited:
                                        queue.append((file_id, child_path))
                                    continue
                                category = kind(name)
                                if category is None or str(item.get("mimeType", "")).startswith("application/vnd.google-apps."):
                                    counters["excluded_count"] += 1
                                    continue
                                if file_id in observed:
                                    continue
                                if counters["files_count"] >= 250000:
                                    raise DriveError("file_limit_reached")
                                observed.add(file_id)
                                with self.connect() as db:
                                    db.execute("INSERT INTO files VALUES(?,?,?,?,?,?)", (scan_id, file_id, root["alias"], child_path, category, json.dumps(item, ensure_ascii=False)))
                                counters["files_count"] += 1
                            self._progress(scan_id, counters, errors)
                            next_token = page.get("nextPageToken")
                            if next_token is None:
                                break
                            if not isinstance(next_token, str) or not next_token or next_token in tokens:
                                raise DriveError("repeated_or_invalid_page_token")
                            tokens.add(next_token)
                            token = next_token
                except Cancelled:
                    raise
                except DriveError as exc:
                    errors.append(str(exc))
            if errors:
                status = "partial"
        except Cancelled:
            status = "cancelled"
            errors.append("cancelled")
        except Exception:
            # Keep all credential-bearing exception messages out of persisted evidence.
            status = "partial"
            errors.append("unexpected_scan_error")
        finally:
            with _LOCK, self.connect() as db:
                self._progress(scan_id, counters, errors, db)
                db.execute("UPDATE scans SET status=?,finished_at=? WHERE scan_id=?", (status, utcnow(), scan_id))
                _ACTIVE.discard(scan_id)
        return self.scan_info(scan_id)

    def _progress(self, scan_id, counters, errors, db=None):
        values = tuple(counters[k] for k in ("files_count", "folders_count", "excluded_count", "pages_count"))
        query = "UPDATE scans SET files_count=?,folders_count=?,excluded_count=?,pages_count=?,errors_json=? WHERE scan_id=?"
        params = values + (json.dumps(sorted(set(errors))), scan_id)
        if db is not None:
            db.execute(query, params)
        else:
            with self.connect() as connection:
                connection.execute(query, params)

    @staticmethod
    def _public(row):
        result = dict(row)
        result.pop("settings_json", None)
        result.pop("pid", None)
        result["errors"] = json.loads(result.pop("errors_json"))
        return result

    def scan_info(self, scan_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM scans WHERE scan_id=?", (scan_id,)).fetchone()
        if row is None:
            raise ValueError("unknown scan")
        return self._public(row)

    def summary(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM scans ORDER BY started_at DESC LIMIT 100").fetchall()
        return {"scans": [self._public(row) for row in rows]}

    def files(self, scan_id, limit=100, offset=0):
        if not isinstance(limit, int) or not 1 <= limit <= 1000 or not isinstance(offset, int) or offset < 0:
            raise ValueError("invalid pagination")
        with self.connect() as db:
            rows = db.execute("SELECT * FROM files WHERE scan_id=? ORDER BY path,file_id LIMIT ? OFFSET ?", (scan_id, limit, offset)).fetchall()
        return [{"file_id": row["file_id"], "root_alias": row["root_alias"], "path": row["path"], "kind": row["kind"], "metadata": json.loads(row["metadata_json"])} for row in rows]
