"""Fresh, independent M5 counterexamples; synthetic fixtures never load a model."""
import hashlib
import json
from pathlib import Path
import tempfile
import sys
import time
import threading
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
import requests

from ai_manager.inference import Inference, InferenceError


MODEL_A = 'fresh-model-a'
MODEL_B = 'fresh-model-b'


def synthetic_manifest(model_id):
    if model_id not in (MODEL_A, MODEL_B):
        raise ValueError('unsupported_model')
    return dict(model_id=model_id, name='Synthetic/' + model_id,
                revision=('a' if model_id == MODEL_A else 'b') * 40,
                source='synthetic-test-fixture', files=[])


class IndependentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.patches = [patch('ai_manager.inference.model_ids', return_value=[MODEL_A, MODEL_B]),
                        patch('ai_manager.inference.manifest', side_effect=synthetic_manifest),
                        patch.object(Inference, '_loop', return_value=None)]
        for item in self.patches:
            item.start()
        self.manager = Inference(self.home)

    def tearDown(self):
        self.manager.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def pair(self):
        return self.manager.comparison_create('새 비교 문장을 읽어 주세요.', [MODEL_A, MODEL_B])

    def start_synthetic_process_queue(self):
        self.manager.close()
        self.patches.pop().stop()
        worker = self.home/'fresh_synthetic_comparison_worker.py'
        worker.write_text(r'''
import hashlib,json,pathlib,struct,sys,time,wave
p=pathlib.Path(sys.argv[1]); r=json.loads(p.read_text(encoding='utf8')); d=p.parent
events=d.parent.parent/'events.jsonl'
def event(kind):
 with events.open('a',encoding='utf8') as stream:
  stream.write(json.dumps(dict(kind=kind,side=r['comparison_side'],id=r['id'],at=time.time()))+'\n')
event('start')
(d/'progress.json').write_text(json.dumps(dict(run_id=r['id'],status='running')))
if r['text']=='cancel-active' or (r['text']=='cancel-b' and r['comparison_side']=='B'): time.sleep(30)
time.sleep(.2)
result=dict(run_id=r['id'],input_sha256=r['input_sha256'],status='generated',metrics={})
if r['text']=='fail-b' and r['comparison_side']=='B': result.update(status='failed',error='inference_failed')
else:
 with wave.open(str(d/'output.wav'),'wb') as stream:
  stream.setparams((1,2,24000,0,'NONE','not compressed'))
  stream.writeframes(struct.pack('<4800h',*([700,-700]*2400)))
event('finish')
(d/'result.json').write_text(json.dumps(result))
''', encoding='utf8')
        self.manager = Inference(self.home, timeout=5)
        def prepare(run):
            (self.manager._path(run['id'])/'request.json').write_text(json.dumps(run), encoding='utf8')
            return Path(getattr(sys, '_base_executable', sys.executable)), worker
        self.manager._prepare = prepare

    def wait_for(self, pair, predicate, timeout=7):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            value = self.manager.comparison_get(pair['id'])
            if predicate(value):
                return value
            time.sleep(.02)
        self.fail('synthetic comparison did not reach expected state')

    def terminal(self, run_id, status):
        state = json.loads((self.manager._path(run_id) / 'state.json').read_text(encoding='utf8'))
        state.update(status=status, finished_at='2026-10-16T00:00:00+00:00')
        if status == 'succeeded':
            state['output'] = {'sha256': hashlib.sha256(run_id.encode()).hexdigest()}
        else:
            state.update(error='synthetic_failure', output=None)
        self.manager._save(state)

    def test_pair_is_fresh_same_input_seed_and_distinct_models(self):
        first = self.pair()
        self.assertEqual(first['status'], 'queued')
        self.assertEqual(len(set(first['run_ids'])), 2)
        expected = hashlib.sha256(first['text'].encode()).hexdigest()
        for side, run in zip(('A', 'B'), first['runs']):
            self.assertEqual(run['comparison_id'], first['id'])
            self.assertEqual(run['comparison_side'], side)
            self.assertEqual(run['input_sha256'], expected)
            self.assertEqual(run['parameters'], first['parameters'])
            self.assertIsNone(run['audio_url'])
        self.assertEqual([r['model']['id'] for r in first['runs']], [MODEL_A, MODEL_B])
        self.assertNotEqual(first['runs'][0]['model']['revision'], first['runs'][1]['model']['revision'])
        self.assertTrue(first['conditions']['cold_loading'])
        self.assertFalse(first['conditions']['cache_reuse'])
        self.assertEqual(first['conditions']['sample_count_per_model'], 1)
        self.assertIsNone(first['evaluation'])
        self.manager.comparison_cancel(first['id'])
        second = self.pair()
        self.assertNotEqual(first['id'], second['id'])
        self.assertFalse(set(first['run_ids']) & set(second['run_ids']))

    def test_bad_models_and_input_cannot_create_runs(self):
        for models in (None, [], [MODEL_A], [MODEL_A, MODEL_A], [MODEL_A, '../old'],
                       [MODEL_A, '0'*32], [MODEL_A, MODEL_B, MODEL_A], [MODEL_A, []]):
            with self.subTest(models=models), self.assertRaises(InferenceError):
                self.manager.comparison_create('새 입력', models)
        for text in ('', ' ', None, [], '가'*301, '\ud800', 'x\x00'):
            with self.subTest(text=repr(text)), self.assertRaises(InferenceError):
                self.manager.comparison_create(text, [MODEL_A, MODEL_B])
        self.assertEqual(self.manager._runs(), [])

    def test_queue_rejection_does_not_admit_half_pair(self):
        self.pair()
        before = {r['id'] for r in self.manager._runs()}
        with self.assertRaisesRegex(InferenceError, 'queue_full'):
            self.pair()
        self.assertEqual({r['id'] for r in self.manager._runs()}, before)

    def test_second_run_write_failure_leaves_no_executable_orphan(self):
        original = self.manager._new_run
        def fail_second(text, model_id, **kwargs):
            if model_id == MODEL_B:
                raise OSError('fresh synthetic disk failure')
            return original(text, model_id, **kwargs)
        with patch.object(self.manager, '_new_run', side_effect=fail_second):
            with self.assertRaisesRegex(InferenceError, 'comparison_enqueue_failed'):
                self.pair()
        states = self.manager._runs()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0]['status'], 'interrupted')
        self.assertEqual(states[0]['error'], 'comparison_enqueue_failed')
        self.assertFalse(any(r['status'] in {'queued', 'running'} for r in states))

    def test_comparison_write_failure_leaves_both_nonexecutable(self):
        with patch.object(self.manager, '_comparison_save', side_effect=OSError('disk failed')):
            with self.assertRaisesRegex(InferenceError, 'comparison_enqueue_failed'):
                self.pair()
        self.assertEqual([r['status'] for r in self.manager._runs()], ['interrupted', 'interrupted'])

    def test_persistent_disk_failure_during_pair_promotion_cannot_leave_queued_a(self):
        self.start_synthetic_process_queue()
        original = self.manager._save
        failing = False
        def fail_after_second_promotion(run):
            nonlocal failing
            if run.get('comparison_side') == 'B' and run['status'] == 'queued':
                failing = True
            if failing:
                raise OSError('fresh persistent disk failure')
            return original(run)
        with patch.object(self.manager, '_save', side_effect=fail_after_second_promotion):
            with self.assertRaisesRegex(InferenceError, 'comparison_enqueue_failed'):
                self.pair()
        states = self.manager._runs()
        self.assertEqual(len(states), 2)
        self.assertTrue(any(run['status'] == 'queued' for run in states),
                        'Counterexample must retain failed durable rollback, not silently skip its trigger')
        self.assertTrue(all(not self.manager._eligible(run) for run in states))
        self.manager.wake.set()
        time.sleep(.8)
        self.assertFalse((self.home/'events.jsonl').exists(),
                         'Failed durable pair must never start either synthetic worker')
        self.manager.close()
        self.manager = Inference(self.home, timeout=5)
        self.manager.wake.set()
        time.sleep(.6)
        self.assertFalse((self.home/'events.jsonl').exists(),
                         'Restart must not execute a failed half-pair')
        self.assertTrue(all(run['status'] == 'interrupted' for run in self.manager._runs()))

    def test_second_failure_is_partial_without_winner_or_audio_b(self):
        pair = self.pair()
        self.terminal(pair['run_ids'][0], 'succeeded')
        self.terminal(pair['run_ids'][1], 'failed')
        value = self.manager.comparison_get(pair['id'])
        self.assertEqual(value['status'], 'partial')
        self.assertTrue(value['runs'][0]['audio_url'])
        self.assertIsNone(value['runs'][1]['audio_url'])
        self.assertNotIn('winner', value)
        self.assertEqual(value['runs'][1]['metrics'], {})
        with self.assertRaisesRegex(InferenceError, 'comparison_not_completed'):
            self.manager.comparison_evaluate(pair['id'], 'A', 'partial is not a completed comparison')

    def test_queued_cancel_cancels_both_and_no_audio(self):
        pair = self.pair()
        value = self.manager.comparison_cancel(pair['id'])
        self.assertEqual(value['status'], 'cancelled')
        self.assertEqual([r['status'] for r in value['runs']], ['cancelled', 'cancelled'])
        self.assertTrue(all(r['audio_url'] is None for r in value['runs']))

    def test_cancel_after_a_success_preserves_partial_not_b_success(self):
        pair = self.pair()
        self.terminal(pair['run_ids'][0], 'succeeded')
        value = self.manager.comparison_cancel(pair['id'])
        self.assertEqual(value['status'], 'partial')
        self.assertEqual([r['status'] for r in value['runs']], ['succeeded', 'cancelled'])
        self.assertIsNone(value['runs'][1]['output'])
        self.assertIsNone(value['runs'][1]['audio_url'])

    def test_evaluation_requires_two_successes_and_valid_explicit_user_input(self):
        pair = self.pair()
        with self.assertRaisesRegex(InferenceError, 'comparison_not_completed'):
            self.manager.comparison_evaluate(pair['id'], 'A', '')
        for preference, notes in [(None, ''), ('winner', ''), ([], ''), ('A', None),
                                  ('A', '가'*2001), ('A', '\ud800'), ('A', '\x00')]:
            with self.subTest(preference=preference), self.assertRaises(InferenceError):
                self.manager.comparison_evaluate(pair['id'], preference, notes)
        for run_id in pair['run_ids']:
            self.terminal(run_id, 'succeeded')
        completed = self.manager.comparison_get(pair['id'])
        self.assertEqual(completed['status'], 'completed')
        self.assertIsNone(completed['evaluation'])
        value = self.manager.comparison_evaluate(pair['id'], 'undecided', ' 새 사용자 평가 ')
        self.assertEqual(value['evaluation']['source'], 'user')
        self.assertEqual(value['evaluation']['notes'], '새 사용자 평가')
        self.assertTrue(value['evaluation']['recorded_at'])
        self.assertEqual(value['run_ids'], pair['run_ids'])
        self.assertEqual(value['parameters'], pair['parameters'])

    def test_foreign_existing_run_cannot_replace_owned_side(self):
        pair = self.pair()
        self.manager.comparison_cancel(pair['id'])
        foreign = self.pair()
        state = self.manager._comparison_load(pair['id'])
        state['run_ids'][1] = foreign['run_ids'][1]
        self.manager._comparison_save(state)
        with self.assertRaisesRegex(InferenceError, 'comparison_invalid'):
            self.manager.comparison_get(pair['id'])
        with self.assertRaisesRegex(InferenceError, 'comparison_invalid'):
            self.manager.comparison_cancel(pair['id'])
        self.assertEqual(self.manager.get(foreign['run_ids'][1])['status'], 'queued')

    def test_run_condition_tampering_is_detected(self):
        pair = self.pair()
        run = json.loads((self.manager._path(pair['run_ids'][1])/'state.json').read_text(encoding='utf8'))
        run['parameters']['seed'] += 1
        self.manager._save(run)
        with self.assertRaisesRegex(InferenceError, 'comparison_invalid'):
            self.manager.comparison_get(pair['id'])

    def test_each_model_preparation_hash_and_provenance_are_independent(self):
        pair = self.pair()
        runtime = self.home/'runtime'
        python = runtime/'venv'/'Scripts'/'python.exe'
        python.parent.mkdir(parents=True)
        python.write_bytes(b'nonexecuted synthetic runtime placeholder')
        (runtime/'requirements.lock').write_text('fresh synthetic lock', encoding='utf8')
        manifests, paths, bases = {}, {}, {}
        for index, model_id in enumerate((MODEL_A, MODEL_B)):
            preparation_id = str(index + 1) * 32
            base = self.home/'synthetic-preparations'/model_id
            assets = base/preparation_id/'assets'
            assets.mkdir(parents=True)
            content = ('new synthetic component for ' + model_id).encode()
            (assets/'weights.bin').write_bytes(content)
            manifests[model_id] = synthetic_manifest(model_id) | {'files': [dict(
                path='weights.bin', size=len(content), sha256=hashlib.sha256(content).hexdigest())]}
            paths[model_id] = self.home/(model_id+'.json')
            paths[model_id].write_text(json.dumps(manifests[model_id]), encoding='utf8')
            bases[model_id] = (base, preparation_id)
        class FreshPreparation:
            def __init__(inner, home, *, model_id):
                inner.base, inner.preparation_id = bases[model_id]
            def _load(inner):
                return dict(id=inner.preparation_id, status='ready', integrity='matched')
            def environment(inner):
                return dict(status='ready', source='synthetic runtime fixture')
        with patch('ai_manager.preparation.Preparation', FreshPreparation), \
             patch('ai_manager.inference.manifest', side_effect=lambda mid: manifests[mid]), \
             patch('ai_manager.inference.manifest_path', side_effect=lambda mid: paths[mid]):
            provenance = []
            for index, run_id in enumerate(pair['run_ids']):
                run = self.manager.get(run_id)
                selected_python, _ = self.manager._prepare(run)
                self.assertEqual(selected_python, python)
                directory = self.manager._path(run_id)
                record = json.loads((directory/'provenance.json').read_text(encoding='utf8'))
                request = json.loads((directory/'request.json').read_text(encoding='utf8'))
                selected_model = (MODEL_A, MODEL_B)[index]
                self.assertEqual(request['model_id'], selected_model)
                self.assertEqual(request['model_revision'], manifests[selected_model]['revision'])
                self.assertEqual(record['inputs'][0]['sha256'], manifests[selected_model]['files'][0]['sha256'])
                self.assertEqual(record['manifest_sha256'], hashlib.sha256(paths[selected_model].read_bytes()).hexdigest())
                self.assertEqual(record['comparison_id'], pair['id'])
                self.assertEqual(record['input_sha256'], pair['input_sha256'])
                self.assertTrue(record['cold_loading'])
                self.assertTrue(record['offline'])
                self.assertIn('inference.py', record['code_sha256'])
                self.assertIn('tts_worker.py', record['code_sha256'])
                self.assertEqual(record['runtime_lock_sha256'], hashlib.sha256((runtime/'requirements.lock').read_bytes()).hexdigest())
                provenance.append(record)
                for key, tampered in [('revision', 'f'*40), ('name', 'Synthetic/wrong-model'), ('id', MODEL_B if index == 0 else MODEL_A)]:
                    changed = self.manager.get(run_id)
                    changed['model'][key] = tampered
                    with self.subTest(model=selected_model, key=key), self.assertRaisesRegex(InferenceError, 'model_integrity_failed'):
                        self.manager._prepare(changed)
            self.assertNotEqual(provenance[0]['inputs'][0]['local_path'], provenance[1]['inputs'][0]['local_path'])
            self.assertNotEqual(provenance[0]['manifest_sha256'], provenance[1]['manifest_sha256'])
            base, preparation_id = bases[MODEL_B]
            (base/preparation_id/'assets'/'weights.bin').write_bytes(b'fresh corruption')
            with self.assertRaisesRegex(InferenceError, 'model_integrity_failed'):
                self.manager._prepare(self.manager.get(pair['run_ids'][1]))
            self.manager._prepare(self.manager.get(pair['run_ids'][0]))

    def test_actual_synthetic_processes_run_sequentially_and_audio_matches(self):
        self.start_synthetic_process_queue()
        pair = self.pair()
        value = self.wait_for(pair, lambda c: c['status'] == 'completed')
        events = [json.loads(line) for line in (self.home/'events.jsonl').read_text().splitlines()]
        self.assertEqual([(e['side'], e['kind']) for e in events],
                         [('A', 'start'), ('A', 'finish'), ('B', 'start'), ('B', 'finish')])
        for run in value['runs']:
            audio = self.manager.audio(run['id'])
            self.assertEqual(hashlib.sha256(audio).hexdigest(), run['output']['sha256'])
            self.assertEqual(run['output']['sample_rate'], 24000)
            self.assertNotIn('loading_seconds', run['metrics'])
            self.assertNotIn('peak_gpu_allocated_bytes', run['metrics'])
        self.assertIsNone(value['evaluation'])

    def test_actual_active_cancel_stops_a_and_never_starts_b(self):
        self.start_synthetic_process_queue()
        pair = self.manager.comparison_create('cancel-active', [MODEL_A, MODEL_B])
        self.wait_for(pair, lambda c: c['runs'][0]['status'] == 'running')
        self.manager.comparison_cancel(pair['id'])
        value = self.wait_for(pair, lambda c: c['status'] == 'cancelled')
        self.assertEqual([r['status'] for r in value['runs']], ['cancelled', 'cancelled'])
        events = [json.loads(line) for line in (self.home/'events.jsonl').read_text().splitlines()]
        self.assertEqual([(e['side'], e['kind']) for e in events], [('A', 'start')])
        self.assertTrue(all(r['output'] is None and r['audio_url'] is None for r in value['runs']))
        self.assertIsNone(self.manager.child)

    def test_actual_b_cancel_after_a_success_is_partial(self):
        self.start_synthetic_process_queue()
        pair = self.manager.comparison_create('cancel-b', [MODEL_A, MODEL_B])
        self.wait_for(pair, lambda c: c['runs'][0]['status'] == 'succeeded' and c['runs'][1]['status'] == 'running')
        self.manager.comparison_cancel(pair['id'])
        value = self.wait_for(pair, lambda c: c['status'] == 'partial')
        self.assertEqual([r['status'] for r in value['runs']], ['succeeded', 'cancelled'])
        self.assertGreater(len(self.manager.audio(value['run_ids'][0])), 44)
        with self.assertRaisesRegex(InferenceError, 'run_not_finished'):
            self.manager.audio(value['run_ids'][1])

    def test_actual_b_failure_preserves_only_fresh_a_output(self):
        self.start_synthetic_process_queue()
        pair = self.manager.comparison_create('fail-b', [MODEL_A, MODEL_B])
        value = self.wait_for(pair, lambda c: c['status'] == 'partial')
        self.assertEqual([r['status'] for r in value['runs']], ['succeeded', 'failed'])
        self.assertFalse((self.manager._path(value['run_ids'][1])/'output.wav').exists())
        self.assertIsNone(value['runs'][1]['audio_url'])


class IndependentComparisonHttpTests(unittest.TestCase):
    def setUp(self):
        from ai_manager.server import serve
        self.fixture = IndependentComparisonTests()
        self.fixture.setUp()
        self.ready = threading.Event()
        self.servers = []
        def factory(*args, **kwargs):
            server = ThreadingHTTPServer(*args, **kwargs)
            self.servers.append(server)
            return server
        def browser(url):
            self.url = url.rstrip('/')
            self.ready.set()
        class Auth:
            class Store:
                def get(self, account): return None
            store = Store()
        self.server_patch = patch('ai_manager.server.ThreadingHTTPServer', factory)
        self.manager_patch = patch('ai_manager.server.Inference', return_value=self.fixture.manager)
        self.server_patch.start()
        self.manager_patch.start()
        self.thread = threading.Thread(target=serve, args=(self.fixture.home, {'allowlist': []}, Auth()),
                                       kwargs={'browser': browser}, daemon=True)
        self.thread.start()
        self.assertTrue(self.ready.wait(3))
        self.csrf = requests.get(self.url+'/api/session', timeout=3).json()['csrf']

    def tearDown(self):
        self.servers[0].shutdown()
        self.thread.join(5)
        self.manager_patch.stop()
        self.server_patch.stop()
        self.fixture.tearDown()

    def post(self, path, data, **headers):
        return requests.post(self.url+path, data=json.dumps(data), timeout=3,
                             headers={'Content-Type': 'application/json', 'X-AiManager-CSRF': self.csrf, **headers})

    def create(self):
        response = self.post('/api/comparisons', {'text': '새 HTTP 비교 입력', 'model_ids': [MODEL_A, MODEL_B]})
        self.assertEqual(response.status_code, 202)
        return response.json()['comparison']

    def test_http_create_rejects_external_runs_audio_paths_and_options(self):
        base = {'text': '새 입력', 'model_ids': [MODEL_A, MODEL_B]}
        for key, value in [('run_ids', ['a'*32, 'b'*32]), ('audio_path', '../old.wav'),
                           ('model_path', '../old-model'), ('parameters', {'speaker': 'other'}),
                           ('comparison_id', 'a'*32), ('output', 'https://example.invalid/old.wav')]:
            with self.subTest(key=key):
                response = self.post('/api/comparisons', base | {key: value})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.fixture.manager._runs(), [])

    def test_http_security_rejects_each_named_case(self):
        for name, headers in [('csrf', {'X-AiManager-CSRF': 'wrong'}),
                              ('origin', {'Origin': 'https://foreign.invalid'}),
                              ('host', {'Host': 'foreign.invalid'})]:
            with self.subTest(case=name):
                response = self.post('/api/comparisons', {'text': '새 입력', 'model_ids': [MODEL_A, MODEL_B]}, **headers)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fixture.manager._runs(), [])

    def test_http_get_cancel_and_evaluation_contract(self):
        pair = self.create()
        path = '/api/comparisons/'+pair['id']
        response = requests.get(self.url+path, timeout=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        public = response.text
        self.assertNotIn(str(self.fixture.home), public)
        self.assertNotIn('local_path', public)
        self.assertNotIn('source_path', public)
        self.assertEqual(self.post(path+'/evaluation', {'preference': 'A', 'notes': ''}).status_code, 409)
        self.assertEqual(self.post(path+'/evaluation', {'preference': 'A', 'notes': '', 'winner': True}).status_code, 400)
        self.assertEqual(self.post(path+'/cancel', {'run_id': pair['run_ids'][0]}).status_code, 400)
        cancelled = self.post(path+'/cancel', {})
        self.assertEqual(cancelled.status_code, 202)
        self.assertEqual(cancelled.json()['comparison']['status'], 'cancelled')
        self.assertEqual(requests.get(self.url+'/api/comparisons/'+'e'*32, timeout=3).status_code, 404)


if __name__ == '__main__':
    unittest.main()
