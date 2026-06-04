"""Tests for apply_mixprijzen node (T7) — table-7002 staffel mechanism.

The node gates ONLY on the customer mixprijzen flag, computes the order-wide
total pallets across mix lines, and picks per line the highest staffel tier
(M{threshold}PAL{rolls}) whose threshold <= the order total — reading valid
codes + prices from the synced Verkoopprijs (NAV 7002) mirror via the
verkoopsoort cascade.

DI style mirrors test_select_ship_to: the `session` fixture seeds the DB
(klant 10001 exists), repos bind to that session via `session=`.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelEenheid, Verkoopprijs
from kwabo.db.repository import KlantRepo
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node


def _set_klant(session, nav_klantnr: str, *, mix: bool, prijsgroep: str | None = None) -> None:
    klant = KlantRepo(session).by_nav_nr(nav_klantnr)
    assert klant is not None, f"seed missing klant {nav_klantnr}"
    klant.mixprijzen = mix
    klant.prijsgroep = prijsgroep
    session.add(klant)
    session.commit()


def _add_uom(session, artikelnr: str, code: str, qty_per_base: float) -> None:
    session.add(
        ArtikelEenheid(
            kwabo_artikelnr=artikelnr,
            eenheid_code=code,
            qty_per_base=qty_per_base,
            is_mix_uom=False,
        )
    )
    session.commit()


def _add_vp(
    session,
    artikelnr: str,
    code: str,
    prijs: float,
    *,
    sales_type: str = "Customer",
    sales_code: str = "10001",
) -> None:
    session.add(
        Verkoopprijs(
            sales_type=sales_type,
            sales_code=sales_code,
            kwabo_artikelnr=artikelnr,
            eenheid_code=code,
            prijs=prijs,
            is_mix=bool(code),
        )
    )
    session.commit()


def _regel(positie: int, artikelnr: str | None, hoeveelheid: float, eenheid: str = "ROL") -> dict:
    return {
        "positie": positie,
        "artikelnummer_kwabo_matched": artikelnr,
        "hoeveelheid": hoeveelheid,
        "eenheid": eenheid,
        "eenheid_origineel": eenheid,
    }


def _state(klant_nr: str | None, regels: list[dict]) -> dict:
    return {
        "email_id": "t7-test",
        "klant_match": {"navision_klantnr": klant_nr} if klant_nr else None,
        "orderregels": regels,
        "needs_review_fields": [],
    }


async def _run(session, state):
    return await apply_mixprijzen_node(state, session=session)


@pytest.mark.asyncio
async def test_no_klant_match_short_circuits(session):
    out = await _run(session, _state(None, [_regel(1, "1515155", 30)]))
    assert out["mixprijzen_actief"] is False


@pytest.mark.asyncio
async def test_klant_mix_false_short_circuits(session):
    _set_klant(session, "10001", mix=False)
    _add_vp(session, "1515155", "M1PAL30", 100.0)
    regel = _regel(1, "1515155", 30)
    out = await _run(session, _state("10001", [regel]))
    assert out["mixprijzen_actief"] is False
    assert out["orderregels"][0] == regel  # untouched


@pytest.mark.asyncio
async def test_no_mix_codes_for_article_not_a_mix_line(session):
    """Mix customer, but the article only has a normal (empty-UOM) 7002 row."""
    _set_klant(session, "10001", mix=True)
    _add_vp(session, "1515155", "", 100.0)  # normal price only
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_gekozen" not in out["orderregels"][0]
    assert out.get("needs_review_fields", []) == []


@pytest.mark.asyncio
async def test_one_pallet_picks_m1(session):
    _set_klant(session, "10001", mix=True)
    _add_uom(session, "1515155", "ROL", 1.0)
    for code, prijs in [("M1PAL30", 600.0), ("M7PAL30", 575.0), ("M10PAL30", 560.0)]:
        _add_vp(session, "1515155", code, prijs)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))  # 30 ROL / 30 = 1 pallet
    assert out["order_mix_total_pallets"] == 1
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == "M1PAL30"
    assert r["mix_actieve_prijs"] == 600.0
    assert r["mix_uom_kandidaat"] == ["M1PAL30", "M7PAL30", "M10PAL30"]
    assert out["mixprijzen_actief"] is True


@pytest.mark.asyncio
async def test_eight_pallets_picks_m7(session):
    _set_klant(session, "10001", mix=True)
    _add_uom(session, "1515155", "ROL", 1.0)
    for code, prijs in [("M1PAL30", 600.0), ("M7PAL30", 575.0), ("M10PAL30", 560.0)]:
        _add_vp(session, "1515155", code, prijs)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 240)]))  # 240/30 = 8 pallets
    assert out["order_mix_total_pallets"] == 8
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M7PAL30"


@pytest.mark.asyncio
async def test_below_lowest_tier_clamps_up(session):
    _set_klant(session, "10001", mix=True)
    _add_uom(session, "1515155", "ROL", 1.0)
    for code in ("M5PAL30", "M7PAL30"):
        _add_vp(session, "1515155", code, 500.0)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 60)]))  # 2 pallets, below M5
    assert out["order_mix_total_pallets"] == 2
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M5PAL30"  # clamp up to lowest


@pytest.mark.asyncio
async def test_veris_multiline_shares_m33_with_own_pal_suffix(session):
    """Two mix lines, different articles/PAL suffixes; total 33 -> both M33."""
    _set_klant(session, "10001", mix=True)
    # Article A: 35 rolls/pallet; B: 60 rolls/pallet.
    _add_uom(session, "AAA", "ROL", 1.0)
    _add_uom(session, "BBB", "ROL", 1.0)
    for code in ("M1PAL35", "M33PAL35"):
        _add_vp(session, "AAA", code, 700.0)
    for code in ("M1PAL60", "M33PAL60"):
        _add_vp(session, "BBB", code, 900.0)
    # 23 pallets of A (23*35=805 ROL) + 10 pallets of B (10*60=600 ROL) = 33.
    regels = [_regel(1, "AAA", 805), _regel(2, "BBB", 600)]
    out = await _run(session, _state("10001", regels))
    assert out["order_mix_total_pallets"] == 33
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M33PAL35"
    assert out["orderregels"][1]["mix_uom_gekozen"] == "M33PAL60"
    assert out["mixprijzen_actief"] is True


@pytest.mark.asyncio
async def test_ambiguous_pallet_math_flags_review(session):
    """A mix line with non-positive quantity makes the order total ambiguous."""
    _set_klant(session, "10001", mix=True)
    _add_uom(session, "1515155", "ROL", 1.0)
    _add_vp(session, "1515155", "M1PAL30", 600.0)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 0)]))
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] is None
    assert "mix_uom:1" in out["needs_review_fields"]
    assert out["mixprijzen_actief"] is False


@pytest.mark.asyncio
async def test_inconsistent_pal_suffix_flags_review(session):
    """Same article exposing two different PAL suffixes is inconsistent NAV data."""
    _set_klant(session, "10001", mix=True)
    _add_uom(session, "1515155", "ROL", 1.0)
    _add_vp(session, "1515155", "M1PAL30", 600.0)
    _add_vp(session, "1515155", "M1PAL35", 600.0)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))
    assert out["orderregels"][0]["mix_uom_gekozen"] is None
    assert "mix_uom:1" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_cascade_falls_back_to_all_customers(session):
    """No Customer/group rows -> All_Customers tier governs."""
    _set_klant(session, "10001", mix=True, prijsgroep=None)
    _add_uom(session, "1515155", "ROL", 1.0)
    _add_vp(session, "1515155", "M1PAL30", 555.0, sales_type="All_Customers", sales_code="")
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M1PAL30"
    assert out["orderregels"][0]["mix_actieve_prijs"] == 555.0


@pytest.mark.asyncio
async def test_unmatched_regel_skipped(session):
    _set_klant(session, "10001", mix=True)
    regel = _regel(1, None, 5)
    out = await _run(session, _state("10001", [regel]))
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_gekozen" not in out["orderregels"][0]
