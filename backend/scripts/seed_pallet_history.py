"""Seed ``artikel_pallet_kennis`` from historical NAV-mock orders (T8).

Reads the existing JSON sales-order files in ``data/navision_mock/orders/``
(or any path passed via ``--data-dir``) and learns, per
``(artikelnr, eenheid)`` pair, whether a europallet line is required.

Heuristic per spec:

  * ``eenheid in (DOOS, PAL)`` → ``pallet_required=True``,
    ``per_pallet=24`` (best-guess default).
  * ``eenheid in (STUK, KG, M2, ROL, ...)`` (anything else) →
    ``pallet_required=False``.

Confidence rises with the observation count, capped at ``0.8`` for the
seed (we leave ``> 0.8`` for human-confirmed entries).

Idempotent: re-running over the same orders folds new observations into
the existing kennis row via ``PalletKennisRepo.upsert``. Running twice
back-to-back is a no-op aside from refreshing ``laatst_bevestigd_op``.

Usage:
  python scripts/seed_pallet_history.py
  python scripts/seed_pallet_history.py --data-dir <path>

Empty / missing folder → log ``no orders found`` and exit ``0``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.models import ArtikelPalletKennis  # noqa: E402
from kwabo.db.repository import PalletKennisRepo  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.utils import utcnow  # noqa: E402
from kwabo.utils.logging import log, setup_logging  # noqa: E402

# Repo root: backend/scripts/.. /.. → kwabo-order-intake/.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "navision_mock" / "orders"

PALLET_EENHEDEN = {"DOOS", "PAL"}
DEFAULT_PER_PALLET = 24
SEED_CONFIDENCE_CAP = 0.8


def _confidence(count: int) -> float:
    """Saturating confidence score: 1 → 0.4, 2 → 0.6, 3 → 0.7, 4+ → 0.8."""
    if count <= 0:
        return 0.0
    table = {1: 0.4, 2: 0.6, 3: 0.7}
    return min(table.get(count, SEED_CONFIDENCE_CAP), SEED_CONFIDENCE_CAP)


def _iter_order_files(data_dir: Path) -> Iterable[Path]:
    if not data_dir.exists() or not data_dir.is_dir():
        return []
    return sorted(data_dir.glob("*.json"))


def _aggregate_observations(
    files: Iterable[Path],
) -> dict[tuple[str, str], int]:
    """Walk the order JSON files and count occurrences of (itemNr, UOM).

    We count every line — even repeats within a single order — because
    repeated UOM use is itself a signal the ``(artikelnr, eenheid)`` pair
    is real.
    """
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("seed_pallet_skip_unreadable", path=str(path), error=str(exc))
            continue

        for line in payload.get("lines") or []:
            artikelnr = line.get("itemNumber") or line.get("itemNo")
            eenheid_raw = line.get("unitOfMeasureCode") or line.get("uomCode") or ""
            eenheid = (eenheid_raw or "").strip().upper()
            if not artikelnr or not eenheid:
                continue
            counts[(artikelnr, eenheid)] += 1
    return counts


def seed_from_dir(
    session: Session, data_dir: Path
) -> tuple[int, int]:
    """Run the seed pass.

    Returns ``(orders_found, kennis_rows_written)``. Both ``0`` is a
    legitimate empty-data outcome — we still exit ``0`` from the CLI.
    """
    files = list(_iter_order_files(data_dir))
    if not files:
        log.info("seed_pallet_no_orders", data_dir=str(data_dir))
        return 0, 0

    counts = _aggregate_observations(files)
    if not counts:
        log.info("seed_pallet_no_lines", data_dir=str(data_dir), n_orders=len(files))
        return len(files), 0

    repo = PalletKennisRepo(session)
    written = 0
    for (artikelnr, eenheid), n in counts.items():
        pallet_required = eenheid in PALLET_EENHEDEN
        confidence = _confidence(n)
        repo.upsert(
            ArtikelPalletKennis(
                kwabo_artikelnr=artikelnr,
                eenheid=eenheid,
                pallet_required=pallet_required,
                per_pallet=DEFAULT_PER_PALLET if pallet_required else 1,
                confidence=confidence,
                laatst_bevestigd_op=utcnow(),
                bevestigd_door="seed_pallet_history",
            )
        )
        written += 1
    log.info(
        "seed_pallet_done",
        data_dir=str(data_dir),
        n_orders=len(files),
        n_unique_pairs=written,
    )
    return len(files), written


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed artikel_pallet_kennis from NAV-mock order JSON files."
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Folder of order JSONs to learn from (default: {DEFAULT_DATA_DIR}).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    setup_logging()
    args = parse_args(argv)

    init_db()
    with Session(engine) as session:
        orders, written = seed_from_dir(session, args.data_dir)

    if orders == 0:
        # Per spec: empty folder is not an error — log and exit 0.
        return 0
    log.info("seed_pallet_summary", orders=orders, kennis_rows=written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
