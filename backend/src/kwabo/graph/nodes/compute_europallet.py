"""Compute europallet node (T8).

Runs after ``apply_mixprijzen`` (T7) and before ``validate_prices``. Reads
the matched orderregels and computes a single optional "europallet" regel
(artikelnr ``19820``) using ``kwabo.utils.pallet_logic.compute_europallet``.

State writes:
- ``europallet_regel``: the computed pallet regel-dict, or ``None`` when no
  pallet is needed. The operations composer (T4) reads this slot
  separately — we deliberately do NOT append the regel to
  ``state["orderregels"]`` so downstream price-validation, mix-pricing,
  and any review-UI line counts stay anchored to the customer's actual
  order lines.

Like the other T5–T7 nodes, this one accepts an injectable ``repo`` so
tests can bind it to their own session without monkeypatching the
module-level engine.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from kwabo.db.repository import PalletKennisRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log
from kwabo.utils.pallet_logic import PALLET_ARTIKELNR, compute_europallet


def _evaluate(state: dict, repo: PalletKennisRepo) -> dict:
    new_state = dict(state)
    regel = compute_europallet(state, repo=repo)
    new_state["europallet_regel"] = regel

    log.info(
        "compute_europallet",
        email_id=state.get("email_id"),
        klant_nr=(state.get("klant_match") or {}).get("navision_klantnr"),
        n_regels=len(state.get("orderregels") or []),
        pallet_added=regel is not None,
        pallet_qty=(regel or {}).get("hoeveelheid"),
        pallet_artikelnr=PALLET_ARTIKELNR if regel else None,
    )
    return new_state


async def compute_europallet_node(
    state: dict, *, repo: Optional[PalletKennisRepo] = None
) -> dict:
    """Compute the optional europallet regel and store it on state.

    Mirrors the dependency-injection style of ``select_ship_to_node`` and
    ``apply_mixprijzen_node``: tests can pass in a repo bound to their own
    session; in production we open a Session against the module-level
    engine.
    """
    if repo is not None:
        return _evaluate(state, repo)

    with Session(engine) as s:
        return _evaluate(state, PalletKennisRepo(s))
