import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
import requests

from ai_manager.server import create_application
from ai_manager.history import HistoryError
from ai_manager.history import History


class SyntheticAuth:
    class Store:
        def get(self,account):return None
    store=Store()
    def access(self,account,force_refresh=False):return 'new synthetic test value, never persisted'


class WorkspaceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.app=create_application(self.home,{'allowlist':[],'accounts':{'A':'private-a@example.invalid','B':'private-b@example.invalid'},'client_path':'PRIVATE_CLIENT_JSON','sources':[{'secret':'MUST_NOT_RETURN'}]},SyntheticAuth())
        self.url=self.app.start().rstrip('/');self.csrf=requests.get(self.url+'/api/session',timeout=5).json()['csrf']
    def tearDown(self):self.app.close();self.temp.cleanup()
    def post(self,path,value,**headers):return requests.post(self.url+path,data=json.dumps(value),headers={'Content-Type':'application/json','X-AiManager-CSRF':self.csrf,**headers},timeout=5)

    def test_real_comparison_serializer_history_list_detail_and_source_are_readonly(self):
        cid='a'*32;ids=['b'*32,'c'*32];text='새 HTTP 원본 비교 기록';params={'seed':321};order=['qwen3-tts-0.6b-customvoice','qwen3-tts-1.7b-customvoice']
        raw=dict(id=cid,created_at='2026-10-17T16:00:00Z',text=text,input_sha256=hashlib.sha256(text.encode()).hexdigest(),parameters=params,run_ids=ids,conditions={'execution_order':order},admitted=True,evaluation=None)
        directory=self.home/'comparisons'/cid;directory.mkdir(parents=True)
        self.app.inference._comparison_save(raw)
        for rid,side,mid in zip(ids,'AB',order):
            root=self.home/'tts'/rid;root.mkdir()
            value=dict(id=rid,status='succeeded',started_at='2026-10-17T16:00:00Z',finished_at='2026-10-17T16:00:02Z',comparison_id=cid,comparison_side=side,text=text,input_sha256=raw['input_sha256'],parameters=params,model={'id':mid},metrics={},output=None)
            (root/'state.json').write_text(json.dumps(value),encoding='utf8')
        before={p:p.read_bytes()for p in self.home.rglob('*.json')}
        listing=requests.get(self.url+'/api/history?kind=comparison',timeout=5).json()['items']
        self.assertEqual(len(listing),1);self.assertEqual(listing[0]['status'],'completed');self.assertFalse(listing[0]['read_error'])
        detail=requests.get(self.url+'/api/history/comparison/'+cid,timeout=5).json()['item'];self.assertEqual(detail['details']['run_ids'],ids)
        original=requests.get(self.url+'/api/comparisons/'+cid,timeout=5).json()['comparison'];self.assertEqual(original['status'],detail['status'])
        self.assertEqual(before,{p:p.read_bytes()for p in self.home.rglob('*.json')})

    def test_preferences_actual_save_cas_and_safe_workspace_metadata(self):
        response=requests.get(self.url+'/api/preferences',timeout=5);self.assertEqual(response.status_code,200)
        raw=response.text
        for secret in ('private-a@','private-b@','PRIVATE_CLIENT_JSON','MUST_NOT_RETURN'):self.assertNotIn(secret,raw)
        first=response.json()['preferences'];self.assertEqual(first['revision'],0)
        values=first['values']|{'default_section':'history','history_page_size':10,'memory_unit':'MiB','time_display':'UTC'}
        # Standard JSON/browser roundtrip contains only bounded primitives; authoritative state is CAS.
        request=json.loads(json.dumps(dict(revision=0,values=values)))
        saved=self.post('/api/preferences',request);self.assertEqual(saved.status_code,200)
        self.assertEqual(self.post('/api/preferences',request).status_code,409)
        self.assertEqual(requests.get(self.url+'/api/preferences',timeout=5).json()['preferences']['values'],values)
        before=(self.home/'preferences.json').read_bytes()
        for invalid in (None,[],{},dict(revision=True,values=values),dict(revision=1,values=values|{'default_browser':'other'})):
            self.assertEqual(self.post('/api/preferences',invalid).status_code,400)
            self.assertEqual((self.home/'preferences.json').read_bytes(),before)

    def test_history_invalid_request_expiry_and_guards(self):
        response=requests.get(self.url+'/api/history?limit=10',timeout=5);self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['items'],[])
        for query in ('limit=1','offset=-1','kind=credential','q=x&q=y','snapshot=missing'):
            self.assertIn(requests.get(self.url+'/api/history?'+query,timeout=5).status_code,(400,410))
        for path in ('/api/history','/api/preferences'):
            self.assertEqual(requests.get(self.url+path,headers={'Origin':'https://foreign.invalid'},timeout=5).status_code,403)
        values=requests.get(self.url+'/api/preferences',timeout=5).json()['preferences']['values']
        self.assertEqual(self.post('/api/preferences',dict(revision=0,values=values),**{'X-AiManager-CSRF':'wrong'}).status_code,403)
        self.assertEqual(self.post('/api/preferences',dict(revision=0,values=values),Origin='https://foreign.invalid').status_code,403)

    def test_new_task_history_is_persistent_sanitized_and_current_running_is_not_invented(self):
        self.assertEqual(self.post('/api/action',dict(action='refresh',account='A')).status_code,202)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            state=requests.get(self.url+'/api/status',timeout=5).json()['task']
            if state['status']!='running':break
            time.sleep(.02)
        self.assertEqual(state['status'],'finished')
        rows=requests.get(self.url+'/api/history?kind=task',timeout=5).json()['items'];self.assertEqual(len(rows),1)
        row=rows[0];self.assertEqual(row['details'],dict(action='refresh',account='A'));self.assertEqual(row['scope'],'recorded_history')
        self.assertNotIn('synthetic test value',json.dumps(rows));self.assertNotIn('token',json.dumps(rows))
        self.assertEqual(requests.get(self.url+'/api/history/task/'+row['id'],timeout=5).json()['item']['id'],row['id'])

    def test_terminal_state_waits_for_journal_and_next_operation_is_immediately_admissible(self):
        entered,release=threading.Event(),threading.Event();original=History.task_record
        def delayed(instance,identifier,action,account,started,status,*rest,**kwargs):
            if status=='finished':entered.set();release.wait(2)
            return original(instance,identifier,action,account,started,status,*rest,**kwargs)
        with patch('ai_manager.history.History.task_record',new=delayed):
            self.assertEqual(self.post('/api/action',dict(action='refresh',account='A')).status_code,202)
            self.assertTrue(entered.wait(2))
            self.assertEqual(requests.get(self.url+'/api/status',timeout=5).json()['task']['status'],'running')
            self.assertEqual(self.post('/api/action',dict(action='refresh',account='B')).status_code,409)
            release.set();deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if requests.get(self.url+'/api/status',timeout=5).json()['task']['status']=='finished':break
                time.sleep(.01)
            self.assertEqual(self.post('/api/action',dict(action='refresh',account='B')).status_code,202)


if __name__=='__main__':unittest.main()
