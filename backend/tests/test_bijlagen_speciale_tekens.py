"""Fase 1 — bijlagen met speciale tekens in de naam + consistent inline/download.

Reproductie van prod #706 (PPG): bijlage "New PO Output: 4510686252 -
Vendor: 95042039.pdf" — de ':' in een gewone bijlagenaam mag nooit als
zip-pad ("archive.zip:inner.pdf") gelezen worden. Plus: "Open in nieuw
tabblad" (disposition=inline) moet voor een PDF echt inline renderen, ook
als de mail-client application/octet-stream als content-type meegeeft;
onveilige types (html/svg) blijven geforceerd attachment.
"""
from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from kwabo.api.orders import _extract_attachment_bytes, _sign_attachment_token
from kwabo.main import app

# Exacte bijlagenaam uit prod-order #706 (PPG) — zie
# tests/test_data/states/order_706_new-po-output-4510686252-vendor-95042039.json
PPG_NAAM = "New PO Output: 4510686252 - Vendor: 95042039.pdf"
PDF_BYTES = b"%PDF-1.4 ppg-fake-bytes"


@pytest.fixture
def client():
    return TestClient(app)


def _eml_met_bijlage(
    naam: str,
    data: bytes = PDF_BYTES,
    maintype: str = "application",
    subtype: str = "pdf",
) -> bytes:
    import email.message

    m = email.message.EmailMessage()
    m["From"] = "orders@ppg.com"
    m["To"] = "pilex@kwabo.nl"
    m["Subject"] = "New PO Output: 4510686252 - Vendor: 95042039"
    m.set_content("body")
    m.add_attachment(data, maintype=maintype, subtype=subtype, filename=naam)
    return m.as_bytes()


def _order_met_eml(tmp_path, eml: bytes, naam: str) -> int:
    """OrderLog-rij waarvan de .eml via state.source_path oplosbaar is."""
    from sqlmodel import Session

    from kwabo.db import session as db_session
    from kwabo.db.repository import OrderLogRepo

    p = tmp_path / "bron.eml"
    p.write_bytes(eml)
    with Session(db_session.engine) as s:
        row = OrderLogRepo(s).create(
            email_id=f"test-{tmp_path.name}", email_from="orders@ppg.com",
            email_subject="PPG order", status="review",
        )
        row.order_state = json.dumps({
            "bijlagen": [{"naam": naam, "type": "pdf"}],
            "source_path": str(p),
        })
        s.add(row)
        s.commit()
        return row.id


# ---------------------------------------------------------------- extractie


def test_kolon_in_bijlagenaam_is_geen_zip_pad():
    """#706: ':' in een gewone bijlagenaam → directe match, geen zip-tak."""
    eml = _eml_met_bijlage(PPG_NAAM)
    result = _extract_attachment_bytes(eml, PPG_NAAM)
    assert result is not None, "bijlage met ':' in de naam moet gevonden worden"
    data, ctype = result
    assert data == PDF_BYTES
    assert ctype == "application/pdf"


def test_zip_pad_blijft_werken():
    """Regressie-borging: echte zip-paden ("archive.zip:inner.pdf") blijven werken."""
    inner = b"%PDF-1.4 inner-bytes"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("inner.pdf", inner)
    eml = _eml_met_bijlage("archive.zip", buf.getvalue(), "application", "zip")
    result = _extract_attachment_bytes(eml, "archive.zip:inner.pdf")
    assert result is not None
    assert result[0] == inner


# ----------------------------------------------------------------- endpoint


def test_endpoint_kolon_naam_inline_met_volledige_naam(client, tmp_path):
    """Endpoint-repro #706: download lukt én Content-Disposition draagt de
    VOLLEDIGE naam (geen split(':')-verminking naar ' 95042039.pdf')."""
    oid = _order_met_eml(tmp_path, _eml_met_bijlage(PPG_NAAM), PPG_NAAM)
    token, _ = _sign_attachment_token(oid, PPG_NAAM, "inline", 60)
    r = client.get(
        f"/api/orders/{oid}/bijlagen",
        params={"naam": PPG_NAAM, "disposition": "inline", "token": token},
    )
    assert r.status_code == 200, r.text
    assert r.content == PDF_BYTES
    cd = r.headers["Content-Disposition"]
    assert cd.startswith("inline"), cd
    # RFC5987-vorm bevat de volledige naam, niet alleen het stuk na de laatste ':'
    assert quote(PPG_NAAM) in cd, cd


def test_endpoint_octet_stream_pdf_blijft_inline(client, tmp_path):
    """Mail-clients geven PDF's vaak als application/octet-stream mee; 'Open in
    nieuw tabblad' moet dan alsnog inline + application/pdf serveren."""
    naam = "factuur 2026.pdf"
    eml = _eml_met_bijlage(naam, subtype="octet-stream")
    oid = _order_met_eml(tmp_path, eml, naam)
    token, _ = _sign_attachment_token(oid, naam, "inline", 60)
    r = client.get(
        f"/api/orders/{oid}/bijlagen",
        params={"naam": naam, "disposition": "inline", "token": token},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.headers["Content-Disposition"].startswith("inline")


def test_endpoint_html_blijft_geforceerd_attachment(client, tmp_path):
    """Security-downgrade blijft: html nooit inline (stored-XSS-mitigatie)."""
    naam = "pagina.html"
    eml = _eml_met_bijlage(naam, b"<script>alert(1)</script>", "text", "html")
    oid = _order_met_eml(tmp_path, eml, naam)
    token, _ = _sign_attachment_token(oid, naam, "inline", 60)
    r = client.get(
        f"/api/orders/{oid}/bijlagen",
        params={"naam": naam, "disposition": "inline", "token": token},
    )
    assert r.status_code == 200, r.text
    assert r.headers["Content-Disposition"].startswith("attachment")
