"""Tests for the signed-URL attachment download flow."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from kwabo.api.orders import (
    _sign_attachment_token,
    _verify_attachment_token,
)
from kwabo.config import settings
from kwabo.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_token_round_trip_accepts_matching_triple():
    token, exp = _sign_attachment_token(42, "factuur.pdf", "inline", 60)
    assert exp > time.time()
    assert _verify_attachment_token(token, 42, "factuur.pdf", "inline") is True


def test_token_rejects_wrong_order_id():
    token, _ = _sign_attachment_token(42, "factuur.pdf", "inline", 60)
    assert _verify_attachment_token(token, 43, "factuur.pdf", "inline") is False


def test_token_rejects_wrong_filename():
    token, _ = _sign_attachment_token(42, "factuur.pdf", "inline", 60)
    assert _verify_attachment_token(token, 42, "evil.pdf", "inline") is False


def test_token_rejects_wrong_disposition():
    token, _ = _sign_attachment_token(42, "factuur.pdf", "inline", 60)
    assert _verify_attachment_token(token, 42, "factuur.pdf", "attachment") is False


def test_token_rejects_expired():
    token, _ = _sign_attachment_token(42, "factuur.pdf", "inline", -1)
    assert _verify_attachment_token(token, 42, "factuur.pdf", "inline") is False


def test_token_rejects_tamper():
    token, _ = _sign_attachment_token(42, "factuur.pdf", "inline", 60)
    body, sig = token.split(".")
    flipped_char = "A" if body[-1] != "A" else "B"
    tampered = body[:-1] + flipped_char + "." + sig
    assert _verify_attachment_token(tampered, 42, "factuur.pdf", "inline") is False


def test_bijlagen_get_rejects_missing_token(client):
    r = client.get("/api/orders/1/bijlagen", params={"naam": "x.pdf"})
    # FastAPI validation returns 422 when a required query param is missing.
    assert r.status_code == 422


def test_bijlagen_get_rejects_invalid_token(client):
    r = client.get(
        "/api/orders/1/bijlagen",
        params={"naam": "x.pdf", "token": "garbage.garbage"},
    )
    assert r.status_code == 401
    assert "verlopen" in r.json()["detail"].lower() or "ongeldig" in r.json()["detail"].lower()


def test_bijlagen_get_with_valid_token_passes_auth_then_404s_on_missing_order(client):
    """Valid token unlocks the auth gate; downstream code then 404s because
    order 99999 does not exist in the test DB."""
    token, _ = _sign_attachment_token(99999, "x.pdf", "inline", 60)
    r = client.get(
        "/api/orders/99999/bijlagen",
        params={"naam": "x.pdf", "token": token},
    )
    assert r.status_code == 404


def test_mint_token_endpoint_returns_valid_token(client):
    r = client.post(
        "/api/orders/7/bijlagen-token",
        json={"naam": "rapport.pdf", "disposition": "attachment"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["expires_at"] > time.time()
    assert _verify_attachment_token(
        body["token"], 7, "rapport.pdf", "attachment"
    ) is True


def test_mint_token_endpoint_rejects_invalid_disposition(client):
    r = client.post(
        "/api/orders/7/bijlagen-token",
        json={"naam": "x.pdf", "disposition": "rogue"},
    )
    assert r.status_code == 400


def _build_eml_with_pdf(naam: str, pdf_bytes: bytes) -> bytes:
    import email.message

    m = email.message.EmailMessage()
    m["From"] = "a@b.nl"
    m["To"] = "c@d.nl"
    m["Subject"] = "Order"
    m.set_content("body")
    m.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=naam)
    return m.as_bytes()


def test_bijlagen_self_heals_via_graph_refetch(client, monkeypatch):
    """When the persisted .eml is gone/stale (e.g. the old storage-key
    collision), a Graph mail's attachment is recovered by re-fetching the
    original MIME from the mailbox by message-id. Regression for 'po17830.pdf
    niet gevonden' on pre-fix orders."""
    import json

    from sqlmodel import Session

    from kwabo.db import session as db_session
    from kwabo.db.repository import OrderLogRepo
    from kwabo.integrations import email_client_graph

    pdf = b"%PDF-1.4 fake-bytes"
    naam = "po17830.pdf"
    with Session(db_session.engine) as s:
        row = OrderLogRepo(s).create(
            email_id="graph-msg-xyz", email_from="x@y.nl",
            email_subject="Bestelnummer 17830", status="review",
        )
        # No storage key / source_path → _resolve_eml_bytes returns None, so the
        # download must fall back to the Graph re-fetch.
        row.order_state = json.dumps({"bijlagen": [{"naam": naam, "type": "pdf"}]})
        s.add(row)
        s.commit()
        oid = row.id

    monkeypatch.setattr(settings, "email_mode", "graph")
    eml = _build_eml_with_pdf(naam, pdf)
    monkeypatch.setattr(
        email_client_graph.GraphEmailClient, "fetch_raw", lambda self, mid: eml
    )

    token, _ = _sign_attachment_token(oid, naam, "inline", 60)
    r = client.get(
        f"/api/orders/{oid}/bijlagen",
        params={"naam": naam, "disposition": "inline", "token": token},
    )
    assert r.status_code == 200
    assert r.content == pdf
    assert "pdf" in r.headers.get("content-type", "")


def test_signed_url_secret_isolation_via_jwt_secret_rotation(monkeypatch):
    """Rotating jwt_secret must invalidate tokens minted under the previous
    secret (because signed_url_secret falls back to jwt_secret)."""
    monkeypatch.setattr(settings, "signed_url_secret", "")
    monkeypatch.setattr(settings, "jwt_secret", "old")
    token, _ = _sign_attachment_token(1, "a.pdf", "inline", 60)
    monkeypatch.setattr(settings, "jwt_secret", "new")
    assert _verify_attachment_token(token, 1, "a.pdf", "inline") is False
