"""Apply mixprijzen node (T7).

Runs after `match_articles` (so every regel has its `artikelnummer_kwabo_matched`
resolved where possible) and before `compute_europallet` / `validate_prices`.

NAV's own mix-codeunit owns the actual price calculation: when we push a line
with a MIX unit-of-measure code, NAV resolves the verkoopsoort cascade
(Customer -> Customer_Price_Group -> All_Customers) and prices the line itself.
This node only picks the right MIX code per line and converts the quantity to
the mix unit (pallets). Confirmed mechanism (Kwabo, Veris example):

1. Gate ONLY on the customer's mix flag (`Klantenkaart.mixprijzen`, synced from
   NAV `PLX_Customer.Mix_Prices_Allowed`). The article-level flag is unreliable
   and is intentionally NOT required.
2. Mix codes have the format ``M{total_pallets_in_mix}PAL{rolls_per_pallet}``
   (e.g. ``M7PAL30``, ``M33PAL35``). The ``M``-number is the order-wide total
   pallets; ``PALxx`` is rolls-per-pallet, article-specific. These codes live in
   ``PLX_ItemUnitOfMeasure`` — already mirrored into ``ArtikelEenheid`` by the
   ``item_uoms`` sync (the ``PALxx`` suffix equals ``Qty_per_Unit_of_Measure``).
3. Per article, the available staffel tiers are the M-numbers across its mix
   codes; we pick the highest tier whose threshold <= the order's total pallets
   (clamp up to the lowest tier when the total is below it).
4. The line is pushed in the mix unit, so the QUANTITY becomes the pallet count
   (``rolls / rolls_per_pallet``) — e.g. 350 ROL at 35/pallet -> 10 x M{tier}PAL35.

Selection is fully automatic; we only flag for review when no codes resolve or
the pallet math is ambiguous (unconvertible unit, non-integer pallet count, or
inconsistent rolls-per-pallet across an article's mix codes).

State writes:
- ``mixprijzen_actief``: True if at least one line got a mix-UOM selection.
- ``order_mix_total_pallets``: the order-wide staffel basis (audit/UI).
- ``regel["mix_uom_kandidaat"]``: candidate codes (ranked by tier) for UI override.
- ``regel["mix_uom_gekozen"]``: chosen code, or None when ambiguous.
- ``regel["mix_aantal"]``: line quantity in the mix unit (pallets) — used by the
  composer for the quantity PATCH and by compute_europallet for the pallet count.
- ``needs_review_fields``: ``mix_uom:<positie>`` when no code could be chosen.

Like ``select_ship_to``, the node accepts an injectable session for tests.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from kwabo.db.repository import ArtikelkaartRepo, KlantRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log
from kwabo.utils.mixcode import MixCode, parse_mix_code
from kwabo.utils.pallet_logic import _qty_per_base

# How close rolls/rolls-per-pallet must be to a whole number to auto-accept the
# pallet count. Mix orders are whole pallets; a non-integer signals an ambiguous
# quantity we should not silently round, so we flag it for review instead.
_PALLET_TOL = 0.02


def _to_rolls(
    kwabo_artikelnr: str, regel: dict, eenheden: list
) -> Optional[float]:
    """Convert a line's ordered quantity to base units (rolls).

    Uses the customer's originally-ordered unit (``eenheid_origineel``), falling
    back to the NAV-facing ``eenheid``. An empty/base unit means the quantity is
    already in base units; an alternate unit is multiplied by its
    ``qty_per_base``. Returns None when the quantity is non-positive.
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
    return qty * _qty_per_base(eenheden, unit)


def _mix_codes_for(eenheden: list) -> list[MixCode]:
    """Parse the article's ArtikelEenheid rows into mix codes (deduped)."""
    out: dict[str, MixCode] = {}
    for e in eenheden:
        mc = parse_mix_code(e.eenheid_code)
        if mc:
            out[mc.code] = mc
    return list(out.values())


def _evaluate(state: dict, klant_repo: KlantRepo, art_repo: ArtikelkaartRepo) -> dict:
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

    regels_in = state.get("orderregels") or []
    regels_out = [dict(r) for r in regels_in]

    # ---- Phase 1: order-wide total pallets across mix-eligible lines ----
    eligible: list[tuple[int, list, int, Optional[int]]] = []  # (idx, codes, rpp, line_pallets)
    total_pallets = 0
    ambiguous = False
    for idx, regel in enumerate(regels_in):
        art = regel.get("artikelnummer_kwabo_matched")
        if not art:
            continue
        eenheden = art_repo.list_eenheden(art)
        codes = _mix_codes_for(eenheden)
        if not codes:
            continue  # normal-only article — not a mix line
        rpps = {c.rolls_per_pallet for c in codes}
        if len(rpps) > 1:
            ambiguous = True  # inconsistent NAV data — PALxx must be article-constant
        rpp = min(rpps)
        rolls = _to_rolls(art, regel, eenheden)
        line_pallets: Optional[int] = None
        if rolls is None or rpp <= 0:
            ambiguous = True
        else:
            lp = rolls / rpp
            line_pallets = round(lp)
            if line_pallets <= 0 or abs(lp - line_pallets) > _PALLET_TOL:
                ambiguous = True
                line_pallets = None
            else:
                total_pallets += line_pallets
        eligible.append((idx, codes, rpp, line_pallets))

    # ---- Phase 2: per-line tier pick + quantity in pallets ----
    needs_review = list(state.get("needs_review_fields") or [])
    n_actief = 0
    n_review = 0
    for idx, codes, _rpp, line_pallets in eligible:
        r = regels_out[idx]
        ranked = sorted(codes, key=lambda c: c.m_threshold)
        r["mix_uom_kandidaat"] = [c.code for c in ranked]
        if ambiguous or total_pallets <= 0 or line_pallets is None:
            r["mix_uom_gekozen"] = None
            r["mix_aantal"] = None
            entry = f"mix_uom:{r.get('positie')}"
            if entry not in needs_review:
                needs_review.append(entry)
            n_review += 1
            continue
        at_or_below = [c for c in ranked if c.m_threshold <= total_pallets]
        pick = at_or_below[-1] if at_or_below else ranked[0]  # clamp up to lowest tier
        r["mix_uom_gekozen"] = pick.code
        r["mix_aantal"] = line_pallets
        n_actief += 1

    new_state["orderregels"] = regels_out
    new_state["mixprijzen_actief"] = n_actief > 0
    new_state["order_mix_total_pallets"] = total_pallets or None
    if needs_review != (state.get("needs_review_fields") or []):
        new_state["needs_review_fields"] = needs_review
        new_state["needs_review_count"] = len(needs_review)

    log.info(
        "apply_mixprijzen",
        email_id=state.get("email_id"),
        klant_nr=klant_nr,
        klant_mix=True,
        order_total_pallets=total_pallets,
        n_actief=n_actief,
        n_review=n_review,
        mixprijzen_actief=new_state["mixprijzen_actief"],
    )
    return new_state


async def apply_mixprijzen_node(
    state: dict,
    *,
    repo_klant: Optional[KlantRepo] = None,
    repo_artikelkaart: Optional[ArtikelkaartRepo] = None,
    session: Optional[Session] = None,
) -> dict:
    """Pick the mix-UOM + pallet quantity per mix-eligible regel; flag on doubt.

    Tests inject ``session`` (and optionally the repos, all bound to the same
    DB). In production the node opens its own session against
    ``kwabo.db.session.engine`` — mirroring ``select_ship_to_node`` and
    ``match_articles_node``.
    """
    if session is not None:
        return _evaluate(
            state,
            repo_klant or KlantRepo(session),
            repo_artikelkaart or ArtikelkaartRepo(session),
        )

    with Session(engine) as s:
        return _evaluate(
            state,
            repo_klant or KlantRepo(s),
            repo_artikelkaart or ArtikelkaartRepo(s),
        )
