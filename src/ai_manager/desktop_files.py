"""Native desktop saves: verified successful output to a new user-selected file."""
import hashlib
import os
from pathlib import Path
import re
import tempfile


def safe_destination(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('save_destination_unsafe')
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('save_destination_unsafe')
    if path.exists() or not path.parent.is_dir():
        raise ValueError('save_destination_exists_or_missing_parent')
    return path


def save_output(inference, run_id, destination):
    if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
        raise ValueError('run_not_found')
    if not inference.owner.handle or inference.closed.is_set():
        raise ValueError('server_owner_unavailable')
    run = inference.get(run_id)
    if run['status'] != 'succeeded':
        raise ValueError('output_not_ready')
    data = inference.audio(run_id)
    target = safe_destination(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ai-manager-', suffix='.partial', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        safe_destination(target)
        if os.name == 'nt':
            # Windows rename refuses an existing destination and also works on
            # user-selected filesystems without hard-link support.
            os.rename(temporary, target)
        else:
            os.link(temporary, target)
        return {'status': 'saved', 'filename': target.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
