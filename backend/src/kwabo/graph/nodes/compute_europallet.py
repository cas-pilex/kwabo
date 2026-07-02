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

from kwabo.db.repository import ArtikelkaartRepo, PalletKennisRepo, PalletPlaatsenRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log
from kwabo.utils.pallet_logic import PALLET_ARTIKELNR, europallet_breakdown


def _onderbouwing(bd: dict) -> str:
    n = bd["europallet_aantal"]
    if n == 0:
        return (f"{bd['totaal_pallets']} pallets in order — onder de drempel, "
                "geen europallet.")
    return (f"{bd['totaal_pallets']} pallets in order → {n} europallet"
            f"{'s' if n != 1 else ''} (afgerond naar boven).")


def _evaluate(state: dict, repo: PalletKennisRepo, uom_repo=None,
              plaatsen_repo=None) -> dict:
    new_state = dict(state)
    bd = europallet_breakdown(state, repo=repo, uom_repo=uom_repo,
                              plaatsen_repo=plaatsen_repo)
    regel = bd["regel"]
    new_state["europallet_regel"] = regel

    # Functie 4 (DEEL B): leg de telling vast in _meta zodat de reviewer kan
    # zien WAAROP de N europallets gebaseerd zijn (per regel + totaal + regel).
    meta = dict(state.get("_meta") or {})
    meta["europallet"] = {
        "regels": bd["regels"],
        "totaal_pallets": bd["totaal_pallets"],
        "europallet_aantal": bd["europallet_aantal"],
        "uitleg": _onderbouwing(bd),
        "onbekend": bd.get("onbekend") or [],
    }
    new_state["_meta"] = meta

    # B4: regels zonder enige europallet-databron -> vlag, geen gok. De
    # warning noemt de artikelen zodat Nico's vul-lijst (pallet_plaatsen_basis)
    # gericht gevuld kan worden.
    onbekend = bd.get("onbekend") or []
    if onbekend:
        nrf = list(new_state.get("needs_review_fields") or [])
        if "europallet" not in nrf:
            nrf.append("europallet")
        new_state["needs_review_fields"] = nrf
        new_state["needs_review_count"] = len(nrf)
        warnings = list(new_state.get("validatie_warnings") or [])
        arts = ", ".join(
            f"{o['artikelnr']} ({o['qty']} {o['eenheid']})" for o in onbekend[:6]
        )
        warnings.append(
            f"⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen "
            f"bruikbare NAV-eenheid voor: {arts} — telling kan onvolledig zijn."
        )
        new_state["validatie_warnings"] = warnings

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
    state: dict, *, repo: Optional[PalletKennisRepo] = None,
    plaatsen_repo=None,
) -> dict:
    """Compute the optional europallet regel and store it on state.

    Mirrors the dependency-injection style of ``select_ship_to_node`` and
    ``apply_mixprijzen_node``: tests can pass in a repo bound to their own
    session; in production we open a Session against the module-level
    engine.
    """
    if repo is not None:
        return _evaluate(state, repo, plaatsen_repo=plaatsen_repo)

    with Session(engine) as s:
        # Same session feeds the item-UOM lookup so stuks/rol lines can be
        # converted to pallets via the article's units-per-pallet.
        return _evaluate(state, PalletKennisRepo(s), uom_repo=ArtikelkaartRepo(s),
                         plaatsen_repo=PalletPlaatsenRepo(s))
