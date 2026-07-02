"""Tests for the pure europallet computation (T8, herzien voor B4).

B4 (structurele upgrade): het leerbestand ``artikel_pallet_kennis`` en de
DOOS-/24-heuristiek zijn bewust UIT de telling (vervuild resp. gok); de
expliciete bron is ``pallet_plaatsen_basis`` per (artikel, eenheid). De
tests die eerder de kennis-/heuristiek-takken dekten, dekken nu het
equivalente gedrag via de plaatsen-stub — en verifiëren expliciet dat het
leerbestand GENEGEERD wordt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from kwabo.db.models import ArtikelPalletKennis
from kwabo.db.repository import PalletKennisRepo
from kwabo.graph.nodes.compute_europallet import compute_europallet_node
from kwabo.utils.pallet_logic import PALLET_ARTIKELNR, compute_europallet


@dataclass
class _Kennis:
    pallet_required: bool
    per_pallet: int = 24


class _StubRepo:
    """Drop-in for ``PalletKennisRepo`` for the pure-logic tests.

    Looks up ``(artikelnr, eenheid)`` against an in-memory dict keyed by
    ``(artikelnr, eenheid_uppercased)``. Returns ``None`` for misses so
    the heuristic branch can exercise.
    """

    def __init__(self, kennis: Optional[dict] = None) -> None:
        self._k = kennis or {}

    def lookup(self, artikelnr: str, eenheid: str):
        return self._k.get((artikelnr, (eenheid or "").upper()))


@dataclass
class _Plaatsen:
    plaatsen_per_eenheid: float


class _PlaatsenStub:
    """Drop-in voor ``PalletPlaatsenRepo`` (B4: de expliciete databron)."""

    def __init__(self, mapping: Optional[dict] = None) -> None:
        self._m = mapping or {}

    def lookup(self, artikelnr: str, eenheid: str):
        v = self._m.get((artikelnr, (eenheid or "").upper()))
        return _Plaatsen(plaatsen_per_eenheid=v) if v is not None else None


def _state(regels: list[dict]) -> dict:
    return {"orderregels": regels}


def test_empty_regels_returns_none():
    out = compute_europallet(_state([]), repo=_StubRepo())
    assert out is None


def test_no_orderregels_key_returns_none():
    out = compute_europallet({}, repo=_StubRepo())
    assert out is None


def test_stuk_with_no_kennis_skips_heuristic_returns_none():
    """STUK is not in the heuristic eenheden set — no contribution."""
    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "eenheid": "STUK",
        "hoeveelheid": 10,
    }
    out = compute_europallet(_state([regel]), repo=_StubRepo())
    assert out is None


def test_doos_via_plaatsen_basis_yields_one_pallet():
    """B4: DOOS telt alleen mee via de expliciete bron (1/24 plaats per doos);
    de oude /24-gok zonder bron bestaat niet meer."""
    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "eenheid": "DOOS",
        "hoeveelheid": 24,
    }
    out = compute_europallet(
        _state([regel]), repo=_StubRepo(),
        plaatsen_repo=_PlaatsenStub({("1515155", "DOOS"): 1 / 24}))
    assert out is not None
    assert out["artikelnummer_kwabo"] == PALLET_ARTIKELNR
    assert out["artikelnummer_kwabo_matched"] == PALLET_ARTIKELNR
    assert out["hoeveelheid"] == 1
    assert out["eenheid"] == "STUK"
    assert out["match_methode"] == "europallet_compute"
    assert out["positie"] == 2  # next-positie after the single regel


def test_doos_zonder_bron_is_onbekend_geen_gok():
    """B4: DOOS zonder plaatsen-waarde/NAV-maat -> géén pallet (en de node
    vlagt 'europallet onbekend' — zie test_europallet_databron.py)."""
    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "eenheid": "DOOS",
        "hoeveelheid": 24,
    }
    out = compute_europallet(_state([regel]), repo=_StubRepo())
    assert out is None


def test_two_doos_regels_sum_to_one_pallet():
    """12/24 + 12/24 = 1.0 → ceil(1.0) = 1 (via de expliciete bron)."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "A",
            "eenheid": "DOOS",
            "hoeveelheid": 12,
        },
        {
            "positie": 2,
            "artikelnummer_kwabo_matched": "B",
            "eenheid": "DOOS",
            "hoeveelheid": 12,
        },
    ]
    out = compute_europallet(
        _state(regels), repo=_StubRepo(),
        plaatsen_repo=_PlaatsenStub({("A", "DOOS"): 1 / 24, ("B", "DOOS"): 1 / 24}))
    assert out is not None
    assert out["hoeveelheid"] == 1
    assert out["positie"] == 3


def test_leerbestand_wordt_genegeerd_in_telling():
    """B4: het (vervuilde) leerbestand stuurt de telling NIET meer — zonder
    plaatsen-waarde of NAV-maat is de uitkomst 'geen pallet' (+ onbekend-vlag
    op node-niveau), niet 20/10=2."""
    kennis = {("ART", "ROL"): _Kennis(pallet_required=True, per_pallet=10)}
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "ROL",
            "hoeveelheid": 20,
        }
    ]
    out = compute_europallet(_state(regels), repo=_StubRepo(kennis))
    assert out is None


def test_plaatsen_basis_vervangt_kennis_per_pallet_10():
    """Dezelfde casus mét de expliciete bron: 20 ROL × 1/10 = 2 pallets."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "ROL",
            "hoeveelheid": 20,
        }
    ]
    out = compute_europallet(
        _state(regels), repo=_StubRepo(),
        plaatsen_repo=_PlaatsenStub({("ART", "ROL"): 1 / 10}))
    assert out is not None
    assert out["hoeveelheid"] == 2


def test_kennis_pallet_not_required_yields_none():
    """Kennis explicitly says no pallet — heuristic must NOT fire as fallback."""
    kennis = {("ART", "DOOS"): _Kennis(pallet_required=False, per_pallet=24)}
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 100,  # would fire heuristic if no kennis
        }
    ]
    out = compute_europallet(_state(regels), repo=_StubRepo(kennis))
    assert out is None


def test_existing_pallet_regel_is_skipped_no_double_counting():
    """If the input already contains a 19820 line, never re-count it."""
    regels = [
        # Regular regel with an explicit plaatsen-waarde (B4-bron).
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 24,
        },
        # Pre-existing pallet regel — must be ignored by the computation.
        {
            "positie": 2,
            "artikelnummer_kwabo_matched": PALLET_ARTIKELNR,
            "eenheid": "STUK",
            "hoeveelheid": 5,
        },
    ]
    out = compute_europallet(
        _state(regels), repo=_StubRepo(),
        plaatsen_repo=_PlaatsenStub({("ART", "DOOS"): 1 / 24}))
    assert out is not None
    # 24 × 1/24 = 1 — no contribution from the second (pallet) line.
    assert out["hoeveelheid"] == 1


def test_unmatched_regel_skipped():
    """A regel without artikelnummer_kwabo_matched contributes nothing."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": None,
            "eenheid": "DOOS",
            "hoeveelheid": 240,
        }
    ]
    out = compute_europallet(_state(regels), repo=_StubRepo())
    assert out is None


def test_total_below_threshold_returns_none():
    """6 × 1/24 = 0.25 < 0.5 → no pallet line (gedocumenteerde afrondingsregel)."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 6,
        }
    ]
    out = compute_europallet(
        _state(regels), repo=_StubRepo(),
        plaatsen_repo=_PlaatsenStub({("ART", "DOOS"): 1 / 24}))
    assert out is None


def test_partial_pallet_rounds_up():
    """36 × 1/24 = 1.5 → ceil = 2 (gedocumenteerde afrondingsregel)."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 36,
        }
    ]
    out = compute_europallet(
        _state(regels), repo=_StubRepo(),
        plaatsen_repo=_PlaatsenStub({("ART", "DOOS"): 1 / 24}))
    assert out is not None
    assert out["hoeveelheid"] == 2


@pytest.mark.asyncio
async def test_compute_europallet_node_sets_state(session):
    """The graph node stores the regel on state and does not touch orderregels.
    B4: de bron is de plaatsen-stub (het leerbestand telt niet meer mee)."""
    state = {
        "email_id": "t8-test",
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [
            {
                "positie": 1,
                "artikelnummer_kwabo_matched": "ART",
                "eenheid": "DOOS",
                "hoeveelheid": 48,
            }
        ],
    }

    out = await compute_europallet_node(
        state, repo=PalletKennisRepo(session),
        plaatsen_repo=_PlaatsenStub({("ART", "DOOS"): 1 / 24}))
    assert out["europallet_regel"] is not None
    assert out["europallet_regel"]["hoeveelheid"] == 2
    assert out["europallet_regel"]["artikelnummer_kwabo"] == PALLET_ARTIKELNR
    # orderregels MUST be untouched — only the new slot carries the pallet.
    assert len(out["orderregels"]) == 1
    assert out["orderregels"][0]["artikelnummer_kwabo_matched"] == "ART"


@pytest.mark.asyncio
async def test_compute_europallet_node_none_when_no_pallet_needed(session):
    state = {
        "email_id": "t8-test-empty",
        "orderregels": [
            {
                "positie": 1,
                "artikelnummer_kwabo_matched": "ART",
                "eenheid": "STUK",
                "hoeveelheid": 3,
            }
        ],
    }
    out = await compute_europallet_node(state, repo=PalletKennisRepo(session))
    assert out["europallet_regel"] is None
    assert len(out["orderregels"]) == 1
