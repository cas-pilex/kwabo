"""Defense-in-depth tegen stored-XSS via reviewer-uploaded bron-documenten.

De download-routes /bijlagen en /incoming-doc/file serveren bytes onder
dezelfde origin als het admin-dashboard. Een opzettelijk-gemanipuleerde
upload (HTML als 'text/plain', SVG met onload-script, image/svg+xml als
'image/png' etc.) kan anders als XSS draaien in de reviewer-sessie.

Mitigatie:
  - Non-safe-inline content-types: force Content-Disposition: attachment
    (browser DOWNLOADT i.p.v. rendert, ook als de caller "inline" vroeg).
  - X-Content-Type-Options: nosniff (Chrome niet laten sniffen).
  - Content-Security-Policy: sandbox; default-src 'none' (geen scripts,
    geen same-origin requests vanuit een iframe-view).

Safe-inline allowlist: PDF + de standaard raster-afbeeldingen. SVG NIET
(kan scripts bevatten).
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
    SAFE_INLINE_CONTENT_TYPES,
    _safe_response_headers,
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
def admin_off(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")


# ---------- _safe_response_headers unit-tests ----------


def test_pdf_inline_stays_inline():
    disp, hdrs = _safe_response_headers("application/pdf", "inline", "x.pdf")
    assert disp == "inline"
    assert "inline" in hdrs["Content-Disposition"]


def test_png_inline_stays_inline():
    disp, _ = _safe_response_headers("image/png", "inline", "x.png")
    assert disp == "inline"


@pytest.mark.parametrize(
    "ctype",
    [
        "text/html",
        "image/svg+xml",
        "text/plain",
        "application/javascript",
        "text/xml",
        "application/xml",
        "application/octet-stream",
    ],
)
def test_dangerous_inline_force_downloaded(ctype):
    """Iedere niet-safe-inline content-type wordt forcibly 'attachment',
    ook wanneer de caller 'inline' vroeg."""
    disp, _ = _safe_response_headers(ctype, "inline", "evil.html")
    assert disp == "attachment"


def test_explicit_attachment_request_stays_attachment():
    disp, _ = _safe_response_headers("application/pdf", "attachment", "x.pdf")
    assert disp == "attachment"


def test_security_headers_always_present():
    _, hdrs = _safe_response_headers("application/pdf", "inline", "x.pdf")
    assert hdrs["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in hdrs["Content-Security-Policy"]
    assert "default-src 'none'" in hdrs["Content-Security-Policy"]


def test_content_disposition_includes_rfc5987_filename():
    _, hdrs = _safe_response_headers(
        "application/pdf", "inline", "fact uur 2026.pdf"
    )
    # RFC5987 form encodes spaces as %20
    assert "filename*=UTF-8''" in hdrs["Content-Disposition"]
    assert "fact%20uur" in hdrs["Content-Disposition"]


def test_safe_inline_list_excludes_svg_and_html():
    """SVG en HTML mogen NOOIT in de inline-allowlist — het hele punt
    van de mitigatie."""
    assert "image/svg+xml" not in SAFE_INLINE_CONTENT_TYPES
    assert "text/html" not in SAFE_INLINE_CONTENT_TYPES
    assert "application/javascript" not in SAFE_INLINE_CONTENT_TYPES


# ---------- End-to-end via /incoming-doc/file ----------


def _make_order(state: dict) -> int:
    with Session(engine) as s:
        row = OrderLog(
            email_id="sec-test",
            order_state=json.dumps(state),
            status="review",
            is_order=True,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def test_download_html_disguised_as_pdf_still_forced_to_attachment(
    client, admin_off, tmp_path
):
    """Stored XSS-scenario: reviewer upload 'evil.html' maar state krijgt
    stored_content_type='application/pdf'. De download-route gebruikt
    extension-derived content-type (.html → text/html), die niet in
    SAFE_INLINE_CONTENT_TYPES staat → force attachment."""
    evil = tmp_path / "evil.html"
    evil.write_bytes(b"<script>alert(1)</script>")
    oid = _make_order({
        "incoming_document_path": str(evil),
        "incoming_document_filename": "evil.html",
        "incoming_document_content_type": "application/pdf",  # liar
    })
    token, _ = _sign_attachment_token(
        oid, INCOMING_DOC_TOKEN_NAAM, "inline", 60
    )
    r = client.get(
        f"/api/orders/{oid}/incoming-doc/file",
        params={"disposition": "inline", "token": token},
    )
    assert r.status_code == 200
    # Mitigation kicks in: content-type is text/html, niet in safe-inline →
    # forced attachment.
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]


def test_download_legitimate_pdf_serves_inline(client, admin_off, tmp_path):
    pdf = tmp_path / "factuur.pdf"
    pdf.write_bytes(b"%PDF-1.4 ok")
    oid = _make_order({
        "incoming_document_path": str(pdf),
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
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff"
