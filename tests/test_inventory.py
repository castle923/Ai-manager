import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from ai_manager.drive import FOLDER, SHORTCUT
from ai_manager.inventory import Inventory, kind


def item(fid, name="model.safetensors", parent="rootA", mime="application/octet-stream", **extra):
    return dict(id=fid, name=name, parents=[parent], mimeType=mime, **extra)


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected network call")
        return self.responses.pop(0)


class InventoryTests(unittest.TestCase):
    def test_exact_configuration_filename_without_arbitrary_json(self):
        self.assertEqual(kind("configuration.json"), "model_component_candidate")
        self.assertIsNone(kind("previous-workflow.json"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.settings = {"version": 1, "allowlist": [{"account": "A", "id": "rootA", "alias": "A_ROOT_01"}, {"account": "B", "id": "rootB", "alias": "B_ROOT_01"}]}

    def inventory(self, responses):
        session = FakeSession(responses)
        return Inventory(self.home, session=session, sleep=lambda _: None), session

    def root(self, fid="rootA", **extra):
        return Response(item(fid, "root", mime=FOLDER, **extra))

    def test_pagination_filtering_cycles_duplicates_and_history(self):
        inv, session = self.inventory([self.root(), Response({"files": [item("sub", "model-folder", mime=FOLDER), item("cache", ".cache", mime=FOLDER), item("out", "outputs", mime=FOLDER), item("short", "link", mime=SHORTCUT), item("code", "loader.py"), item("workflow", "workflow.json"), item("outside", parent="elsewhere"), item("shared", driveId="shared-drive"), item("w")], "nextPageToken": "p2"}), Response({"files": [item("w"), item("w2", "model.safetensors")]}), Response({"files": [item("rootA", "cycle", parent="sub", mime=FOLDER), item("config", "config.json", parent="sub")]})])
        result = inv.scan(self.settings, "A", "synthetic-token")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["files_count"], 3)
        self.assertEqual(result["pages_count"], 3)
        self.assertEqual(result["folders_count"], 2)
        self.assertEqual(len(inv.files(result["scan_id"], limit=2)), 2)
        self.assertEqual(len(inv.files(result["scan_id"], limit=2, offset=2)), 1)
        self.assertEqual(len({x["file_id"] for x in inv.files(result["scan_id"])}), 3)
        self.assertFalse(any("rootB" in str(call) for call in session.calls))
        for _, kwargs in session.calls:
            self.assertNotIn("alt", kwargs["params"])
            self.assertFalse(kwargs["allow_redirects"])
        self.assertNotIn("synthetic-token", inv.db.read_bytes().decode("latin1"))
        self.assertNotIn("rootA", json.dumps(inv.summary()))

    def test_empty_pages_continue_and_complete(self):
        inv, session = self.inventory([self.root(), Response({"files": [], "nextPageToken": "next"}), Response({"files": [item("w")]})])
        result = inv.scan(self.settings, "A", "x")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["files_count"], 1)
        self.assertEqual(session.calls[-1][1]["params"]["pageToken"], "next")

    def test_repeated_page_token_and_incomplete_search_are_partial(self):
        inv, _ = self.inventory([self.root(), Response({"files": [], "incompleteSearch": True, "nextPageToken": "same"}), Response({"files": [], "nextPageToken": "same"})])
        result = inv.scan(self.settings, "A", "x")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(set(result["errors"]), {"incomplete_search", "repeated_or_invalid_page_token"})

    def test_forbidden_wrong_root_shared_drive_and_trashed(self):
        for response in [Response({}, 403), Response(item("rootA")), self.root(driveId="sd"), self.root(trashed=True)]:
            with self.subTest(response=response.payload):
                inv, session = self.inventory([response])
                result = inv.scan(self.settings, "A", "x")
                self.assertEqual(result["status"], "partial")
                self.assertEqual(len(session.calls), 1)

    def test_429_bounded_retry_then_success_and_exhaustion(self):
        inv, session = self.inventory([self.root(), Response({}, 429), Response({"files": []})])
        self.assertEqual(inv.scan(self.settings, "A", "x")["status"], "complete")
        self.assertEqual(len(session.calls), 3)
        inv.session = FakeSession([self.root()] + [Response({}, 503)] * 5)
        result = inv.scan(self.settings, "A", "x")
        self.assertEqual(result["status"], "partial")
        self.assertIn("http_retry_exhausted_503", result["errors"])
        self.assertEqual(len(inv.session.calls), 6)

    def test_401_refresh_callback_and_cancel(self):
        inv, session = self.inventory([Response({}, 401), self.root(), Response({"files": []})])
        flags = []
        def access(force_refresh=False):
            flags.append(force_refresh)
            return "new" if force_refresh else "token"
        self.assertEqual(inv.scan(self.settings, "A", access)["status"], "complete")
        self.assertEqual(flags, [False, True, False])
        cancel = threading.Event()
        cancel.set()
        result = inv.scan(self.settings, "B", "x", cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(len(session.calls), 3)

    def test_history_account_isolation_and_interrupted_recovery(self):
        inv, _ = self.inventory([self.root(), Response({"files": [item("a")]})])
        first = inv.scan(self.settings, "A", "x")
        inv.session = FakeSession([self.root("rootB"), Response({"files": [item("b", parent="rootB")]})])
        self.settings["version"] = 2
        second = inv.scan(self.settings, "B", "x")
        self.assertEqual(inv.files(first["scan_id"])[0]["file_id"], "a")
        self.assertEqual(inv.files(second["scan_id"])[0]["file_id"], "b")
        self.assertEqual(inv.scan_info(first["scan_id"])["settings_version"], 1)
        with inv.connect() as db:
            db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid) VALUES('interrupted','A',1,'{}','y','running',?)", (os.getpid(),))
        restarted = Inventory(self.home)
        self.assertEqual(restarted.scan_info("interrupted")["status"], "interrupted")
        self.assertEqual(restarted.scan_info(first["scan_id"])["status"], "complete")

    def test_invalid_root_rejected_before_any_request(self):
        inv, session = self.inventory([])
        self.settings["allowlist"][0]["id"] = "bad' or true"
        with self.assertRaises(ValueError):
            inv.scan(self.settings, "A", "x")
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
