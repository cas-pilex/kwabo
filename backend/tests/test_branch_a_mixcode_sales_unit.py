"""FASE 1 — PPG #941 (XO092614): een NAV-kaart die een MIX-staffelcode als
verkoopeenheid (Sales_Unit_of_Measure) draagt mag die NIET stil als
verkoopeenheid op een niet-mix-order zetten.

Echte casus: 3 ProGold-zusterartikelen, alle in STUK besteld, kregen
STUK / M1PAL30 / PALLET omdat 23522's kaart `verkoop_eenheid = M1PAL30` (een
mix-UOM, is_mix_uom=True) heeft. M1PAL30 is een mix-staffelcode, geen geldige
verkoopeenheid op een gewone order → terugval op base + review-vlag.
PALLET (23523) is wél een geldige verkoopeenheid en blijft.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import Artikelkaart, ArtikelEenheid
from kwabo.db.repository import KlantRepo
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node


def _kaart(session, nr, *, basis, verkoop, eenheden):
    session.add(Artikelkaart(kwabo_artikelnr=nr, naam=f"art {nr}",
                             basis_eenheid=basis, verkoop_eenheid=verkoop))
    for code, qty, mix in eenheden:
        session.add(ArtikelEenheid(kwabo_artikelnr=nr, eenheid_code=code,
                                   qty_per_base=qty, is_mix_uom=mix))
    session.commit()


def _set_mix(session, nr, mix):
    k = KlantRepo(session).by_nav_nr(nr)
    k.mixprijzen = mix
    session.add(k)
    session.commit()


def _state(regel):
    return {"email_id": "ppg941", "klant_match": {"navision_klantnr": "10001"},
            "orderregels": [regel], "needs_review_fields": [], "validatie_warnings": []}


def _regel(art, qty=60.0):
    return {"positie": 1, "artikelnummer_kwabo_matched": art, "hoeveelheid": qty,
            "eenheid": "STUK", "eenheid_origineel": "STUK", "eenheid_default": "STUK"}


@pytest.mark.asyncio
async def test_mixcode_verkoopeenheid_valt_terug_op_base_met_review(session):
    """23522: kaart-verkoop_eenheid = M1PAL30 (mix-UOM) → NIET als
    verkoopeenheid; terugval op STUK + review-vlag."""
    _set_mix(session, "10001", False)
    _kaart(session, "23522", basis="STUK", verkoop="M1PAL30",
           eenheden=[("STUK", 1.0, False), ("M1PAL30", 30.0, True),
                     ("PALLET", 30.0, False)])
    out = await apply_mixprijzen_node(_state(_regel("23522")), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] != "M1PAL30"
    assert r["verkoop_uom_gekozen"] == "STUK"
    assert r["verkoop_aantal"] == 60.0
    assert any("verkoop_eenheid" in p for p in out["needs_review_fields"])
    assert any("M1PAL30" in w for w in out["validatie_warnings"])


@pytest.mark.asyncio
async def test_echte_pallet_verkoopeenheid_blijft(session):
    """23523: kaart-verkoop_eenheid = PALLET (géén mix-code) → blijft de
    verkoopeenheid (60 STUK → 2 PALLET), géén review-vlag."""
    _set_mix(session, "10001", False)
    _kaart(session, "23523", basis="STUK", verkoop="PALLET",
           eenheden=[("STUK", 1.0, False), ("PALLET", 30.0, False),
                     ("M1PAL30", 30.0, True)])
    out = await apply_mixprijzen_node(_state(_regel("23523")), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "PALLET"
    assert r["verkoop_aantal"] == 2
    assert not any("verkoop_eenheid" in p for p in out["needs_review_fields"])
