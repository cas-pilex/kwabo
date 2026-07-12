"""FASE 2 (F2.2) — mix-ambiguïteit is een REGEL-eigenschap, geen order-gif.

Her-diagnose 10-7 (FASE1_DIAGNOSE.md, categorie 3): bij echte mix-klanten
(Veris #685: 8 regels, Witzand #718) zette één onresolveerbare regel de
order-brede `ambiguous`-boolean, waardoor ÁLLE regels mix_uom=None + vlag
kregen (n_actief=0) — de mix-laag koos nooit iets en de reviewer kreeg een
vlag-muur zonder handvat.

Contract dat hier vastligt:
  * een regel die niet naar hele pallets omrekent (of een onbesliste
    multi-familie heeft) krijgt ZELF de mix_uom-vlag; schone regels krijgen
    gewoon hun tier;
  * de staffelbasis (order-totaal) telt alleen de resolveerbare regels en
    dat wordt EXPLICIET gemeld via een validatie-warning (geen stille
    versmalling van de basis);
  * staffelranden per opdracht-matrix E5: hoogste M-drempel <= totaal;
    onder de laagste tier wordt naar de laagste geklemd; één tier is
    gewoon die tier.
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
    session.add(ArtikelEenheid(
        kwabo_artikelnr=artikelnr, eenheid_code=code,
        qty_per_base=qty_per_base, is_mix_uom=False,
    ))
    session.commit()


def _add_mix_tiers(session, artikelnr: str, tiers: list[int], rpp: int, *, base="ROL") -> None:
    _add_uom(session, artikelnr, base, 1.0)
    for t in tiers:
        _add_uom(session, artikelnr, f"M{t}PAL{rpp}", float(rpp))


def _regel(positie: int, artikelnr: str, hoeveelheid: float, eenheid: str = "ROL") -> dict:
    return {
        "positie": positie,
        "artikelnummer_kwabo_matched": artikelnr,
        "hoeveelheid": hoeveelheid,
        "eenheid": eenheid,
        "eenheid_origineel": eenheid,
    }


def _state(regels: list[dict]) -> dict:
    return {
        "email_id": "f22-test",
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": regels,
        "needs_review_fields": [],
        "validatie_warnings": [],
    }


async def _run(session, state):
    return await apply_mixprijzen_node(state, session=session)


# ---------- per-regel-ambiguïteit (Veris-klasse) ----------

@pytest.mark.asyncio
async def test_onresolveerbare_regel_vergiftigt_niet_de_rest(session):
    """#685-klasse: regel 3 (22 ROL bij 30/pallet = 0,73 pallet) is geen hele
    pallet — alleen DIE regel hoort de vlag; regel 1/2 krijgen hun tier."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [1, 7, 10], 30)
    _add_mix_tiers(session, "23546", [1, 7, 10], 60)
    _add_mix_tiers(session, "23924", [1, 7, 10], 30)
    out = await _run(session, _state([
        _regel(1, "23544", 150),   # 5 pallets
        _regel(2, "23546", 120),   # 2 pallets
        _regel(3, "23924", 22),    # 0,73 pallet -> onresolveerbaar
    ]))
    r1, r2, r3 = out["orderregels"]
    # staffelbasis = 5 + 2 = 7 -> hoogste tier <= 7 = M7
    assert r1["mix_uom_gekozen"] == "M7PAL30"
    assert r1["mix_aantal"] == 5
    assert r2["mix_uom_gekozen"] == "M7PAL60"
    assert r2["mix_aantal"] == 2
    assert r3["mix_uom_gekozen"] is None
    nrf = out["needs_review_fields"]
    assert "mix_uom:3" in nrf
    assert "mix_uom:1" not in nrf
    assert "mix_uom:2" not in nrf
    assert out["mixprijzen_actief"] is True
    assert out["order_mix_total_pallets"] == 7


@pytest.mark.asyncio
async def test_staffelbasis_warning_bij_uitgesloten_regels(session):
    """De versmalde staffelbasis mag nooit stil zijn (grondwet: geen stille
    versmalling): een warning benoemt de uitgesloten positie(s)."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [1, 7], 30)
    _add_mix_tiers(session, "23924", [1, 7], 30)
    out = await _run(session, _state([
        _regel(1, "23544", 30),   # 1 pallet
        _regel(2, "23924", 22),   # onresolveerbaar
    ]))
    warnings = " | ".join(out.get("validatie_warnings") or [])
    assert "staffelbasis" in warnings.lower()
    assert "2" in warnings  # de uitgesloten positie is benoemd


@pytest.mark.asyncio
async def test_multi_familie_zonder_sales_uom_vlagt_alleen_die_regel(session):
    """Een artikel met mix-codes in twee pallet-families (30 én 35) zonder
    beslissende kaart-verkoopeenheid is regel-ambigu — de zusterregel met één
    familie krijgt gewoon zijn tier."""
    _set_klant_mix(session, "10001", True)
    _add_uom(session, "88801", "ROL", 1.0)
    _add_uom(session, "88801", "M1PAL30", 30.0)
    _add_uom(session, "88801", "M1PAL35", 35.0)   # tweede familie, geen sales-uom
    _add_mix_tiers(session, "23544", [1, 7], 30)
    out = await _run(session, _state([
        _regel(1, "88801", 60),
        _regel(2, "23544", 30),   # 1 pallet
    ]))
    r1, r2 = out["orderregels"]
    assert r1["mix_uom_gekozen"] is None
    assert "mix_uom:1" in out["needs_review_fields"]
    assert r2["mix_uom_gekozen"] == "M1PAL30"
    assert r2["mix_aantal"] == 1
    assert "mix_uom:2" not in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_alle_regels_onresolveerbaar_alles_gevlagd(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23924", [1, 7], 30)
    out = await _run(session, _state([_regel(1, "23924", 22)]))
    assert out["orderregels"][0]["mix_uom_gekozen"] is None
    assert "mix_uom:1" in out["needs_review_fields"]
    assert out["mixprijzen_actief"] is False


# ---------- staffelranden (opdracht-matrix E5: 1/8/12 -> M1/M7/M10) ----------

@pytest.mark.asyncio
async def test_staffelrand_totaal_1_kiest_m1(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [1, 7, 10], 30)
    out = await _run(session, _state([_regel(1, "23544", 30)]))
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M1PAL30"


@pytest.mark.asyncio
async def test_staffelrand_totaal_8_kiest_m7(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [1, 7, 10], 30)
    out = await _run(session, _state([_regel(1, "23544", 240)]))  # 8 pallets
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M7PAL30"


@pytest.mark.asyncio
async def test_staffelrand_totaal_12_kiest_m10(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [1, 7, 10], 30)
    out = await _run(session, _state([_regel(1, "23544", 360)]))  # 12 pallets
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M10PAL30"


@pytest.mark.asyncio
async def test_staffelrand_onder_laagste_tier_klemt_omhoog(session):
    """Tiers [7, 10], totaal 3 -> klem omhoog naar de laagste tier (M7)."""
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [7, 10], 30)
    out = await _run(session, _state([_regel(1, "23544", 90)]))  # 3 pallets
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M7PAL30"


@pytest.mark.asyncio
async def test_staffelrand_precies_een_tier(session):
    _set_klant_mix(session, "10001", True)
    _add_mix_tiers(session, "23544", [7], 30)
    out = await _run(session, _state([_regel(1, "23544", 30)]))  # 1 pallet
    assert out["orderregels"][0]["mix_uom_gekozen"] == "M7PAL30"
