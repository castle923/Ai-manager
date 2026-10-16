import json
from pathlib import Path
import tempfile
import threading
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
