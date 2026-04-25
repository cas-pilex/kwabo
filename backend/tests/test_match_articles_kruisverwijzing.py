"""Tests for the kruisverwijzing (item cross-reference) match step (T6).

Inserted as the second priority in match_articles, after exact and before
klantenkaart/history. Confidence 0.95 (just below exact 1.0).
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelKruisverwijzing, KlantenkaartArtikel
from kwabo.graph.nodes.match_articles import match_articles_node


@pytest.fixture
def app_engine(session, monkeypatch):
    """Swap the module-level engine so the node sees our test DB."""
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_articles as ma_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


def _insert_kruisverwijzing(
    session, klant_nr: str, klant_artikelnr: str, kwabo_artikelnr: str
) -> None:
    session.add(
        ArtikelKruisverwijzing(
            klant_nr=klant_nr,
            klant_artikelnr=klant_artikelnr,
            kwabo_artikelnr=kwabo_artikelnr,
            bron="customer",
        )
    )
    session.commit()


def _insert_klantenkaart_mapping(
    session, klant_nr: str, klant_artikelnr: str, kwabo_artikelnr: str
) -> None:
    session.add(
        KlantenkaartArtikel(
            klant_nr=klant_nr,
            klant_artikelnr=klant_artikelnr,
            kwabo_artikelnr=kwabo_artikelnr,
            omschrijving="t6 mapping",
        )
    )
    session.commit()


def _state(klant_nr: str, regels: list[dict]) -> dict:
    return {
        "email_id": "t6-test",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": {"navision_klantnr": klant_nr},
        "orderregels": regels,
    }


@pytest.mark.asyncio
async def test_kruisverwijzing_resolves_customer_sku_to_kwabo(session, app_engine):
    """Positive: regel with klant SKU resolves via kruisverwijzing."""
    _insert_kruisverwijzing(session, "10001", "ALT-123", "1515155")

    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "ALT-123",
                "artikelnummer_kwabo": None,
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    )

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "kruisverwijzing"
    assert regel["artikelnummer_kwabo_matched"] == "1515155"
    assert regel["match_confidence"] >= 0.95


@pytest.mark.asyncio
async def test_kruisverwijzing_unknown_falls_through(session, app_engine):
    """Negative: when no kruisverwijzing/klantenkaart hit, falls through to fuzzy or manual."""
    # Note: NO kruisverwijzing or klantenkaart inserted for "UNKNOWN".
    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "UNKNOWN",
                "artikelnummer_kwabo": None,
                # No omschrijving → fuzzy step is skipped → manual.
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    )

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    # Must NOT have matched via kruisverwijzing.
    assert regel["match_methode"] != "kruisverwijzing"
    # And must fall through to manual (no omschrijving for fuzzy).
    assert regel["match_methode"] == "manual"
    assert regel["artikelnummer_kwabo_matched"] is None


@pytest.mark.asyncio
async def test_kruisverwijzing_wins_over_klantenkaart(session, app_engine):
    """Order test: both kruisverwijzing AND klantenkaart for same key -> kruisverwijzing wins.

    Both rows resolve to a real NAV item, but to *different* numbers, so we
    can verify which path was taken.
    """
    # Klantenkaart says ALT-123 -> 228321 (also a real NAV mock item).
    _insert_klantenkaart_mapping(session, "10001", "ALT-123", "228321")
    # Kruisverwijzing says ALT-123 -> 1515155. Should win.
    _insert_kruisverwijzing(session, "10001", "ALT-123", "1515155")

    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "ALT-123",
                "artikelnummer_kwabo": None,
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    )

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "kruisverwijzing"
    assert regel["artikelnummer_kwabo_matched"] == "1515155"


@pytest.mark.asyncio
async def test_kruisverwijzing_skipped_without_klant_nr(session, app_engine):
    """If state has no klant_match, kruisverwijzing step is skipped (no klant_nr)."""
    _insert_kruisverwijzing(session, "10001", "ALT-123", "1515155")

    state = {
        "email_id": "t6-no-klant",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": None,
        "orderregels": [
            {
                "positie": 1,
                "artikelnummer_klant": "ALT-123",
                "artikelnummer_kwabo": None,
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    }

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    # Without klant_nr, both kruisverwijzing and klantenkaart steps are
    # skipped; falls straight through to fuzzy/manual.
    assert regel["match_methode"] != "kruisverwijzing"


@pytest.mark.asyncio
async def test_exact_kwabo_still_wins_over_kruisverwijzing(session, app_engine):
    """Sanity: existing exact-match priority is preserved (kruisverwijzing is #2, not #1)."""
    # Kruisverwijzing maps ALT-123 to 1515155.
    _insert_kruisverwijzing(session, "10001", "ALT-123", "1515155")

    state = _state(
        "10001",
        [
            {
                "positie": 1,
                "artikelnummer_klant": "ALT-123",
                # But the regel ALSO has an explicit valid kwabo nr -> exact wins.
                "artikelnummer_kwabo": "228321",
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    )

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "exact"
    assert regel["artikelnummer_kwabo_matched"] == "228321"
    assert regel["match_confidence"] == 1.0
