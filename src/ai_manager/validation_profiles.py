"""Six pinned public contracts. Reads packaged manifests, never model folders."""
import hashlib
from pathlib import Path
from .validation_contracts import load_json, document_sha, fail

# Manifest bytes are part of the versioned catalogue, not runtime discovery.
SPECS = (
    ('model_manifest.json', '90ffd45e6be59c204a018d8595defd5c0cf7e708b193089a7313a4b79ee854c0', 'text', 'wav', 'm11-new-text-v1'),
    ('model_manifest_1.7b.json', '38677226f853c29e3630ff8e395eb35264040aea92a43571fc2236a9b37a4e08', 'text', 'wav', 'm11-new-text-v1'),
    ('adapter_manifest_whisper.json', 'de849175ecf8d9c261ab54987f973e3472b5b259b20b641c78a48d8a914e76c0', 'audio16k', 'transcript', 'm11-derived-wav16k-v1'),
    ('adapter_manifest_image.json', '695b34f4644255807691a3bff00517d3a7b0181f87def26a1beff4053148bb62', 'prompt', 'image', 'm11-new-prompt-v1'),
    ('adapter_manifest_llama.json', 'a8fcf721121d9704daea0b45189868cdc479b18e6755df07d984e8637007318d', 'text', 'response', 'm11-new-text-v1'),
    ('adapter_manifest_tracking.json', 'f40e1200e68cead27e4b2b5042081066054506e573fe83d14fa32eb6d3435afb', 'video_points', 'tracks', 'm11-new-synthetic-video-v1'),
)


def catalog():
    profiles = {}
    for filename, expected, input_kind, output_kind, recipe in SPECS:
        try:
            raw = (Path(__file__).parent / filename).read_bytes()
        except OSError:
            fail('catalog_read_failed')
        if hashlib.sha256(raw).hexdigest() != expected:
            fail('catalog_manifest_changed')
        source = load_json(raw)
        profile = {
            'profile_id': source['model_id'], 'name': source['name'],
            'revision': source['revision'], 'manifest_sha256': expected,
            'file_count': len(source['files']),
            'required_bytes': sum(item['size'] for item in source['files']),
            'license': source['license'], 'input_kind': input_kind,
            'output_kind': output_kind, 'recipe_id': recipe,
        }
        profiles[profile['profile_id']] = profile
    if len(profiles) != 6:
        fail('catalog_invalid')
    return profiles, document_sha({'schema_version': 1, 'profiles': profiles})
