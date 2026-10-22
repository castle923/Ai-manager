"""New isolated M9 inputs. Synthetic metrics are not actual GPU measurements."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import wave

from ai_manager.history import History,HistoryError,stamp
from ai_manager.preferences import Preferences,PreferenceError,DEFAULTS
from ai_manager.inference import DEFAULTS as RUN_DEFAULTS, Inference
from ai_manager.inventory import Inventory
from ai_manager.models import model_ids,load_manifest,manifest_path


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf8')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name);self.history=History(self.home)
    def tearDown(self):self.temp.cleanup()

    def test_scan_history_closes_database_on_success_and_query_error(self):
        Inventory(self.home)
        connect=sqlite3.connect
        connections=[]
        class TrackedConnection(sqlite3.Connection):
            closed=False
            def close(self):
                self.closed=True
                super().close()
        def tracked(*args,**kwargs):
            db=connect(*args,**kwargs,factory=TrackedConnection)
            connections.append(db)
            return db
        try:
            for malformed in (False,True):
                if malformed:
                    with Inventory(self.home).connect() as db:db.execute('DROP TABLE scans')
                with patch('ai_manager.history.sqlite3.connect',side_effect=tracked):
                    records,issues=self.history._records()
                self.assertEqual('scan_records_unavailable' in issues,malformed)
                self.assertTrue(connections[-1].closed)
        finally:
            for db in connections:db.close()

    def fixture(self):
        pairid='a'*32;params={k:copy.deepcopy(RUN_DEFAULTS[k])for k in('language','speaker','batch_size','instruct','max_new_tokens','sampling')};params['seed']=123
        text='새 합성 비교 테스트 입력';inputsha=hashlib.sha256(text.encode()).hexdigest();runs=[]
        code={name:hashlib.sha256(('new synthetic '+name).encode()).hexdigest()for name in('inference.py','tts_worker.py','models.py','preparation.py','server.py','external_process.py','runtime_bootstrap.py','runtime_paths.py','desktop.py','security.py','config.py','registry.py')}
        for side,mid,runid in zip(('A','B'),model_ids(),('b'*32,'c'*32)):
            root=self.home/'tts'/runid;root.mkdir(parents=True)
            wav=root/'output.wav'
            with wave.open(str(wav),'wb')as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b'\x01\x00'*24)
            model=load_manifest(mid)
            run=dict(id=runid,status='succeeded',started_at='2026-10-18T01:00:00+09:00',finished_at='2026-10-17T16:00:01+00:00',model=dict(id=mid,name=model['name'],revision=model['revision']),parameters=copy.deepcopy(params),input_sha256=inputsha,comparison_id=pairid,comparison_side=side,metrics=dict(total_seconds=1.2,loading_seconds=.2,inference_seconds=.8,peak_gpu_allocated_bytes=0,seed=123,cold_loading=True,device='NVIDIA synthetic device',dtype='bfloat16',attention='sdpa'),output=dict(bytes=wav.stat().st_size,sha256=hashlib.sha256(wav.read_bytes()).hexdigest()))
            proof=dict(run_id=runid,comparison_id=pairid,comparison_side=side,input_sha256=inputsha,manifest_sha256=hashlib.sha256(manifest_path(mid).read_bytes()).hexdigest(),runtime_directory=str(self.home/'runtime-new'),runtime_lock_sha256='d'*64,code_sha256=code,cold_loading=True)
            write(root/'input.json',dict(text=text,sha256=inputsha,parameters=params));write(root/'provenance.json',proof);write(root/'state.json',run);runs.append(run)
        pair=dict(id=pairid,status='completed',run_ids=[r['id']for r in runs],runs=runs,parameters=params,conditions=dict(cold_loading=True,cache_reuse=False,sample_count_per_model=1))
        class Fake:
            def comparison_get(self,_):return pair
        return pair,Fake()

    def raw_comparison(self):
        pair,_=self.fixture();text='새 합성 비교 테스트 입력'
        for run in pair['runs']:
            run['text']=text;write(self.home/'tts'/run['id']/'state.json',run)
        raw=dict(id=pair['id'],created_at='2026-10-17T16:00:00Z',text=text,input_sha256=hashlib.sha256(text.encode()).hexdigest(),parameters=pair['parameters'],run_ids=pair['run_ids'],conditions=pair['conditions']|{'execution_order':model_ids()},evaluation=None,admitted=True)
        engine=Inference.__new__(Inference);engine.home=self.home;engine.comparison_base=self.home/'comparisons'
        (engine.comparison_base/raw['id']).mkdir(parents=True)
        engine._comparison_save(raw)
        self.assertNotIn('status',json.loads((engine.comparison_base/raw['id']/'state.json').read_text(encoding='utf8')))
        return raw,pair['runs']

    def test_raw_comparison_serializer_projection_all_states_and_bytes_unchanged(self):
        raw,runs=self.raw_comparison()
        cases=[(('succeeded','succeeded'),'completed'),(('succeeded','failed'),'partial'),(('failed','cancelled'),'failed'),(('cancelled','cancelled'),'cancelled'),(('interrupted','failed'),'interrupted'),(('queued','staged'),'queued'),(('succeeded','running'),'running'),(('cancelling','queued'),'cancelling')]
        for states,expected in cases:
            for run,status in zip(runs,states):
                value=dict(run,status=status,finished_at='2026-10-18T01:00:02+09:00' if status in {'succeeded','failed','cancelled','interrupted'} else None)
                write(self.home/'tts'/run['id']/'state.json',value)
            before={p:p.read_bytes()for p in self.home.rglob('*.json')}
            row=self.history.detail('comparison',raw['id'])
            with self.subTest(states=states):
                self.assertEqual(row['status'],expected);self.assertFalse(row['read_error']);self.assertEqual(row['details']['run_ids'],raw['run_ids'])
                self.assertEqual(row['finished_at'],'2026-10-17T16:00:02+00:00' if expected not in {'queued','running','cancelling'} else None)
                self.assertEqual(before,{p:p.read_bytes()for p in self.home.rglob('*.json')})

    def test_raw_comparison_completion_uses_utc_instants_not_offset_text_order(self):
        raw,runs=self.raw_comparison()
        for run,finished in zip(runs,['2026-10-17T16:00:02Z','2026-10-18T01:00:01+09:00']):
            write(self.home/'tts'/run['id']/'state.json',dict(run,finished_at=finished))
        row=self.history.detail('comparison',raw['id'])
        self.assertEqual(row['finished_at'],'2026-10-17T16:00:02+00:00');self.assertFalse(row['read_error'])
    def test_raw_comparison_missing_or_wrong_child_never_false_complete(self):
        raw,runs=self.raw_comparison();path=self.home/'tts'/runs[0]['id']/'state.json';original=path.read_bytes()
        for key,value in [('comparison_id','d'*32),('comparison_side','B'),('input_sha256','0'*64),('text','다른 새 입력'),('parameters',{}),('model',{'id':model_ids()[1]}),('status','completed'),('finished_at','naive')]:
            write(path,dict(runs[0],**{key:value}))
            row=self.history.detail('comparison',raw['id'])
            with self.subTest(key=key):self.assertTrue(row['read_error']);self.assertEqual(row['status'],'unknown')
        path.unlink();row=self.history.detail('comparison',raw['id']);self.assertTrue(row['read_error']);self.assertEqual(row['status'],'unknown')
        path.write_bytes(original)
        parent=self.home/'comparisons'/raw['id']/'state.json';write(parent,dict(raw,run_ids=[runs[0]['id']]*2))
        self.assertTrue(self.history.detail('comparison',raw['id'])['read_error'])

    def test_performance_positive_preserves_zero_and_different_model_manifests(self):
        pair,engine=self.fixture();data=self.history.performance(pair['id'],engine)
        self.assertTrue(data['common_conditions_confirmed']);self.assertEqual(data['rows'][0]['metrics']['peak_gpu_allocated_bytes'],0)
        self.assertNotEqual(data['rows'][0]['manifest_sha256'],data['rows'][1]['manifest_sha256'])
        self.assertIsNone(data['quality_winner']);self.assertEqual(data['aggregation'],'none')

    def test_performance_missing_boolean_and_identity_conditions_never_confirmed(self):
        pair,engine=self.fixture();original=copy.deepcopy(pair)
        for target,key,value in [('parameters','seed',True),('parameters','batch_size',True),('parameters','sampling',{}),('conditions','sample_count_per_model',True),('conditions','cache_reuse',True)]:
            with self.subTest(key=key):
                pair.clear();pair.update(copy.deepcopy(original));pair[target][key]=value
                for run in pair['runs']:run['parameters']=pair['parameters']
                self.assertFalse(self.history.performance(pair['id'],engine)['common_conditions_confirmed'])
        for mutation in ('duplicate','wrong_ids','same_model','empty_device','seed_bool','wrong_side','bad_revision'):
            pair.clear();pair.update(copy.deepcopy(original))
            if mutation=='duplicate':pair['runs'][1]=pair['runs'][0];pair['run_ids'][1]=pair['run_ids'][0]
            elif mutation=='wrong_ids':pair['run_ids'].reverse()
            elif mutation=='same_model':pair['runs'][1]['model']=pair['runs'][0]['model']
            elif mutation=='empty_device':
                for run in pair['runs']:run['metrics']['device']=' '
            elif mutation=='seed_bool':
                for run in pair['runs']:run['metrics']['seed']=True
            elif mutation=='wrong_side':pair['runs'][1]['comparison_side']='A'
            else:pair['runs'][0]['model']['revision']='f'*40
            with self.subTest(mutation=mutation):self.assertFalse(self.history.performance(pair['id'],engine)['common_conditions_confirmed'])
        pair['runs'].append(pair['runs'][0])
        with self.assertRaises(HistoryError):self.history.performance(pair['id'],engine)

    def test_performance_tamper_missing_source_and_partial_values(self):
        pair,engine=self.fixture();root=self.home/'tts'/pair['runs'][0]['id']
        (root/'output.wav').write_bytes(b'new corrupt output')
        data=self.history.performance(pair['id'],engine);self.assertFalse(data['common_conditions_confirmed']);self.assertEqual(data['rows'][0]['output_integrity'],'unconfirmed')
        pair['runs'][1]['status']='cancelled';pair['runs'][1]['metrics']['inference_seconds']=0
        self.assertIsNone(self.history.performance(pair['id'],engine)['rows'][1]['metrics']['inference_seconds'])
        (root/'provenance.json').unlink();self.assertFalse(self.history.performance(pair['id'],engine)['rows'][0]['provenance_available'])

    def test_history_snapshots_stable_identity_filter_and_read_only(self):
        pair,_=self.fixture();write(self.home/'comparisons'/pair['id']/'state.json',pair)
        before={p:p.read_bytes()for p in self.home.rglob('*.json')}
        first=self.history.query({'limit':['10']});write(self.home/'task-history'/('f'*32+'.json'),dict(id='f'*32,status='running',action='runtime_check',account='B',started_at='2026-10-18T00:00:00Z'))
        frozen=self.history.query({'limit':['10'],'snapshot':[first['snapshot']]})
        self.assertEqual(first['items'],frozen['items']);self.assertEqual(first['total'],3)
        self.assertEqual(len(self.history.query({'kind':['task']})['items']),1)
        for path,data in before.items():self.assertEqual(path.read_bytes(),data)
        self.history.snapshots[first['snapshot']]['expires']=0
        with self.assertRaisesRegex(HistoryError,'expired'):self.history.query({'snapshot':[first['snapshot']]})

    def test_malformed_records_are_individual_unknown_not_whole_list_failure(self):
        pair,_=self.fixture()
        base=copy.deepcopy(pair['runs'][0]);identifier=base['id']
        for key,value in [('model','wrong'),('metrics',[1]),('parameters','wrong'),('status',[]),('started_at','naive date'),('metrics',{'total_seconds':float('nan')})]:
            state=copy.deepcopy(base);state[key]=value;write(self.home/'tts'/identifier/'state.json',state)
            with self.subTest(key=key):
                items=self.history.query({})['items'];row=next(r for r in items if r['id']==identifier)
                self.assertTrue(row['read_error']);self.assertEqual(row['status'],'unknown');self.assertEqual(len(items),2)
        (self.home/'tts'/identifier/'state.json').unlink()
        self.assertTrue(next(r for r in self.history.query({})['items']if r['id']==identifier)['read_error'])

    def test_scan_blob_counts_and_database_bytes_are_preserved(self):
        inventory=Inventory(self.home)
        with inventory.connect()as db:db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid)VALUES(?,'A',1,'{}','bad time','complete',0)",(sqlite3.Binary(b'new invalid identifier'),))
        before=(self.home/'inventory.sqlite3').read_bytes();row=self.history.query({})['items'][0]
        self.assertTrue(row['read_error']);self.assertFalse(row['source_id_available']);self.assertEqual((self.home/'inventory.sqlite3').read_bytes(),before)

    def test_timezone_normalization_and_unknown_timestamp(self):
        self.assertEqual(stamp('2026-10-18T01:00:00+09:00'),stamp('2026-10-17T16:00:00Z'))
        for value in ('invalid','2026-10-17T10:00:00',float('nan'),True):self.assertIsNone(stamp(value))

    def test_preferences_strict_cas_persistence_and_invalid_rollback(self):
        prefs=Preferences(self.home);self.assertEqual(prefs.read()['revision'],0);self.assertFalse(prefs.path.exists())
        changed=prefs.update(dict(revision=0,values=DEFAULTS|{'memory_unit':'MiB'}));self.assertEqual(Preferences(self.home).read(),changed)
        before=prefs.path.read_bytes()
        for request in (dict(revision=0,values=DEFAULTS),dict(revision=True,values=DEFAULTS),dict(revision=1,values=DEFAULTS|{'history_page_size':True}),dict(revision=1,values=DEFAULTS|{'shell':'arbitrary'})):
            with self.assertRaises(PreferenceError):prefs.update(request)
            self.assertEqual(prefs.path.read_bytes(),before)
        with patch('ai_manager.preferences.os.replace',side_effect=OSError('synthetic failure')):
            with self.assertRaises(PreferenceError):prefs.update(dict(revision=1,values=DEFAULTS))
        self.assertEqual(prefs.path.read_bytes(),before);self.assertEqual(list(self.home.glob('preferences-*.tmp')),[])

    def test_task_journal_never_contains_result_or_secret_fields(self):
        self.history.task_record('d'*32,'refresh','A','2026-10-17T12:00:00Z','failed',has_error=True)
        text=(self.home/'task-history'/('d'*32+'.json')).read_text()
        self.assertNotIn('token',text);self.assertNotIn('result',text);self.assertTrue(self.history.query({})['items'][0]['has_error'])

    def test_unsafe_preference_revision_is_rejected_without_repair(self):
        path=self.home/'preferences.json';write(path,dict(schema_version=1,revision=2**60+1,values=DEFAULTS));before=path.read_bytes()
        with self.assertRaises(PreferenceError):Preferences(self.home).read()
        with self.assertRaises(PreferenceError):Preferences(self.home).update(dict(revision=2**60+1,values=DEFAULTS))
        self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
