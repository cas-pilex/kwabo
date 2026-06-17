"""Functie 3 DEEL A/C — een PAL-bestelling moet de geldige pallet-verkoopeenheid
gebruiken, niet stil terugvallen op STUK.

De extractor normaliseert "Paletten" naar "PAL" (eenheid_mapping). NAV's eigen
eenheid-code voor een artikel is echter vaak "PALLET" (qty_per_base=20 voor
23691). match_articles matchte de bestelde eenheid exact tegen de item-UoM-codes,
dus "PAL" != "PALLET" -> terugval op base STUK + review-vlag (faalgeval #819).

DEEL A: "PAL" brugt naar de ondubbelzinnige pallet-code "PALLET".
DEEL C: een echt ongeldige eenheid (ROL) valt nog steeds terug + vlag.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kwabo.db.models import Artikelkaart, ArtikelEenheid
from kwabo.graph.nodes import match_articles as ma_mod
from kwabo.graph.nodes.match_articles import match_articles_node
from kwabo.integrations.navision_steps import _emit_line_ops

STATES = Path(__file__).resolve().parent / "test_data" / "states"


@pytest.fixture
def app_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


def _seed_23691(session) -> None:
    """Echte masterdata 23691: base STUK, pallet-UoM PALLET (qty_per_base 20)."""
    session.add(Artikelkaart(kwabo_artikelnr="23691", naam="Stucloper 20/pallet",
                             basis_eenheid="STUK", verkoop_eenheid="PALLET"))
    rows = [r for r in json.loads((STATES / "artikel_eenheden.json").read_text("utf-8"))
            if r["kwabo_artikelnr"] == "23691"]
    assert rows, "geen UoM-rijen voor 23691 in de export"
    for r in rows:
        session.add(ArtikelEenheid(**r))
    session.commit()


def _state(eenheid: str, hoeveelheid: float = 4):
    return {
        "email_id": "f3a",
        "klant_match": {"navision_klantnr": "10001"},
        "stappen_log": [],
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo": "23691",
             "eenheid": eenheid, "hoeveelheid": hoeveelheid},
        ],
    }


@pytest.mark.asyncio
async def test_pallet_order_maps_to_pallet_uom(session, app_engine):
    """#819: 4 Paletten -> eenheid PALLET (geen stille STUK-terugval, geen vlag)."""
    _seed_23691(session)
    out = await match_articles_node(_state("PAL"))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "23691"
    assert regel["eenheid"] == "PALLET"            # niet STUK
    assert regel["eenheid_origineel"] == "PAL"
    assert regel["eenheid_default"] == "STUK"
    assert "orderregels[0].eenheid" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_pallet_order_emits_pallet_ops(session, app_engine):
    """De NAV-operaties tonen PALLET + quantity 4 (niet 4 STUK)."""
    _seed_23691(session)
    out = await match_articles_node(_state("PAL"))
    regel = out["orderregels"][0]
    ops = _emit_line_ops(regel, regel["artikelnummer_kwabo_matched"], "regel")
    bodies = [op["body"] for op in ops]
    assert {"unitOfMeasureCode": "PALLET"} in bodies
    assert {"quantity": 4} in bodies
    assert {"unitOfMeasureCode": "STUK"} not in bodies


@pytest.mark.asyncio
async def test_invalid_unit_still_falls_back_and_flags(session, app_engine):
    """DEEL C: een ongeldige eenheid (ROL, geen item-UoM van 23691) valt nog
    steeds veilig terug op base + review-vlag."""
    _seed_23691(session)
    out = await match_articles_node(_state("ROL"))
    regel = out["orderregels"][0]
    assert regel["eenheid"] == "STUK"              # base fallback
    assert regel["eenheid_origineel"] == "ROL"
    assert "orderregels[0].eenheid" in out["needs_review_fields"]
    assert any("EENHEID CONTROLEREN" in w for w in out.get("validatie_warnings") or [])
