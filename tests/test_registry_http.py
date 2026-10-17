"""Fresh HTTP registry/security tests. No inference or OAuth request is sent."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import requests
from ai_manager.server import create_application
from ai_manager.models import DEFAULT_MODEL
from ai_manager.preparation import manifest


class Auth:
    class Store:
        def get(self,account):return None
    store=Store()


class RegistryHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=create_application(Path(self.temp.name),{'allowlist':[]},Auth())
        self.url=self.app.start().rstrip('/')
        self.csrf=requests.get(self.url+'/api/session',timeout=5).json()['csrf']
        self.body=dict(metadata=dict(name='HTTP 신규모델',type='영상 추적',description='',version_label='초안',tags=['새 입력'],notes=''),artifact=dict(adapter_id='',revision=''),references=[])

    def tearDown(self):self.app.close();self.temp.cleanup()

    def post(self,path,body,**headers):
        return requests.post(self.url+path,json=body,headers={'X-AiManager-CSRF':self.csrf,**headers},timeout=5)

    def test_create_edit_stale_conflict_filter_and_archive_counts(self):
        row=self.post('/api/registry',self.body).json()['model']
        data=requests.get(self.url+'/api/registry?q=신규',timeout=5).json()
        self.assertEqual(data['summary'],dict(registered=1,verified=0,configuration_needed=1))
        edit=copy.deepcopy(self.body)|{'row_version':row['row_version'],'archived':False}
        edit['metadata']['description']='이번 HTTP 검증에서 새로 작성한 설명'
        changed=self.post('/api/registry/'+row['id'],edit)
        self.assertEqual(changed.status_code,200)
        self.assertEqual(self.post('/api/registry/'+row['id'],edit).status_code,409)
        current=changed.json()['model'];edit['row_version']=current['row_version'];edit['archived']=True
        self.assertEqual(self.post('/api/registry/'+row['id'],edit).status_code,200)
        self.assertEqual(requests.get(self.url+'/api/registry',timeout=5).json()['summary']['registered'],0)
        self.assertEqual(len(requests.get(self.url+'/api/registry?archived=1',timeout=5).json()['models']),1)

    def test_registry_mutations_keep_csrf_host_origin_guards(self):
        for headers in ({'X-AiManager-CSRF':'wrong'},{'Origin':'https://foreign.invalid'},{'Host':'foreign.invalid'}):
            self.assertEqual(self.post('/api/registry',self.body,**headers).status_code,403)
        self.assertEqual(requests.get(self.url+'/api/registry',headers={'Origin':'https://foreign.invalid'},timeout=5).status_code,403)
        self.assertEqual(requests.get(self.url+'/api/registry',timeout=5).json()['summary']['registered'],0)

    def test_invalid_shape_unknown_model_and_manual_adapter_never_run(self):
        for data in ([],None,{},self.body|{'verified':True},self.body|{'references':[{'scan_id':[]}]}):
            result=requests.post(self.url+'/api/registry',data='null' if data is None else __import__('json').dumps(data),headers={'Content-Type':'application/json','X-AiManager-CSRF':self.csrf},timeout=5)
            self.assertEqual(result.status_code,400)
        self.assertEqual(requests.get(self.url+'/api/registry/'+'a'*32,timeout=5).status_code,404)
        row=self.post('/api/registry',self.body).json()['model']
        self.assertEqual(self.post('/api/registry/'+row['id']+'/runs',{'row_version':1,'text':'새 테스트'}).status_code,400)
        self.assertEqual(requests.get(self.url+'/api/tts/status',timeout=5).json()['runs'],[])

    def test_unknown_candidate_in_fresh_home_returns_json_error_not_dropped_connection(self):
        data=self.body|{'references':[{'candidate_id':'a'*24,'scan_id':'b'*32}]}
        response=self.post('/api/registry',data)
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['error'],'candidate_not_found')
        self.assertEqual(requests.get(self.url+'/api/registry',timeout=5).json()['summary']['registered'],0)

    def test_long_valid_notes_do_not_fail_generic_4k_limit(self):
        self.body['metadata']['notes']='새'*2800
        self.body['metadata']['description']='설명'*1200
        self.assertEqual(self.post('/api/registry',self.body).status_code,200)

    def test_attested_reference_browser_roundtrip_preserves_server_integers(self):
        node=shutil.which('node')
        self.assertIsNotNone(node,'Node is required to verify the actual browser JSON number boundary')
        directory=Path(self.temp.name)/'fresh-assets';directory.mkdir()
        component=directory/'config.json';component.write_bytes(b'fresh HTTP attestation input')
        os.utime(component,ns=(1792231627382906300,1792231627382906300))
        fixture=manifest()|{'files':[dict(path='config.json',size=component.stat().st_size,sha256=hashlib.sha256(component.read_bytes()).hexdigest())]}
        with patch('ai_manager.registry.manifest',return_value=fixture):
            body=copy.deepcopy(self.body)|{'artifact':{'adapter_id':DEFAULT_MODEL,'revision':fixture['revision']},'references':[{'local_directory':str(directory)}]}
            created=self.post('/api/registry',body);self.assertEqual(created.status_code,200)
            raw=created.json()['model']
            result=subprocess.run([node,'-e',"process.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8'))))"],input=created.text,text=True,capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0)
            browser=json.loads(result.stdout)['model']
            self.assertNotEqual(raw['references'][0]['components'][0]['mtime_ns'],browser['references'][0]['components'][0]['mtime_ns'])
            edit=dict(row_version=browser['row_version'],metadata=browser['metadata'],artifact=body['artifact'],references=[{'existing_identity':ref['identity']} for ref in browser['references']],archived=False)
            edit['metadata']['description']='실제 자바스크립트 왕복 후 설명만 수정'
            changed=self.post('/api/registry/'+raw['id'],edit)
            self.assertEqual(changed.status_code,200)
            current=changed.json()['model']
            for key in ('references','generation','fingerprint'):self.assertEqual(current[key],raw[key])
            self.assertFalse(current['configuration_attention'])
            for archived in (True,False):
                edit['row_version']=current['row_version'];edit['archived']=archived
                response=self.post('/api/registry/'+raw['id'],edit)
                self.assertEqual(response.status_code,200)
                current=response.json()['model'];self.assertEqual(current['references'],raw['references'])
            self.assertEqual(self.post('/api/registry',body|{'references':edit['references']}).status_code,400)
            other=self.post('/api/registry',self.body).json()['model']
            foreign=edit|{'row_version':other['row_version']}
            self.assertEqual(self.post('/api/registry/'+other['id'],foreign).status_code,400)
            for refs,code in (([{'existing_identity':'fake'}],400),(edit['references']*2,409),([edit['references'][0]|{'components':[]}],400)):
                invalid=edit|{'row_version':current['row_version'],'references':refs}
                self.assertEqual(self.post('/api/registry/'+raw['id'],invalid).status_code,code)
            self.assertEqual(self.post('/api/registry/'+raw['id'],edit|{'row_version':0,'references':[{'existing_identity':'fake'}]}).status_code,409)
            removed=self.post('/api/registry/'+raw['id'],edit|{'row_version':current['row_version'],'references':[]})
            self.assertEqual(removed.status_code,200)
            self.assertEqual(removed.json()['model']['references'],[])

    def test_search_only_metadata_values_not_json_field_names(self):
        self.body['metadata']=dict(name='분류 검증 모델',type='영상 추적',description='한글 설명',version_label='초안',tags=['푸른정원'],notes='새 메모')
        row=self.post('/api/registry',self.body).json()['model']
        for query in ('name','notes','version_label','description'):
            self.assertEqual(requests.get(self.url+'/api/registry',params={'q':query},timeout=5).json()['models'],[])
        self.assertEqual(len(requests.get(self.url+'/api/registry',params={'q':'푸른정원'},timeout=5).json()['models']),1)
        edit=self.body|{'row_version':row['row_version'],'archived':False}
        edit['metadata']['name']='English NAME example'
        self.assertEqual(self.post('/api/registry/'+row['id'],edit).status_code,200)
        self.assertEqual(len(requests.get(self.url+'/api/registry',params={'q':'name'},timeout=5).json()['models']),1)


if __name__=='__main__':unittest.main()
