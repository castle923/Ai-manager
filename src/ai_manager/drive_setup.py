"""Explicit local-to-Drive configuration; no token import or OAuth side effect."""
import hashlib
import json
import os
from pathlib import Path
import uuid

from .auth import client_config
from .config import private_home, validate
from .inference import FileOwner


def original(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('drive_setup_original_required')
    target = private_home(path.strip())
    if not target.is_file() or target.suffix.lower() != '.json' or not 0 < target.stat().st_size <= 1048576:
        raise ValueError('drive_setup_original_required')
    return target, target.read_bytes()


def configuration(client_path, allowlist_path):
    client, client_raw = original(client_path)
    allowlist, allowlist_raw = original(allowlist_path)
    validated_client = client_config(client)  # Existing official endpoint checks.
    if validated_client != json.loads(client_raw.decode('utf-8-sig')).get('installed', {}):
        raise ValueError('drive_setup_original_changed')
    values = json.loads(allowlist_raw.decode('utf-8-sig'))
    settings = dict(version=1, accounts=values['accounts'], allowlist=values['roots'], client_path=str(client),
                    sources=[dict(kind='designated_allowlist', path=str(allowlist), sha256=hashlib.sha256(allowlist_raw).hexdigest()),
                             dict(kind='desktop_oauth_client', path=str(client), sha256=hashlib.sha256(client_raw).hexdigest())])
    validate(settings)
    if client.read_bytes() != client_raw or allowlist.read_bytes() != allowlist_raw:
        raise ValueError('drive_setup_original_changed')
    return settings


class ConfigurationChange:
    """Hold the cooperative config lock through server replacement or rollback."""
    def __init__(self, home, expected, settings):
        self.home = private_home(home)
        self.path = private_home(self.home/'settings.json')
        self.expected = expected
        self.settings = validate(settings)
        self.owner = FileOwner(private_home(self.home/'drive-setup.lock'))
        self.installed = None
        self.backup = None
        if not self.owner.handle:
            raise ValueError('drive_setup_busy')

    def apply(self):
        if self.path.read_bytes() != self.expected:
            raise ValueError('drive_setup_settings_changed')
        current = validate(json.loads(self.expected))
        if current.get('mode') != 'local' or (self.home/'credentials').exists():
            raise ValueError('drive_setup_requires_local_workspace')
        if self.settings.get('mode') == 'local':
            raise ValueError('drive_setup_invalid')
        identifier = uuid.uuid4().hex
        self.backup = private_home(self.home/('settings-before-drive-'+identifier+'.json'))
        with self.backup.open('xb') as stream:
            stream.write(self.expected)
            stream.flush()
            os.fsync(stream.fileno())
        replacement = private_home(self.home/('settings-drive-'+identifier+'.partial'))
        raw = json.dumps(self.settings, ensure_ascii=False, indent=2).encode('utf8')
        with replacement.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if self.path.read_bytes() != self.expected:
            raise ValueError('drive_setup_settings_changed')
        os.replace(replacement, self.path)
        self.installed = raw

    def rollback(self):
        if self.installed is None:
            return
        if self.path.read_bytes() != self.installed:
            raise ValueError('drive_setup_rollback_conflict_restart_required')
        replacement = private_home(self.home/('settings-rollback-'+uuid.uuid4().hex+'.partial'))
        with replacement.open('xb') as stream:
            stream.write(self.expected)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(replacement, self.path)
        self.installed = None

    def close(self):
        self.owner.close()
