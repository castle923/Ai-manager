import copy
import hashlib
import importlib
import json
import socket
import unittest
from unittest.mock import patch

try:
    from ai_manager import colab_contract as contract
except ImportError:
    contract = None


PINS = {"contract": "a" * 64, "worker": "b" * 64,
        "guard": "218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b"}


def signed(value, field):
    value = copy.deepcopy(value)
    value[field] = hashlib.sha256(json.dumps(
        {k: v for k, v in value.items() if k != field}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return value


def success(request, text="얼음입니다."):
    return signed({
        "schema_version": 1, "request_id": request["request_id"],
        "request_sha256": request["request_sha256"],
        "input_sha256": request["input"]["sha256"],
        "model": copy.deepcopy(request["model"]),
        "execution": copy.deepcopy(request["execution"]), "status": "success",
        "response": {"text": text, "input_tokens": 25, "generated_tokens": 8,
                     "eos_reached": True, "length_cap_reached": False},
        "engine": {"generation_calls": 1, "quantized_linear_count": 224,
                   "gpu_parameter_tensor_count": 291, "cpu_offload": False,
                   "disk_offload": False, "model_sha_verified": True,
                   "runtime_verified": True},
        "phase": {"stage": "done"},
        "guard": {"status": "completed", "reason": "worker_exited",
                  "gate_opened": True, "worker_returncode": 0,
                  "final_worker_returncode": 0, "remaining_owned_count": 0,
                  "cleanup_measurement_error": False},
    }, "result_sha256")


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(contract, "strict handoff contract is not implemented")
        self.request = contract.build_request("물은 얼면 무엇이 되나요?", PINS)

    def reject(self, fn, *args):
        with self.assertRaises(contract.ColabContractError) as caught:
            fn(*args)
        self.assertEqual(str(caught.exception), caught.exception.code)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_request_is_bound_and_preview_preserves_unicode(self):
        for text in ["한글 <script>alert(1)</script>", "e\u0301", "é", " x \n"]:
            value = contract.build_request(text, PINS)
            self.assertEqual(value["input"]["text"], text)
            self.assertEqual(value["input"]["bytes"], len(text.encode()))
            self.assertEqual(value["input"]["sha256"], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(contract.validate_request(value, PINS), value)
        self.assertNotEqual(contract.build_request("e\u0301", PINS)["input"]["sha256"],
                            contract.build_request("é", PINS)["input"]["sha256"])
        self.assertEqual(contract.validate_input_text("물"),
                         {"text": "물", "bytes": 3, "sha256": hashlib.sha256("물".encode()).hexdigest()})

    def test_canonical_omits_only_own_digest(self):
        value = {"z": "e\u0301", "a": {"request_sha256": "keep"}, "request_sha256": "omit"}
        expected = '{"a":{"request_sha256":"keep"},"z":"é"}'.encode()
        self.assertEqual(contract.canonical_bytes(value, "request_sha256"), expected)
        self.assertEqual(contract.document_digest(value, "request_sha256"), hashlib.sha256(expected).hexdigest())

    def test_strict_parser_rejects_duplicate_nonfinite_surrogate_and_depth(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                    b'{"a":1e999}', b'{"a":"\\ud800"}', b'{"a":"\xff"}',
                    b'[' * 40 + b'0' + b']' * 40, b'[]', b'{} {}']:
            with self.subTest(raw=raw[:35]):
                self.reject(contract.parse_document, raw, "request")
        for kind, limit in [("request", 16384), ("result", 65536)]:
            self.assertEqual(contract.parse_document(b'{}' + b' ' * (limit - 2), kind), {})
            self.reject(contract.parse_document, b'{}' + b' ' * (limit - 1), kind)
        self.reject(contract.parse_document, b'{}', "other")

    def test_input_limits_and_required_source_pins(self):
        for text in ["", " \n\t", "a\x00b", "\ud800", "한" * 683, None]:
            self.reject(contract.build_request, text, PINS)
        self.assertEqual(contract.build_request("a" * 2048, PINS)["input"]["bytes"], 2048)
        for pins in [{}, {**PINS, "guard": "c" * 64}, {**PINS, "token": "SECRET"}]:
            self.reject(contract.build_request, "valid", pins)

    def test_request_rejects_tampering_unknown_keys_bool_and_bad_identity(self):
        changes = [((), "auth", "SECRET"), (("input",), "text", "changed"),
                   (("input",), "bytes", True), (("execution", "limits"), "seed", False),
                   (("execution", "runtime"), "torch", "wrong"),
                   ((), "request_id", "../SECRET"), ((), "request_id", "0" * 32),
                   ((), "created_at", "2026-10-25T01:00:00"),
                   ((), "created_at", "2026-10-25T01:00:00+09:00"),
                   ((), "schema_version", True)]
        for path, key, replacement in changes:
            value = copy.deepcopy(self.request)
            target = value
            for part in path:
                target = target[part]
            target[key] = replacement
            value = signed(value, "request_sha256")
            with self.subTest(path=path, key=key):
                self.reject(contract.validate_request, value, PINS)
        value = copy.deepcopy(self.request)
        value["input"]["text"] += "x"
        self.reject(contract.validate_request, value, PINS)

    def test_success_and_length_cap_require_all_evidence(self):
        value = success(self.request, "e\u0301 <b>한국어</b>")
        self.assertEqual(contract.validate_result(value, self.request), value)
        value["response"].update(generated_tokens=32, eos_reached=False, length_cap_reached=True)
        self.assertEqual(contract.validate_result(signed(value, "result_sha256"), self.request)["response"]["generated_tokens"], 32)
        mutations = [("engine", "generation_calls", 2), ("engine", "quantized_linear_count", 223),
                     ("engine", "gpu_parameter_tensor_count", 290), ("engine", "cpu_offload", True),
                     ("engine", "disk_offload", True), ("engine", "model_sha_verified", False),
                     ("engine", "runtime_verified", False), ("response", "input_tokens", 65),
                     ("response", "input_tokens", True), ("response", "generated_tokens", 0),
                     ("response", "generated_tokens", 33), ("response", "eos_reached", False),
                     ("response", "length_cap_reached", True), ("guard", "status", "stopped"),
                     ("guard", "worker_returncode", None), ("guard", "final_worker_returncode", 1),
                     ("guard", "remaining_owned_count", 1), ("guard", "gate_opened", False),
                     ("guard", "cleanup_measurement_error", True), ("phase", "stage", "loading")]
        for group, key, replacement in mutations:
            altered = success(self.request)
            altered[group][key] = replacement
            with self.subTest(group=group, key=key):
                self.reject(contract.validate_result, signed(altered, "result_sha256"), self.request)
        value["response"]["generated_tokens"] = 31
        self.reject(contract.validate_result, signed(value, "result_sha256"), self.request)

    def test_binding_and_failure_schemas_do_not_promote_stop(self):
        value = success(self.request)
        for key in ["request_id", "request_sha256", "input_sha256"]:
            altered = copy.deepcopy(value)
            altered[key] = "0" * len(altered[key])
            self.reject(contract.validate_result, signed(altered, "result_sha256"), self.request)
        value["response"]["text"] += "x"
        self.reject(contract.validate_result, value, self.request)
        for status, reason in [("stopped", "approval_required"), ("failure", "worker_failed")]:
            value = success(self.request)
            del value["response"], value["engine"]
            value.update(status=status, reason=reason, phase={"stage": "preflight"})
            value["guard"].update(status="not_started", reason="not_started", gate_opened=False,
                                  worker_returncode=None, final_worker_returncode=None)
            value = signed(value, "result_sha256")
            self.assertEqual(contract.validate_result(value, self.request)["status"], status)
            value["response"] = {"text": "SECRET"}
            self.reject(contract.validate_result, signed(value, "result_sha256"), self.request)

    def test_contract_import_and_use_do_not_import_runtime_or_network(self):
        original_import = __import__
        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0] in {"torch", "transformers", "numpy", "bitsandbytes", "requests"}:
                raise AssertionError("runtime import forbidden")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=guarded_import), patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            spec = importlib.util.spec_from_file_location("isolated_colab_contract", contract.__file__)
            isolated = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(isolated)
            self.assertEqual(isolated.validate_request(isolated.build_request("합성", PINS), PINS)["input"]["text"], "합성")


if __name__ == "__main__":
    unittest.main()
