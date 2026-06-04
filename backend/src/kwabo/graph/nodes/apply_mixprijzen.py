"""Apply mixprijzen node (T7).

Runs after `match_articles` (so every regel has its `artikelnummer_kwabo_matched`
resolved where possible) and before `compute_europallet` / `validate_prices`.

NAV's own mix-codeunit owns the actual price calculation. This node only picks
the right MIX unit-of-measure code per line so NAV will price the line via the
correct staffel. The mechanism (confirmed with Kwabo, Veris example):

1. Gate ONLY on the customer's ``mixprijzen`` flag (NAV table 18 field 50013).
   The article-level flag is unreliable and is intentionally NOT required.
2. Mix codes have the format ``M{total_pallets_in_mix}PAL{rolls_per_pallet}``.
   The ``M``-number is order-wide: the TOTAL pallets across all mix lines. The
   ``PALxx`` suffix is rolls-per-pallet, article-specific and tier-independent.
3. Valid codes + active price come from the synced NAV table 7002 mirror
   (``Verkoopprijs``), resolved through the verkoopsoort cascade
   (Customer -> Customer_Price_Group -> All_Customers) in ``VerkoopprijsRepo``.

Algorithm:
- Phase 1 — compute the order-wide total pallets by converting each mix-eligible
  line's quantity to rolls and dividing by that article's rolls-per-pallet.
- Phase 2 — for each mix-eligible line, pick the highest staffel tier whose
  ``M``-threshold is <= the order total (clamp up to the lowest tier when the
  total is below it). Selection is fully automatic; we only flag for review when
  no codes resolve or the pallet math is ambiguous.

State writes:
- ``mixprijzen_actief``: True if at least one line got a mix-UOM selection.
- ``order_mix_total_pallets``: the order-wide staffel basis (audit/UI).
- ``regel["mix_uom_kandidaat"]``: candidate codes (ranked by tier) for UI override.
- ``regel["mix_uom_gekozen"]``: chosen code, or None when ambiguous.
- ``regel["mix_actieve_prijs"]``: active NAV-7002 price for the chosen code.
- ``needs_review_fields``: ``mix_uom:<positie>`` when no code could be chosen.

WARNING (calibration): the line-quantity -> pallets conversion in ``_to_rolls``
is the #1 calibration risk for auto-push. It must be validated against real
Veris orders before the chosen codes are trusted blindly (see plan).

Like ``select_ship_to``, the node accepts injectable repos/session for tests so
we do not need to monkeypatch the module-level engine.
"""
from __future__ import annotations

from datetime import date
from math import ceil
from typing import Optional

from sqlmodel import Session

from kwabo.db.repository import ArtikelkaartRepo, KlantRepo, VerkoopprijsRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log
from kwabo.utils.pallet_logic import _qty_per_base


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _to_rolls(
    kwabo_artikelnr: str, regel: dict, art_repo: ArtikelkaartRepo
) -> Optional[float]:
    """Convert a line's ordered quantity to base units (rolls).

    Uses the customer's originally-ordered unit (``eenheid_origineel``), falling
    back to the NAV-facing ``eenheid``. An empty/base unit means the quantity is
    already in rolls; an alternate unit is multiplied by its ``qty_per_base``.
    Returns None when the quantity is non-positive.

    NOTE (calibration): unknown alternate units default to a 1.0 factor (same as
    ``compute_europallet``). This is the documented calibration gate — validate
    against real Veris orders before trusting auto-push.
    """
    try:
        qty = float(regel.get("hoeveelheid") or 0)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None
    unit = (regel.get("eenheid_origineel") or regel.get("eenheid") or "").strip().upper()
    if not unit:
        return qty
    eenheden = art_repo.list_eenheden(kwabo_artikelnr)
    return qty * _qty_per_base(eenheden, unit)


def _evaluate(
    state: dict,
    klant_repo: KlantRepo,
    vp_repo: VerkoopprijsRepo,
    art_repo: ArtikelkaartRepo,
) -> dict:
    new_state = dict(state)
    new_state["mixprijzen_actief"] = False
    new_state["order_mix_total_pallets"] = None

    klant_match = state.get("klant_match") or {}
    klant_nr = klant_match.get("navision_klantnr")
    if not klant_nr:
        return new_state

    klant = klant_repo.by_nav_nr(klant_nr)
    if not klant or not klant.mixprijzen:
        # Customer not mix-eligible — short-circuit, leave regels untouched.
        log.info(
            "apply_mixprijzen",
            email_id=state.get("email_id"),
            klant_nr=klant_nr,
            klant_mix=False,
            mixprijzen_actief=False,
        )
        return new_state

    on_date = _parse_date(state.get("orderdatum")) or date.today()
    prijsgroep = klant.prijsgroep
    regels_in = state.get("orderregels") or []
    regels_out = [dict(r) for r in regels_in]

    # ---- Phase 1: order-wide total pallets across mix-eligible lines ----
    eligible: list[tuple[int, list, int, list]] = []  # (idx, mix_codes, rolls_per_pallet, rows)
    total_pallets = 0.0
    ambiguous = False
    for idx, regel in enumerate(regels_in):
        art = regel.get("artikelnummer_kwabo_matched")
        if not art:
            continue
        rows = vp_repo.active_rows(
            kwabo_artikelnr=art, klant_nr=klant_nr, prijsgroep=prijsgroep, on_date=on_date
        )
        codes = vp_repo.mix_codes(rows)
        if not codes:
            continue  # normal-only article — not a mix line
        rpps = {c.rolls_per_pallet for c in codes}
        if len(rpps) > 1:
            ambiguous = True  # inconsistent NAV data — PALxx must be tier-constant
        rpp = min(rpps)
        rolls = _to_rolls(art, regel, art_repo)
        if rolls is None or rpp <= 0:
            ambiguous = True
        else:
            total_pallets += rolls / rpp
        eligible.append((idx, codes, rpp, rows))

    total = ceil(total_pallets) if total_pallets > 0 else 0

    # ---- Phase 2: per-line tier pick ----
    needs_review = list(state.get("needs_review_fields") or [])
    n_actief = 0
    n_review = 0
    for idx, codes, _rpp, rows in eligible:
        r = regels_out[idx]
        ranked = sorted(codes, key=lambda c: c.m_threshold)
        r["mix_uom_kandidaat"] = [c.code for c in ranked]
        if ambiguous or total <= 0:
            r["mix_uom_gekozen"] = None
            r["mix_actieve_prijs"] = None
            entry = f"mix_uom:{r.get('positie')}"
            if entry not in needs_review:
                needs_review.append(entry)
            n_review += 1
            continue
        at_or_below = [c for c in ranked if c.m_threshold <= total]
        pick = at_or_below[-1] if at_or_below else ranked[0]  # clamp up to lowest tier
        r["mix_uom_gekozen"] = pick.code
        r["mix_actieve_prijs"] = next(
            (row.prijs for row in rows if (row.eenheid_code or "").upper() == pick.code),
            None,
        )
        n_actief += 1

    new_state["orderregels"] = regels_out
    new_state["mixprijzen_actief"] = n_actief > 0
    new_state["order_mix_total_pallets"] = total or None
    if needs_review != (state.get("needs_review_fields") or []):
        new_state["needs_review_fields"] = needs_review
        new_state["needs_review_count"] = len(needs_review)

    log.info(
        "apply_mixprijzen",
        email_id=state.get("email_id"),
        klant_nr=klant_nr,
        klant_mix=True,
        order_total_pallets=total,
        n_actief=n_actief,
        n_review=n_review,
        mixprijzen_actief=new_state["mixprijzen_actief"],
    )
    return new_state


async def apply_mixprijzen_node(
    state: dict,
    *,
    repo_klant: Optional[KlantRepo] = None,
    repo_verkoopprijs: Optional[VerkoopprijsRepo] = None,
    repo_artikelkaart: Optional[ArtikelkaartRepo] = None,
    session: Optional[Session] = None,
) -> dict:
    """Pick the mix-UOM per mix-eligible regel; flag review when ambiguous.

    Tests can inject the repos + ``session`` (all bound to the same DB) to
    exercise the node without monkeypatching the module-level engine. In
    production, when nothing is injected, the node opens its own session against
    ``kwabo.db.session.engine`` — mirroring ``select_ship_to_node`` and
    ``match_articles_node``.
    """
    if session is not None:
        return _evaluate(
            state,
            repo_klant or KlantRepo(session),
            repo_verkoopprijs or VerkoopprijsRepo(session),
            repo_artikelkaart or ArtikelkaartRepo(session),
        )

    with Session(engine) as s:
        return _evaluate(
            state,
            repo_klant or KlantRepo(s),
            repo_verkoopprijs or VerkoopprijsRepo(s),
            repo_artikelkaart or ArtikelkaartRepo(s),
        )
