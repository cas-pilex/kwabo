"""Tests for the pure europallet computation (T8).

The unit-style tests use a tiny in-memory stub for ``PalletKennisRepo`` so
they exercise the heuristic + kennis branches without touching the DB.
The graph-node-level test (``test_compute_europallet_node_sets_state``)
runs the async node against the real session fixture to confirm the
node correctly stores the regel under ``state["europallet_regel"]`` and
does NOT mutate ``state["orderregels"]``.
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


def test_doos_qty_24_no_kennis_yields_one_pallet():
    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "1515155",
        "eenheid": "DOOS",
        "hoeveelheid": 24,
    }
    out = compute_europallet(_state([regel]), repo=_StubRepo())
    assert out is not None
    assert out["artikelnummer_kwabo"] == PALLET_ARTIKELNR
    assert out["artikelnummer_kwabo_matched"] == PALLET_ARTIKELNR
    assert out["hoeveelheid"] == 1
    assert out["eenheid"] == "STUK"
    assert out["match_methode"] == "europallet_compute"
    assert out["positie"] == 2  # next-positie after the single regel


def test_two_doos_regels_sum_to_one_pallet():
    """12/24 + 12/24 = 1.0 → ceil(1.0) = 1."""
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
    out = compute_europallet(_state(regels), repo=_StubRepo())
    assert out is not None
    assert out["hoeveelheid"] == 1
    assert out["positie"] == 3


def test_kennis_pallet_required_with_per_pallet_10():
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
    assert out is not None
    # 20 / 10 = 2.0 pallets exact.
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
        # Regular regel that should produce a pallet via heuristic.
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
    out = compute_europallet(_state(regels), repo=_StubRepo())
    assert out is not None
    # 24 / 24 = 1 — no contribution from the second (pallet) line.
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


def test_doos_qty_below_min_skips_heuristic():
    """hoeveelheid < 5 must NOT trigger the heuristic even for DOOS."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 4,
        }
    ]
    out = compute_europallet(_state(regels), repo=_StubRepo())
    assert out is None


def test_total_below_threshold_returns_none():
    """6 / 24 = 0.25 < 0.5 → no pallet line."""
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 6,
        }
    ]
    out = compute_europallet(_state(regels), repo=_StubRepo())
    assert out is None


def test_partial_pallet_rounds_up():
    """36 / 24 = 1.5 → ceil = 2."""
    kennis = {("ART", "DOOS"): _Kennis(pallet_required=True, per_pallet=24)}
    regels = [
        {
            "positie": 1,
            "artikelnummer_kwabo_matched": "ART",
            "eenheid": "DOOS",
            "hoeveelheid": 36,
        }
    ]
    out = compute_europallet(_state(regels), repo=_StubRepo(kennis))
    assert out is not None
    assert out["hoeveelheid"] == 2


@pytest.mark.asyncio
async def test_compute_europallet_node_sets_state(session):
    """The graph node stores the regel on state and does not touch orderregels."""
    repo = PalletKennisRepo(session)
    repo.upsert(
        ArtikelPalletKennis(
            kwabo_artikelnr="ART",
            eenheid="DOOS",
            pallet_required=True,
            per_pallet=24,
            confidence=0.5,
        )
    )

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

    out = await compute_europallet_node(state, repo=repo)
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
