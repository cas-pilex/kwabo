"""FASE 1 — BAUHAUS #944 (1049577521): een exacte afleveradres-postcode is het
sterkste leversignaal en wint vóór de order-tekst-heuristiek.

Echte casus: afleveradres BAUHAUS Hengelo 7559 SR, maar de pijplijn koos
ship-to 3981 LB BUNNIK omdat BAUHAUS' eigen factuurstad 'Bunnik' in de PDF-tekst
staat → 'plaats_in_order_text' pakte Bunnik vóórdat de exacte leverpostcode
(7559 SR, óók een kandidaat) ooit werd gescoord.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import KlantenkaartShipTo
from kwabo.db.repository import ShipToRepo
from kwabo.graph.nodes.select_ship_to import select_ship_to_node

_BAUHAUS_SHIPTO = [
    ("2635 BS", "Den Hoorn", "2635 BS"),
    ("3981 LB", "BUNNIK", "3981 LB"),
    ("5916 PR", "VENLO", "5916 PR"),
    ("7559 SR", "HENGELO OV", "7559 SR"),
    ("9723 AW", "GRONINGEN", "9723 AW"),
]


def _seed(session):
    for code, plaats, pc in _BAUHAUS_SHIPTO:
        session.add(KlantenkaartShipTo(
            klant_nr="61854", ship_to_code=code, naam="Bauhaus Nederland C.V.",
            straat="x", postcode=pc, plaats=plaats, land="NL", is_default=False))
    session.commit()


@pytest.mark.asyncio
async def test_exacte_leverpostcode_wint_van_factuurstad_in_tekst(session):
    _seed(session)
    state = {
        "email_id": "bauhaus944",
        "klant_match": {"navision_klantnr": "61854"},
        # De factuurstad 'Bunnik' staat in de order-tekst (zou de oude
        # plaats_in_order_text-heuristiek naar 3981 LB sturen).
        "email_body": "BAUHAUS Nederland C.V., Runnenburg 12, 3981 AZ Bunnik. "
                      "Afleveradres: Het Plein 10, 7559 SR Hengelo.",
        "afleveradres": {"naam": "BAUHAUS Vestiging 462", "straat": "Het Plein 10",
                         "postcode": "7559 SR", "plaats": "Hengelo"},
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=ShipToRepo(session))
    assert out["ship_to_gekozen"] == "7559 SR"


@pytest.mark.asyncio
async def test_meerdere_kandidaten_zelfde_postcode_valt_terug_op_scoring(session):
    """Twee kandidaten met exact dezelfde postcode → geen unieke postcode-winnaar;
    de bestaande scoring/heuristiek beslist (geen regressie)."""
    session.add(KlantenkaartShipTo(klant_nr="70001", ship_to_code="A", naam="Loc A",
                straat="x", postcode="1000 AA", plaats="Alpha", land="NL", is_default=False))
    session.add(KlantenkaartShipTo(klant_nr="70001", ship_to_code="B", naam="Loc B Beta",
                straat="x", postcode="1000 AA", plaats="Beta", land="NL", is_default=False))
    session.commit()
    state = {
        "email_id": "tie",
        "klant_match": {"navision_klantnr": "70001"},
        "email_body": "lever in Beta",
        "afleveradres": {"postcode": "1000 AA", "plaats": "Beta"},
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=ShipToRepo(session))
    assert out["ship_to_gekozen"] == "B"  # via plaats/naam, niet de postcode-shortcut
