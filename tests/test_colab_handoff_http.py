import json
import http.client
from pathlib import Path
import socket
import shutil
from unittest.mock import patch
import tempfile
import unittest
from ai_manager.server import create_application
from test_colab_handoff_contract import success, signed

class Auth:
    class Store:
        def get(self, account): return None
    store = Store()

class HandoffHTTPTests(unittest.TestCase):
    def setUp(self):
        evidence = Path(__file__).resolve().parents[2] / 'development-evidence/llama-colab-implementation-20261025-r4n8'
        self.temp = tempfile.TemporaryDirectory(prefix='task-3-http-', dir=evidence)
        self.home = Path(self.temp.name)
        self.app = create_application(self.home, {'allowlist': [], 'mode': 'local'}, Auth())
        self.app.start()
        self.port = self.app.server.server_port
        self.csrf = self.call('GET', '/api/session')[1]['csrf']
    def tearDown(self):
        self.app.close(); self.temp.cleanup()
    def call(self, method, path, value=None, raw=None, headers=None):
        body = raw if raw is not None else json.dumps(value, ensure_ascii=False).encode() if value is not None else None
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        hs = {'Content-Type':'application/json', 'X-AiManager-CSRF':getattr(self, 'csrf', '')}
        hs.update(headers or {})
        conn.request(method, path, body=body, headers=hs)
        response = conn.getresponse(); data = response.read(); status=response.status; conn.close()
        try: data=json.loads(data)
        except ValueError: pass
        return status, data
    def preview(self):
        status, request=self.call('POST', '/api/colab-handoff/preview', {'text':'물은 얼면 무엇이 되나요?'})
        self.assertEqual(status, 200); return request
    def test_preview_export_import_and_conflict_preserve_local_state(self):
        before=self.call('GET','/api/registry')[1]
        request=self.preview()
        self.assertFalse((self.home/'colab-handoff').exists())
        self.assertEqual(self.call('POST','/api/colab-handoff/requests',request)[0],200)
        path='/api/colab-handoff/requests/'+request['request_id']
        self.assertEqual(self.call('GET',path+'/download')[1],request)
        result=success(request, '<script>alert(1)</script> 한글 e\u0301')
        # Exceeds the old global 4KiB limit, still a valid external result.
        result=success(request,'물'*1700)
        self.assertEqual(self.call('POST','/api/colab-handoff/results',result)[0],200)
        self.assertEqual(self.call('POST','/api/colab-handoff/results',result)[0],200)
        changed=success(request,'다른 결과')
        self.assertEqual(self.call('POST','/api/colab-handoff/results',changed), (409,{'error':'result_conflict'}))
        wrong=dict(result,request_sha256='f'*64);wrong=signed(wrong,'result_sha256')
        self.assertEqual(self.call('POST','/api/colab-handoff/results',wrong)[0],400)
        self.assertEqual(self.call('GET','/api/registry')[1],before)
        self.assertEqual(self.call('GET',path)[1]['result'],result)
    def test_strict_json_size_and_security(self):
        self.assertEqual(self.call('GET','/api/colab-handoff/meta')[0],200)
        for raw in (b'{"text":"a","text":"b"}', b'{"text":"a","path":"SECRET"}', b'{"request":{"text":"a"}}', b'{"text":1e999}'):
            status,data=self.call('POST','/api/colab-handoff/preview',raw=raw)
            self.assertEqual(status,400); self.assertNotIn('SECRET',str(data));self.assertNotIn(str(self.home),str(data))
        for route,limit in [('preview',16384),('requests',16384),('results',65536)]:
            self.assertEqual(self.call('POST','/api/colab-handoff/'+route,raw=b' '* (limit+1))[0],400)
        for headers in ({'Host':'evil.invalid'}, {'Origin':'https://evil.invalid'}, {'X-AiManager-CSRF':'bad'}):
            self.assertEqual(self.call('POST','/api/colab-handoff/preview',{'text':'물'},headers=headers)[0],403)
        self.assertEqual(self.call('POST','/api/colab-handoff/preview',{'text':'물'},headers={'Content-Type':'text/plain'})[0],415)
    def test_framing_rejects_chunked_duplicate_invalid_truncated_lengths(self):
        for framing,body in [('Transfer-Encoding: chunked\r\n','1\r\nx\r\n0\r\n\r\n'),('Content-Length: -1\r\n',''),('Content-Length: x\r\n',''),('Content-Length: 2\r\nContent-Length: 2\r\n','{}'),('Content-Length: 50\r\n','{}')]:
            with socket.create_connection(('127.0.0.1',self.port),timeout=4) as s:
                raw=f'POST /api/colab-handoff/preview HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\nX-AiManager-CSRF: {self.csrf}\r\n{framing}\r\n{body}'
                s.sendall(raw.encode());s.shutdown(socket.SHUT_WR)
                self.assertIn(b' 400 ',s.recv(4096).split(b'\r\n')[0])
    def test_actual_public_source_changes_block_preview_and_export_without_publication(self):
        repo = Path(__file__).resolve().parents[1]
        public = ('src/ai_manager/colab_contract.py', 'scripts/colab/llama_handoff_worker.py',
                  'scripts/colab/llama_watchdog.py', 'src/ai_manager/adapter_manifest_llama.json',
                  'src/ai_manager/colab_source_pins.json')
        for relative in public:
            for mutation in ('changed', 'missing'):
                with self.subTest(source=relative, mutation=mutation), tempfile.TemporaryDirectory(dir=self.home) as temporary:
                    fixture = Path(temporary)
                    for source in public:
                        target = fixture / source
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(repo / source, target)
                    with patch('ai_manager.server._HANDOFF_PUBLIC_ROOT', fixture, create=True):
                        request = self.preview()
                        target = fixture / relative
                        if mutation == 'missing':
                            target.unlink()
                        elif relative.endswith('colab_source_pins.json'):
                            pins = json.loads(target.read_bytes()); pins['worker'] = 'f' * 64
                            target.write_text(json.dumps(pins), encoding='utf-8')
                        else:
                            target.write_bytes(target.read_bytes() + b'\nchanged synthetic public source\n')
                        status, data = self.call('POST', '/api/colab-handoff/requests', request)
                        self.assertEqual((status, data), (400, {'error':'source_mismatch'}))
                        self.assertFalse((self.home / 'colab-handoff').exists())
                        self.assertEqual(self.call('POST', '/api/colab-handoff/preview', {'text':'새 합성 입력'}),
                                         (400, {'error':'source_mismatch'}))
                        self.assertFalse((self.home / 'colab-handoff').exists())

    def test_public_notebook_download(self):
        status,notebook=self.call('GET','/api/colab-handoff/bundle')
        self.assertEqual(status,200);self.assertEqual(notebook['nbformat'],4)

if __name__=='__main__': unittest.main()
