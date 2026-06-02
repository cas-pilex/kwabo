"""Europallet via item-UOM conversion (Cas' "60 stuks = 1 pallet").

These exercise the pure pallet_logic.compute_europallet with injected repos,
so no DB/engine is needed. The kennis-repo always returns None (no learned
ground truth) so we test the item-UOM-driven branch and its fallback.
"""
from __future__ import annotations

from kwabo.utils.pallet_logic import compute_europallet


class _NoKennis:
    def lookup(self, artikelnr, eenheid):
        return None


class _UOM:
    def __init__(self, code: str, qty_per_base: float):
        self.eenheid_code = code
        self.qty_per_base = qty_per_base


class _UomRepo:
    def __init__(self, mapping: dict[str, list[_UOM]]):
        self._m = mapping

    def list_eenheden(self, artikelnr: str):
        return self._m.get(artikelnr, [])


def _state(regels):
    return {"email_id": "e", "orderregels": regels}


def test_60_stuks_is_one_pallet():
    """60 STUK of an article with 60 pieces per pallet -> exactly 1 europallet."""
    repo = _UomRepo({"1001": [_UOM("STUK", 1), _UOM("PAL", 60)]})
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "1001",
         "eenheid_origineel": "STUK", "hoeveelheid": 60},
    ])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=repo)
    assert regel is not None
    assert regel["hoeveelheid"] == 1


def test_small_quantities_consolidate_to_one_pallet():
    """10 + 4 + 1 stuks of the same 60/pallet article = 0.25 pallet.

    Below the 0.5 threshold -> no europallet line. The point is they do NOT
    each become a pallet (that was the bug Cas flagged: "niet 14 europallets").
    """
    repo = _UomRepo({"1001": [_UOM("STUK", 1), _UOM("PAL", 60)]})
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "1001",
         "eenheid_origineel": "STUK", "hoeveelheid": 10},
        {"positie": 2, "artikelnummer_kwabo_matched": "1001",
         "eenheid_origineel": "STUK", "hoeveelheid": 4},
        {"positie": 3, "artikelnummer_kwabo_matched": "1001",
         "eenheid_origineel": "STUK", "hoeveelheid": 1},
    ])
    assert compute_europallet(state, repo=_NoKennis(), uom_repo=repo) is None


def test_rol_converts_via_pallet_uom():
    """70 ROL with a PAL35 unit (35 rolls/pallet) -> 2 pallets."""
    repo = _UomRepo({"2002": [_UOM("ROL", 1), _UOM("PAL35", 35)]})
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "2002",
         "eenheid_origineel": "ROL", "hoeveelheid": 70},
    ])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=repo)
    assert regel is not None
    assert regel["hoeveelheid"] == 2


def test_pal_line_counts_one_to_one():
    """A line already ordered in PAL counts 1:1 regardless of conversion data."""
    repo = _UomRepo({"3003": [_UOM("STUK", 1), _UOM("PAL", 48)]})
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "3003",
         "eenheid_origineel": "PAL", "hoeveelheid": 3},
    ])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=repo)
    assert regel is not None
    assert regel["hoeveelheid"] == 3


def test_ambiguous_pallet_uoms_fall_back_to_heuristic():
    """Two PAL variants and no plain PAL -> can't pick the conversion, so a
    STUK line contributes nothing (legacy heuristic), giving no europallet."""
    repo = _UomRepo({"4004": [_UOM("STUK", 1), _UOM("PAL30", 30), _UOM("PAL35", 35)]})
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "4004",
         "eenheid_origineel": "STUK", "hoeveelheid": 60},
    ])
    assert compute_europallet(state, repo=_NoKennis(), uom_repo=repo) is None


def test_no_uom_repo_keeps_legacy_behaviour():
    """Without item-UOM data a STUK line contributes nothing (unchanged)."""
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "1001",
         "eenheid_origineel": "STUK", "hoeveelheid": 600},
    ])
    assert compute_europallet(state, repo=_NoKennis(), uom_repo=None) is None
