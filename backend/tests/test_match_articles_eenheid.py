"""match_articles must honour the customer's ordered unit when it is valid for
the article (per the synced item-UOM mirror), instead of forcing the article's
base unit — that is the "60 stuks != 60 pallets" fix. Unknown units fall back
to the base unit AND flag the line for review.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import Artikelkaart, ArtikelEenheid
from kwabo.graph.nodes import match_articles as ma_mod
from kwabo.graph.nodes.match_articles import match_articles_node


@pytest.fixture
def app_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


def _seed_article(session):
    # Base unit PAL, but STUK (60/pallet) is a valid alternative unit.
    session.add(Artikelkaart(kwabo_artikelnr="9001", naam="Loper", basis_eenheid="PAL"))
    session.add(ArtikelEenheid(kwabo_artikelnr="9001", eenheid_code="PAL", qty_per_base=60))
    session.add(ArtikelEenheid(kwabo_artikelnr="9001", eenheid_code="STUK", qty_per_base=1))
    session.commit()


def _state(eenheid: str):
    return {
        "email_id": "u",
        "klant_match": {"navision_klantnr": "10001"},
        "stappen_log": [],
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo": "9001",
             "eenheid": eenheid, "hoeveelheid": 60},
        ],
    }


@pytest.mark.asyncio
async def test_valid_customer_unit_is_kept(session, app_engine):
    _seed_article(session)
    out = await match_articles_node(_state("STUK"))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "9001"
    assert regel["eenheid"] == "STUK"          # honoured, not forced to PAL
    assert regel["eenheid_default"] == "PAL"
    assert "orderregels[0].eenheid" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_unknown_unit_falls_back_and_flags(session, app_engine):
    _seed_article(session)
    out = await match_articles_node(_state("DOOS"))  # not a valid UoM for 9001
    regel = out["orderregels"][0]
    assert regel["eenheid"] == "PAL"            # safe fallback to base
    assert regel["eenheid_origineel"] == "DOOS"
    assert "orderregels[0].eenheid" in out["needs_review_fields"]
    assert any("EENHEID CONTROLEREN" in w for w in out.get("validatie_warnings") or [])


@pytest.mark.asyncio
async def test_base_unit_order_not_flagged(session, app_engine):
    _seed_article(session)
    out = await match_articles_node(_state("PAL"))
    regel = out["orderregels"][0]
    assert regel["eenheid"] == "PAL"
    assert "orderregels[0].eenheid" not in (out.get("needs_review_fields") or [])
