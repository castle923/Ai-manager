"""Metadata-only Google Drive v3 client; no content or write methods exist here."""
from __future__ import annotations

import random
import re
import time
from urllib.parse import quote

import requests

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
FIELDS = "id,name,mimeType,parents,size,modifiedTime,md5Checksum,sha1Checksum,sha256Checksum,version,driveId,trashed"


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
