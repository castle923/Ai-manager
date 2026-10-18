"""One explicit runtime per installed desktop Python base; legacy CLI stays compatible."""
import hashlib
import json
import os
from pathlib import Path
import re

from .config import private_home

INSTANCE_ENV = 'AI_MANAGER_RUNTIME_INSTANCE'
_DESKTOP_CONTEXT = None


def configure_desktop_runtime(resources, home=None):
    global _DESKTOP_CONTEXT
    if home is not None:
        from .runtime_reuse import bind
        _DESKTOP_CONTEXT = bind(resources, home)
        instance = _DESKTOP_CONTEXT['roles']['tts']['root'].name.removeprefix('runtime-')
        os.environ[INSTANCE_ENV] = instance
        return instance
    _DESKTOP_CONTEXT = None
    resources = private_home(resources)
    metadata = json.loads((resources / 'python-runtime.json').read_text(encoding='utf-8'))
    binding = {'python_base': str(private_home(resources / 'python_runtime')),
               'python_archive_sha256': metadata['archive_sha256'],
               'requirements_sha256': hashlib.sha256((resources / 'requirements-runtime.lock').read_bytes()).hexdigest()}
    image_metadata=resources/'python-image-runtime.json'
    if image_metadata.is_file():
        image=json.loads(image_metadata.read_text('utf8'))
        binding.update(image_python_base=str(private_home(resources/'python_image_runtime')),image_python_archive_sha256=image['archive_sha256'])
    locks={}
    for name in ('requirements_stt.lock','requirements_tracking.lock','requirements_llm.lock','requirements_image.lock'):
        component=resources/'ai_manager'/name
        if component.is_file():locks[name]=hashlib.sha256(component.read_bytes()).hexdigest()
    if locks:binding['adapter_requirements_sha256']=locks
    instance = hashlib.sha256(json.dumps(binding, sort_keys=True).encode('utf-8')).hexdigest()[:16]
    os.environ[INSTANCE_ENV] = instance  # This process and its owned children only.
    return instance


def runtime_directory(home):
    if _DESKTOP_CONTEXT is not None and private_home(home) == _DESKTOP_CONTEXT['home']:
        return private_home(_DESKTOP_CONTEXT['roles']['tts']['root'])
    instance = os.environ.get(INSTANCE_ENV)
    if instance is not None and not re.fullmatch('[a-f0-9]{16}', instance):
        raise ValueError('runtime_instance_invalid')
    return private_home(Path(home) / ('runtime-' + instance if instance else 'runtime'))


def adapter_runtime_root(home, identifier):
    if _DESKTOP_CONTEXT is not None and private_home(home) == _DESKTOP_CONTEXT['home']:
        return private_home(_DESKTOP_CONTEXT['roles'][identifier]['root'])
    instance = runtime_directory(home).name
    directory = Path(home) / 'task-runtimes' / identifier
    return private_home(directory / instance.removeprefix('runtime-') if instance != 'runtime' else directory)


def python_base(home, role, default):
    if _DESKTOP_CONTEXT is not None and private_home(home) == _DESKTOP_CONTEXT['home']:
        return private_home(_DESKTOP_CONTEXT['roles'][role]['base'])
    return private_home(default)


def runtime_dependencies(home):
    if _DESKTOP_CONTEXT is None or private_home(home) != _DESKTOP_CONTEXT['home']:
        return []
    return [dict(role=role, runtime_root=str(value['root']), python_base=str(value['base']),
        reused=value['reused'], base_required=True, validation='startup_manifest_and_fresh_metadata')
        for role, value in _DESKTOP_CONTEXT['roles'].items()]


def reused_runtime(home, role):
    return bool(_DESKTOP_CONTEXT is not None and private_home(home) == _DESKTOP_CONTEXT['home']
        and _DESKTOP_CONTEXT['roles'][role]['reused'])
