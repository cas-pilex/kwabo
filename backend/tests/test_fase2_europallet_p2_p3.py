"""FASE 2 (F2.6) — europallet-waardebewijs P2/P3 met pallet_plaatsen_basis-fixturedata.

De prod-tabel is leeg (0 rijen; GEBLOKKEERD op de vullijst van Nico/OPS) —
deze tests bewijzen dat het MECHANISME de K-targets (#832=1, #833=1) exact
oplevert zodra de data bestaat, inclusief de gedocumenteerde afronding
(ceil vanaf PALLET_THRESHOLD=0.5) op de grensgevallen. Fixture-waarden zijn
gelabelde reconstructies van de vullijst (1/33 plaats per stuk 238601 enz.).

Hergebruikt het test-harnas van test_europallet_databron (B4).
"""
from __future__ import annotations

from kwabo.utils.pallet_logic import europallet_breakdown

from test_europallet_databron import (  # noqa: F401 (test-harnas, geen tests)
    _KennisRepo,
    _PlaatsenRepo,
    _UomRepo,
    _regel,
    _state,
)


def _regels_833():
    """#833-reconstructie: 5 STUK 229231 + 15 STUK 238531 (deelpallets)."""
    return [
        {"positie": 1, "artikelnummer_kwabo_matched": "229231",
         "hoeveelheid": 5.0, "eenheid": "STUK", "eenheid_origineel": "STUK"},
        {"positie": 2, "artikelnummer_kwabo_matched": "238531",
         "hoeveelheid": 15.0, "eenheid": "STUK", "eenheid_origineel": "STUK"},
    ]


def test_p3_deelpallets_833_som_boven_drempel_wordt_1():
    """K-target #833: 5×(1/33) + 15×(1/33) = 0,606 ≥ 0,5 -> ceil -> 1."""
    bd = europallet_breakdown(
        _state(_regels_833()),
        repo=_KennisRepo(None),
        uom_repo=_UomRepo([], verkoop_eenheid="STUK"),
        plaatsen_repo=_PlaatsenRepo({("229231", "STUK"): 1 / 33,
                                     ("238531", "STUK"): 1 / 33}),
    )
    assert bd["europallet_aantal"] == 1
    assert {r["bron"] for r in bd["regels"]} == {"pallet_plaatsen_basis"}
    assert not bd["onbekend"]


def test_p3_som_net_onder_drempel_geeft_geen_pallet():
    """Grens: 0,45 < 0,5 -> geen europallet-regel (0), geen vlag, geen gok."""
    bd = europallet_breakdown(
        _state([_regel(art="229231", qty=15.0)]),
        repo=_KennisRepo(None),
        uom_repo=_UomRepo([], verkoop_eenheid="STUK"),
        plaatsen_repo=_PlaatsenRepo({("229231", "STUK"): 0.03}),  # 15×0,03=0,45
    )
    assert bd["europallet_aantal"] in (0, None)
    assert not bd["onbekend"]


def test_p3_som_precies_op_drempel_rondt_op():
    bd = europallet_breakdown(
        _state([_regel(art="229231", qty=25.0)]),
        repo=_KennisRepo(None),
        uom_repo=_UomRepo([], verkoop_eenheid="STUK"),
        plaatsen_repo=_PlaatsenRepo({("229231", "STUK"): 0.02}),  # 25×0,02=0,50
    )
    assert bd["europallet_aantal"] == 1


def test_p5_meerdere_pallets_som_en_ceil():
    """2,6 plaatsen -> 3 europallets (som + gedocumenteerde afronding)."""
    bd = europallet_breakdown(
        _state([_regel(art="238601", qty=66.0),      # 66/33 = 2,0
                _regel(art="229231", qty=20.0)]),    # 20×0,03 = 0,6
        repo=_KennisRepo(None),
        uom_repo=_UomRepo([], verkoop_eenheid="STUK"),
        plaatsen_repo=_PlaatsenRepo({("238601", "STUK"): 1 / 33,
                                     ("229231", "STUK"): 0.03}),
    )
    assert bd["europallet_aantal"] == 3
