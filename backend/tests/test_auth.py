"""Tests for the single-admin password gate."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from kwabo.api.auth import _sign, _verify, issue_token
from kwabo.config import settings
from kwabo.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_token_round_trip_signs_and_verifies():
    payload = {"sub": "admin", "exp": int(time.time()) + 600}
    token = _sign(payload, "test-secret")
    decoded = _verify(token, "test-secret")
    assert decoded == payload


def test_token_rejects_tamper():
    payload = {"sub": "admin", "exp": int(time.time()) + 600}
    token = _sign(payload, "test-secret")
    # flip a single byte in the body portion
    body, sig = token.split(".")
    tampered = (body[:-1] + ("A" if body[-1] != "A" else "B")) + "." + sig
    assert _verify(tampered, "test-secret") is None


def test_token_rejects_expiry():
    payload = {"sub": "admin", "exp": int(time.time()) - 1}
    token = _sign(payload, "test-secret")
    assert _verify(token, "test-secret") is None


def test_token_rejects_wrong_secret():
    payload = {"sub": "admin", "exp": int(time.time()) + 600}
    token = _sign(payload, "secret-a")
    assert _verify(token, "secret-b") is None


def test_login_no_password_set_treats_as_dev_open(client, monkeypatch):
    """When ADMIN_PASSWORD is empty (default for tests/dev), login returns
    ok=True with a placeholder token and the dependency lets the request
    through. This is the documented dev escape hatch."""
    monkeypatch.setattr(settings, "admin_password", "")
    r = client.post("/api/auth/login", json={"password": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_login_rejects_wrong_password(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "correct-horse-battery-staple")
    r = client.post("/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_login_with_correct_password_returns_bearer_token(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "correct-horse-battery-staple")
    r = client.post(
        "/api/auth/login", json={"password": "correct-horse-battery-staple"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["token"]
    assert body["expires_at"] > time.time()


def test_protected_route_rejects_anonymous_when_password_is_set(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "admin_password", "x-y-z")
    r = client.get("/api/orders")
    assert r.status_code == 401


def test_protected_route_accepts_bearer(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "x-y-z")
    monkeypatch.setattr(settings, "jwt_secret", "secret")
    token = issue_token()
    r = client.get(
        "/api/orders", headers={"Authorization": f"Bearer {token}"}
    )
    # /api/orders may legitimately return [] (200) for an empty DB; we only
    # care it didn't 401.
    assert r.status_code != 401


def test_health_is_unauthenticated(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "x-y-z")
    r = client.get("/api/health")
    assert r.status_code == 200
    # Health is reachable without auth and reports ok. It now also carries a
    # `poller` liveness field (see test_main_poll_guard) — assert the stable
    # contract rather than an exact-dict match.
    assert r.json()["status"] == "ok"


def test_login_endpoint_is_unauthenticated(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "x-y-z")
    # POST /api/auth/login itself must not require auth, otherwise nobody
    # could ever log in.
    r = client.post("/api/auth/login", json={"password": "x-y-z"})
    assert r.status_code == 200
