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
   pallets staffel tier. These codes live in ``PLX_ItemUnitOfMeasure`` — already
   mirrored into ``ArtikelEenheid`` by the ``item_uoms`` sync.
   IMPORTANT: the ``PALxx`` suffix is a human-typed *label* and is NOT reliable
   — live NAV has typos (item 15450: ``M10PAL1028`` / ``M5PAL528`` whose real
   ``Qty_per_Unit_of_Measure`` is 1728). The authoritative units-per-pallet is
   ``ArtikelEenheid.qty_per_base`` ( == NAV ``Qty_per_Unit_of_Measure`` == the
   ``PALLET`` unit's qty), which is physically constant per article. We compute
   pallets with ``qty_per_base`` and treat the suffix as cosmetic only.
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
from kwabo.utils.eenheid_resolve import (
    PALLET_TOL,
    branch_a,
    mix_tiers_for,
    to_base_qty,
)
from kwabo.utils.logging import log
from kwabo.utils.pallet_logic import _qty_per_base


def _branch_a_via_repo(regel: dict, art_repo: ArtikelkaartRepo) -> Optional[str]:
    """Mirror-data ophalen en het eenheid-contract (branch_a) toepassen.
    Alle beslislogica leeft in kwabo.utils.eenheid_resolve (F2.3)."""
    art = regel.get("artikelnummer_kwabo_matched")
    if not art:
        return None
    kaart = art_repo.get(art)
    if not kaart or not (kaart.basis_eenheid or "").strip():
        return None
    return branch_a(regel, kaart, art_repo.list_eenheden(art))


def _evaluate(state: dict, klant_repo: KlantRepo, art_repo: ArtikelkaartRepo) -> dict:
    new_state = dict(state)
    new_state["mixprijzen_actief"] = False
    new_state["order_mix_total_pallets"] = None

    regels_in = state.get("orderregels") or []
    regels_out = [dict(r) for r in regels_in]

    klant_match = state.get("klant_match") or {}
    klant_nr = klant_match.get("navision_klantnr")
    klant = klant_repo.by_nav_nr(klant_nr) if klant_nr else None
    if not klant or not klant.mixprijzen:
        # Customer not mix-eligible — mix phase is skipped, but Branch A
        # (expliciete verkoopeenheid, E1/E2) geldt voor élke gematchte regel.
        warnings = list(state.get("validatie_warnings") or [])
        needs_review = list(state.get("needs_review_fields") or [])
        for r in regels_out:
            w = _branch_a_via_repo(r, art_repo)
            if w:
                warnings.append(w)
                entry = f"verkoop_eenheid:{r.get('positie')}"
                if entry not in needs_review:
                    needs_review.append(entry)
        new_state["orderregels"] = regels_out
        if warnings != (state.get("validatie_warnings") or []):
            new_state["validatie_warnings"] = warnings
        if needs_review != (state.get("needs_review_fields") or []):
            new_state["needs_review_fields"] = needs_review
            new_state["needs_review_count"] = len(needs_review)
        log.info(
            "apply_mixprijzen",
            email_id=state.get("email_id"),
            klant_nr=klant_nr,
            klant_mix=False,
            mixprijzen_actief=False,
        )
        return new_state

    # ---- Phase 1: per regel pallets bepalen ----
    # F2.2 (her-diagnose 10-7): ambiguïteit is een REGEL-eigenschap. De oude
    # order-brede `ambiguous`-boolean liet één onresolveerbare regel (geen
    # hele pallets, of onbesliste multi-familie) ÁLLE regels vergiftigen —
    # bij echte mix-klanten (Veris #685, 8 regels) koos de mix-laag daardoor
    # nooit iets (n_actief=0) en kreeg de reviewer alleen een vlag-muur.
    eligible: list[tuple[int, list, Optional[int]]] = []  # (idx, codes, line_pallets)
    total_pallets = 0
    uitgesloten: list = []  # posities buiten de staffelbasis (regel-ambigu)
    for idx, regel in enumerate(regels_in):
        art = regel.get("artikelnummer_kwabo_matched")
        if not art:
            continue
        eenheden = art_repo.list_eenheden(art)
        codes = mix_tiers_for(eenheden)
        if not codes:
            continue  # normal-only article — not a mix line
        # Units-per-pallet is the physical pallet size. Use qty_per_base
        # (authoritative), not the cosmetic PALxx suffix which can have typos
        # (live item 15450). Een artikel kan mixcodes in MEERDERE families
        # hebben (238601: M*PAL33/35/42) — dan kiest de verkoopeenheid van de
        # kaart de juiste familie (M4: "binnen de juiste PAL{Y}-familie").
        line_ambiguous = False
        upps = {c.units_per_pallet for c in codes}
        if len(upps) > 1:
            kaart = art_repo.get(art)
            sales_per = _qty_per_base(
                eenheden, (kaart.verkoop_eenheid if kaart else "") or ""
            )
            familie = [c for c in codes if abs(c.units_per_pallet - sales_per) < 0.01]
            if sales_per > 1 and familie:
                codes = familie
                upps = {sales_per}
        if len(upps) > 1 or any(u <= 0 for u in upps):
            line_ambiguous = True  # inconsistent/incomplete NAV data op DEZE regel
        line_pallets: Optional[int] = None
        if not line_ambiguous:
            rpp = min(upps)
            rolls = to_base_qty(regel, eenheden)
            if rolls is None or rpp <= 0:
                line_ambiguous = True
            else:
                lp = rolls / rpp
                line_pallets = round(lp)
                if line_pallets <= 0 or abs(lp - line_pallets) > PALLET_TOL:
                    line_pallets = None
                else:
                    total_pallets += line_pallets
        if line_pallets is None:
            uitgesloten.append(regel.get("positie"))
        eligible.append((idx, codes, line_pallets))

    # ---- Phase 2: per-line tier pick + quantity in pallets ----
    needs_review = list(state.get("needs_review_fields") or [])
    n_actief = 0
    n_review = 0
    for idx, codes, line_pallets in eligible:
        r = regels_out[idx]
        ranked = sorted(codes, key=lambda c: c.m_threshold)
        r["mix_uom_kandidaat"] = [c.code for c in ranked]
        if line_pallets is None or total_pallets <= 0:
            r["mix_uom_gekozen"] = None
            r["mix_aantal"] = None
            r["eenheid_bron"] = (
                "mix-ambigu: geen hele pallets of onbesliste pallet-familie — "
                "keuze aan de reviewer (kandidaten: "
                + ", ".join(c.code for c in ranked) + ")"
            )
            entry = f"mix_uom:{r.get('positie')}"
            if entry not in needs_review:
                needs_review.append(entry)
            n_review += 1
            continue
        at_or_below = [c for c in ranked if c.m_threshold <= total_pallets]
        pick = at_or_below[-1] if at_or_below else ranked[0]  # clamp up to lowest tier
        r["mix_uom_gekozen"] = pick.code
        r["mix_aantal"] = line_pallets
        r["eenheid_bron"] = (
            f"mix-staffel {pick.code}: {line_pallets} pallet(s) x "
            f"{pick.units_per_pallet:g}/pallet, tier M{pick.m_threshold} bij "
            f"staffelbasis M{total_pallets} (hoogste tier <= totaal)"
        )
        n_actief += 1

    # Branch A (E1/E2) voor de niet-mix-regels van een mix-klant: ook die
    # moeten met een EXPLICIETE eenheid naar NAV. Mix-regels (incl. de
    # review-gevallen, herkenbaar aan mix_uom_kandidaat) blijven van de
    # mix-logica.
    warnings = list(state.get("validatie_warnings") or [])
    # Versmalde staffelbasis nooit stil (grondwet): de tier van de gekozen
    # regels is berekend zónder de uitgesloten regels — dat moet de reviewer
    # kunnen zien en corrigeren.
    if uitgesloten and n_actief:
        warnings.append(
            f"⚠ MIX-STAFFEL: staffelbasis M{total_pallets} telt alleen de "
            f"resolveerbare regels; regel(s) "
            f"{', '.join(str(p) for p in uitgesloten)} vallen erbuiten "
            f"(geen hele pallets of ambigue pallet-familie) — controleer de tier."
        )
    for r in regels_out:
        if "mix_uom_kandidaat" not in r:
            w = _branch_a_via_repo(r, art_repo)
            if w:
                warnings.append(w)
                entry = f"verkoop_eenheid:{r.get('positie')}"
                if entry not in needs_review:
                    needs_review.append(entry)

    new_state["orderregels"] = regels_out
    new_state["mixprijzen_actief"] = n_actief > 0
    new_state["order_mix_total_pallets"] = total_pallets or None
    if warnings != (state.get("validatie_warnings") or []):
        new_state["validatie_warnings"] = warnings
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
