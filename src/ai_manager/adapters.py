"""Explicit typed adapters. Missing assets and unavailable workers never imply support."""
import hashlib
import json
from pathlib import Path
import re

CATALOG = {
    'whisper-large-v3-turbo': dict(task_type='stt', name='Whisper large-v3-turbo', worker='stt_worker.py', manifest='adapter_manifest_whisper.json', input_type='wav', output_types=['transcript', 'text']),
    'qwen-image-2.1': dict(task_type='image', name='Qwen Image 2.1', worker='image_worker.py', manifest='adapter_manifest_image.json', input_type='prompt', output_types=['image','image_metadata'], blocker='runtime_memory_feasibility_unconfirmed'),
    'llama-3.1-8b-instruct': dict(task_type='llm', name='Llama 3.1 8B Instruct', worker='llm_worker.py', manifest='adapter_manifest_llama.json', input_type='text', output_types=['response','response_text']),
    'tapir': dict(task_type='tracking', name='BootsTAPIR v2', worker='tracking_worker.py', manifest='adapter_manifest_tracking.json', input_type='video_points', output_types=['tracks','preview']),
}


def descriptor(identifier):
    if not isinstance(identifier, str) or identifier not in CATALOG:
        raise ValueError('adapter_unsupported')
    return dict(CATALOG[identifier], id=identifier)


def manifest_path(identifier):
    name = descriptor(identifier)['manifest']
    if not name:
        raise ValueError('adapter_manifest_unavailable')
    return Path(__file__).with_name(name)


def manifest(identifier):
    from .preparation import safe_relative
    path = manifest_path(identifier)
    if not path.is_file(): raise ValueError('adapter_manifest_unavailable')
    value = json.loads(path.read_text(encoding='utf8'))
    if value.get('model_id') != identifier or not isinstance(value.get('revision'), str) or not value['revision'] or not isinstance(value.get('files'), list) or not value['files'] or not value.get('license'):
        raise ValueError('adapter_manifest_invalid')
    names = set()
    for item in value['files']:
        safe_relative(item['path'])
        if item['path'] in names or type(item['size']) is not int or item['size'] <= 0 or not re.fullmatch('[a-f0-9]{64}', item['sha256']):
            raise ValueError('adapter_manifest_invalid')
        names.add(item['path'])
    return value


def configured_ids():
    result = []
    for identifier in CATALOG:
        try: manifest(identifier)
        except (ValueError, OSError, KeyError, TypeError): continue
        result.append(identifier)
    return result


def catalog(home):
    from .task_runtime import environment
    result = []
    for identifier in CATALOG:
        item = descriptor(identifier)
        item.pop('manifest', None); item.pop('worker', None)
        try:
            value = manifest(identifier)
            item.update(revision=value['revision'], provenance_kind=value.get('provenance_kind'), license=value['license'], manifest_sha256=hashlib.sha256(manifest_path(identifier).read_bytes()).hexdigest(), configuration='manifest_available')
        except (ValueError, OSError, KeyError, TypeError):
            item.update(configuration='unconfirmed', blocker=item.get('blocker', 'adapter_manifest_unavailable'))
        item['runtime'] = environment(home, identifier)
        item['implementation_available'] = bool(CATALOG[identifier]['worker']) and item['configuration']=='manifest_available'
        item['execution_verified'] = False
        # The app launches local workers. Separate cloud experiment artifacts
        # never grant this catalog or a registered local model an execution PASS.
        item['execution_target'] = 'local'
        item['resource_check'] = 'at_run_start'
        item['execution_advisories'] = [item['blocker']] if item.get('blocker') else []
        item['execution_blockers'] = ([] if item['implementation_available'] else ['adapter_unsupported']) + ([] if item['runtime']['status']=='ready' else ['adapter_runtime_not_ready'])
        item['execution_eligibility'] = 'blocked' if item['execution_blockers'] else 'requires_run_preflight'
        if identifier == 'qwen-image-2.1':
            from .image_worker import MEMORY_REQUIREMENTS
            item['memory_requirements'] = dict(MEMORY_REQUIREMENTS)
        result.append(item)
    return result
