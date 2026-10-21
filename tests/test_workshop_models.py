"""Fresh synthetic metadata and display-only choices; no model/API execution."""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

from ai_manager.config import SettingsStore
from ai_manager.inventory import Inventory
from ai_manager.local_mode import NoDriveAuth
from ai_manager.registry import Registry, manifest
from ai_manager.server import create_application
from ai_manager.workshop_models import WorkshopModels, ReferenceError


class WorkshopModelsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.settings = dict(version=1, accounts={'A':'synthetic@example.invalid'}, allowlist=[dict(account='A', alias='ROOT', id='root-a')])
        self.inventory = Inventory(self.home)
        self.registry = Registry(self.home, self.settings)
        self.home.joinpath('settings.json').write_text('{"synthetic":"preserve"}')
        self.resources = dict(observed_at='fresh-observation', unit='bytes', workspace_volume='E:',
                              ram_total_bytes=32*1024**3, ram_available_bytes=0,
                              disk_free_bytes=50*1024**3, gpu_total_bytes=None, gpu_free_bytes=None)
        self.service = WorkshopModels(self.home, self.settings, lambda home: dict(self.resources))
        self.scan_counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def scan(self, status='complete', zero=False):
        self.scan_counter += 1
        identifier = f'{self.scan_counter:032x}'
        profile = manifest('whisper-large-v3-turbo')
        name = profile['name'].rsplit('/',1)[-1]
        with self.inventory.connect() as db:
            db.execute('INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid) VALUES(?,?,?,?,?,?,?)',
                       (identifier, 'A', 1, json.dumps(self.settings), identifier, status, 0))
            for index, component in enumerate(profile['files']):
                if '/' in component['path']:
                    continue
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)', (identifier, f'file-{index}', 'ROOT',
                    f'ROOT/{name}/{component["path"]}', 'weight_candidate' if component['path'].endswith(('.bin','.safetensors')) else 'model_component_candidate',
                    json.dumps(dict(name=component['path'], size='0' if zero else str(component['size']), parents=['folder-a']))))
        return identifier

    def choose(self, item, revision=0):
        return self.service.choose(dict(task=item['task'], revision=revision,
            choice={k:item[k] for k in ('kind','id','fingerprint')}))

    def test_read_only_overview_and_preview_do_not_modify_any_existing_files_or_attest(self):
        self.scan()
        before={p.name:p.read_bytes() for p in self.home.iterdir() if p.is_file()}
        with patch.object(Registry, '_attest', side_effect=AssertionError('no attestation')), patch.object(Registry, '_local_match', side_effect=AssertionError('no model files')):
            view=self.service.overview('stt')
            candidate=view['candidates'][0]
            preview=self.service.preview('stt',{k:candidate[k] for k in ('kind','id','fingerprint')})
        self.assertFalse(view['execution_allowed'])
        self.assertFalse(preview['sampled_generation'])
        self.assertEqual(view['registered_total'],0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.home.iterdir() if p.is_file()})

    def test_all_five_tasks_have_six_fixed_profiles_with_own_sources(self):
        views=[self.service.overview(t) for t in ('tts','stt','llm','image','tracking')]
        self.assertEqual(sum(len(v['profiles']) for v in views),6)
        for view in views:
            self.assertEqual(view['representative']['status'],'not_selected')
            self.assertEqual(view['representative']['fallback']['ownership'],'unconfirmed')
            self.assertTrue(all(p['manifest_sha256'] and p['task']==view['task'] for p in view['profiles']))
            self.assertFalse(view['execution_allowed'])

    def test_candidate_choice_is_display_only_and_rescan_expires_without_substitution(self):
        self.scan()
        candidate=self.service.overview('stt')['candidates'][0]
        original={n:(self.home/n).read_bytes() for n in ('inventory.sqlite3','registry.sqlite3','settings.json')}
        chosen=self.choose(candidate)
        self.assertEqual(chosen['representative']['status'],'current')
        self.scan()
        changed=self.service.overview('stt')
        self.assertEqual(changed['representative']['status'],'expired')
        self.assertIsNone(changed['representative']['fallback'])
        self.assertIsNone(changed['representative']['item'])
        with self.assertRaisesRegex(ReferenceError,'reference_expired'):
            self.service.preview('stt',{k:candidate[k] for k in ('kind','id','fingerprint')})
        self.assertEqual((self.home/'registry.sqlite3').read_bytes(),original['registry.sqlite3'])
        self.assertEqual((self.home/'settings.json').read_bytes(),original['settings.json'])

    def test_removed_scope_and_reused_alias_with_different_root_exclude_candidates(self):
        self.scan()
        self.assertTrue(self.service.overview('stt')['candidates'])
        changed=copy.deepcopy(self.settings);changed['allowlist'][0]['id']='different-root'
        self.assertEqual(WorkshopModels(self.home,changed).overview('stt')['candidates'],[])
        self.assertEqual(WorkshopModels(self.home,{'allowlist':[]}).overview('stt')['candidates'],[])

    def test_partial_and_zero_byte_metadata_remain_reference_not_ready(self):
        self.scan(status='partial',zero=True)
        candidate=self.service.overview('stt')['candidates'][0]
        self.assertEqual(candidate['size_bytes'],0)
        self.assertFalse(candidate['matched_profile_metadata'])
        self.assertEqual(candidate['scan_status'],'partial')
        self.assertTrue(any('부족' in r or '부분' in r for r in candidate['reasons']))
        self.assertFalse(self.service.preview('stt',{k:candidate[k] for k in ('kind','id','fingerprint')})['execution_allowed'])

    def test_untyped_management_model_is_not_tts_but_explicit_user_type_is_labeled(self):
        payload=dict(metadata=dict(name='Managed only',type='미분류',description='',version_label='',tags=[],notes=''),artifact=dict(adapter_id='',revision=''),references=[])
        self.registry.create(payload)
        self.assertEqual(self.service.overview('tts')['registered'],[])
        payload['metadata']['type']='음성 인식'
        row=self.registry.create(payload|{'metadata':payload['metadata']|{'name':'User typed'}})
        item=self.service.overview('stt')['registered'][0]
        self.assertEqual(item['id'],row['id'])
        self.assertEqual(item['task_evidence'],'user_metadata_type_only')
        self.assertIn('실행 미지원',item['label'])
        self.assertIn('지정되지',item['reason'])

    def test_archive_or_metadata_edit_invalidates_registered_representative(self):
        payload=dict(metadata=dict(name='Managed',type='음성 인식',description='',version_label='',tags=[],notes=''),artifact=dict(adapter_id='',revision=''),references=[])
        row=self.registry.create(payload)
        self.choose(self.service.overview('stt')['registered'][0])
        edit=dict(row_version=row['row_version'],metadata=payload['metadata']|{'name':'Changed'},artifact=payload['artifact'],references=[],archived=True)
        self.registry.update(row['id'],edit)
        self.assertEqual(self.service.overview('stt')['representative']['status'],'expired')

    def test_resource_unknown_zero_and_minimum_do_not_leak_between_profiles(self):
        image=self.service.overview('image')['profiles'][0]
        checks={c['metric']:c for c in image['resource_checks']}
        self.assertEqual(checks['ram_available_bytes']['observed_bytes'],0)
        self.assertEqual(checks['ram_available_bytes']['status'],'below_recipe_minimum')
        self.assertEqual(checks['gpu_free_bytes']['status'],'unknown')
        self.assertEqual(self.service.overview('stt')['profiles'][0]['resource_checks'],[])

    def test_volatile_resources_do_not_change_profile_fingerprint_but_policy_does(self):
        profile=self.service.overview('stt')['profiles'][0]
        self.choose(profile)
        self.resources.update(observed_at='new',ram_available_bytes=1)
        self.assertEqual(self.service.overview('stt')['representative']['status'],'current')
        with patch('ai_manager.workshop_models.POLICY',2):
            self.assertEqual(self.service.overview('stt')['representative']['status'],'expired')

    def test_catalog_change_invalidates_profile_and_registered_reference(self):
        catalog=self.service._catalog()
        profile=self.service.overview('stt')['profiles'][0]
        self.choose(profile)
        changed=[]
        for raw,purpose in catalog:
            m=json.loads(raw)
            if purpose=='stt':m['revision']='changed-revision'
            changed.append((json.dumps(m).encode(),purpose))
        with patch.object(self.service,'_catalog',return_value=changed):
            self.assertEqual(self.service.overview('stt')['representative']['status'],'expired')
        payload=dict(metadata=dict(name='Managed',type='음성 인식',description='',version_label='',tags=[],notes=''),artifact=dict(adapter_id='',revision=''),references=[])
        self.registry.create(payload)
        self.choose(self.service.overview('stt')['registered'][0],revision=1)
        with patch.object(self.service,'_catalog',return_value=changed):
            self.assertEqual(self.service.overview('stt')['representative']['status'],'expired')

    def test_strict_input_forgery_task_kind_fingerprint_and_revision(self):
        self.scan();candidate=self.service.overview('stt')['candidates'][0]
        for task in ('__proto__','constructor','unknown',''):
            with self.subTest(task=task),self.assertRaises(ReferenceError):self.service.overview(task)
        base=dict(task='stt',revision=0,choice={k:candidate[k] for k in ('kind','id','fingerprint')})
        invalid=[base|{'extra':True},base|{'revision':True},base|{'choice':base['choice']|{'kind':[]}},base|{'choice':base['choice']|{'fingerprint':'0'*64}},base|{'task':'image'}]
        for data in invalid:
            with self.subTest(data=data),self.assertRaises(ReferenceError):self.service.choose(data)
        self.assertFalse(self.service.path.exists())

    def test_revision_conflict_and_corrupt_sidecar_preserve_prior_bytes(self):
        profile=self.service.overview('tts')['profiles'][0]
        self.choose(profile)
        original=self.service.path.read_bytes()
        with self.assertRaisesRegex(ReferenceError,'representative_stale'):self.choose(profile)
        self.assertEqual(self.service.path.read_bytes(),original)
        self.service.path.write_text('{broken')
        with self.assertRaises(ReferenceError):self.service.overview('tts')
        self.assertEqual(self.service.path.read_text(),'{broken')

    def external_sidecar_change(self, initially_present):
        profile=self.service.overview('stt')['profiles'][0]
        revision=0
        if initially_present:
            self.choose(profile)
            revision=1
        reached=threading.Event();release=threading.Event();outcome=[];fsync=os.fsync
        def stop_after_temporary_flush(fd):
            fsync(fd);reached.set()
            if not release.wait(5):raise AssertionError('test barrier not released')
        def save():
            try:outcome.append(self.choose(profile,revision))
            except Exception as error:outcome.append(error)
        with patch('ai_manager.workshop_models.os.fsync',stop_after_temporary_flush):
            worker=threading.Thread(target=save);worker.start()
            try:
                self.assertTrue(reached.wait(5))
                external=b'externally changed display preference - preserve these bytes'
                self.service.path.write_bytes(external)
            finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(outcome[0],ReferenceError)
        self.assertEqual(str(outcome[0]),'representative_stale_preserved')
        self.assertEqual(self.service.path.read_bytes(),external)

    def test_external_edit_during_temporary_write_preserves_existing_sidecar(self):
        self.external_sidecar_change(True)

    def test_external_creation_during_temporary_write_preserves_new_sidecar(self):
        self.external_sidecar_change(False)

    def test_committed_save_does_not_reread_resources_or_database_for_acknowledgement(self):
        profile=self.service.overview('stt')['profiles'][0]
        calls=[]
        def observer(home):
            calls.append(1)
            if len(calls)>1:raise OSError('later observation unavailable')
            return dict(self.resources)
        self.service.resource_observer=observer
        result=self.choose(profile)
        self.assertEqual(len(calls),1)
        self.assertTrue(result['representative']['saved'])
        self.assertEqual(result['representative']['status'],'current')
        self.assertEqual(self.service.read_choices()['revision'],1)

    def test_inventory_scope_and_files_are_observed_under_one_read_transaction(self):
        self.scan();statements=[];connect=Inventory.connect
        @contextmanager
        def traced(inventory):
            with connect(inventory) as db:
                db.set_trace_callback(statements.append)
                yield db
        with patch.object(Inventory,'connect',traced):
            self.service.overview('stt')
        self.assertEqual(sum(s=='BEGIN' for s in statements),1)
        self.assertEqual(sum('settings_json FROM scans' in s for s in statements),0)

    def test_concurrent_new_scan_does_not_mix_scope_and_files_in_reference_snapshot(self):
        first=self.scan()
        with sqlite3.connect(self.home/'inventory.sqlite3') as db:db.execute('PRAGMA journal_mode=WAL')
        original=Inventory._public
        advanced=[]
        def after_scan_read(row):
            if not advanced:
                advanced.append(self.scan())
            return original(row)
        with patch.object(Inventory,'_public',staticmethod(after_scan_read)):
            observed=self.service.overview('stt')['candidates'][0]
        self.assertEqual(observed['scan_id'],first)
        self.assertEqual(self.service.overview('stt')['candidates'][0]['scan_id'],advanced[0])


class WorkshopModelsHttpTests(unittest.TestCase):
    def test_host_csrf_admission_and_display_only_post(self):
        with tempfile.TemporaryDirectory() as root:
            home=Path(root);settings=SettingsStore(home).initialize_local()
            app=create_application(home,settings,NoDriveAuth());app.start()
            try:
                def call(path,body=None,csrf=None):
                    headers={'Content-Type':'application/json'}
                    if csrf:headers['X-AiManager-CSRF']=csrf
                    return urllib.request.urlopen(urllib.request.Request(app.url.rstrip('/')+path,data=json.dumps(body).encode()if body is not None else None,headers=headers),timeout=10)
                session=json.load(call('/api/session'))['csrf']
                view=json.load(call('/api/workshop-models?task=stt'))
                with self.assertRaises(urllib.error.HTTPError)as rejected:
                    urllib.request.urlopen(urllib.request.Request(app.url+'api/workshop-models?task=stt',headers={'Host':'untrusted.invalid'}),timeout=10)
                self.assertEqual(rejected.exception.code,403)
                item=view['profiles'][0];body=dict(task='stt',revision=0,choice={k:item[k]for k in('kind','id','fingerprint')})
                with self.assertRaises(urllib.error.HTTPError)as rejected:call('/api/workshop-models/representative',body)
                self.assertEqual(rejected.exception.code,403)
                app.admission['accepting']=False
                with self.assertRaises(urllib.error.HTTPError)as rejected:call('/api/workshop-models/representative',body,session)
                self.assertEqual(rejected.exception.code,409)
                app.resume_requests()
                result=json.load(call('/api/workshop-models/representative',body,session))
                self.assertFalse(result['execution_allowed'])
                self.assertEqual(result['representative']['status'],'current')
                self.assertEqual(Registry(home).query()['summary']['registered'],0)
                with self.assertRaises(urllib.error.HTTPError):call('/api/workshop-models?task=tts&task=stt')
            finally:app.close()
