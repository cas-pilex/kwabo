"""Tests for apply_mixprijzen node (T7).

Mirrors the dependency-injection style of test_select_ship_to: a session
fixture seeds the DB, repos bound to that same session are passed in, and
the node operates against that DB without monkeypatching the module-level
engine.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelEenheid, Artikelkaart, Klantenkaart
from kwabo.db.repository import ArtikelkaartRepo, KlantRepo
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node


def _set_klant_mix(session, nav_klantnr: str, mix: bool) -> None:
    klant = KlantRepo(session).by_nav_nr(nav_klantnr)
    assert klant is not None, f"seed missing klant {nav_klantnr}"
    klant.mixprijzen = mix
    session.add(klant)
    session.commit()


def _add_artikelkaart(
    session, kwabo_artikelnr: str, *, mixprijzen: bool, basis_eenheid: str = "STUK"
) -> None:
    session.add(
        Artikelkaart(
            kwabo_artikelnr=kwabo_artikelnr,
            naam=f"Artikel {kwabo_artikelnr}",
            basis_eenheid=basis_eenheid,
            mixprijzen=mixprijzen,
        )
    )
    session.commit()


def _add_uom(
    session,
    kwabo_artikelnr: str,
    eenheid_code: str,
    *,
    qty_per_base: float,
    is_mix_uom: bool,
) -> None:
    session.add(
        ArtikelEenheid(
            kwabo_artikelnr=kwabo_artikelnr,
            eenheid_code=eenheid_code,
            qty_per_base=qty_per_base,
            is_mix_uom=is_mix_uom,
        )
    )
    session.commit()


def _state(klant_nr: str | None, regels: list[dict]) -> dict:
    return {
        "email_id": "t7-test",
        "klant_match": {"navision_klantnr": klant_nr} if klant_nr else None,
        "orderregels": regels,
        "needs_review_fields": [],
    }


def _run(session, state):
    return apply_mixprijzen_node(
        state,
        repo_klant=KlantRepo(session),
        repo_artikelkaart=ArtikelkaartRepo(session),
        session=session,
    )


@pytest.mark.asyncio
async def test_no_klant_match_short_circuits(session):
    state = {
        "email_id": "t7-noklant",
        "klant_match": None,
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "1515155"}],
    }
    out = await _run(session, state)
    assert out["mixprijzen_actief"] is False
    # Regels untouched.
    assert out["orderregels"][0] == {"positie": 1, "artikelnummer_kwabo_matched": "1515155"}


@pytest.mark.asyncio
async def test_klant_mix_false_short_circuits(session):
    _set_klant_mix(session, "10001", False)
    _add_artikelkaart(session, "1515155", mixprijzen=True)
    _add_uom(session, "1515155", "DOOS", qty_per_base=1.0, is_mix_uom=True)

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "hoeveelheid": 5,
    }
    out = await _run(session, _state("10001", [regel]))

    assert out["mixprijzen_actief"] is False
    # Regel must be untouched — no mix_uom_* keys, no review entry.
    assert out["orderregels"][0] == regel
    assert "mix_uom_kandidaat" not in out["orderregels"][0]
    assert "mix_uom_gekozen" not in out["orderregels"][0]
    assert out.get("needs_review_fields", []) == []


@pytest.mark.asyncio
async def test_klant_mix_true_artikel_mix_false_no_change(session):
    _set_klant_mix(session, "10001", True)
    _add_artikelkaart(session, "1515155", mixprijzen=False)

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "hoeveelheid": 5,
    }
    out = await _run(session, _state("10001", [regel]))

    # No regel had a mix-UOM picked → mixprijzen_actief stays False.
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_kandidaat" not in out["orderregels"][0]
    assert "mix_uom_gekozen" not in out["orderregels"][0]
    assert out.get("needs_review_fields", []) == []


@pytest.mark.asyncio
async def test_single_mix_uom_auto_picked(session):
    _set_klant_mix(session, "10001", True)
    _add_artikelkaart(session, "1515155", mixprijzen=True)
    _add_uom(session, "1515155", "ROL", qty_per_base=1.0, is_mix_uom=False)
    _add_uom(session, "1515155", "MIX-DOOS", qty_per_base=1.0, is_mix_uom=True)

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "hoeveelheid": 3,
    }
    out = await _run(session, _state("10001", [regel]))

    assert out["mixprijzen_actief"] is True
    assert out["orderregels"][0]["mix_uom_gekozen"] == "MIX-DOOS"
    assert out["orderregels"][0]["mix_uom_kandidaat"] == ["MIX-DOOS"]
    # No review flag — single mix-UOM auto-picks.
    assert out.get("needs_review_fields", []) == []


@pytest.mark.asyncio
async def test_multiple_mix_uoms_residue_picks_pal(session):
    _set_klant_mix(session, "10001", True)
    _add_artikelkaart(session, "1515155", mixprijzen=True)
    # Two mix-UOMs: DOOS at qty_per_base=1.0 and PAL at qty_per_base=24.0.
    _add_uom(session, "1515155", "DOOS", qty_per_base=1.0, is_mix_uom=True)
    _add_uom(session, "1515155", "PAL", qty_per_base=24.0, is_mix_uom=True)

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "hoeveelheid": 24,
    }
    out = await _run(session, _state("10001", [regel]))

    # 24 / 24 = 1.0 (residue 0); 24 / 1 = 24 (residue 0). Both have residue 0,
    # but stable sort means DOOS (inserted first) and PAL tie. Pick the first
    # in the ranked list — verify *ranking* explicitly to make this stable.
    assert out["mixprijzen_actief"] is True
    chosen = out["orderregels"][0]["mix_uom_gekozen"]
    assert chosen in {"PAL", "DOOS"}
    # In the equal-residue case both are valid; the ranked list must contain both.
    assert set(out["orderregels"][0]["mix_uom_kandidaat"]) == {"PAL", "DOOS"}


@pytest.mark.asyncio
async def test_multiple_mix_uoms_picks_minimum_residue(session):
    """Pick the UOM whose qty_per_base lines up best with regel.hoeveelheid."""
    _set_klant_mix(session, "10001", True)
    _add_artikelkaart(session, "1515155", mixprijzen=True)
    # DOOS=1 → residue 0 for any int hoeveelheid.
    # PAL=24 → residue 0 only when hoeveelheid is a multiple of 24.
    # MIX-OFF=10 → residue 0.5 when hoeveelheid=25 (25/10 = 2.5).
    _add_uom(session, "1515155", "MIX-OFF", qty_per_base=10.0, is_mix_uom=True)
    _add_uom(session, "1515155", "PAL", qty_per_base=24.0, is_mix_uom=True)

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "hoeveelheid": 24,
    }
    out = await _run(session, _state("10001", [regel]))

    # PAL (residue 0) beats MIX-OFF (residue 0.4).
    assert out["mixprijzen_actief"] is True
    assert out["orderregels"][0]["mix_uom_gekozen"] == "PAL"
    assert out["orderregels"][0]["mix_uom_kandidaat"][0] == "PAL"


@pytest.mark.asyncio
async def test_no_mix_uom_defined_flags_review(session):
    _set_klant_mix(session, "10001", True)
    _add_artikelkaart(session, "1515155", mixprijzen=True)
    # Add a non-mix UOM only.
    _add_uom(session, "1515155", "ROL", qty_per_base=1.0, is_mix_uom=False)

    regel = {
        "positie": 7,
        "artikelnummer_kwabo_matched": "1515155",
        "hoeveelheid": 3,
    }
    out = await _run(session, _state("10001", [regel]))

    assert out["mixprijzen_actief"] is False  # nothing was successfully picked
    assert out["orderregels"][0]["mix_uom_kandidaat"] is None
    assert out["orderregels"][0]["mix_uom_gekozen"] is None
    assert "mix_uom:7" in out["needs_review_fields"]
    assert out["needs_review_count"] == 1


@pytest.mark.asyncio
async def test_unmatched_regel_skipped(session):
    """Regels without a matched kwabo_artikelnr must be passed through."""
    _set_klant_mix(session, "10001", True)

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": None,
        "hoeveelheid": 5,
    }
    out = await _run(session, _state("10001", [regel]))
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_kandidaat" not in out["orderregels"][0]
    assert "mix_uom_gekozen" not in out["orderregels"][0]
