"""Read-only Drive metadata and selected model byte downloads; no write methods."""
from __future__ import annotations

import random
import re
import time
from urllib.parse import quote

import requests

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
FIELDS = "id,name,mimeType,parents,size,modifiedTime,md5Checksum,sha1Checksum,sha256Checksum,version,driveId,trashed"
RANGE_BYTES = 1024 * 1024
RANGE_WORKERS = 8


class DriveError(Exception):
    """A deliberately sanitized error, safe for status output."""


class Cancelled(DriveError):
    pass


def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value))


class Drive:
    def __init__(self, access, session=None, cancel=None, sleep=time.sleep):
        self.access = access
        self.session = session or requests.Session()
        self.cancel = cancel
        self.sleep = sleep

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled("cancelled")

    def get(self, suffix, params):
        force_refresh = False
        refreshed = False
        for attempt in range(5):
            self.check_cancel()
            try:
                token = (self.access(force_refresh=True) if force_refresh else self.access()) if callable(self.access) else self.access
            except Exception:
                raise DriveError("authentication_refresh_failed") from None
            if not isinstance(token, str) or not token:
                raise DriveError("authentication_required")
            try:
                response = self.session.get(
                    "https://www.googleapis.com/drive/v3/files" + suffix,
                    params=params, headers={"Authorization": "Bearer " + token},
                    timeout=(10, 45), allow_redirects=False,
                )
            except requests.RequestException:
                if attempt == 4:
                    raise DriveError("network_retry_exhausted") from None
                self._wait(attempt)
                continue
            self.check_cancel()
            status = response.status_code
            if status == 401 and callable(self.access) and not refreshed and attempt < 4:
                refreshed = True
                force_refresh = True
                continue
            force_refresh = False
            retry = status == 429 or 500 <= status <= 599
            if status == 403:
                try:
                    reasons = {e.get("reason") for e in response.json().get("error", {}).get("errors", [])}
                    retry = bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded"})
                except (ValueError, TypeError, AttributeError):
                    pass
            if retry:
                if attempt == 4:
                    raise DriveError("http_retry_exhausted_" + str(status))
                self._wait(attempt)
                continue
            if status != 200:
                raise DriveError("http_" + str(status))
            try:
                payload = response.json()
            except ValueError:
                raise DriveError("invalid_json") from None
            if not isinstance(payload, dict):
                raise DriveError("invalid_response")
            return payload
        raise DriveError("retry_exhausted")

    def _wait(self, attempt):
        delay = min(16, 2 ** attempt) + random.random()
        if self.cancel is not None:
            if self.cancel.wait(delay):
                raise Cancelled("cancelled")
        else:
            self.sleep(delay)

    def metadata(self, file_id):
        if not valid_id(file_id):
            raise DriveError("invalid_file_id")
        return self.get("/" + quote(file_id, safe=""), {"fields": FIELDS, "supportsAllDrives": "false"})

    def children(self, folder_id, page_token=None):
        if not valid_id(folder_id):
            raise DriveError("invalid_folder_id")
        params = {"q": "'" + folder_id + "' in parents and trashed = false", "fields": "nextPageToken,incompleteSearch,files(" + FIELDS + ")",
                  "pageSize": 1000, "spaces": "drive", "corpora": "user",
                  "includeItemsFromAllDrives": "false", "supportsAllDrives": "false"}
        if page_token is not None:
            params["pageToken"] = page_token
        return self.get("", params)

    def content(self, file_id, size=None):
        """Stream original bytes without following bearer-bearing redirects."""
        if not valid_id(file_id):
            raise DriveError("invalid_file_id")
        if size is not None and size >= 8 * 1024 * 1024:
            yield from self._parallel_content(file_id, size)
            return
        self.check_cancel()
        try:
            token = self.access() if callable(self.access) else self.access
            response = self.session.get(
                "https://www.googleapis.com/drive/v3/files/" + quote(file_id, safe=""),
                params={"alt": "media", "supportsAllDrives": "false"},
                headers={"Authorization": "Bearer " + token},
                timeout=(10, 45), allow_redirects=False, stream=True,
            )
            with response:
                if response.status_code != 200:
                    raise DriveError("download_http_" + str(response.status_code))
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    self.check_cancel()
                    if chunk:
                        yield chunk
        except requests.RequestException:
            raise DriveError("download_network_interrupted") from None

    def _parallel_content(self, file_id, size):
        """Bounded range reads in file order; caller verifies full official hash."""
        from concurrent.futures import ThreadPoolExecutor
        import threading
        chunk_size = RANGE_BYTES
        token_lock = threading.Lock()
        try:
            first_token = self.access() if callable(self.access) else self.access
        except Exception:
            raise DriveError("authentication_refresh_failed") from None
        if not isinstance(first_token, str) or not first_token:
            raise DriveError("authentication_required")
        token_state = {"value": first_token, "generation": 0}

        def fetch(start):
            for attempt in range(5):
                try:
                    return fetch_once(start)
                except DriveError as error:
                    if str(error) == "download_auth_retry" and attempt < 4:
                        continue
                    if str(error) != "download_retryable" or attempt == 4:
                        raise
                    self._wait(attempt)

        def fetch_once(start):
            started = time.monotonic()
            self.check_cancel()
            end = min(size - 1, start + chunk_size - 1)
            with token_lock:
                token = token_state["value"]
                generation = token_state["generation"]
            try:
                with self.session.get(
                    "https://www.googleapis.com/drive/v3/files/" + quote(file_id, safe=""),
                    params={"alt": "media", "supportsAllDrives": "false"},
                    headers={"Authorization": "Bearer " + token, "Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
                    timeout=(10, 45), allow_redirects=False, stream=True,
                ) as response:
                    if response.status_code == 401 and callable(self.access):
                        with token_lock:
                            if generation == token_state["generation"]:
                                try:
                                    refreshed_token = self.access(force_refresh=True)
                                except Exception:
                                    raise DriveError("authentication_refresh_failed") from None
                                if not isinstance(refreshed_token, str) or not refreshed_token:
                                    raise DriveError("authentication_required")
                                token_state["value"] = refreshed_token
                                token_state["generation"] += 1
                        raise DriveError("download_auth_retry")
                    if response.status_code == 429 or 500 <= response.status_code <= 599:
                        raise DriveError("download_retryable")
                    if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise DriveError("download_invalid_range")
                    data = bytearray()
                    for block in response.iter_content(256 * 1024):
                        self.check_cancel()
                        if time.monotonic() - started > 120:
                            raise DriveError("download_range_timeout")
                        data.extend(block)
                        if len(data) > end - start + 1:
                            raise DriveError("download_invalid_range")
                    if len(data) != end - start + 1:
                        raise DriveError("download_invalid_range")
                    return bytes(data)
            except requests.RequestException:
                raise DriveError("download_network_interrupted") from None

        starts = iter(range(0, size, chunk_size))
        with ThreadPoolExecutor(max_workers=RANGE_WORKERS) as pool:
            pending = []
            for _ in range(RANGE_WORKERS):
                start = next(starts, None)
                if start is not None:
                    pending.append(pool.submit(fetch, start))
            while pending:
                self.check_cancel()
                yield pending.pop(0).result()
                start = next(starts, None)
                if start is not None:
                    pending.append(pool.submit(fetch, start))
