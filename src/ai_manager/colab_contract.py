"""Bounded, stdlib-only contracts for manually transferred Colab reports."""

from datetime import datetime, timezone
import hashlib
import json
import math
import re
import uuid


REQUEST_MAX_BYTES = 16384
RESULT_MAX_BYTES = 65536
INPUT_MAX_BYTES = 2048
MAX_NESTING = 16
SCHEMA_VERSION = 1
GUARD_SHA256 = "218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b"
MODEL = {"model_id": "llama-3.1-8b-instruct",
         "revision": "0e9e39f249a16976918f6564b8830bc894c89659",
         "manifest_sha256": "a8fcf721121d9704daea0b45189868cdc479b18e6755df07d984e8637007318d"}
RUNTIME = {"python": "3.12.13", "torch": "2.11.0+cu128", "numpy": "2.0.2",
           "transformers": "4.57.3", "accelerate": "1.12.0", "safetensors": "0.8.0",
           "bitsandbytes": "0.50.2"}
LIMITS = {"max_input_tokens": 64, "max_new_tokens": 32, "seed": 0,
          "do_sample": False, "batch_size": 1}
PROFILE_ID = "llama-colab-int8-handoff-v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_UUID = re.compile(r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}\Z")
_REQUEST_KEYS = "schema_version request_id created_at input model execution request_sha256".split()
_RESULT_KEYS = "schema_version request_id request_sha256 input_sha256 model execution status result_sha256".split()


class ColabContractError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(condition, code="invalid_document"):
    if not condition:
        raise ColabContractError(code)


def _keys(value, keys):
    _require(type(value) is dict and set(value) == set(keys))


def _tree(value, depth=0):
    _require(depth <= MAX_NESTING, "nesting_limit")
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str)
            _tree(key, depth + 1)
            _tree(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _tree(item, depth + 1)
    elif type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ColabContractError("invalid_unicode") from None
    elif type(value) is float:
        _require(math.isfinite(value), "nonfinite_number")
    else:
        _require(value is None or type(value) in (int, bool))


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate_key")
        value[key] = item
    return value


def _constant(_value):
    raise ColabContractError("nonfinite_number")


def parse_document(raw: bytes, kind: str) -> dict:
    _require(kind in ("request", "result"), "invalid_kind")
    _require(type(raw) is bytes, "invalid_json")
    _require(len(raw) <= (REQUEST_MAX_BYTES if kind == "request" else RESULT_MAX_BYTES), "document_too_large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ColabContractError):
            raise
        raise ColabContractError("invalid_json") from None
    _require(type(value) is dict, "invalid_document")
    _tree(value)
    return value


def canonical_bytes(value: dict, digest_field: str) -> bytes:
    _require(type(value) is dict and type(digest_field) is str)
    _tree(value)
    try:
        return json.dumps({key: item for key, item in value.items() if key != digest_field},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ColabContractError("invalid_document") from None


def document_digest(value: dict, digest_field: str) -> str:
    return hashlib.sha256(canonical_bytes(value, digest_field)).hexdigest()


def validate_input_text(text: str) -> dict:
    _require(type(text) is str, "invalid_input")
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError:
        raise ColabContractError("invalid_input") from None
    _require(bool(text.strip()) and "\x00" not in text and len(raw) <= INPUT_MAX_BYTES, "invalid_input")
    return {"text": text, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def validate_request_id(value: str) -> str:
    _require(type(value) is str and bool(_UUID.fullmatch(value)), "invalid_request_id")
    return value


def _pins(value):
    _keys(value, ("contract", "worker", "guard"))
    for item in value.values():
        _require(type(item) is str and bool(_HASH.fullmatch(item)), "invalid_source_pins")
    _require(value["guard"] == GUARD_SHA256, "invalid_source_pins")


def _exact(value, expected):
    # Python equality alone accepts True as 1 and 1.0 as 1.
    _require(type(value) is type(expected))
    if type(expected) is dict:
        _keys(value, expected)
        for key in expected:
            _exact(value[key], expected[key])
    else:
        _require(value == expected)


def _bounded_document(value, field, limit):
    encoded = canonical_bytes(value, "")
    _require(len(encoded) <= limit, "document_too_large")
    _require(type(value.get(field)) is str and bool(_HASH.fullmatch(value[field])), "invalid_digest")
    _require(value[field] == document_digest(value, field), "digest_mismatch")


def build_request(text: str, source_pins: dict) -> dict:
    _pins(source_pins)
    value = {"schema_version": SCHEMA_VERSION, "request_id": uuid.uuid4().hex,
             "created_at": datetime.now(timezone.utc).isoformat(),
             "input": validate_input_text(text), "model": dict(MODEL),
             "execution": {"profile_id": PROFILE_ID, "runtime": dict(RUNTIME),
                           "source_sha256": dict(source_pins), "limits": dict(LIMITS)}}
    value["request_sha256"] = document_digest(value, "request_sha256")
    return validate_request(value, source_pins)


def validate_request(value: dict, source_pins: dict) -> dict:
    _pins(source_pins)
    _keys(value, _REQUEST_KEYS)
    _bounded_document(value, "request_sha256", REQUEST_MAX_BYTES)
    _exact(value["schema_version"], SCHEMA_VERSION)
    validate_request_id(value["request_id"])
    created = value["created_at"]
    _require(type(created) is str and bool(re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", created)), "invalid_created_at")
    try:
        datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        raise ColabContractError("invalid_created_at") from None
    _keys(value["input"], ("text", "sha256", "bytes"))
    _exact(value["input"], validate_input_text(value["input"]["text"]))
    _exact(value["model"], MODEL)
    _exact(value["execution"], {"profile_id": PROFILE_ID, "runtime": RUNTIME,
                                "source_sha256": source_pins, "limits": LIMITS})
    return value


def _integer(value, minimum, maximum):
    _require(type(value) is int and minimum <= value <= maximum)


def _boolean(value):
    _require(type(value) is bool)


def validate_result(value: dict, request: dict) -> dict:
    _require(type(request) is dict and type(request.get("execution")) is dict)
    validate_request(request, request["execution"].get("source_sha256"))
    _require(type(value) is dict)
    status = value.get("status")
    _require(status in ("success", "stopped", "failure"))
    _keys(value, _RESULT_KEYS + (["response", "engine", "phase", "guard"] if status == "success"
                               else ["reason", "phase", "guard"]))
    _bounded_document(value, "result_sha256", RESULT_MAX_BYTES)
    for key, expected in {"schema_version": SCHEMA_VERSION, "request_id": request["request_id"],
                          "request_sha256": request["request_sha256"],
                          "input_sha256": request["input"]["sha256"],
                          "model": request["model"], "execution": request["execution"]}.items():
        _exact(value[key], expected)
    _keys(value["phase"], ("stage",))
    _require(value["phase"]["stage"] in ("preflight", "hashing", "loading", "generating", "done"))
    guard = value["guard"]
    _keys(guard, "status reason gate_opened worker_returncode final_worker_returncode remaining_owned_count cleanup_measurement_error".split())
    _require(guard["status"] in ("not_started", "completed", "stopped"))
    _require(guard["reason"] in ("not_started", "worker_exited", "guard_stopped", "worker_failed", "cleanup_failed"))
    _boolean(guard["gate_opened"])
    _boolean(guard["cleanup_measurement_error"])
    for key in ("worker_returncode", "final_worker_returncode"):
        if guard[key] is not None:
            _integer(guard[key], -(2 ** 31), 2 ** 32 - 1)
    _integer(guard["remaining_owned_count"], 0, 2 ** 31 - 1)
    if status != "success":
        reasons = ("approval_required", "environment_unavailable", "source_mismatch", "model_mismatch",
                   "input_token_limit", "guard_stopped", "already_started") if status == "stopped" else (
                       "worker_failed", "output_invalid", "cleanup_failed")
        _require(value["reason"] in reasons)
        return value
    response = value["response"]
    _keys(response, "text input_tokens generated_tokens eos_reached length_cap_reached".split())
    _require(type(response["text"]) is str and "\x00" not in response["text"])
    _integer(response["input_tokens"], 1, 64)
    _integer(response["generated_tokens"], 1, 32)
    _boolean(response["eos_reached"])
    _boolean(response["length_cap_reached"])
    _require(response["eos_reached"] != response["length_cap_reached"])
    _require(not response["length_cap_reached"] or response["generated_tokens"] == 32)
    _exact(value["engine"], {"generation_calls": 1, "quantized_linear_count": 224,
                              "gpu_parameter_tensor_count": 291, "cpu_offload": False,
                              "disk_offload": False, "model_sha_verified": True,
                              "runtime_verified": True})
    _exact(value["phase"], {"stage": "done"})
    _exact(guard, {"status": "completed", "reason": "worker_exited", "gate_opened": True,
                   "worker_returncode": 0, "final_worker_returncode": 0,
                   "remaining_owned_count": 0, "cleanup_measurement_error": False})
    return value
