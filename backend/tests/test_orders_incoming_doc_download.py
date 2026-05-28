"""Fase 3 tests: download-pad voor reviewer-uploaded bron-documenten.

Voorheen kon je via /api/orders/{id}/incoming-doc wel een PDF uploaden,
maar er was geen frontend-route om hem weer op te halen — audit §13.10 /
§14.4 bug. Deze tests dekken het nieuwe `/incoming-doc/file` endpoint +
de Supabase-first upload-pad.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session

from kwabo.api.orders import (
    INCOMING_DOC_TOKEN_NAAM,
    _sign_attachment_token,
)
from kwabo.config import settings
from kwabo.db.models import OrderLog
from kwabo.db.session import engine
from kwabo.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://test.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "service-role-jwt")
    monkeypatch.setattr(settings, "supabase_bucket_incoming_docs", "incoming-docs")


@pytest.fixture
def no_supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")


@pytest.fixture
def admin_off(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")


def _make_order(state: dict, email_id: str = "test-001") -> int:
    with Session(engine) as s:
        row = OrderLog(
            email_id=email_id,
            order_state=json.dumps(state),
            status="review",
            is_order=True,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


# ---------- Upload-pad gebruikt Supabase ----------


@respx.mock
def test_upload_incoming_doc_uses_supabase_when_configured(
    client, admin_off, supabase_env
):
    oid = _make_order({})

    route = respx.post(
        f"https://test.supabase.co/storage/v1/object/incoming-docs/by_order/{oid}/factuur.pdf"
    ).mock(return_value=httpx.Response(200, json={}))

    files = {"file": ("factuur.pdf", b"%PDF-1.4 data", "application/pdf")}
    r = client.post(f"/api/orders/{oid}/incoming-doc", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert route.called
    assert body["storage_key"] == f"by_order/{oid}/factuur.pdf"
    assert body["filename"] == "factuur.pdf"

    # State moet storage_key + filename + content_type krijgen
    with Session(engine) as s:
        row = s.get(OrderLog, oid)
        state = json.loads(row.order_state)
    assert state["incoming_document_storage_key"] == f"by_order/{oid}/factuur.pdf"
    assert state["incoming_document_filename"] == "factuur.pdf"
    assert state["incoming_document_content_type"] == "application/pdf"
    # Geen disk-write bij Supabase-success (clears legacy path)
    assert "incoming_document_path" not in state


def test_upload_incoming_doc_falls_back_to_disk(client, admin_off, no_supabase, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "incoming_documents_dir", str(tmp_path))
    oid = _make_order({})

    files = {"file": ("foto.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")}
    r = client.post(f"/api/orders/{oid}/incoming-doc", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["storage_key"] is None
    assert (tmp_path / str(oid) / "foto.jpg").exists()

    with Session(engine) as s:
        row = s.get(OrderLog, oid)
        state = json.loads(row.order_state)
    assert state.get("incoming_document_storage_key") is None
    assert state["incoming_document_path"].endswith("foto.jpg")


# ---------- Token-mint ----------


def test_mint_incoming_doc_token_returns_valid_token(client, admin_off):
    oid = _make_order({})
    r = client.post(
        f"/api/orders/{oid}/incoming-doc-token",
        json={"naam": "anything", "disposition": "inline"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    # Token-binding is (oid, "incoming-doc", "inline") ongeacht "naam" in request
    from kwabo.api.orders import _verify_attachment_token
    assert _verify_attachment_token(
        body["token"], oid, INCOMING_DOC_TOKEN_NAAM, "inline"
    ) is True


def test_mint_incoming_doc_token_rejects_invalid_disposition(client, admin_off):
    oid = _make_order({})
    r = client.post(
        f"/api/orders/{oid}/incoming-doc-token",
        json={"naam": "x", "disposition": "rogue"},
    )
    assert r.status_code == 400


# ---------- Download-pad ----------


def test_download_incoming_doc_rejects_missing_token(client, admin_off):
    oid = _make_order({})
    r = client.get(f"/api/orders/{oid}/incoming-doc/file")
    assert r.status_code == 422  # required query param missing


def test_download_incoming_doc_rejects_invalid_token(client, admin_off):
    oid = _make_order({})
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": "garbage.garbage"},
    )
    assert r.status_code == 401


def test_download_incoming_doc_rejects_wrong_binding_token(client, admin_off):
    """Token gemint voor een andere disposition mag NIET werken."""
    oid = _make_order({})
    token, _ = _sign_attachment_token(
        oid, INCOMING_DOC_TOKEN_NAAM, "attachment", 60
    )
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": token},
    )
    assert r.status_code == 401


def test_download_incoming_doc_404_when_no_doc_stored(client, admin_off):
    oid = _make_order({})  # no incoming_document_* in state
    token, _ = _sign_attachment_token(
        oid, INCOMING_DOC_TOKEN_NAAM, "inline", 60
    )
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": token},
    )
    assert r.status_code == 404
    assert "Geen bron-document" in r.json()["detail"]


@respx.mock
def test_download_incoming_doc_serves_pdf_from_supabase(
    client, admin_off, supabase_env
):
    """End-to-end happy-path: PDF in Supabase → bytes terug via download-route."""
    oid = _make_order({
        "incoming_document_storage_key": f"by_order/123/factuur.pdf",
        "incoming_document_filename": "factuur.pdf",
        "incoming_document_content_type": "application/pdf",
    })

    respx.get(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_order/123/factuur.pdf"
    ).mock(return_value=httpx.Response(200, content=b"%PDF-1.4 hello"))

    token, _ = _sign_attachment_token(
        oid, INCOMING_DOC_TOKEN_NAAM, "inline", 60
    )
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": token},
    )
    assert r.status_code == 200, r.text
    assert r.content == b"%PDF-1.4 hello"
    assert r.headers["content-type"].startswith("application/pdf")
    assert "inline" in r.headers["content-disposition"]
    assert "factuur.pdf" in r.headers["content-disposition"]


def test_download_incoming_doc_serves_from_disk_when_no_supabase(
    client, admin_off, no_supabase, tmp_path
):
    pdf_path = tmp_path / "factuur.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 disk")
    oid = _make_order({
        "incoming_document_path": str(pdf_path),
        "incoming_document_filename": "factuur.pdf",
        "incoming_document_content_type": "application/pdf",
    })

    token, _ = _sign_attachment_token(
        oid, INCOMING_DOC_TOKEN_NAAM, "inline", 60
    )
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": token},
    )
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 disk"


@respx.mock
def test_download_incoming_doc_falls_back_to_disk_when_supabase_500(
    client, admin_off, supabase_env, tmp_path
):
    """Supabase 500 mag de UI niet kapotmaken — disk-pad als safety net."""
    disk_path = tmp_path / "factuur.pdf"
    disk_path.write_bytes(b"%PDF-1.4 disk")
    oid = _make_order({
        "incoming_document_storage_key": "by_order/999/factuur.pdf",
        "incoming_document_path": str(disk_path),
        "incoming_document_filename": "factuur.pdf",
    })
    respx.get(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_order/999/factuur.pdf"
    ).mock(return_value=httpx.Response(500))

    token, _ = _sign_attachment_token(
        oid, INCOMING_DOC_TOKEN_NAAM, "inline", 60
    )
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": token},
    )
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 disk"
