import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ai_manager.dashboard import Dashboard
from ai_manager.inventory import Inventory
from ai_manager.models import DEFAULT_MODEL
from ai_manager.preparation import manifest
from ai_manager.registry import Registry, RegistryError


def payload(name='새 등록 모델'):
    return dict(metadata=dict(name=name,type='음성 합성',description='',version_label='',tags=[],notes=''),
                artifact=dict(adapter_id='',revision=''),references=[])


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.home=Path(self.temp.name)
        self.settings={'allowlist':[dict(account='A',alias='ROOT',id='root-a')]}
        self.registry=Registry(self.home,self.settings)

    def tearDown(self): self.temp.cleanup()

    def update_payload(self,row):
        return dict(row_version=row['row_version'],metadata=copy.deepcopy(row['metadata']),
                    artifact={k:row['artifact'][k] for k in ('adapter_id','revision')},references=row['references'],archived=row['archived'])

    def scan(self,identifier='new',status='complete'):
        inventory=Inventory(self.home)
        with inventory.connect() as db:
            db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid) VALUES(?,'A',1,?,? ,?,0)",(identifier,json.dumps(self.settings),identifier,status))
            db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',(identifier,'file-1','ROOT','ROOT/새모델/model.bin','weight_candidate',json.dumps(dict(name='model.bin',size='5',parents=['folder-1']))))
        return Dashboard(self.home).query({'scan':[identifier]})['rows'][0]

    def test_empty_and_unknown_models_never_verified(self):
        self.assertEqual(self.registry.query()['summary'],dict(registered=0,verified=0,configuration_needed=0))
        row=self.registry.create(payload())
        self.assertEqual(row['status'],'configuration_needed')
        self.assertEqual(row['execution'],'unexecuted')
        self.assertEqual(len(row['id']),32)
        with self.assertRaisesRegex(RegistryError,'adapter_unsupported'): self.registry.inference=object(); self.registry.create_run(row['id'],1,'새문장')

    def test_metadata_cas_generation_and_archive(self):
        row=self.registry.create(payload())
        edit=self.update_payload(row);edit['metadata']['name']='이름 변경';edit['metadata']['notes']='새 메모'
        changed=self.registry.update(row['id'],edit)
        self.assertEqual(changed['generation'],row['generation'])
        self.assertEqual(changed['id'],row['id'])
        with self.assertRaisesRegex(RegistryError,'stale_edit'):self.registry.update(row['id'],edit)
        edit=self.update_payload(changed);edit['artifact']['revision']='새 가중치 버전'
        changed=self.registry.update(row['id'],edit)
        self.assertNotEqual(changed['generation'],row['generation'])
        edit=self.update_payload(changed);edit['archived']=True
        self.registry.update(row['id'],edit)
        self.assertEqual(self.registry.query()['summary']['registered'],0)
        self.assertEqual(len(self.registry.query(include_archived=True)['models']),1)

    def test_candidate_registration_duplicate_rollback_and_legacy_preservation(self):
        candidate=self.scan()
        original=(self.home/'inventory.sqlite3').read_bytes()
        data=payload();data['references']=[dict(candidate_id=candidate['id'],scan_id='new')]
        row=self.registry.create(data)
        self.assertEqual(row['references'][0]['identity'],'drive:A:folder-1')
        with self.assertRaisesRegex(RegistryError,'duplicate_reference'):self.registry.create(data)
        self.assertEqual(self.registry.query()['summary']['registered'],1)
        self.assertEqual((self.home/'inventory.sqlite3').read_bytes(),original)
        candidate2=self.scan('rescan','partial')
        with self.assertRaisesRegex(RegistryError,'duplicate_reference'):
            self.registry.create(payload('이름이 달라도 동일 source')|{'references':[dict(candidate_id=candidate2['id'],scan_id='rescan')]})
        self.assertEqual(self.registry.get(row['id'])['metadata']['name'],row['metadata']['name'])

    def test_scope_and_arbitrary_reference_input_rejected(self):
        candidate=self.scan();data=payload();data['references']=[dict(candidate_id=candidate['id'],scan_id='new')]
        registry=Registry(self.home,{'allowlist':[]})
        with self.assertRaisesRegex(RegistryError,'out_of_scope'):registry.create(data)
        for ref in ({'file_id':'injected'},{'local_directory':'relative'}, {'local_directory':str(self.home/'missing')}):
            with self.subTest(ref=ref),self.assertRaises(RegistryError):self.registry.create(payload()|{'references':[ref]})

    def test_local_observation_is_not_hash_or_execution(self):
        directory=self.home/'새 원본';directory.mkdir()
        row=self.registry.create(payload()|{'references':[{'local_directory':str(directory)}]})
        self.assertEqual(row['references'][0]['components'],[])
        self.assertEqual(row['execution'],'unexecuted')
        self.assertTrue(row['configuration_attention'])

    def test_supported_manifest_and_metadata_cannot_inject_status(self):
        data=payload();data['artifact']={'adapter_id':DEFAULT_MODEL,'revision':'wrong'}
        with self.assertRaisesRegex(RegistryError,'unsupported_artifact'):self.registry.create(data)
        data=payload();data['metadata']['status']='verified'
        with self.assertRaises(RegistryError):self.registry.create(data)

    def test_unknown_schema_no_mutation_and_foreign_key(self):
        with self.registry.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("INSERT INTO model_references VALUES('missing','x','{}')")
        with closing(sqlite3.connect(self.registry.path)) as db, db:db.execute('PRAGMA user_version=99')
        before=hashlib.sha256(self.registry.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RegistryError,'schema_unsupported'):Registry(self.home)
        self.assertEqual(hashlib.sha256(self.registry.path.read_bytes()).hexdigest(),before)

    def test_same_alias_different_root_id_is_out_of_scope(self):
        candidate=self.scan()
        changed=Registry(self.home,{'allowlist':[dict(account='A',alias='ROOT',id='different-root')]})
        data=payload()|{'references':[dict(candidate_id=candidate['id'],scan_id='new')]}
        with self.assertRaisesRegex(RegistryError,'reference_out_of_scope'): changed.create(data)
        row=self.registry.create(data)
        self.assertIn('reference_out_of_scope',changed.get(row['id'])['configuration_reasons'])

    def test_supported_empty_local_folder_is_unconfirmed_and_cannot_run(self):
        directory=self.home/'empty';directory.mkdir()
        data=payload()|{'references':[{'local_directory':str(directory)}], 'artifact':{'adapter_id':DEFAULT_MODEL,'revision':manifest()['revision']}}
        row=self.registry.create(data)
        self.assertIn('artifact_files_unconfirmed',row['configuration_reasons'])
        self.registry.inference=FakeEngine()
        with self.assertRaisesRegex(RegistryError,'configuration_required'):self.registry.create_run(row['id'],1,'새 검증')
        self.assertEqual(self.registry.inference.values,[])

    def test_new_binding_generation_metadata_edit_and_late_completion(self):
        directory=self.home/'new-assets';directory.mkdir()
        original=b'fresh synthetic model component, not an actual model'
        component=directory/'config.json';component.write_bytes(original)
        model_manifest=manifest()|{'files':[dict(path='config.json',size=len(original),sha256=hashlib.sha256(original).hexdigest())]}
        self.registry.inference=FakeEngine()
        with patch('ai_manager.registry.manifest',return_value=model_manifest):
            data=payload()|{'references':[{'local_directory':str(directory)}], 'artifact':{'adapter_id':DEFAULT_MODEL,'revision':model_manifest['revision']}}
            row=self.registry.create(data)
            self.assertFalse(row['configuration_attention'])
            run=self.registry.create_run(row['id'],1,'새 합성 실행 입력')
            self.assertEqual(run['registry_binding']['id'],row['id'])
            edit=self.update_payload(row);edit['metadata']['notes']='모델 관리 메모'
            same=self.registry.update(row['id'],edit)
            self.registry.inference.values[0]['status']='succeeded'
            self.assertEqual(self.registry.get(row['id'])['execution'],'verified')
            edit=self.update_payload(same);edit['artifact']={'adapter_id':'','revision':'다른 버전'}
            changed=self.registry.update(row['id'],edit)
            self.assertNotEqual(changed['generation'],row['generation'])
            self.assertEqual(changed['execution'],'unexecuted')
            self.assertFalse(changed['runs'][0]['current_artifact'])
            self.assertEqual(self.registry.query()['summary']['verified'],0)

    def test_source_mutation_after_registration_invalidates_and_prevents_run(self):
        directory=self.home/'source';directory.mkdir();component=directory/'config.json';component.write_bytes(b'new!')
        fixture=manifest()|{'files':[dict(path='config.json',size=4,sha256=hashlib.sha256(b'new!').hexdigest())]}
        self.registry.inference=FakeEngine()
        with patch('ai_manager.registry.manifest',return_value=fixture):
            row=self.registry.create(payload()|{'references':[{'local_directory':str(directory)}], 'artifact':{'adapter_id':DEFAULT_MODEL,'revision':fixture['revision']}})
            component.write_bytes(b'bad!')
            self.assertTrue(self.registry.get(row['id'])['configuration_attention'])
            with self.assertRaises(RegistryError):self.registry.create_run(row['id'],row['row_version'],'실행 불가')
            self.assertEqual(self.registry.inference.values,[])

    def test_candidate_query_never_recovers_or_writes_running_scan(self):
        candidate=self.scan('running-observation','running')
        with closing(sqlite3.connect(self.home/'inventory.sqlite3')) as db, db:db.execute('UPDATE scans SET pid=2147483000')
        before=(self.home/'inventory.sqlite3').read_bytes()
        self.registry.create(payload()|{'references':[dict(candidate_id=candidate['id'],scan_id='running-observation')]})
        self.assertEqual((self.home/'inventory.sqlite3').read_bytes(),before)

    def test_schema_initialization_failure_rolls_back_and_reopens_cleanly(self):
        other=self.home/'schema-failure';other.mkdir()
        from ai_manager.registry import SCHEMA
        with patch('ai_manager.registry.SCHEMA',SCHEMA+'; INVALID SQL;'):
            with self.assertRaises(sqlite3.DatabaseError):Registry(other)
        with closing(sqlite3.connect(other/'registry.sqlite3')) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0],0)
        self.assertEqual(Registry(other).query()['summary']['registered'],0)

    def test_partial_scan_is_observation_only_and_legacy_backup_still_works(self):
        candidate=self.scan('partial-observation','partial')
        original=(self.home/'inventory.sqlite3').read_bytes()
        row=self.registry.create(payload()|{'references':[dict(candidate_id=candidate['id'],scan_id='partial-observation')]})
        self.assertEqual(row['references'][0]['observation_status'],'partial')
        self.assertEqual(row['execution'],'unexecuted')
        from ai_manager.db_recovery import copy_database_to_new_target
        result=copy_database_to_new_target(self.home/'inventory.sqlite3',self.home/'snapshot'/'inventory.sqlite3')
        self.assertEqual(result['integrity'],'ok')
        self.assertEqual((self.home/'inventory.sqlite3').read_bytes(),original)
        self.assertEqual(self.registry.get(row['id'])['metadata']['name'],row['metadata']['name'])


class FakeEngine:
    """State-transition fixture only: no model, worker, real WAV or runtime."""
    def __init__(self):self.values=[]
    def registry_runs(self,identifier):return [r for r in self.values if r['registry_binding']['id']==identifier]
    def registry_verified(self,run,binding):return run['status']=='succeeded'
    def create_registered(self,text,adapter,binding):
        run={'id':'f'*32,'status':'queued','registry_binding':binding,'model':{'id':adapter},'text':text}
        self.values.append(run)
        return run


if __name__=='__main__':unittest.main()
