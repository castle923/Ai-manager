"""Explicit, versioned model allowlist; never discover executable models by path."""
import json
from pathlib import Path

DEFAULT_MODEL = 'qwen3-tts-0.6b-customvoice'
SECOND_MODEL = 'qwen3-tts-1.7b-customvoice'
MODEL_FILES = {DEFAULT_MODEL: 'model_manifest.json', SECOND_MODEL: 'model_manifest_1.7b.json'}


def manifest_path(model_id=DEFAULT_MODEL):
    if not isinstance(model_id, str) or model_id not in MODEL_FILES:
        raise ValueError('unsupported_model')
    return Path(__file__).with_name(MODEL_FILES[model_id])


def load_manifest(model_id=DEFAULT_MODEL):
    path = manifest_path(model_id)
    if not path.is_file():
        raise ValueError('model_manifest_unavailable')
    value = json.loads(path.read_text(encoding='utf8'))
    if value.get('model_id') != model_id:
        raise ValueError('model_manifest_invalid')
    return value


def model_ids():
    return list(MODEL_FILES)


def segment(model_id=DEFAULT_MODEL):
    return load_manifest(model_id)['name'].split('/')[-1]
