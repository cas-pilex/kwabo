"""Outlook .msg support: conversion to MIME + upload acceptance.

Kwabo forwards orders as .msg (both the loose-mail upload and the
bron-document upload). We convert .msg → MIME once and reuse the .eml path,
so extraction / storage / attachment-download all keep working uniformly.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kwabo.main import app


class _FakeAttachment:
    def __init__(self, data, filename):
        self.data = data
        self.longFilename = filename
        self.shortFilename = filename


class _FakeMsg:
    sender = "inkoop@klant.nl"
    to = "orders@kwabo.nl"
    subject = "Bestelling 999"
    date = None

    def __init__(self, body, attachments):
        self.body = body
        self.attachments = attachments

    def close(self):
        pass


def test_parse_msg_bytes_converts_and_extracts_pdf(monkeypatch):
    """A .msg with a PDF attachment converts to MIME whose attachment is then
    discoverable exactly like a native .eml (so it later opens in the UI)."""
    import extract_msg

    from kwabo.integrations.email_client import parse_msg_bytes

    fake = _FakeMsg("Zie bijlage", [_FakeAttachment(b"%PDF-1.4 fake", "po999.pdf")])
    monkeypatch.setattr(extract_msg, "openMsg", lambda _p: fake)

    raw = parse_msg_bytes(b"\xd0\xcf\x11\xe0 fake-ole-bytes")  # OLE magic-ish

    assert raw.email_subject == "Bestelling 999"
    assert "klant.nl" in raw.email_from
    names = [b.naam for b in raw.bijlagen]
    assert "po999.pdf" in names
    # raw_eml is real MIME → the download walker can re-extract the PDF.
    from kwabo.api.orders import _extract_attachment_bytes

    result = _extract_attachment_bytes(raw.raw_eml, "po999.pdf")
    assert result is not None
    data, _ctype = result
    assert data == b"%PDF-1.4 fake"


def test_msg_skips_non_bytes_attachment(monkeypatch):
    """Embedded-message attachments (data is not bytes) are skipped, not fatal."""
    import extract_msg

    from kwabo.integrations.email_client import parse_msg_bytes

    fake = _FakeMsg("body", [_FakeAttachment(object(), "embedded.msg"),
                             _FakeAttachment(b"%PDF-1.4 x", "real.pdf")])
    monkeypatch.setattr(extract_msg, "openMsg", lambda _p: fake)

    raw = parse_msg_bytes(b"ole")
    names = [b.naam for b in raw.bijlagen]
    assert "real.pdf" in names
    assert "embedded.msg" not in names


def test_intake_upload_rejects_unsupported_extension(monkeypatch):
    """Upload button accepts .eml/.msg; anything else is a clean 400."""
    from kwabo.config import settings

    monkeypatch.setattr(settings, "admin_password", "")  # disable auth gate
    client = TestClient(app)
    r = client.post(
        "/api/intake/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert ".eml" in r.json()["detail"] and ".msg" in r.json()["detail"]


def test_incoming_doc_allows_msg():
    """Bron-document upload must accept Outlook .msg."""
    from kwabo.api.orders import ALLOWED_INCOMING_DOC_TYPES, SAFE_OCTET_STREAM_EXTENSIONS

    assert ".msg" in SAFE_OCTET_STREAM_EXTENSIONS
    assert "application/vnd.ms-outlook" in ALLOWED_INCOMING_DOC_TYPES
