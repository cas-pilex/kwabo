"""Tests voor de Supabase-Storage flow voor bron-mails (Fase 2).

Dekt:
- de `SupabaseStorageClient` REST-wrapper (httpx via respx mocks).
- `get_supabase_storage()` factory: returns None bij missing config.
- `_persist_source_eml` met en zonder Supabase, met en zonder fallback.
- `_resolve_eml_bytes` lookup-volgorde (Supabase → disk → source_path → scan).
- het nieuwe 404-bericht in download_attachment.

Wij raken NOOIT de echte Supabase aan; alles via respx.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session

from kwabo.api.intake_trigger import _persist_source_eml, _safe_eml_id
from kwabo.api.orders import _resolve_eml_bytes, _sign_attachment_token
from kwabo.config import settings
from kwabo.db.models import OrderLog
from kwabo.db.session import engine
from kwabo.integrations import supabase_storage
from kwabo.integrations.supabase_storage import (
    SupabaseStorageClient,
    get_supabase_storage,
)
from kwabo.main import app


# ---------- helpers ----------


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
def client():
    return TestClient(app)


# ---------- factory ----------


def test_factory_returns_none_without_config(no_supabase):
    assert get_supabase_storage() is None


def test_factory_returns_client_with_config(supabase_env):
    c = get_supabase_storage()
    assert c is not None
    assert c.bucket == "incoming-docs"
    assert c.base_url == "https://test.supabase.co"


# ---------- SupabaseStorageClient ----------


@respx.mock
def test_put_object_sets_required_headers():
    route = respx.post(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/abc.eml"
    ).mock(return_value=httpx.Response(200, json={"Key": "incoming-docs/by_email_id/abc.eml"}))

    c = SupabaseStorageClient(
        url="https://test.supabase.co",
        service_role_key="srk",
        bucket="incoming-docs",
    )
    c.put_object("by_email_id/abc.eml", b"raw bytes", "message/rfc822")

    assert route.called
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer srk"
    assert req.headers["apikey"] == "srk"
    assert req.headers["Content-Type"] == "message/rfc822"
    assert req.headers["x-upsert"] == "true"
    assert req.content == b"raw bytes"


@respx.mock
def test_get_object_returns_bytes():
    respx.get(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/abc.eml"
    ).mock(return_value=httpx.Response(200, content=b"RFC822 body"))

    c = SupabaseStorageClient(
        url="https://test.supabase.co",
        service_role_key="srk",
        bucket="incoming-docs",
    )
    assert c.get_object("by_email_id/abc.eml") == b"RFC822 body"


@respx.mock
def test_head_object_returns_false_on_404():
    respx.head(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/missing.eml"
    ).mock(return_value=httpx.Response(404))

    c = SupabaseStorageClient(
        url="https://test.supabase.co",
        service_role_key="srk",
        bucket="incoming-docs",
    )
    assert c.head_object("by_email_id/missing.eml") is False


@respx.mock
def test_head_object_returns_true_on_200():
    respx.head(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/found.eml"
    ).mock(return_value=httpx.Response(200))

    c = SupabaseStorageClient(
        url="https://test.supabase.co",
        service_role_key="srk",
        bucket="incoming-docs",
    )
    assert c.head_object("by_email_id/found.eml") is True


# ---------- _persist_source_eml ----------


@respx.mock
def test_persist_source_eml_uses_supabase_when_configured(supabase_env, tmp_path, monkeypatch):
    """With Supabase available: storage_key returned, no disk write."""
    monkeypatch.setattr(settings, "incoming_documents_dir", str(tmp_path))

    route = respx.post(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/test123.eml"
    ).mock(return_value=httpx.Response(200, json={}))

    storage_key, local_path = _persist_source_eml(b"From: a@b\n\nhi", "test123")

    assert route.called
    assert storage_key == "by_email_id/test123.eml"
    # Bij Supabase success: GEEN disk write (saves Railway ephemere FS).
    assert local_path is None
    assert not (tmp_path / "by_email_id" / "test123.eml").exists()


@respx.mock
def test_persist_source_eml_falls_back_to_disk_on_supabase_fail(
    supabase_env, tmp_path, monkeypatch
):
    """Supabase 500 → still try local disk. Don't fail the intake."""
    monkeypatch.setattr(settings, "incoming_documents_dir", str(tmp_path))

    respx.post(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/test123.eml"
    ).mock(return_value=httpx.Response(500, text="Supabase exploded"))

    storage_key, local_path = _persist_source_eml(b"raw", "test123")
    assert storage_key is None
    assert local_path is not None
    assert Path(local_path).read_bytes() == b"raw"


def test_persist_source_eml_disk_only_without_supabase(no_supabase, tmp_path, monkeypatch):
    """Lokaal/docker dev: geen Supabase config → disk-only pad."""
    monkeypatch.setattr(settings, "incoming_documents_dir", str(tmp_path))

    storage_key, local_path = _persist_source_eml(b"raw", "abc")
    assert storage_key is None
    assert local_path is not None
    assert Path(local_path).read_bytes() == b"raw"


def test_persist_source_eml_returns_none_none_when_everything_fails(
    no_supabase, tmp_path, monkeypatch
):
    """Disk-write fails (read-only dir): both return values None so caller
    sets `incoming_document_save_failed` marker."""
    # Point to a non-existent + non-creatable path
    bogus = tmp_path / "does" / "not" / "exist"
    bogus.mkdir(parents=True)
    bogus.chmod(0o400)  # read-only — write should fail on most systems
    monkeypatch.setattr(settings, "incoming_documents_dir", str(bogus))

    # On Windows chmod 0o400 doesn't actually block writes; force-fail via
    # patching Path.write_bytes for cross-platform reliability.
    import pathlib
    orig = pathlib.Path.write_bytes

    def boom(self, _data):
        raise OSError("simulated disk full")

    monkeypatch.setattr(pathlib.Path, "write_bytes", boom)
    try:
        storage_key, local_path = _persist_source_eml(b"raw", "abc")
        assert storage_key is None
        assert local_path is None
    finally:
        monkeypatch.setattr(pathlib.Path, "write_bytes", orig)


def test_safe_eml_id_strips_unsafe_chars():
    assert _safe_eml_id("graph://AAMkAGI=1234?$top") == "graphAAMkAGI1234top"
    assert _safe_eml_id("") == "source"
    assert _safe_eml_id(None) == "source"
    assert len(_safe_eml_id("a" * 100)) == 32


# ---------- _resolve_eml_bytes ----------


@respx.mock
def test_resolve_eml_bytes_prefers_supabase_over_disk(supabase_env, tmp_path):
    """Bij beide aanwezig wint Supabase (canoniek). Bewijst dat de migratie
    'oude order met disk-pad krijgt nieuwe storage_key' correct werkt."""
    disk_path = tmp_path / "disk.eml"
    disk_path.write_bytes(b"DISK")

    respx.get(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/test.eml"
    ).mock(return_value=httpx.Response(200, content=b"SUPABASE"))

    state = {
        "incoming_document_storage_key": "by_email_id/test.eml",
        "incoming_document_path": str(disk_path),
    }
    assert _resolve_eml_bytes(state, "test") == b"SUPABASE"


@respx.mock
def test_resolve_eml_bytes_falls_back_to_disk_when_supabase_fails(
    supabase_env, tmp_path
):
    """Supabase 500 mag de download niet kapotmaken — val terug op disk-pad."""
    disk_path = tmp_path / "disk.eml"
    disk_path.write_bytes(b"DISK")

    respx.get(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/test.eml"
    ).mock(return_value=httpx.Response(500))

    state = {
        "incoming_document_storage_key": "by_email_id/test.eml",
        "incoming_document_path": str(disk_path),
    }
    assert _resolve_eml_bytes(state, "test") == b"DISK"


def test_resolve_eml_bytes_uses_disk_path_when_no_storage_key(no_supabase, tmp_path):
    disk_path = tmp_path / "legacy.eml"
    disk_path.write_bytes(b"LEGACY")
    state = {"incoming_document_path": str(disk_path)}
    assert _resolve_eml_bytes(state, "x") == b"LEGACY"


def test_resolve_eml_bytes_skips_graph_uri_source_path(no_supabase):
    state = {"source_path": "graph://AAMkAGI="}
    assert _resolve_eml_bytes(state, "x") is None


def test_resolve_eml_bytes_returns_none_when_nothing_found(no_supabase):
    assert _resolve_eml_bytes({}, None) is None


# ---------- End-to-end via download_attachment route ----------


@respx.mock
def test_download_attachment_404_honest_message_when_no_source(client, monkeypatch):
    """De nieuwe 404-message moet niet meer 'verwijderd uit inbox/processed'
    suggereren — dat misleidde Cas in eerdere debug-sessies."""
    monkeypatch.setattr(settings, "admin_password", "")  # auth gate uit voor de POST

    # Maak een order met email_id maar geen storage_key/path
    with Session(engine) as s:
        row = OrderLog(
            email_id="orphan-001",
            order_state=json.dumps({}),
            status="review",
            is_order=True,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        oid = row.id

    token, _ = _sign_attachment_token(oid, "factuur.pdf", "inline", 60)
    r = client.get(
        f"/api/orders/{oid}/bijlagen",
        params={"naam": "factuur.pdf", "token": token},
    )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "Bron-document niet meer beschikbaar" in detail
    assert "verwijderd uit inbox" not in detail


@respx.mock
def test_download_attachment_serves_pdf_from_supabase(client, monkeypatch, supabase_env):
    """End-to-end: order met storage_key → /bijlagen haalt .eml uit Supabase,
    parsed de PDF-bijlage en serveert die. Dit is de happy-path bewijs voor
    Fase 2 = root-cause weg."""
    monkeypatch.setattr(settings, "admin_password", "")

    # Bouw een echte .eml met PDF-attachment
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = "klant@example.com"
    msg["To"] = "info@kwabo.nl"
    msg["Subject"] = "Order"
    msg.set_content("Beste, zie bijlage")
    msg.add_attachment(b"%PDF-1.4 fake PDF body", maintype="application", subtype="pdf", filename="order.pdf")
    raw_eml = msg.as_bytes()

    respx.get(
        "https://test.supabase.co/storage/v1/object/incoming-docs/by_email_id/sup-test.eml"
    ).mock(return_value=httpx.Response(200, content=raw_eml))

    with Session(engine) as s:
        row = OrderLog(
            email_id="sup-test",
            order_state=json.dumps({
                "incoming_document_storage_key": "by_email_id/sup-test.eml",
            }),
            status="review",
            is_order=True,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        oid = row.id

    token, _ = _sign_attachment_token(oid, "order.pdf", "inline", 60)
    r = client.get(
        f"/api/orders/{oid}/bijlagen",
        params={"naam": "order.pdf", "token": token},
    )
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")
    assert "inline" in r.headers["Content-Disposition"]
