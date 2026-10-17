"""Single-app private settings and explicit designated input provenance."""
import hashlib
import json
import os
from pathlib import Path


def private_home(override=None):
    if override is not None:
        value = Path(override)
        if not value.is_absolute() or '..' in value.parts:
            raise ValueError("App home must be an absolute path without traversal")
        for item in (value, *value.parents):
            try:
                info = item.lstat()
            except FileNotFoundError:
                continue
            if item.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError("App home cannot use reparse paths")
        return value.resolve()
    return Path(os.environ["LOCALAPPDATA"]) / "AiManager" / "m1-20261016"


def validate(settings):
    import re
    if set(settings["accounts"]) != {"A", "B"}:
        raise ValueError("Exactly account A and B are required")
    emails = list(settings["accounts"].values())
    if any(not isinstance(v, str) or "@" not in v for v in emails) or len(set(v.casefold() for v in emails)) != 2:
        raise ValueError("Two distinct expected accounts required")
    if not settings["allowlist"]:
        raise ValueError("Explicit allowlist required")
    for entry in settings["allowlist"]:
        if entry["account"] not in settings["accounts"] or not re.fullmatch(r"[A-Za-z0-9_-]+", entry["id"]):
            raise ValueError("Invalid allowlist entry")
    if len({(r["account"], r["id"]) for r in settings["allowlist"]}) != len(settings["allowlist"]):
        raise ValueError("Duplicate allowlist roots")
    return settings


class SettingsStore:
    def __init__(self, home):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        from .security import protect_directory
        protect_directory(self.home)
        self.path = self.home / "settings.json"

    def load(self):
        return validate(json.loads(self.path.read_text(encoding="utf-8")))

    def initialize(self, source, client):
        if self.path.exists():
            raise ValueError("App already initialized; existing configuration preserved")
        source_path, client_path = Path(source).resolve(), Path(client).resolve()
        allowed = json.loads(source_path.read_text(encoding="utf-8-sig"))
        settings = dict(version=1, accounts=allowed["accounts"], allowlist=allowed["roots"], client_path=str(client_path),
                        sources=[{"kind": "designated_allowlist", "path": str(source_path), "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()},
                                 {"kind": "desktop_oauth_client", "path": str(client_path), "sha256": hashlib.sha256(client_path.read_bytes()).hexdigest()}])
        validate(settings)
        with self.path.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(settings, ensure_ascii=False, indent=2))
        return settings
