"""Fase 5 (E) — file_drop mark_seen moet een herstart overleven (§14.7).

`_path_by_id` is in-memory. Crashte het proces tussen list_new() en
mark_seen(), dan was mark_seen op de nieuwe instantie een stille no-op:
de .eml bleef in de inbox en werd elke volgende scan opnieuw verwerkt
(duplicaat in order_log — de intake dedupt niet op email_id). email_id is
sha256(bytes)[:16], dus deterministisch herleidbaar uit het bestand zelf.
"""
from __future__ import annotations

import email.message
from pathlib import Path

from kwabo.integrations.email_client import FileDropEmailClient


def _schrijf_eml(pad: Path) -> None:
    m = email.message.EmailMessage()
    m["From"] = "a@b.nl"
    m["To"] = "pilex@kwabo.nl"
    m["Subject"] = "Order 123"
    m.set_content("2x stucloper")
    pad.write_bytes(m.as_bytes())


def _client(tmp_path: Path) -> FileDropEmailClient:
    return FileDropEmailClient(
        inbox=tmp_path / "inbox", processed=tmp_path / "processed"
    )


def test_mark_seen_na_herstart_verplaatst_alsnog(tmp_path):
    """Herstart-scenario: nieuwe instantie (lege _path_by_id) moet de mail
    alsnog naar processed/ verplaatsen — geen herverwerking volgende scan."""
    a = _client(tmp_path)
    _schrijf_eml(a.inbox / "order.eml")
    [em] = a.list_new()

    b = _client(tmp_path)  # simuleert proces-herstart
    b.mark_seen(em.email_id)

    assert not (a.inbox / "order.eml").exists(), "mail bleef in inbox → duplicaat"
    assert (a.processed / "order.eml").exists()


def test_mark_seen_zelfde_instantie_blijft_werken(tmp_path):
    a = _client(tmp_path)
    _schrijf_eml(a.inbox / "order.eml")
    [em] = a.list_new()
    a.mark_seen(em.email_id)
    assert (a.processed / "order.eml").exists()


def test_mark_seen_onbekende_id_is_noop(tmp_path):
    a = _client(tmp_path)
    _schrijf_eml(a.inbox / "order.eml")
    a.mark_seen("bestaat-niet-0000")
    assert (a.inbox / "order.eml").exists()
    assert not (a.processed / "order.eml").exists()
