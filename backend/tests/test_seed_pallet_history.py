"""Tests for ``scripts/seed_pallet_history.py`` (T8 self-learning seeder).

Covers:
- end-to-end seed pass over a temp dir of fake NAV order JSONs;
- idempotency: re-running over the same orders does not duplicate rows
  (composite-PK upsert);
- empty folder is logged as a clean no-op (returns 0/0).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlmodel import select

# Bring the scripts/ directory onto sys.path so we can import the seeder.
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from seed_pallet_history import seed_from_dir  # noqa: E402

from kwabo.db.models import ArtikelPalletKennis  # noqa: E402


def _write_order(folder: Path, name: str, lines: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": name,
        "number": name,
        "header": {"customerNumber": "10001"},
        "lines": lines,
        "status": "Draft",
    }
    (folder / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_seed_from_dir_creates_expected_kennis(session, tmp_path):
    data_dir = tmp_path / "orders"
    _write_order(
        data_dir,
        "SO-0001",
        [
            {"itemNumber": "ART-1", "unitOfMeasureCode": "DOOS", "quantity": 12},
            {"itemNumber": "ART-2", "unitOfMeasureCode": "STUK", "quantity": 7},
        ],
    )
    _write_order(
        data_dir,
        "SO-0002",
        [
            {"itemNumber": "ART-1", "unitOfMeasureCode": "DOOS", "quantity": 5},
            {"itemNumber": "ART-3", "unitOfMeasureCode": "PAL", "quantity": 1},
        ],
    )

    n_orders, n_written = seed_from_dir(session, data_dir)
    assert n_orders == 2
    assert n_written == 3  # (ART-1, DOOS), (ART-2, STUK), (ART-3, PAL)

    rows = list(session.exec(select(ArtikelPalletKennis)).all())
    by_key = {(r.kwabo_artikelnr, r.eenheid): r for r in rows}

    # DOOS / PAL → pallet_required=True, per_pallet=24.
    assert by_key[("ART-1", "DOOS")].pallet_required is True
    assert by_key[("ART-1", "DOOS")].per_pallet == 24
    assert by_key[("ART-3", "PAL")].pallet_required is True

    # STUK → pallet_required=False.
    assert by_key[("ART-2", "STUK")].pallet_required is False

    # Two observations of (ART-1, DOOS) → confidence at the 2-obs tier (0.6).
    assert by_key[("ART-1", "DOOS")].confidence == pytest.approx(0.6)
    # Single-observation entries land at the 1-obs tier (0.4).
    assert by_key[("ART-2", "STUK")].confidence == pytest.approx(0.4)

    assert by_key[("ART-1", "DOOS")].bevestigd_door == "seed_pallet_history"


def test_seed_from_dir_is_idempotent(session, tmp_path):
    data_dir = tmp_path / "orders"
    _write_order(
        data_dir,
        "SO-0001",
        [{"itemNumber": "ART-X", "unitOfMeasureCode": "DOOS", "quantity": 12}],
    )

    seed_from_dir(session, data_dir)
    rows_after_first = list(session.exec(select(ArtikelPalletKennis)).all())
    assert len(rows_after_first) == 1

    # Second run — same data, same key → upsert (no duplicates).
    seed_from_dir(session, data_dir)
    rows_after_second = list(session.exec(select(ArtikelPalletKennis)).all())
    assert len(rows_after_second) == 1


def test_seed_from_dir_empty_folder_is_clean_noop(session, tmp_path):
    empty = tmp_path / "no-orders"
    empty.mkdir()
    n_orders, n_written = seed_from_dir(session, empty)
    assert (n_orders, n_written) == (0, 0)
    assert list(session.exec(select(ArtikelPalletKennis)).all()) == []


def test_seed_from_dir_missing_folder_is_clean_noop(session, tmp_path):
    missing = tmp_path / "does-not-exist"
    n_orders, n_written = seed_from_dir(session, missing)
    assert (n_orders, n_written) == (0, 0)
