"""Tests for the needs_review threshold in match_articles (Nico-reported bug).

Before this fix: any fuzzy/manual match triggered a review warning even when
the confidence was high (≥0.85). Result: Nico saw "1 velden vereisen
aanvulling" on every order. The threshold now keys solely on confidence.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelKruisverwijzing
from kwabo.graph.nodes.match_articles import match_articles_node


@pytest.fixture
def app_engine(session, monkeypatch):
    """Bind the node's module-level engine to the test DB."""
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_articles as ma_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


def _state(klant_nr: str, regels: list[dict]) -> dict:
    return {
        "email_id": "needs-review-test",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": {"navision_klantnr": klant_nr},
        "orderregels": regels,
    }


def _meta_for(out: dict, idx: int) -> dict:
    return ((out.get("_meta") or {}).get("orderregels") or [])[idx][
        "artikelnummer_kwabo_matched"
    ]


@pytest.mark.asyncio
async def test_high_confidence_fuzzy_match_does_not_need_review(session, app_engine):
    """Fuzzy match on a near-exact description should clear the warning.
    Pre-fix this returned needs_review=True purely because methode='fuzzy'.
    """
    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "X",
                "artikelnummer_kwabo": None,
                # Seed item 1515155 has displayName "Ferney stucloper 120cm".
                "omschrijving": "Ferney stucloper 120cm",
                "hoeveelheid": 1,
            }
        ],
    )
    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] in ("fuzzy", "klantenkaart", "history")
    assert regel["match_confidence"] >= 0.85
    meta = _meta_for(out, 0)
    assert meta["needs_review"] is False, (
        f"high-confidence ({regel['match_confidence']}) {regel['match_methode']} "
        "match must not be flagged for review"
    )


@pytest.mark.asyncio
async def test_no_match_still_flags_needs_review(session, app_engine):
    """Manual fallback path (no match found) keeps needs_review=True so the
    reviewer is forced to pick an article."""
    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "TOTALLY-UNKNOWN-SKU",
                "artikelnummer_kwabo": None,
                "omschrijving": "",  # forces manual fallback
                "hoeveelheid": 1,
            }
        ],
    )
    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "manual"
    assert regel["artikelnummer_kwabo_matched"] is None
    meta = _meta_for(out, 0)
    assert meta["needs_review"] is True


@pytest.mark.asyncio
async def test_kruisverwijzing_match_at_095_does_not_need_review(session, app_engine):
    """Kruisverwijzing match scores 0.95 — same logical case as the fuzzy
    fix. Should clear needs_review."""
    session.add(
        ArtikelKruisverwijzing(
            klant_nr="10001",
            klant_artikelnr="ALT-1",
            kwabo_artikelnr="1515155",
            bron="customer",
        )
    )
    session.commit()
    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "ALT-1",
                "artikelnummer_kwabo": None,
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    )
    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "kruisverwijzing"
    assert regel["match_confidence"] >= 0.95
    meta = _meta_for(out, 0)
    assert meta["needs_review"] is False
