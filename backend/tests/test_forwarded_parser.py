"""Forward detection op de voorbeeld-mails."""
from __future__ import annotations

import pytest

from kwabo.integrations.email_client import parse_eml_file
from kwabo.integrations.forwarded_parser import detect_forward

EXPECTED_FORWARDS = {
    "FW_ Bestellungen Abdeckvlies 160gr.eml": "r.carvalho@bugel.ch",
    "FW_ Inkooporder IO2029003.eml": "fransvanvliet@isero.nl",
    "FW_ New order OT3478.eml": "maarjaliisa.nomm@tectis.ee",
    "FW_ Stukbouw B.V. -  IOR2601198.eml": "magazijn@stukbouw.nl",
    "FW_ VO2602754 - Kirchner GmbH - 27-2-2026.eml": "tobias.leyhausen@kirchner-online.com",
    "Fwd_ Nieuwe order.eml": "e.sun@enkabouwmarkt.nl",
}


@pytest.mark.parametrize("filename,expected", sorted(EXPECTED_FORWARDS.items()))
def test_forward_sender_extracted(eml_dir, filename, expected):
    em = parse_eml_file(eml_dir / filename)
    bijl = "\n".join((b.inhoud_tekst or "")[:5000] for b in em.bijlagen)
    fwd = detect_forward(em.email_from, em.email_subject, em.email_body, bijl)
    assert fwd.is_forwarded, f"{filename}: niet als forward gedetecteerd ({fwd.reason})"
    assert fwd.original_from_email == expected, (
        f"{filename}: verwachtte {expected}, kreeg {fwd.original_from_email}"
    )


def test_non_forward_niet_gedetecteerd(eml_dir):
    em = parse_eml_file(eml_dir / "Ferney inkooporder 4200056148.eml")
    fwd = detect_forward(em.email_from, em.email_subject, em.email_body, "")
    assert not fwd.is_forwarded, "Ferney is géén forward"


# ---- real-world forward tests ----

from pathlib import Path as _Path
from kwabo.integrations.email_client import parse_eml_file as _parse_eml
from kwabo.integrations.forwarded_parser import detect_forward as _detect_forward


def _load_fwd(name: str):
    p = _Path(__file__).resolve().parent / "test_data" / "emails" / name
    return _parse_eml(p)


def _detect_on_email(name: str):
    raw = _load_fwd(name)
    bijl_blob = "\n".join((b.inhoud_tekst or "") for b in raw.bijlagen)[:40000]
    return _detect_forward(raw.email_from, raw.email_subject, raw.email_body, bijl_blob)


def test_forward_io2029003_detected():
    fwd = _detect_on_email("FW_ Inkooporder IO2029003.eml")
    assert fwd.is_forwarded, f"is_forwarded False, reason={fwd.reason}"
    assert fwd.original_from_email and "@" in fwd.original_from_email
    assert "kwabo.nl" not in fwd.original_from_email.lower()


def test_forward_ot3478_detected():
    fwd = _detect_on_email("FW_ New order OT3478.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email and "@" in fwd.original_from_email


def test_forward_stukbouw_detected():
    fwd = _detect_on_email("FW_ Stukbouw B.V. -  IOR2601198.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email and "@" in fwd.original_from_email


def test_forward_kirchner_detected():
    fwd = _detect_on_email("FW_ VO2602754 - Kirchner GmbH - 27-2-2026.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email
    # Kirchner staff email should contain 'kirchner' as a domain hint
    assert "kirchner" in fwd.original_from_email.lower()


def test_forward_abdeckvlies_detected():
    fwd = _detect_on_email("FW_ Bestellungen Abdeckvlies 160gr.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email and "@" in fwd.original_from_email


def test_forward_fwd_nieuwe_order_detected():
    fwd = _detect_on_email("Fwd_ Nieuwe order.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email and "@" in fwd.original_from_email
