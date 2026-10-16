"""Fresh synthetic observations exercise the M2 read-only contracts."""
import json
from pathlib import Path
import tempfile
import unittest

from ai_manager.dashboard import Dashboard, observations, family


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dashboard = Dashboard(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def scan(self, identifier, account="A", status="complete", when="2026-01-01", files=()):
        with self.dashboard.inventory.connect() as db:
            db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid,files_count) VALUES(?,?,1,'{}',?,?,0,?)", (identifier, account, when, status, len(files)))
            for i, metadata in enumerate(files):
                metadata = {"id": str(i), **metadata}
                db.execute("INSERT INTO files VALUES(?,?,?,?,?,?)", (identifier, str(i), "ROOT", "ROOT/duplicate/" + metadata["name"], metadata.pop("kind", "weight_candidate"), json.dumps(metadata)))

    def test_parent_identity_and_ambiguous_parents_do_not_merge(self):
        self.scan("s", files=[{"name": "model.safetensors", "parents": ["one"]}, {"name": "config.json", "kind": "model_component_candidate", "parents": ["two"]}, {"name": "part.bin", "parents": ["one", "two"]}, {"name": "other.bin"}])
        data = self.dashboard.query({})
        self.assertEqual(data["summary"]["groups"], 4)
        weight = next(r for r in data["rows"] if r["observations"]["weight_files"] == 1 and self.dashboard.detail(r["id"])["files"][0]["name"] == "model.safetensors")
        self.assertFalse(weight["observations"]["config_observed"])
        self.assertNotIn("parent_identity", str(data))

    def test_latest_partial_not_hidden_by_old_success_and_history_is_explicit(self):
        self.scan("old", when="2026-01-01", files=[{"name": "old.bin", "size": "1"}])
        self.scan("new", status="partial", when="2026-01-02", files=[{"name": "new.bin"}])
        self.scan("b", account="B", files=[{"name": "b.bin"}])
        data = self.dashboard.query({"view": ["files"]})
        self.assertEqual({r["name"] for r in data["rows"]}, {"new.bin", "b.bin"})
        self.assertEqual(next(s for s in data["scans"] if s["account"] == "A")["status"], "partial")
        self.assertIsNone(next(r for r in data["rows"] if r["name"] == "new.bin")["size"])
        self.assertEqual(self.dashboard.query({"scan": ["old"]})["summary"]["files"], 1)

    def test_search_filters_pagination_detail_and_unknown_states(self):
        self.scan("s", files=[{"name": f"qwen-tts-{i:03}.bin", "size": str(i), "parents": [f"p{i}"]} for i in range(53)])
        data = self.dashboard.query({"view": ["files"], "q": ["TTS"], "account": ["A"], "kind": ["weight_candidate"], "family": ["음성 합성"], "limit": ["24"], "page": ["2"]})
        self.assertEqual(data["total"], 53)
        self.assertEqual(len(data["rows"]), 24)
        self.assertEqual(self.dashboard.query({"page": ["999"]})["page"], 3)
        detail = self.dashboard.detail(self.dashboard.query({})["rows"][0]["id"])
        self.assertEqual(detail["observations"]["integrity"], "unverified")
        self.assertEqual(detail["observations"]["execution"], "unverified")
        self.assertEqual(self.dashboard.query({"account": ["B"]})["total"], 0)
        with self.assertRaises(KeyError):
            self.dashboard.detail("unknown")
        with self.assertRaises(ValueError):
            self.dashboard.query({"page": ["0"]})

    def test_shard_arithmetic_is_bounded_and_observation_not_verification(self):
        files = [{"name": n, "kind": "weight_candidate"} for n in ("model-00001-of-999999999.safetensors", "model-00000-of-999999999.safetensors", "model-00001-of-999999999999999999999999999.safetensors")]
        state = observations(files)
        self.assertEqual(state["shards_missing"], 999999998)
        self.assertEqual(state["configuration"], "unverified")
        complete = observations([{"name": f"model-{i:05}-of-00002.safetensors", "kind": "weight_candidate"} for i in (1, 2)])
        self.assertEqual(complete["shards_missing"], 0)
        self.assertEqual(complete["integrity"], "unverified")

    def test_empty_inventory_and_missing_sizes_are_explicit(self):
        self.assertEqual(self.dashboard.query({})["scans"], [])
        self.scan("s", files=[{"name": "<img onerror=alert(1)>.bin", "parents": ["p"]}])
        result = self.dashboard.query({"view": ["files"]})
        self.assertEqual(result["summary"]["unknown_sizes"], 1)
        self.assertIsNone(result["rows"][0]["size"])
        self.assertEqual(result["rows"][0]["name"], "<img onerror=alert(1)>.bin")

    def test_family_specific_names_precede_generic_family(self):
        self.assertEqual(family("Qwen-Image/model.safetensors"), "이미지 생성")
        self.assertEqual(family("Qwen3-TTS/model.safetensors"), "음성 합성")
        self.assertEqual(family("Qwen-ASR/model.safetensors"), "음성 인식")
        self.assertEqual(family("Qwen3/model.safetensors"), "언어 모델")
        self.assertEqual(family("unknown/model.safetensors"), "미분류")


if __name__ == "__main__":
    unittest.main()
