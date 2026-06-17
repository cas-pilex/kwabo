"""Functie 6 — artikel-keuze valideren tegen de prijslijst.

Een gematcht artikel zonder actieve prijs voor de klant is verdacht als een
alternatief (kruisverwijzing/klantenkaart) WÉL een prijs heeft (#816: 23853 geen
prijs, 238531 wel). Cas-bevestigd: VLAGGEN + kandidaat tonen (nooit auto-switchen,
nooit zelf prijzen). Data-gated: zonder gevulde prijsafspraken een no-op.

DEEL B: de tool stuurt nooit een prijs naar NAV; de "geen prijsafspraak"-tekst is
gecorrigeerd.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelKruisverwijzing, Prijsafspraak
from kwabo.graph.nodes import validate_prices as vp


@pytest.fixture
def app_engine(session, monkeypatch):
    monkeypatch.setattr(vp, "engine", session.get_bind())
    yield


def _state(*, prijs=None, matched="23853", sku="SKU-816"):
    return {
        "email_id": "f6",
        "klant_match": {"navision_klantnr": "K9"},
        "orderregels": [
            {"positie": 1, "artikelnummer_klant": sku,
             "artikelnummer_kwabo_matched": matched, "hoeveelheid": 10.0,
             "eenheid": "STUK", "prijs_per_eenheid": prijs},
        ],
        "needs_review_fields": [],
    }


@pytest.mark.asyncio
async def test_816_flags_when_alternative_has_price(session, app_engine):
    session.add(Prijsafspraak(klant_nr="K9", kwabo_artikelnr="238531", prijs=24.8))
    session.add(ArtikelKruisverwijzing(klant_nr="K9", klant_artikelnr="SKU-816",
                                       kwabo_artikelnr="238531"))
    session.commit()

    out = await vp.validate_prices_node(_state(prijs=None, matched="23853"))
    regel = out["orderregels"][0]

    # Gevlagd, alternatief getoond, matched ONgewijzigd (geen auto-switch).
    assert regel["artikelnummer_kwabo_matched"] == "23853"
    assert (regel.get("artikel_prijs_alternatief") or {}).get("kwabo") == "238531"
    assert any("ARTIKEL ONZEKER" in w and "238531" in w
               for w in out["validatie_warnings"])
    assert "orderregels[0].artikelnummer_kwabo_matched" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_no_flag_when_matched_has_price(session, app_engine):
    session.add(Prijsafspraak(klant_nr="K9", kwabo_artikelnr="23853", prijs=12.0))
    session.add(ArtikelKruisverwijzing(klant_nr="K9", klant_artikelnr="SKU-816",
                                       kwabo_artikelnr="238531"))
    session.commit()

    out = await vp.validate_prices_node(_state(prijs=None, matched="23853"))
    regel = out["orderregels"][0]
    assert regel.get("artikel_prijs_alternatief") is None
    assert not any("ARTIKEL ONZEKER" in w for w in out["validatie_warnings"])


@pytest.mark.asyncio
async def test_data_gated_empty_table_is_noop(session, app_engine):
    # Wel een kruisverwijzing, maar GEEN enkele prijsrij -> geen geprijsd
    # alternatief -> geen vlag (geen schijn-validatie op lege data).
    session.add(ArtikelKruisverwijzing(klant_nr="K9", klant_artikelnr="SKU-816",
                                       kwabo_artikelnr="238531"))
    session.commit()

    out = await vp.validate_prices_node(_state(prijs=None, matched="23853"))
    regel = out["orderregels"][0]
    assert regel.get("artikel_prijs_alternatief") is None
    assert not any("ARTIKEL ONZEKER" in w for w in out["validatie_warnings"])


@pytest.mark.asyncio
async def test_deel_b_warning_text_corrected(session, app_engine):
    # Mailprijs aanwezig, geen prijsafspraak -> waarheidsgetrouwe tekst.
    out = await vp.validate_prices_node(_state(prijs=12.65, matched="23853"))
    geen_afspraak = [w for w in out["validatie_warnings"] if "Geen prijsafspraak" in w]
    assert geen_afspraak
    assert any("NAV berekent de prijs zelf" in w for w in geen_afspraak)
    assert not any("1-op-1 doorgezet" in w for w in out["validatie_warnings"])
