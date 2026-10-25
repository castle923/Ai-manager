"""Home-bound sidecar storage; external reports never enter local validation DBs."""

import os
from pathlib import Path
import stat
import tempfile

from .colab_contract import (
    ColabContractError, REQUEST_MAX_BYTES, RESULT_MAX_BYTES, _pins,
    canonical_bytes, parse_document, validate_request, validate_request_id, validate_result,
)


class HandoffStore:
    def __init__(self, home: Path, source_pins: dict):
        _pins(source_pins)
        self.home = Path(os.path.abspath(home))
        self.root = self.home / "colab-handoff"
        self.source_pins = dict(source_pins)

    @staticmethod
    def _check(path):
        # Inspect, rather than resolve, every parent so junctions cannot hide.
        for item in (*reversed(path.parents), path):
            try:
                info = item.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ColabContractError("unsafe_storage_path")
            if item != path and not stat.S_ISDIR(info.st_mode):
                raise ColabContractError("unsafe_storage_path")

    def _path(self, request_id, kind):
        validate_request_id(request_id)
        return self.root / kind / (request_id + ".json")

    def _read(self, path, kind):
        try:
            self._check(path)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ColabContractError("unsafe_storage_path")
                limit = REQUEST_MAX_BYTES if kind == "request" else RESULT_MAX_BYTES
                raw = stream.read(limit + 1)
            self._check(path)
            return parse_document(raw, kind)
        except FileNotFoundError:
            raise ColabContractError(kind + "_not_found") from None
        except OSError:
            raise ColabContractError("storage_error") from None

    def _mkdir(self, directory):
        for item in (*reversed(directory.parents), directory):
            self._check(item)
            if item.is_dir():
                continue
            try:
                item.mkdir(mode=0o700)
            except FileExistsError:
                if not item.is_dir():
                    raise ColabContractError("unsafe_storage_path") from None
            self._check(item)

    def _publish(self, path, value):
        temporary = None
        try:
            self._check(path)
            self._mkdir(path.parent)
            descriptor, name = tempfile.mkstemp(prefix=".handoff-", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_bytes(value, ""))
                stream.flush()
                os.fsync(stream.fileno())
            self._check(path)
            try:
                os.link(temporary, path)  # Exclusive, complete publication on NTFS and POSIX.
            except FileExistsError:
                return False
            return True
        except OSError:
            raise ColabContractError("storage_error") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    raise ColabContractError("storage_error") from None

    def save_request(self, value: dict) -> dict:
        # Freeze the caller's object before validation/publication.
        validate_request(value, self.source_pins)
        value = parse_document(canonical_bytes(value, ""), "request")
        validate_request(value, self.source_pins)
        path = self._path(value["request_id"], "requests")
        if not self._publish(path, value):
            existing = self.get_request(value["request_id"])
            if existing["request_sha256"] != value["request_sha256"]:
                raise ColabContractError("request_conflict")
            return existing
        return value

    def get_request(self, request_id: str) -> dict:
        value = self._read(self._path(request_id, "requests"), "request")
        validate_request(value, self.source_pins)
        if value["request_id"] != request_id:
            raise ColabContractError("request_mismatch")
        return value

    def import_result(self, raw: bytes) -> dict:
        value = parse_document(raw, "result")
        request = self.get_request(value.get("request_id"))
        validate_result(value, request)
        path = self._path(value["request_id"], "results")
        if not self._publish(path, value):
            existing = self._read(path, "result")
            validate_result(existing, request)
            if existing["result_sha256"] != value["result_sha256"]:
                raise ColabContractError("result_conflict")
            return existing
        return value

    def detail(self, request_id: str) -> dict:
        request = self.get_request(request_id)
        try:
            result = self._read(self._path(request_id, "results"), "result")
        except ColabContractError as error:
            if error.code != "result_not_found":
                raise
            result = None
        if result is not None:
            validate_result(result, request)
        return {"request": request, "result": result}
