"""K3.1 (Fase 2): extractie levert de naam van de BESTELLENDE partij.

Nodig voor de klant-naam-fallback (K3): bij portaal/agent-mails (GBI Borne
via zevij-necomij, TABS via pontmeyer) is de afzender niet de klant en staat
de klantnaam alléén in het orderdocument. `afleveradres.naam` is de
contactpersoon van het afleveradres — niet bruikbaar.

Het veld is optioneel: een ontbrekende naam mag een review nooit blokkeren
(het is een matching-signaal, geen push-veld).
"""
from __future__ import annotations

from kwabo.graph.nodes.extract import _build_state_from_extract
from kwabo.integrations.email_client import RawEmail


def _raw() -> RawEmail:
    return RawEmail(
        email_id="k3-test", email_from="support@zevij-necomij.com",
        email_subject="Order van GBI Borne - 2601922", email_date="",
        email_body="", bijlagen=[],
    )


def test_klantnaam_besteller_komt_in_state_met_provenance():
    parsed = {
        "taal": {"value": "NL", "source": "email_body", "source_detail": None,
                 "confidence": 0.99, "needs_review": False},
        "klantnaam_besteller": {"value": "GBI Borne", "source": "email_body",
                                "source_detail": "portal-onderwerp",
                                "confidence": 0.9, "needs_review": False},
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert flat["klantnaam_besteller"] == "GBI Borne"
    assert meta["klantnaam_besteller"]["source"] == "email_body"


def test_ontbrekende_klantnaam_blokkeert_review_nooit():
    flat, meta, needs = _build_state_from_extract({"orderregels": []}, _raw())
    assert flat["klantnaam_besteller"] is None
    assert "klantnaam_besteller" not in needs
    assert meta["klantnaam_besteller"]["needs_review"] is False
