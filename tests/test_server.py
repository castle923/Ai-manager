import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import requests

from ai_manager.server import serve


class FakeAuth:
    class Store:
        def get(self, account):
            return None
    store = Store()


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.ready = threading.Event()
        cls.servers = []
        def factory(*args, **kwargs):
            server = ThreadingHTTPServer(*args, **kwargs)
            cls.servers.append(server)
            return server
        def browser(url):
            cls.url = url.rstrip("/")
            cls.ready.set()
        cls.patcher = patch("ai_manager.server.ThreadingHTTPServer", factory)
        cls.patcher.start()
        cls.thread = threading.Thread(target=serve, args=(Path(cls.temp.name), {"allowlist": []}, FakeAuth()), kwargs={"browser": browser}, daemon=True)
        cls.thread.start()
        if not cls.ready.wait(5):
            raise RuntimeError("test server failed to start")
        cls.csrf = requests.get(cls.url + "/api/session", timeout=5).json()["csrf"]

    @classmethod
    def tearDownClass(cls):
        cls.servers[0].shutdown()
        cls.thread.join(5)
        cls.patcher.stop()
        cls.temp.cleanup()

    def post(self, data, **headers):
        return requests.post(self.url + "/api/action", data=json.dumps(data), headers={"Content-Type": "application/json", "X-AiManager-CSRF": self.csrf, **headers}, timeout=5)

    def test_malformed_json_shapes_are_400_not_connection_drop(self):
        for value in (None, [], {}, {"action": []}, {"action": "scan", "account": []}, {"action": "scan", "account": "C"}):
            with self.subTest(value=value):
                self.assertEqual(self.post(value).status_code, 400)

    def test_csrf_host_origin_remain_enforced(self):
        self.assertEqual(self.post({"action": "cancel"}, **{"X-AiManager-CSRF": "wrong"}).status_code, 403)
        self.assertEqual(self.post({"action": "cancel"}, Origin="https://foreign.invalid").status_code, 403)
        self.assertEqual(requests.get(self.url + "/api/status", headers={"Host": "evil.invalid"}, timeout=5).status_code, 403)
        self.assertEqual(self.post({"action": "cancel"}).status_code, 202)

    def test_dashboard_validation_and_security_headers(self):
        result = requests.get(self.url + "/api/dashboard", timeout=5)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["scans"], [])
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", result.headers["Content-Security-Policy"])
        self.assertEqual(requests.get(self.url + "/api/dashboard?page=-1", timeout=5).status_code, 400)
        self.assertEqual(requests.get(self.url + "/api/detail?id=unknown", timeout=5).status_code, 404)

    def test_preparation_runtime_check_and_cancel_ui_contract(self):
        # The actual preparation screen used to send model_id for every action.
        # Runtime checks are local/global, and cancel must not select a model.
        for model_id in (None, 'qwen3-tts-0.6b-customvoice', 'qwen3-tts-1.7b-customvoice'):
            with self.subTest(model_id=model_id), patch('ai_manager.preparation.Preparation.probe_runtime', return_value={'status':'blocked','blockers':['synthetic_probe_no_gpu']}):
                body={'action':'runtime_check','account':'B'}
                if model_id: body['model_id']=model_id
                self.assertEqual(self.post(body).status_code,202)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    task=requests.get(self.url+'/api/status',timeout=3).json()['task']
                    if task['status']!='running':break
                    time.sleep(.01)
                self.assertEqual(task['result']['blockers'],['synthetic_probe_no_gpu'])
        self.assertEqual(self.post({'action':'cancel','account':'B'}).status_code,202)
        self.assertEqual(self.post({'action':'runtime_check','account':'B','model_id':'unsupported-model'}).status_code,400)
        self.assertEqual(self.post({'action':'runtime_check','account':'A'}).status_code,400)
        for model_id in ('qwen3-tts-0.6b-customvoice', 'qwen3-tts-1.7b-customvoice'):
            with patch('ai_manager.preparation.Preparation.prepare',return_value={'status':'ready','source':'synthetic_contract_no_download'}):
                self.assertEqual(self.post({'action':'prepare','account':'B','model_id':model_id}).status_code,202)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    task=requests.get(self.url+'/api/status',timeout=3).json()['task']
                    if task['status']!='running':break
                    time.sleep(.01)
                self.assertEqual(task['result']['source'],'synthetic_contract_no_download')
