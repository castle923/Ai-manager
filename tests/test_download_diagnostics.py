import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import requests
from ai_manager.download_diagnostics import DownloadDiagnostics
from ai_manager.server import serve
from ai_manager.inference import InferenceError


class DiagnosticsTests(unittest.TestCase):
    def test_disabled_creates_no_files(self):
        with tempfile.TemporaryDirectory() as temp:
            diag = DownloadDiagnostics(temp)
            self.assertIsNone(diag.begin('GET', '/api/diagnostics/health'))
            self.assertEqual(list(Path(temp).iterdir()), [])
            self.assertFalse(diag.health()['healthy'])

    def test_privacy_scope_thread_safety_and_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            diag=DownloadDiagnostics(temp,True)
            self.assertIsNone(diag.begin('GET','/api/session?secret=DO_NOT_LOG'))
            context=diag.begin('GET','/api/tts/runs/'+'a'*32+'/audio?token=DO_NOT_LOG')
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: diag.record(context,'body_written',bytes_written=12),range(80)))
            diag.record(context,'response_prepared',mime='unsafeDO_NOT_LOG',download='../../DO_NOT_LOG',status=200)
            data=diag.path.read_text();self.assertNotIn('DO_NOT_LOG',data);self.assertNotIn('/api/',data)
            self.assertEqual(len([json.loads(row) for row in data.splitlines()]),82)
            for _ in range(1100): diag.record(context,'body_written',bytes_written=1)
            self.assertEqual(diag.count,1000);self.assertFalse(diag.health()['healthy'])

    def test_write_failure_degrades_health_without_throwing(self):
        with tempfile.TemporaryDirectory() as temp:
            diag=DownloadDiagnostics(temp,True); context=diag.begin('GET','/api/diagnostics/health')
            with patch('pathlib.Path.open',side_effect=PermissionError('secret_absolute_path')):
                diag.record(context,'response_complete',bytes_written=0)
            self.assertFalse(diag.health()['healthy'])
            self.assertNotIn('secret_absolute_path',diag.path.read_text())

    def test_fresh_synthetic_http_success_rejection_and_error_keep_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); ready=threading.Event(); holders={}
            def factory(*args,**kwargs):
                result=ThreadingHTTPServer(*args,**kwargs); holders['server']=result;return result
            def browser(url): holders['url']=url.rstrip('/');ready.set()
            class Auth:
                class Store:
                    def get(self, account): return None
                store=Store()
            with patch('ai_manager.server.ThreadingHTTPServer',factory), patch.dict('os.environ',{'AI_MANAGER_DOWNLOAD_DIAGNOSTICS':'1'}), patch('ai_manager.server.Inference.audio',return_value=b'new-synthetic-audio-not-a-model-output'):
                thread=threading.Thread(target=serve,args=(home,{'allowlist':[]},Auth()),kwargs={'browser':browser},daemon=True);thread.start();self.assertTrue(ready.wait(5))
                try:
                    url=holders['url'];health=requests.get(url+'/api/diagnostics/health?private=DO_NOT_LOG',timeout=5)
                    self.assertTrue(health.json()['healthy']);self.assertNotIn('path',health.text)
                    route='/api/tts/runs/'+'a'*32+'/audio?download=1&secret=DO_NOT_LOG'
                    audio=requests.get(url+route,timeout=5)
                    self.assertEqual(audio.content,b'new-synthetic-audio-not-a-model-output')
                    self.assertEqual(audio.headers['Content-Type'],'audio/wav')
                    self.assertEqual(audio.headers['Content-Disposition'],'attachment; filename="'+'a'*32+'.wav"')
                    rejected=requests.get(url+route,headers={'Host':'evil.invalid','Authorization':'DO_NOT_LOG'},timeout=5);self.assertEqual(rejected.status_code,403)
                    with patch('ai_manager.server.Inference.audio',side_effect=InferenceError('run_not_found')):
                        self.assertEqual(requests.get(url+route,timeout=5).status_code,404)
                    rows=[json.loads(row) for row in next((home/'diagnostics').glob('*/*.jsonl')).read_text().splitlines()]
                    self.assertNotIn('DO_NOT_LOG',json.dumps(rows)); self.assertNotIn(str(home),json.dumps(rows))
                    complete=[row for row in rows if row['stage']=='response_complete'];self.assertEqual(len(complete),4)
                    prepared=[row for row in rows if row['stage']=='response_prepared'];self.assertEqual([r['status'] for r in prepared],[200,200,403,404])
                    self.assertEqual(complete[1]['bytes_written'],len(audio.content))
                finally: holders['server'].shutdown();thread.join(5)
