"""New M5 registry, pinned supplement and preservation contract tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import threading

from ai_manager.models import DEFAULT_MODEL, SECOND_MODEL, load_manifest, manifest_path
from ai_manager.preparation import Preparation, PreparationError
from test_preparation_review import FakeDrive, PAYLOAD, DIGEST


class ModelPreparationTests(unittest.TestCase):
    def test_registry_rejects_unknown_paths_and_preserves_default_location(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            first = Preparation(home)
            second = Preparation(home, model_id=SECOND_MODEL)
            self.assertEqual(first.current, home / 'preparations' / 'current.json')
            self.assertEqual(second.current, home / 'preparations' / SECOND_MODEL / 'current.json')
            first.current.parent.mkdir()
            first.current.write_text('{"status":"idle","preserved":"original"}')
            before = first.current.read_bytes()
            second.snapshot()
            self.assertEqual(first.current.read_bytes(), before)
            for model_id in ('../x', '/x', None, 'unknown'):
                with self.assertRaises(ValueError): manifest_path(model_id)

    def test_pinned_second_manifest_has_only_one_small_supplement(self):
        first, second = load_manifest(DEFAULT_MODEL), load_manifest(SECOND_MODEL)
        self.assertEqual(len(first['files']), 13)
        self.assertEqual(len(second['files']), 12)
        self.assertEqual(sum(item['size'] for item in second['files']), 4_520_217_432)
        supplements = [item for item in second['files'] if item.get('official_supplement')]
        self.assertEqual(len(supplements), 1)
        self.assertEqual(supplements[0]['path'], 'speech_tokenizer/config.json')
        self.assertEqual(supplements[0]['size'], 2336)
        self.assertEqual(supplements[0]['official_supplement']['observed_drive_bytes'], 0)
        self.assertTrue(all(len(item['sha256']) == 64 for item in second['files']))

    def test_prepare_preserves_empty_drive_component_and_records_dual_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            drive = FakeDrive()
            drive.items['supp'] = dict(id='supp', name='config.json', parents=['speech'], mimeType='application/octet-stream',
                                       size='0', version='1', sha256Checksum=hashlib.sha256(b'').hexdigest())
            model = dict(model_id=SECOND_MODEL, name='Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice', revision='synthetic', source='https://example.invalid/official',
                         files=[dict(path='config.json', size=len(PAYLOAD), sha256=DIGEST),
                                dict(path='speech_tokenizer/config.json', size=len(PAYLOAD), sha256=DIGEST,
                                     official_supplement=dict(url='https://example.invalid/pinned-config', observed_drive_bytes=0))])
            prep = Preparation(home, {'allowlist':[{'account':'B','id':'root'}]}, object(), lambda *args, **kwargs:drive, model_id=SECOND_MODEL)
            observed = [{'path':'B_ROOT/'+prep.segment+'/config.json','metadata':drive.items['config']}]
            original = dict(drive.items['supp'])
            with patch('ai_manager.preparation.manifest', return_value=model), patch.object(prep, '_observed', return_value=observed), patch.object(prep, '_official_content', return_value=iter([PAYLOAD])):
                state = prep.prepare()
            self.assertEqual(state['status'], 'ready')
            self.assertEqual(drive.items['supp'], original)
            run = prep.base / state['id']
            self.assertEqual((run/'assets/speech_tokenizer/config.json').read_bytes(), PAYLOAD)
            provenance = json.loads((run/'inputs.json').read_text())
            self.assertEqual(provenance['origins']['config.json']['kind'], 'designated_drive_component')
            self.assertEqual(provenance['origins']['speech_tokenizer/config.json']['kind'], 'official_model_component')
            self.assertEqual(provenance['files']['speech_tokenizer/config.json']['size'], '0')

    def test_supplement_cannot_fetch_a_weight_or_unpinned_url(self):
        with tempfile.TemporaryDirectory() as directory:
            prep = Preparation(Path(directory), model_id=SECOND_MODEL)
            item = next(item for item in load_manifest(SECOND_MODEL)['files'] if item.get('official_supplement'))
            for changed in (dict(item, path='model.safetensors'), dict(item, official_supplement={'url':'https://example.invalid/weight'})):
                with patch('ai_manager.preparation.requests.Session') as session:
                    with self.assertRaises(PreparationError): list(prep._official_content(changed, threading.Event()))
                    session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
