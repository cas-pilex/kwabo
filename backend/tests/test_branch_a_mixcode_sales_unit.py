"""FASE 1 + gap-fix — PPG #941 (XO092614): een NAV-kaart die een MIX-staffelcode
als verkoopeenheid (Sales_Unit_of_Measure) draagt is een datafout. Die code mag
NOOIT stil als verkoopeenheid op een niet-mix-order, maar moet worden vertaald
naar de PLAIN pallet-eenheid van het artikel (zelfde qty_per_base) — zodat de
regel consistent is met zuster-artikelen (23522 -> PALLET 2, net als 23523) en
GEEN handmatige review vergt. Alleen als er geen schone pallet-vertaling is valt
hij terug op de base-eenheid + review-vlag.
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
async def test_mixcode_verkoopeenheid_vertaalt_naar_plain_pallet(session):
    """23522: kaart-verkoop_eenheid = M1PAL30 (mix-UOM, qty 30) → vertaald naar de
    PLAIN PALLET-eenheid (60 STUK / 30 = 2 PALLET), NIET STUK, GEEN review-vlag."""
    _set_mix(session, "10001", False)
    _kaart(session, "23522", basis="STUK", verkoop="M1PAL30",
           eenheden=[("STUK", 1.0, False), ("M1PAL30", 30.0, True),
                     ("PALLET", 30.0, False), ("FCA PAL30", 30.0, False),
                     ("AFHAAL", 30.0, False)])
    out = await apply_mixprijzen_node(_state(_regel("23522")), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "PALLET"
    assert r["verkoop_aantal"] == 2
    assert not any("verkoop_eenheid" in p for p in out["needs_review_fields"])


@pytest.mark.asyncio
async def test_mixcode_zonder_plain_pallet_valt_terug_op_base_met_review(session):
    """Geen schone pallet-vertaling (alleen de mix-code + base) → terugval op
    base + review-vlag (veilig, nooit stil de mix-code)."""
    _set_mix(session, "10001", False)
    _kaart(session, "29999", basis="STUK", verkoop="M1PAL30",
           eenheden=[("STUK", 1.0, False), ("M1PAL30", 30.0, True)])
    out = await apply_mixprijzen_node(_state(_regel("29999")), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "STUK"
    assert r["verkoop_aantal"] == 60.0
    assert any("verkoop_eenheid" in p for p in out["needs_review_fields"])
    assert any("M1PAL30" in w for w in out["validatie_warnings"])


@pytest.mark.asyncio
async def test_echte_pallet_verkoopeenheid_blijft(session):
    """23523: kaart-verkoop_eenheid = PALLET (géén mix-code) → blijft PALLET
    (60 STUK → 2 PALLET), géén review-vlag."""
    _set_mix(session, "10001", False)
    _kaart(session, "23523", basis="STUK", verkoop="PALLET",
           eenheden=[("STUK", 1.0, False), ("PALLET", 30.0, False),
                     ("M1PAL30", 30.0, True)])
    out = await apply_mixprijzen_node(_state(_regel("23523")), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "PALLET"
    assert r["verkoop_aantal"] == 2
    assert not any("verkoop_eenheid" in p for p in out["needs_review_fields"])
