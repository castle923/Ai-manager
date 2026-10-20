"""Fresh-workspace readiness, with a forced file-before-schema interleaving."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import requests

from ai_manager.config import SettingsStore
from ai_manager.inventory import Inventory
from ai_manager.local_mode import NoDriveAuth
from ai_manager.server import create_application


class StartupInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / 'fresh-local'
        self.settings = SettingsStore(self.home).initialize_local()

    def tearDown(self):
        self.temp.cleanup()

    def test_new_database_schema_finishes_before_server_binding(self):
        opened, release, finished = threading.Event(), threading.Event(), threading.Event()
        original = Inventory.connect
        result = {}

        @contextmanager
        def gate(inventory):
            with original(inventory) as db:
                if not inventory.read_only and not opened.is_set():
                    opened.set()
                    if not release.wait(5):
                        raise AssertionError('schema barrier timeout')
                yield db

        def construct():
            try:
                result['app'] = create_application(self.home, self.settings, NoDriveAuth())
            except BaseException as error:
                result['error'] = error
            finally:
                finished.set()

        with patch.object(Inventory, 'connect', gate), patch('ai_manager.server.ThreadingHTTPServer', wraps=__import__('http.server', fromlist=['ThreadingHTTPServer']).ThreadingHTTPServer) as bind:
            thread = threading.Thread(target=construct)
            thread.start()
            try:
                self.assertTrue(opened.wait(2), 'startup did not initialize the inventory')
                self.assertTrue((self.home / 'inventory.sqlite3').exists())
                self.assertFalse(finished.is_set())
                bind.assert_not_called()
                with sqlite3.connect((self.home/'inventory.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'no such table'):
                        db.execute('SELECT * FROM scans')
            finally:
                release.set()
                thread.join(5)
                if result.get('app'):
                    result['app'].close()
            self.assertFalse(thread.is_alive())
            self.assertNotIn('error', result)
            bind.assert_called_once()

    def test_fresh_concurrent_initial_reads_all_return_complete_responses(self):
        app = create_application(self.home, self.settings, NoDriveAuth())
        url = app.start().rstrip('/')
        paths = ['/api/status', '/api/dashboard', '/api/session', '/api/preferences'] * 5
        def get(path):
            response = requests.get(url+path, timeout=5)
            self.assertEqual(response.status_code, 200, path)
            return path, response.json()
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(get, paths))
            for path, data in results:
                if path == '/api/dashboard':
                    self.assertEqual(data['total'], 0)
                    self.assertEqual(data['scans'], [])
                if path == '/api/status':
                    self.assertEqual(data['accounts'], {})
        finally:
            app.close()
        self.assertFalse((self.home/'credentials').exists())

    def test_existing_inventory_observations_and_settings_are_preserved(self):
        inventory = Inventory(self.home)
        with inventory.connect() as db:
            db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid) VALUES('fresh-synthetic','A',1,'{}','2026-10-21','complete',0)")
            db.execute("INSERT INTO files VALUES('fresh-synthetic','synthetic-file','ROOT','ROOT/new/config.json','model_component_candidate','{\"name\":\"config.json\"}')")
        tracked = [self.home/'inventory.sqlite3', self.home/'settings.json']
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
        app = create_application(self.home, self.settings, NoDriveAuth())
        try:
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked})
        finally:
            app.close()

    def test_corrupt_inventory_fails_before_binding_without_replacement(self):
        database = self.home/'inventory.sqlite3'
        database.write_bytes(b'new synthetic invalid database')
        before = database.read_bytes()
        app = None
        with patch('ai_manager.server.ThreadingHTTPServer') as bind:
            try:
                with self.assertRaises(sqlite3.DatabaseError):
                    app = create_application(self.home, self.settings, NoDriveAuth())
                bind.assert_not_called()
            finally:
                if app:
                    app.close()
        self.assertEqual(database.read_bytes(), before)
