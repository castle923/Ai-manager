"""New synthetic namespace and per-candidate explanation counterexamples."""
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import requests

from ai_manager.candidate_recommendations import explain, _profiles
from ai_manager.dashboard import Dashboard
from ai_manager.server import serve
from test_candidate_recommendations import profile, root_files, seed


class NamespaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.dashboard=Dashboard(self.home)

    def tearDown(self):self.temp.cleanup()

    def group(self, name, identifier='qwen3-tts-1.7b-customvoice'):
        return dict(path=name,files=root_files(profile(identifier)))

    def row(self, name, identifier='qwen3-tts-1.7b-customvoice'):
        seed(self.dashboard,[self.group(name,identifier)])
        return self.dashboard.snapshot()['models'][0]

    def test_fixed_publisher_forms_and_bare_names_keep_same_gates(self):
        for p in _profiles():
            canonical=p['name'].rsplit('/',1)[-1]
            publisher=p['name'].split('/')[0]
            for path in (canonical,publisher+'/'+canonical,publisher+'--'+canonical,publisher+'__'+canonical):
                with self.subTest(path=path):
                    files=[dict(name=f['path'],size=f['size'],kind='weight_candidate' if Path(f['path']).suffix in {'.safetensors','.pt','.bin'} else 'model_component_candidate') for f in root_files(p)]
                    row=dict(name=path.rsplit('/',1)[-1],path='ROOT/'+path,files=files,scan_status='complete',observations={})
                    r=explain(row,p['purpose'])
                    self.assertEqual([c['id'] for c in r['profile_name_candidates']],[p['model_id']])
                    self.assertEqual(r['eligible'],p['purpose']!='image')
                    self.assertEqual(r['identity'],'unverified');self.assertEqual(r['execution'],'unverified')
                    self.assertEqual(r['quality'],'unassessed')
                    if p['purpose']=='image':self.assertIn('distributed_weights_unobserved',r['reason_codes'])

    def test_unknown_publishers_and_lookalikes_never_grant_a_rank(self):
        canonical='Qwen3-TTS-12Hz-1.7B-CustomVoice'
        row=self.row(canonical)
        for name in ('Unknown--'+canonical,'Unknown__'+canonical,'models--Qwen--'+canonical,'Qwen--'+canonical+'-extra','Qwen__'+canonical+'.backup','not'+canonical,'Qwen--'+canonical[:20],'Qwen--'+canonical.replace('1.7B','1.7B-Base')):
            with self.subTest(name=name):
                r=explain(row|dict(path='ROOT/'+name,name=name),'tts')
                self.assertFalse(r['eligible']);self.assertIsNone(r['rank'])
                self.assertEqual(r['profile_name_candidates'],[])
        r=explain(row|dict(path='ROOT/Unknown--'+canonical,name='Unknown--'+canonical),'tts')
        self.assertIn('unrecognized_name_form',r['reason_codes'])

    def test_nested_conflicting_profiles_and_unknown_namespace_fail_closed(self):
        row=self.row('Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice')
        for path in (row['path']+'/openai__whisper-large-v3-turbo', row['path']+'/Qwen__Qwen3-TTS-12Hz-0.6B-CustomVoice'):
            r=explain(row|dict(path=path),'tts')
            self.assertFalse(r['eligible']);self.assertIn('ambiguous_profile',r['reason_codes'])
        r=explain(row|dict(path='ROOT/Unknown--Qwen3-TTS-12Hz-1.7B-CustomVoice/'+row['name']),'tts')
        self.assertFalse(r['eligible']);self.assertIn('unrecognized_name_form',r['reason_codes'])
        r=explain(row|dict(path=row['path']+'/'+row['name']),'tts')
        self.assertEqual(len(r['profile_name_candidates']),1)

    def test_recognized_namespace_does_not_bypass_root_or_missing_file_checks(self):
        row=self.row('Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice')
        r=explain(row|dict(name='speech_tokenizer',path=row['path']+'/speech_tokenizer'),'tts')
        self.assertFalse(r['eligible']);self.assertIn('not_model_root',r['reason_codes'])
        for f in row['files']:
            altered=[other for other in row['files'] if other is not f]
            r=explain(row|dict(files=altered),'tts')
            self.assertFalse(r['eligible']);self.assertTrue(r['missing_evidence'])
            self.assertIn(f['name'],str(r['missing_evidence']))
        r=explain(row|dict(scan_status='partial'),'tts')
        self.assertFalse(r['eligible']);self.assertIn('incomplete_scan',r['reason_codes'])

    def test_observed_names_and_different_deferrals_are_inspectable(self):
        seed(self.dashboard,[self.group('hexgrad--Kokoro-82M'),self.group('microsoft--VibeVoice-1.5B'),self.group('Unknown--Qwen3-TTS-12Hz-1.7B-CustomVoice')])
        rows=self.dashboard.query({'purpose':['tts']})['rows']
        self.assertEqual(len({tuple(r['recommendation']['reasons']) for r in rows}),3)
        for row in rows:
            rec=row['recommendation'];self.assertEqual(rec['observed_name'],row['name'])
            self.assertTrue(rec['task_clues']);self.assertTrue(rec['defined_profiles'])
            self.assertFalse(rec['eligible'])

    def test_new_name_cases_are_exposed_by_actual_get_api(self):
        seed(self.dashboard,[self.group('Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice'),self.group('Qwen__Qwen-Image-2.1','qwen-image-2.1'),self.group('Other--Qwen3-TTS-12Hz-1.7B-CustomVoice')])
        class Auth:
            class Store:
                def get(self,account):return None
            store=Store()
        servers=[];ready=threading.Event();urls=[]
        def factory(*a,**kw):
            server=ThreadingHTTPServer(*a,**kw);servers.append(server);return server
        def browser(url):urls.append(url.rstrip('/'));ready.set()
        before=hashlib.sha256((self.home/'inventory.sqlite3').read_bytes()).hexdigest()
        with patch('ai_manager.server.ThreadingHTTPServer',factory):
            worker=threading.Thread(target=serve,args=(self.home,{'allowlist':[]},Auth()),kwargs={'browser':browser},daemon=True);worker.start()
            self.assertTrue(ready.wait(5))
            try:
                r=requests.get(urls[0]+'/api/dashboard?purpose=tts',timeout=5)
                self.assertEqual(r.status_code,200)
                data=r.json();self.assertEqual(data['recommendation']['recommended'],1)
                eligible=next(row for row in data['rows'] if row['recommendation']['eligible'])
                self.assertEqual(eligible['recommendation']['rank'],1)
                detail=requests.get(urls[0]+'/api/detail',params={'id':eligible['id'],'purpose':'tts'},timeout=5).json()
                self.assertTrue(detail['recommendation']['name_evidence'])
                image=requests.get(urls[0]+'/api/dashboard?purpose=image',timeout=5).json()
                self.assertEqual(image['recommendation']['recommended'],0)
                row=next(row for row in image['rows'] if row['name'].startswith('Qwen__'))
                self.assertIn('distributed_weights_unobserved',row['recommendation']['reason_codes'])
            finally:servers[0].shutdown();worker.join(5)
        self.assertEqual(before,hashlib.sha256((self.home/'inventory.sqlite3').read_bytes()).hexdigest())
