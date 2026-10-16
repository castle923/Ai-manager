import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_manager.auth import AUTH_URL, SCOPE, TOKEN_URL, AuthError, AuthManager, callback_result, client_config, verify_identity, verify_scope
from ai_manager.config import SettingsStore, validate
from ai_manager.security import SecretStore


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


class Session:
    def __init__(self, posts=(), gets=()):
        self.posts, self.gets = list(posts), list(gets)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.posts.pop(0)

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.gets.pop(0)


class MemoryStore:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = dict(value)

    def delete(self, key):
        self.values.pop(key, None)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "client.json"
        self.path.write_text(json.dumps({"installed": {"client_id": "synthetic.apps.googleusercontent.com", "client_secret": "synthetic-client", "auth_uri": AUTH_URL, "token_uri": TOKEN_URL}}))
        self.settings = {"client_path": str(self.path), "accounts": {"A": "alpha@example.invalid", "B": "beta@example.invalid"}}

    def test_state_path_duplicates_and_denial(self):
        self.assertEqual(callback_result("/oauth/callback?code=x&state=s", "s"), "x")
        for path in ("/wrong?code=x&state=s", "/oauth/callback?code=x&state=bad", "/oauth/callback?code=x&state=s&state=s", "/oauth/callback?code=x&code=y&state=s", "/oauth/callback?error=access_denied&state=s"):
            with self.subTest(path=path), self.assertRaises(AuthError):
                callback_result(path, "s")

    def test_scope_exact_and_no_url_token(self):
        session = Session(posts=[Response({"scope": SCOPE})])
        self.assertEqual(verify_scope({"access_token": "synthetic-access"}, session), [SCOPE])
        self.assertNotIn("synthetic-access", session.calls[0][0])
        for scopes in ("", SCOPE + " https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/drive"):
            with self.assertRaises(AuthError):
                verify_scope({"access_token": "synthetic-access"}, Session(posts=[Response({"scope": scopes})]))

    def test_identity_binding(self):
        for actual in ("beta@example.invalid", "", None):
            with self.assertRaises(AuthError):
                verify_identity("synthetic", "alpha@example.invalid", Session(gets=[Response({"user": {"emailAddress": actual}})]))

    def test_refresh_isolated_accounts_and_actual_identity(self):
        store = MemoryStore()
        store.put("A", dict(access_token="old-A", refresh_token="refresh-A", expires_at=0, verified_scopes=[SCOPE], account="alpha@example.invalid"))
        store.put("B", dict(access_token="old-B"))
        session = Session(posts=[Response({"access_token": "new-A", "expires_in": 3600}), Response({"scope": SCOPE})], gets=[Response({"user": {"emailAddress": "alpha@example.invalid"}})])
        manager = AuthManager(self.settings, store, session)
        self.assertEqual(manager.access("A", force_refresh=True), "new-A")
        self.assertEqual(store.get("B"), {"access_token": "old-B"})
        self.assertEqual(session.calls[0][1]["data"]["refresh_token"], "refresh-A")

    def test_refresh_failure_not_success_or_plaintext_exception(self):
        store = MemoryStore()
        store.put("A", dict(access_token="old", refresh_token="secret", expires_at=0, verified_scopes=[SCOPE], account="alpha@example.invalid"))
        with self.assertRaisesRegex(AuthError, "refresh_failed_reconnect_required"):
            AuthManager(self.settings, store, Session(posts=[Response({"secret": "never print"}, 400)])).access("A", True)

    def test_disconnect_preserves_credential_if_remote_revoke_fails(self):
        store = MemoryStore()
        store.put("A", {"refresh_token": "synthetic"})
        with self.assertRaises(AuthError):
            AuthManager(self.settings, store, Session(posts=[Response({}, 503)])).disconnect("A")
        self.assertIsNotNone(store.get("A"))
        AuthManager(self.settings, store, Session(posts=[Response({})])).disconnect("A")
        self.assertIsNone(store.get("A"))

    def test_cancel_without_exchanging_code(self):
        event = threading.Event()
        event.set()
        session = Session()
        with self.assertRaisesRegex(AuthError, "authentication_cancelled"):
            AuthManager(self.settings, MemoryStore(), session).connect("A", cancel=event, browser=lambda url: True)
        self.assertEqual(session.calls, [])

    def test_browser_failure_and_config_endpoint_rejection(self):
        with self.assertRaisesRegex(AuthError, "system_browser_failed"):
            AuthManager(self.settings, MemoryStore()).connect("A", browser=lambda url: False)
        self.path.write_text(json.dumps({"installed": {"client_id": "a.apps.googleusercontent.com", "client_secret": "x", "auth_uri": "https://evil.invalid/auth", "token_uri": TOKEN_URL}}))
        with self.assertRaisesRegex(AuthError, "untrusted_oauth_endpoint"):
            client_config(self.path)

    def test_dpapi_roundtrip_account_separation_and_no_plaintext(self):
        store = SecretStore(Path(self.temp.name) / "credentials")
        store.put("A", {"access_token": "synthetic-marker-secret"})
        store.put("B", {"access_token": "other-synthetic"})
        self.assertEqual(store.get("A")["access_token"], "synthetic-marker-secret")
        self.assertNotIn(b"synthetic-marker-secret", store._path("A").read_bytes())
        with self.assertRaises(ValueError):
            store.get("../A")
        store.delete("A")
        self.assertIsNone(store.get("A"))
        self.assertIsNotNone(store.get("B"))

    def test_account_lock_blocks_same_account_and_allows_other(self):
        store = SecretStore(Path(self.temp.name) / "credentials")
        with store.lock("A"):
            with self.assertRaisesRegex(RuntimeError, "account_operation_busy"):
                with store.lock("A"):
                    pass
            with store.lock("B"):
                pass
        with store.lock("A"):
            pass


class ConfigTests(unittest.TestCase):
    def test_reject_duplicates_and_unknown_account(self):
        config = {"accounts": {"A": "a@example.invalid", "B": "b@example.invalid"}, "allowlist": [{"account": "A", "id": "synthetic-root"}]}
        validate(config)
        for roots in ([{"account": "C", "id": "synthetic-root"}], [{"account": "A", "id": "../escape"}], config["allowlist"] * 2, []):
            with self.assertRaises(ValueError):
                validate(dict(config, allowlist=roots))

    def test_initialize_provenance_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source, client = base / "source.json", base / "client.json"
            source.write_text(json.dumps({"accounts": {"A": "a@example.invalid", "B": "b@example.invalid"}, "roots": [{"account": "A", "id": "synthetic-root"}]}))
            client.write_text("{}")
            store = SettingsStore(base / "state")
            config = store.initialize(source, client)
            self.assertEqual(len(config["sources"][0]["sha256"]), 64)
            with self.assertRaises(ValueError):
                store.initialize(source, client)
            self.assertEqual(store.load(), config)


if __name__ == "__main__":
    unittest.main()
