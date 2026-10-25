from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_manager import colab_contract as contract
from test_colab_handoff_contract import PINS, signed, success

try:
    from ai_manager.colab_handoff import HandoffStore
except ImportError:
    HandoffStore = None


EVIDENCE = Path(__file__).resolve().parents[2] / "development-evidence" / "llama-colab-implementation-20261025-r4n8"


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(HandoffStore, "handoff sidecar is not implemented")
        self.temp = tempfile.TemporaryDirectory(prefix="task1-home-", dir=EVIDENCE)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "new-home"
        self.request = contract.build_request("새 합성 입력", PINS)
        self.store = HandoffStore(self.home, PINS)

    def error(self, code, function, *args):
        with self.assertRaises(contract.ColabContractError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertNotIn(str(self.home), str(caught.exception))

    def test_preview_and_reads_do_not_create_home(self):
        self.assertFalse(self.home.exists())
        self.error("request_not_found", self.store.get_request, self.request["request_id"])
        self.assertFalse(self.home.exists())
        self.error("invalid_request_id", self.store.detail, "../SECRET")
        self.assertFalse(self.home.exists())

    def test_saved_request_and_import_are_bound_and_private(self):
        self.store.save_request(self.request)
        result = success(self.request, "e\u0301 <script>한글</script>")
        self.assertEqual(self.store.detail(self.request["request_id"]), {"request": self.request, "result": None})
        self.assertEqual(self.store.import_result(raw(result)), result)
        self.assertEqual(self.store.detail(self.request["request_id"]), {"request": self.request, "result": result})
        files = sorted(str(path.relative_to(self.home)) for path in self.home.rglob("*") if path.is_file())
        self.assertEqual(files, [str(Path("colab-handoff/requests") / (self.request["request_id"] + ".json")),
                                 str(Path("colab-handoff/results") / (self.request["request_id"] + ".json"))])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
            for path in self.home.rglob("*.json"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_request_conflict_and_validation_never_replace(self):
        self.store.save_request(self.request)
        path = self.home / "colab-handoff/requests" / (self.request["request_id"] + ".json")
        before = path.read_bytes()
        self.assertEqual(self.store.save_request(copy.deepcopy(self.request)), self.request)
        altered = contract.build_request("다른 요청", PINS)
        altered["request_id"] = self.request["request_id"]
        altered = signed(altered, "request_sha256")
        self.error("request_conflict", self.store.save_request, altered)
        self.assertEqual(path.read_bytes(), before)
        invalid = copy.deepcopy(self.request)
        invalid["input"]["text"] = "SECRET"
        with self.assertRaises(contract.ColabContractError):
            self.store.save_request(invalid)
        self.assertEqual(path.read_bytes(), before)

    def test_empty_unknown_key_is_not_silently_dropped_during_freeze(self):
        value = copy.deepcopy(self.request)
        value[""] = "SECRET"
        with self.assertRaises(contract.ColabContractError):
            self.store.save_request(value)
        self.assertFalse(self.home.exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_actual_windows_junction_is_rejected_without_writing_target(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.home.mkdir()
        junction = self.home / "colab-handoff"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                              capture_output=True, check=False)
        self.assertEqual(made.returncode, 0, "fixture junction creation failed")
        self.error("unsafe_storage_path", self.store.save_request, self.request)
        self.assertEqual(list(outside.iterdir()), [])

    def test_same_result_is_idempotent_other_result_conflicts_binding_always_checked(self):
        self.store.save_request(self.request)
        first = success(self.request)
        self.store.import_result(raw(first))
        path = self.home / "colab-handoff/results" / (self.request["request_id"] + ".json")
        before = path.read_bytes()
        self.assertEqual(self.store.import_result(raw(first)), first)
        self.error("result_conflict", self.store.import_result, raw(success(self.request, "다른 결과")))
        altered = copy.deepcopy(first)
        altered["request_sha256"] = "0" * 64
        altered = signed(altered, "result_sha256")
        with self.assertRaises(contract.ColabContractError):
            self.store.import_result(raw(altered))
        self.assertEqual(path.read_bytes(), before)

    def test_concurrent_publication_keeps_one_complete_document(self):
        self.store.save_request(self.request)
        values = [success(self.request, "결과 A"), success(self.request, "결과 B")]
        def publish(value):
            try:
                return self.store.import_result(raw(value))
            except contract.ColabContractError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(publish, values * 8))
        saved = self.store.detail(self.request["request_id"])["result"]
        self.assertIn(saved, values)
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 8)
        self.assertEqual(outcomes.count("result_conflict"), 8)
        self.assertFalse(list(self.home.rglob("*.tmp")))

    def test_failed_publication_leaves_no_partial_target_or_temp(self):
        self.store.save_request(self.request)
        with patch("ai_manager.colab_handoff.os.link", side_effect=OSError("SECRET path")):
            self.error("storage_error", self.store.import_result, raw(success(self.request)))
        self.assertIsNone(self.store.detail(self.request["request_id"])["result"])
        self.assertFalse(list(self.home.rglob("*.tmp")))

    def test_oversize_read_is_bounded_and_corrupt_existing_data_is_preserved(self):
        self.store.save_request(self.request)
        path = self.home / "colab-handoff/requests" / (self.request["request_id"] + ".json")
        path.write_bytes(b" " * 16385)
        self.error("document_too_large", self.store.get_request, self.request["request_id"])
        self.assertEqual(path.stat().st_size, 16385)

    def test_reparse_attributes_and_symlink_parents_are_rejected(self):
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)):
            self.error("unsafe_storage_path", self.store.save_request, self.request)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.home.mkdir()
        try:
            (self.home / "colab-handoff").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable; reparse attribute rejection checked")
        self.error("unsafe_storage_path", self.store.save_request, self.request)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
