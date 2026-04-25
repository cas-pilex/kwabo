"""Tests for POST /api/orders/{id}/incoming-doc (T10).

The endpoint uploads the original email/PDF/image as the incoming document
for an order, stores it under ``data/incoming_documents/{order_id}/...``,
and updates ``state["incoming_document_path"]`` with the absolute saved
path so the push_navision pipeline can attach it as /incomingDocuments.
"""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from kwabo.api import orders as orders_module


@pytest.fixture
def client(session, tmp_path, monkeypatch):
    """TestClient backed by the seeded test DB + a tmp incoming_documents dir."""
    # Re-bind the module-level engine so the API uses the test DB.
    from kwabo.db import session as db_session_mod
    original_engine = db_session_mod.engine
    db_session_mod.engine = session.get_bind()

    # Pin the incoming-documents dir to tmp so we don't pollute the real
    # data dir during tests.
    incoming_dir = tmp_path / "incoming_documents"
    monkeypatch.setattr(
        orders_module.settings,
        "incoming_documents_dir",
        str(incoming_dir),
    )

    from kwabo.main import create_app
    app = create_app()
    with TestClient(app) as c:
        c.incoming_dir = incoming_dir  # surface for assertions
        yield c

    db_session_mod.engine = original_engine


def _seed_order(session) -> int:
    from kwabo.db.repository import OrderLogRepo
    repo = OrderLogRepo(session)
    row = repo.create(
        email_id="t10-incoming-1",
        status="needs_review",
        is_order=True,
        order_state=json.dumps({"orderregels": []}),
    )
    return row.id


def test_upload_pdf_happy_path(client, session):
    order_id = _seed_order(session)
    pdf_bytes = b"%PDF-1.4\n%mock pdf content\n%%EOF"

    r = client.post(
        f"/api/orders/{order_id}/incoming-doc",
        files={"file": ("invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content_type"] == "application/pdf"
    assert body["file_size"] == len(pdf_bytes)
    assert body["saved_path"].endswith("invoice.pdf")

    # File actually written to disk.
    saved = client.incoming_dir / str(order_id) / "invoice.pdf"
    assert saved.exists()
    assert saved.read_bytes() == pdf_bytes

    # state["incoming_document_path"] populated to the saved absolute path.
    detail = client.get(f"/api/orders/{order_id}").json()
    assert detail["order_state"]["incoming_document_path"] == body["saved_path"]


def test_upload_eml_accepted(client, session):
    order_id = _seed_order(session)
    eml_bytes = b"From: test@example.com\nSubject: order\n\nbody"
    r = client.post(
        f"/api/orders/{order_id}/incoming-doc",
        files={"file": ("order.eml", io.BytesIO(eml_bytes), "message/rfc822")},
    )
    assert r.status_code == 200
    assert r.json()["content_type"] == "message/rfc822"


def test_upload_png_accepted(client, session):
    order_id = _seed_order(session)
    r = client.post(
        f"/api/orders/{order_id}/incoming-doc",
        files={"file": ("scan.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
    )
    assert r.status_code == 200


def test_upload_wrong_content_type_rejected(client, session):
    order_id = _seed_order(session)
    r = client.post(
        f"/api/orders/{order_id}/incoming-doc",
        files={
            "file": (
                "bad.exe",
                io.BytesIO(b"MZ\x90\x00"),
                "application/x-msdownload",
            )
        },
    )
    assert r.status_code == 400
    assert "niet toegestaan" in r.json()["detail"].lower()


def test_upload_too_large_rejected(client, session):
    order_id = _seed_order(session)
    too_big = b"\x00" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    r = client.post(
        f"/api/orders/{order_id}/incoming-doc",
        files={"file": ("big.pdf", io.BytesIO(too_big), "application/pdf")},
    )
    assert r.status_code == 413
    assert "te groot" in r.json()["detail"].lower()


def test_upload_path_traversal_sanitized(client, session):
    """A filename containing ../ must be sanitized to its bare name. The
    saved file lives under data/incoming_documents/{order_id}/passwd —
    NOT outside the order directory.
    """
    order_id = _seed_order(session)
    r = client.post(
        f"/api/orders/{order_id}/incoming-doc",
        files={
            "file": (
                "../../etc/passwd",
                io.BytesIO(b"%PDF-1.4\n%fake\n"),
                "application/pdf",
            )
        },
    )
    assert r.status_code == 200, r.text
    saved_path = r.json()["saved_path"]
    assert saved_path.endswith("passwd")
    # No directory escape — saved file must be inside the order's dir.
    expected_parent = (client.incoming_dir / str(order_id)).resolve()
    assert str(expected_parent) in saved_path
    assert "etc" not in saved_path.replace("incoming_documents", "")
    assert (expected_parent / "passwd").exists()


def test_upload_order_not_found(client):
    r = client.post(
        "/api/orders/999999/incoming-doc",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert r.status_code == 404
