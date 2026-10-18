"""Explicit user-folder installation of the verified portable application."""
import hashlib
import json
import os
from pathlib import Path

from .config import private_home


def install_to_new_directory(source, destination, home):
    source, target, home = map(private_home, (source, destination, home))
    for left, right in ((source, target), (home, target)):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError('installation_paths_overlap')
    if target.exists():
        raise ValueError('installation_destination_exists')
    manifest = json.loads((source / 'DESKTOP-MANIFEST.json').read_text(encoding='utf-8'))
    if manifest['version'] != '0.10.0':
        raise ValueError('installation_version_invalid')
    checked = []
    for relative, expected in manifest['files'].items():
        path = private_home(source / relative)
        if not path.is_relative_to(source) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('installation_integrity_failed')
        checked.append((relative, path, expected))
    target.mkdir(parents=False, exist_ok=False)
    for relative, source_file, expected in checked:
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as handle:
            handle.write(source_file.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        if hashlib.sha256(output.read_bytes()).hexdigest() != expected:
            raise ValueError('installation_copy_integrity_failed')
    with (target / 'DESKTOP-MANIFEST.json').open('xb') as handle:
        handle.write((source / 'DESKTOP-MANIFEST.json').read_bytes())
    if not (target / 'AiManager.exe').is_file():
        raise ValueError('installation_executable_missing')
    return {'status': 'installed', 'version': '0.10.0', 'files_verified': len(checked)}
