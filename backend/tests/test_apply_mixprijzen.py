"""Tests for apply_mixprijzen node (T7) — staffel from PLX_ItemUnitOfMeasure.

The node gates ONLY on the customer mixprijzen flag, reads the article's mix
codes (M{n}PAL{r}) from ArtikelEenheid (mirrored from PLX_ItemUnitOfMeasure),
computes the order-wide total pallets, picks per line the highest tier whose
threshold <= the total, and converts the line quantity to pallets (mix_aantal).
NAV prices the chosen code itself on push.

DI style mirrors test_select_ship_to: the `session` fixture seeds the DB
(klant 10001 exists); the node binds repos to that session via `session=`.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelEenheid
from kwabo.db.repository import KlantRepo
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node


def _set_klant_mix(session, nav_klantnr: str, mix: bool) -> None:
    klant = KlantRepo(session).by_nav_nr(nav_klantnr)
    assert klant is not None, f"seed missing klant {nav_klantnr}"
    klant.mixprijzen = mix
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


def _add_mix_tiers(session, artikelnr: str, tiers: list[int], rpp: int, *, base="ROL") -> None:
    """Seed an article with a base unit + a set of M{tier}PAL{rpp} mix codes."""
    _add_uom(session, artikelnr, base, 1.0)
    for t in tiers:
        _add_uom(session, artikelnr, f"M{t}PAL{rpp}", float(rpp))


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
    _set_klant_mix(session, "10001", False)
    _add_mix_tiers(session, "1515155", [1, 7, 10], 30)
    regel = _regel(1, "1515155", 30)
    out = await _run(session, _state("10001", [regel]))
    assert out["mixprijzen_actief"] is False
    assert out["orderregels"][0] == regel  # untouched


@pytest.mark.asyncio
async def test_no_mix_codes_for_article_not_a_mix_line(session):
    """Mix customer, but the article has only a normal (non-M) unit."""
    _set_klant_mix(session, "10001", True)
    _add_uom(session, "1515155", "ROL", 1.0)
    _add_uom(session, "1515155", "PALLET", 30.0)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_gekozen" not in out["orderregels"][0]
    assert out.get("needs_review_fields", []) == []


@pytest.mark.asyncio
async def test_one_pallet_picks_m1_and_qty_in_pallets(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "1515155", [1, 7, 10], 30)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))  # 30 ROL / 30 = 1 pallet
    assert out["order_mix_total_pallets"] == 1
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == "M1PAL30"
    assert r["mix_aantal"] == 1
    assert r["mix_uom_kandidaat"] == ["M1PAL30", "M7PAL30", "M10PAL30"]
    assert out["mixprijzen_actief"] is True


@pytest.mark.asyncio
async def test_eight_pallets_picks_m7(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "1515155", [1, 7, 10], 30)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 240)]))  # 240/30 = 8 pallets
    assert out["order_mix_total_pallets"] == 8
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == "M7PAL30"
    assert r["mix_aantal"] == 8


@pytest.mark.asyncio
async def test_below_lowest_tier_clamps_up(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "1515155", [5, 7], 30)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 60)]))  # 2 pallets, below M5
    assert out["order_mix_total_pallets"] == 2
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M5PAL30"  # clamp up to lowest


@pytest.mark.asyncio
async def test_quantity_ordered_in_pallets(session):
    """Customer orders in PALLET; conversion still yields the pallet count."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "1515155", [1, 7, 10], 30)
    _add_uom(session, "1515155", "PALLET", 30.0)  # 1 PALLET = 30 ROL
    out = await _run(session, _state("10001", [_regel(1, "1515155", 8, eenheid="PALLET")]))
    assert out["order_mix_total_pallets"] == 8
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M7PAL30"
    assert out["orderregels"][0]["mix_aantal"] == 8


@pytest.mark.asyncio
async def test_veris_multiline_shares_tier_with_own_pal_suffix(session):
    """Two articles, different PAL suffixes; pallets sum to 33 -> both M33."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "AAA", [1, 33], 35)
    _add_mix_tiers(session, "BBB", [1, 33], 60)
    # 23 pallets of A (23*35=805 ROL) + 10 pallets of B (10*60=600 ROL) = 33.
    regels = [_regel(1, "AAA", 805), _regel(2, "BBB", 600)]
    out = await _run(session, _state("10001", regels))
    assert out["order_mix_total_pallets"] == 33
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M33PAL35"
    assert out["orderregels"][0]["mix_aantal"] == 23
    assert out["orderregels"][1]["mix_uom_gekozen"] == "M33PAL60"
    assert out["orderregels"][1]["mix_aantal"] == 10


@pytest.mark.asyncio
async def test_non_integer_pallets_flags_review(session):
    """A quantity that isn't a whole number of pallets is ambiguous."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "1515155", [1, 7], 30)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 40)]))  # 40/30 = 1.33
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] is None
    assert r["mix_aantal"] is None
    assert "mix_uom:1" in out["needs_review_fields"]
    assert out["mixprijzen_actief"] is False


@pytest.mark.asyncio
async def test_inconsistent_units_per_pallet_flags_review(session):
    """Two mix codes with genuinely different qty_per_base (physical pallet
    size) is inconsistent NAV data -> review."""
    _set_klant_mix(session, "10001", True)
    _add_uom(session, "1515155", "ROL", 1.0)
    _add_uom(session, "1515155", "M1PAL30", 30.0)
    _add_uom(session, "1515155", "M1PAL35", 35.0)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))
    assert out["orderregels"][0]["mix_uom_gekozen"] is None
    assert "mix_uom:1" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_typoed_pal_suffix_uses_qty_per_base(session):
    """Live prod item 15450: the PALxx suffix has typos (M5PAL528) but the
    authoritative Qty_per_Unit_of_Measure (== qty_per_base) is constant (1728).

    Pallets must be computed via qty_per_base, the chosen code is sent
    LITERALLY (typo and all — NAV resolves it), and no false review fires.
    The old suffix-based math would have read rolls/pallet = min(528, 1728) and
    flagged the order (3456/528 = 6.54, non-integer + inconsistent suffix).
    """
    _set_klant_mix(session, "10001", True)
    _add_uom(session, "15450", "STUK", 1.0)
    _add_uom(session, "15450", "M5PAL528", 1728.0)    # suffix 528 is a typo
    _add_uom(session, "15450", "M33PAL1728", 1728.0)
    # 3456 STUK / 1728 = 2 pallets -> below M5, clamp up to the lowest tier.
    out = await _run(session, _state("10001", [_regel(1, "15450", 3456, eenheid="STUK")]))
    assert out.get("needs_review_fields", []) == []
    assert out["order_mix_total_pallets"] == 2
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == "M5PAL528"  # literal NAV code, typo preserved
    assert r["mix_aantal"] == 2
    assert out["mixprijzen_actief"] is True


@pytest.mark.asyncio
async def test_ambiguity_keys_on_qty_per_base_not_suffix(session):
    """Same PALxx suffix but DIFFERENT qty_per_base is a real inconsistency ->
    review. Proves the ambiguity check keys on qty_per_base, not the suffix:
    the old suffix-based code would have seen one suffix ({40}) and proceeded."""
    _set_klant_mix(session, "10001", True)
    _add_uom(session, "15450", "ROL", 1.0)
    _add_uom(session, "15450", "M5PAL40", 40.0)
    _add_uom(session, "15450", "M33PAL40", 50.0)  # same suffix, different real qty
    out = await _run(session, _state("10001", [_regel(1, "15450", 200)]))
    assert out["orderregels"][0]["mix_uom_gekozen"] is None
    assert "mix_uom:1" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_unmatched_regel_skipped(session):
    _set_klant_mix(session, "10001", True)
    regel = _regel(1, None, 5)
    out = await _run(session, _state("10001", [regel]))
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_gekozen" not in out["orderregels"][0]


# ---- Fase 3: M-regels vastgezet op de ECHTE prod-export (grondwet 4) -------

def _seed_echte_eenheden(session, artikelnr: str) -> None:
    """Seed de échte ArtikelEenheid-rijen van een artikel uit de prod-export."""
    import json

    from conftest import STATES_DIR

    p = STATES_DIR / "artikel_eenheden.json"
    if not p.is_file():
        pytest.skip("artikel_eenheden.json ontbreekt — draai export_order_states.py")
    rows = [r for r in json.loads(p.read_text(encoding="utf-8"))
            if r["kwabo_artikelnr"] == artikelnr]
    assert rows, f"geen UoM-rijen voor {artikelnr} in export"
    for r in rows:
        session.add(ArtikelEenheid(**r))
    session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("pallets,verwacht", [(1, "M1PAL30"), (8, "M7PAL30"), (12, "M10PAL30")])
async def test_m4_staffel_echte_23685(session, pallets, verwacht):
    """M3/M4 op het échte artikel 23685 (M1/M2/M3/M7/M10 PAL30, 30/pallet):
    de M-waarde is een staffel-DREMPEL — kies de hoogste M <= totaal-pallets.
    1 -> M1PAL30, 8 -> M7PAL30, 12 -> M10PAL30."""
    _set_klant_mix(session, "10001", True)
    _seed_echte_eenheden(session, "23685")
    out = await _run(session, _state(
        "10001", [_regel(1, "23685", pallets * 30.0, eenheid="STUK")]))
    assert out["order_mix_total_pallets"] == pallets
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == verwacht
    assert r["mix_aantal"] == pallets


@pytest.mark.asyncio
async def test_m4_familie_keuze_echte_238601(session):
    """M4 "binnen de juiste PAL{Y}-familie": het échte artikel 238601 heeft
    mixcodes in DRIE families (PAL33/35/42). De verkoopeenheid van de kaart
    (PALLET33) kiest de familie; 66 base = 2 pallets -> M2PAL33."""
    from kwabo.db.models import Artikelkaart

    _set_klant_mix(session, "10001", True)
    session.add(Artikelkaart(kwabo_artikelnr="238601", naam="afdekvlies",
                             basis_eenheid="STUK", verkoop_eenheid="PALLET33"))
    session.commit()
    _seed_echte_eenheden(session, "238601")
    out = await _run(session, _state(
        "10001", [_regel(1, "238601", 66.0, eenheid="STUK")]))
    assert out["order_mix_total_pallets"] == 2
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == "M2PAL33"
    assert r["mix_aantal"] == 2
    assert all(c.endswith("PAL33") for c in r["mix_uom_kandidaat"])


@pytest.mark.asyncio
async def test_een_tier_clamp(session):
    """Edge: artikel met één enkele tier -> die tier, ook onder de drempel."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "1515155", [7], 30)
    out = await _run(session, _state("10001", [_regel(1, "1515155", 30)]))  # 1 pallet
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M7PAL30"
    assert out["orderregels"][0]["mix_aantal"] == 1


@pytest.mark.asyncio
async def test_artikel_zonder_mixcodes_gaat_via_branch_a(session):
    """Negatief (M2/verificatie 5): mix-klant, maar artikel zonder mixcodes
    -> géén mix; Branch A kiest de verkoopeenheid expliciet."""
    from kwabo.db.models import Artikelkaart

    _set_klant_mix(session, "10001", True)
    session.add(Artikelkaart(kwabo_artikelnr="909091", naam="t",
                             basis_eenheid="ROL", verkoop_eenheid="PALLET24"))
    session.commit()
    _add_uom(session, "909091", "ROL", 1.0)
    _add_uom(session, "909091", "PALLET24", 24.0)
    out = await _run(session, _state("10001", [_regel(1, "909091", 48.0)]))
    r = out["orderregels"][0]
    assert out["mixprijzen_actief"] is False
    assert "mix_uom_gekozen" not in r
    assert r["verkoop_uom_gekozen"] == "PALLET24"
    assert r["verkoop_aantal"] == 2
