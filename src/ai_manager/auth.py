"""Desktop OAuth, fresh PKCE/state and current-user protected credentials."""
import base64
import hashlib
import hmac
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from functools import wraps
from contextlib import nullcontext

import requests

SCOPE = "https://www.googleapis.com/auth/drive.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class AuthError(Exception):
    """Messages are controlled codes and never response bodies or token values."""


def serialized_account(operation):
    @wraps(operation)
    def call(self, account, *args, **kwargs):
        self._account(account)
        try:
            with (self.store.lock(account) if hasattr(self.store, "lock") else nullcontext()):
                return operation(self, account, *args, **kwargs)
        except RuntimeError as error:
            if str(error) == "account_operation_busy":
                raise AuthError("account_operation_busy") from None
            raise
    return call


def client_config(path):
    from pathlib import Path
    parsed = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    value = parsed.get("installed", {})
    if not value.get("client_id", "").endswith(".apps.googleusercontent.com") or not value.get("client_secret"):
        raise AuthError("desktop_client_required")
    if value.get("auth_uri") not in (AUTH_URL, "https://accounts.google.com/o/oauth2/auth") or value.get("token_uri") != TOKEN_URL:
        raise AuthError("untrusted_oauth_endpoint")
    return value


def checked_json(response, error):
    if response.status_code != 200:
        raise AuthError(error)
    try:
        return response.json()
    except ValueError:
        raise AuthError("invalid_server_response") from None


def verify_scope(token, session):
    # POST avoids putting credentials into URL and proxy access logs.
    info = checked_json(session.post("https://oauth2.googleapis.com/tokeninfo", data={"access_token": token["access_token"]}, timeout=30, allow_redirects=False), "scope_check_failed")
    scopes = set(info.get("scope", "").split())
    if scopes != {SCOPE}:
        raise AuthError("unexpected_granted_scope")
    return sorted(scopes)


def verify_identity(access, expected, session):
    result = checked_json(session.get("https://www.googleapis.com/drive/v3/about", params={"fields": "user(emailAddress)"}, headers={"Authorization": "Bearer " + access}, timeout=30, allow_redirects=False), "identity_check_failed")
    if not hmac.compare_digest(str(result.get("user", {}).get("emailAddress", "")).casefold(), expected.casefold()):
        raise AuthError("account_mismatch")


def callback_result(path, expected_state):
    url = urlsplit(path)
    if url.path != "/oauth/callback":
        raise AuthError("invalid_callback_path")
    values = parse_qs(url.query, keep_blank_values=True)
    if len(values.get("state", [])) != 1 or not hmac.compare_digest(values["state"][0], expected_state):
        raise AuthError("invalid_state")
    if "error" in values:
        raise AuthError("consent_denied")
    if len(values.get("code", [])) != 1 or not values["code"][0]:
        raise AuthError("missing_authorization_code")
    return values["code"][0]


class AuthManager:
    def __init__(self, settings, store, session=None):
        self.settings, self.store = settings, store
        self.session = session or requests.Session()
        self.client = client_config(settings["client_path"])

    def _account(self, account):
        if account not in self.settings["accounts"]:
            raise AuthError("invalid_account")
        return self.settings["accounts"][account]

    @serialized_account
    def connect(self, account, cancel=None, timeout=300, browser=webbrowser.open):
        expected = self._account(account)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        outcome = {}

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                    self.send_error(400)
                    return
                try:
                    outcome["code"] = callback_result(self.path, state)
                except AuthError as error:
                    # A stray invalid request must not abort a pending valid login.
                    if str(error) == "consent_denied":
                        outcome["error"] = error
                    self.send_response(400)
                else:
                    self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                self.wfile.write("인증 응답을 받았습니다. Ai-manager로 돌아가세요.".encode())

        with HTTPServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = .25
            redirect = f"http://127.0.0.1:{server.server_port}/oauth/callback"
            url = AUTH_URL + "?" + urlencode(dict(client_id=self.client["client_id"], redirect_uri=redirect, response_type="code", scope=SCOPE,
                                                   state=state, code_challenge=challenge, code_challenge_method="S256", access_type="offline",
                                                   prompt="consent select_account", login_hint=expected))
            if not browser(url):
                raise AuthError("system_browser_failed")
            deadline = time.monotonic() + timeout
            while not outcome:
                if cancel and cancel.is_set():
                    raise AuthError("authentication_cancelled")
                if time.monotonic() > deadline:
                    raise AuthError("authentication_timeout")
                server.handle_request()
        if "error" in outcome:
            raise outcome["error"]
        token = checked_json(self.session.post(TOKEN_URL, data=dict(client_id=self.client["client_id"], client_secret=self.client["client_secret"],
                             code=outcome["code"], code_verifier=verifier, redirect_uri=redirect, grant_type="authorization_code"), timeout=30, allow_redirects=False), "code_exchange_failed")
        try:
            scopes = verify_scope(token, self.session)
            verify_identity(token["access_token"], expected, self.session)
            if not token.get("refresh_token"):
                raise AuthError("refresh_token_required")
        except (AuthError, KeyError):
            self._revoke_value(token.get("refresh_token") or token.get("access_token"))
            raise
        token.update(expires_at=time.time() + int(token.get("expires_in", 3600)), verified_scopes=scopes, account=expected)
        self.store.put(account, token)
        return {"account": account, "status": "connected", "scopes": scopes}

    @serialized_account
    def access(self, account, force_refresh=False):
        expected = self._account(account)
        token = self.store.get(account)
        if not token:
            raise AuthError("not_connected")
        if token.get("account", "").casefold() != expected.casefold() or token.get("verified_scopes") != [SCOPE]:
            raise AuthError("stored_binding_invalid")
        if force_refresh or token.get("expires_at", 0) < time.time() + 60:
            refreshed = checked_json(self.session.post(TOKEN_URL, data=dict(client_id=self.client["client_id"], client_secret=self.client["client_secret"], refresh_token=token["refresh_token"], grant_type="refresh_token"), timeout=30, allow_redirects=False), "refresh_failed_reconnect_required")
            token.update(refreshed)
            token["verified_scopes"] = verify_scope(token, self.session)
            verify_identity(token["access_token"], expected, self.session)
            token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
            self.store.put(account, token)
        return token["access_token"]

    def _revoke_value(self, value):
        if value:
            response = self.session.post("https://oauth2.googleapis.com/revoke", data={"token": value}, timeout=30, allow_redirects=False)
            if response.status_code != 200:
                raise AuthError("revoke_failed_local_credential_retained")

    @serialized_account
    def disconnect(self, account):
        self._account(account)
        token = self.store.get(account)
        if token:
            self._revoke_value(token.get("refresh_token") or token["access_token"])
            self.store.delete(account)
        return {"account": account, "status": "disconnected"}
