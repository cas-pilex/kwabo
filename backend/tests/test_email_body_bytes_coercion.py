"""Regressie: bytes-body mag de pipeline niet slopen (prod-crash 29-05-2026).

Live in productie crashte ELKE inkomende mail in `match_customer_node` met
``cannot use a string pattern on a bytes-like object``. Oorzaak: bij een
non-multipart mail met een niet-text content-type (bv. een kale PDF of
``application/octet-stream``) geeft ``Message.get_content()`` *bytes* terug.
`_plain_body` gaf die bytes ongewijzigd door als ``email_body``, waarna
`detect_forward` (de eerste stap van match_customer) een str-regex op bytes
losliet → exceptie vóór ``mark_seen`` → poison-pill loop.

Deze tests borgen dat:
  1. `_plain_body` ALTIJD een str teruggeeft.
  2. `detect_forward` een bytes-body verdraagt zonder te crashen.
  3. `match_customer_node` met een bytes-body niet meer crasht.
"""
from __future__ import annotations

import email
import email.policy

import pytest

from kwabo.integrations.email_client import _plain_body
from kwabo.integrations.forwarded_parser import detect_forward


def _msg(content_type: bytes, cte: bytes, payload: bytes):
    raw = (
        b"From: a@b.nl\r\nSubject: t\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: " + content_type + b"\r\n"
        b"Content-Transfer-Encoding: " + cte + b"\r\n\r\n" + payload + b"\r\n"
    )
    return email.message_from_bytes(raw, policy=email.policy.default)


def test_plain_body_returns_str_for_octet_stream():
    """Non-multipart application/octet-stream → get_content() levert bytes;
    _plain_body moet dat coercen naar str."""
    msg = _msg(b"application/octet-stream", b"8bit", b"binaire troep \xe9\xff")
    body = _plain_body(msg)
    assert isinstance(body, str)


def test_plain_body_returns_str_for_bare_pdf():
    """Een kale PDF-mail (geen multipart) heeft een non-text body."""
    msg = _msg(b"application/pdf; name=o.pdf", b"base64", b"JVBERi0xLjQK")
    body = _plain_body(msg)
    assert isinstance(body, str)


def test_plain_body_str_for_normal_text():
    msg = _msg(b"text/plain; charset=utf-8", b"8bit", b"gewoon tekst \xc3\xa9")
    body = _plain_body(msg)
    assert isinstance(body, str)
    assert "gewoon tekst" in body


def test_detect_forward_tolerates_bytes_body():
    """De exacte prod-crash: bytes als email_body mag geen exceptie geven."""
    info = detect_forward(
        "klant@extern.nl",
        "Bestelling 123",
        b"Dit is een bytes-body \xe9\xff met rare bytes",
        b"",
    )
    # Niet crashen is het hele punt; resultaat mag gewoon 'geen forward' zijn.
    assert info.is_forwarded in (True, False)


def test_detect_forward_bytes_body_still_finds_forward():
    """Forward-detectie blijft werken nadat de bytes-body gedecodeerd is."""
    body = (
        b"---------- Forwarded message ----------\r\n"
        b"From: Echte Klant <klant@echt.nl>\r\n"
        b"Subject: Order\r\n\r\nDetails \xe9"
    )
    info = detect_forward("ivar@kwabo.nl", "Fwd: Order", body, b"")
    assert info.is_forwarded is True
    assert info.original_from_email == "klant@echt.nl"


@pytest.mark.asyncio
async def test_match_customer_node_survives_bytes_body():
    """End-to-end op de node: bytes email_body mag de node niet laten crashen."""
    from kwabo.graph.nodes.match_customer import match_customer_node

    state = {
        "email_id": "x",
        "email_from": "onbekend@nergens.nl",
        "email_subject": "Test",
        "email_body": b"bytes body \xe9\xff",
        "bijlagen": [],
        "orderregels": [],
    }
    result = await match_customer_node(state)
    # Geen klant gevonden is prima; het gaat erom dat er geen exceptie vliegt.
    assert "validatie_warnings" in result
