"""One explicit runtime per installed desktop Python base; legacy CLI stays compatible."""
import hashlib
import json
import os
from pathlib import Path
import re

from .config import private_home

INSTANCE_ENV = 'AI_MANAGER_RUNTIME_INSTANCE'


def configure_desktop_runtime(resources):
    resources = private_home(resources)
    metadata = json.loads((resources / 'python-runtime.json').read_text(encoding='utf-8'))
    binding = {'python_base': str(private_home(resources / 'python_runtime')),
               'python_archive_sha256': metadata['archive_sha256'],
               'requirements_sha256': hashlib.sha256((resources / 'requirements-runtime.lock').read_bytes()).hexdigest()}
    instance = hashlib.sha256(json.dumps(binding, sort_keys=True).encode('utf-8')).hexdigest()[:16]
    os.environ[INSTANCE_ENV] = instance  # This process and its owned children only.
    return instance


def runtime_directory(home):
    instance = os.environ.get(INSTANCE_ENV)
    if instance is not None and not re.fullmatch('[a-f0-9]{16}', instance):
        raise ValueError('runtime_instance_invalid')
    return private_home(Path(home) / ('runtime-' + instance if instance else 'runtime'))
