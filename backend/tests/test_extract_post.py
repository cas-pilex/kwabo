"""Tests for the extract_node post-processors (KW-week date + pallet detection)."""
from __future__ import annotations

from datetime import date

import pytest

from kwabo.graph.nodes.extract import (
    KW_WEEK_RE,
    _iso_week_to_date,
    _kw_date_from_text,
)
from kwabo.utils.eenheid_mapping import normalize_eenheid
from kwabo.utils.pallet_logic import compute_europallet


# --- KW-week regex/parser ---


def test_kw_regex_matches_basic_forms():
    for s in ("KW24", "KW 24", "KW24/2026", "Lieferung KW 24"):
        assert KW_WEEK_RE.search(s), f"should match {s!r}"


def test_kw_regex_ignores_non_kw():
    assert KW_WEEK_RE.search("kgwm-99") is None
    assert KW_WEEK_RE.search("week 24") is None  # plain "week" is not KW


def test_iso_week_to_date_kw24_2026():
    # ISO 2026-W24 starts Monday June 8.
    assert _iso_week_to_date(24, 2026) == date(2026, 6, 8)


def test_iso_week_to_date_invalid_week():
    assert _iso_week_to_date(0, 2026) is None
    assert _iso_week_to_date(54, 2026) is None


def test_kw_date_from_text_with_explicit_year():
    iso = _kw_date_from_text("Lieferung KW24/2026", today=date(2024, 1, 1))
    assert iso == "2026-06-08"


def test_kw_date_from_text_uses_current_year_when_future():
    today = date(2026, 1, 1)
    iso = _kw_date_from_text("Lieferung KW24", today)
    assert iso == "2026-06-08"


def test_kw_date_from_text_rolls_to_next_year_when_past():
    # KW10/2026 = Mar 2. If today is Apr 1 2026, that week has passed →
    # author probably means 2027.
    today = date(2026, 4, 1)
    iso = _kw_date_from_text("Lieferung KW10", today)
    assert iso is not None
    assert iso.startswith("2027-")


def test_kw_date_from_text_returns_none_without_match():
    assert _kw_date_from_text("Bitte schnellstmöglich", date.today()) is None
    assert _kw_date_from_text("", date.today()) is None


# --- Eenheid mapping (Duitse pallet varianten) ---


@pytest.mark.parametrize("raw", ["palette", "Paletten", "EUR-Palette", "Europalette", "europallet"])
def test_normalize_eenheid_duitse_pallet_varianten(raw):
    assert normalize_eenheid(raw) == "PAL"


# --- compute_europallet uses eenheid_origineel ---


class _StubKennisRepo:
    def lookup(self, artikelnr, eenheid):
        return None  # force heuristic fallback


def test_compute_europallet_uses_eenheid_origineel_when_overwritten():
    """match_articles overwrites `eenheid` with NAV base UoM (often STUK).
    Without preserving the LLM-extracted unit, compute_europallet would
    miss "66 PAL"-style orders. The eenheid_origineel side-field is the
    workaround until we can validate alternative UoMs against NAV."""
    state = {
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "19090",
                "hoeveelheid": 66,
                "eenheid": "STUK",            # ← overwritten by match_articles
                "eenheid_origineel": "PAL",   # ← LLM's actual extraction
            }
        ]
    }
    regel = compute_europallet(state, repo=_StubKennisRepo())
    assert regel is not None
    assert regel["artikelnummer_kwabo"] == "19820"
    assert regel["hoeveelheid"] == 66


def test_compute_europallet_falls_back_to_eenheid_when_origineel_missing():
    state = {
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "19090",
                "hoeveelheid": 5,
                "eenheid": "PAL",
                # no eenheid_origineel — older state shape
            }
        ]
    }
    regel = compute_europallet(state, repo=_StubKennisRepo())
    assert regel is not None
    assert regel["hoeveelheid"] == 5


def test_compute_europallet_single_pal_still_counts():
    """Even '1 PAL' should produce one europallet line (no qty threshold)."""
    state = {
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "19090",
                "hoeveelheid": 1,
                "eenheid_origineel": "PAL",
            }
        ]
    }
    regel = compute_europallet(state, repo=_StubKennisRepo())
    assert regel is not None
    assert regel["hoeveelheid"] == 1


def test_compute_europallet_doos_still_uses_legacy_heuristic():
    """DOOS path: 5 boxes / 24 per pallet ≈ 0.21 → rounds to 1 pallet via
    PALLET_THRESHOLD logic (5/24 = 0.208, below 0.5 → returns None).
    Demonstrates the DOOS heuristic still behaves the old way."""
    state = {
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "19090",
                "hoeveelheid": 5,
                "eenheid_origineel": "DOOS",
            }
        ]
    }
    # 5 DOOS at HEURISTIC_PER_PALLET=24 → 0.208 → below 0.5 → no pallet
    regel = compute_europallet(state, repo=_StubKennisRepo())
    assert regel is None

    # 13 DOOS → 0.54 → just over → one pallet
    state["orderregels"][0]["hoeveelheid"] = 13
    regel = compute_europallet(state, repo=_StubKennisRepo())
    assert regel is not None
    assert regel["hoeveelheid"] == 1
