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

from typing import NamedTuple, Optional

from sqlmodel import Session

from kwabo.db.repository import ArtikelkaartRepo, KlantRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log
from kwabo.utils.mixcode import is_mix_code, parse_mix_code
from kwabo.utils.pallet_logic import _qty_per_base

# How close rolls/rolls-per-pallet must be to a whole number to auto-accept the
# pallet count. Mix orders are whole pallets; a non-integer signals an ambiguous
# quantity we should not silently round, so we flag it for review instead.
_PALLET_TOL = 0.02


class _MixTier(NamedTuple):
    """A mix staffel tier for one article: the literal NAV code, its M-number
    threshold (parsed from the code, reliable), and the authoritative
    units-per-pallet read from ``ArtikelEenheid.qty_per_base`` (NOT the PALxx
    suffix, which is a possibly-typo'd label)."""

    code: str
    m_threshold: int
    units_per_pallet: float


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


def _mix_codes_for(eenheden: list) -> list[_MixTier]:
    """Parse the article's ArtikelEenheid rows into mix tiers (deduped).

    Each tier pairs the parsed M-number threshold with the row's own
    ``qty_per_base`` (== NAV ``Qty_per_Unit_of_Measure``) as the authoritative
    units-per-pallet. The PALxx suffix is ignored for the math.
    """
    out: dict[str, _MixTier] = {}
    for e in eenheden:
        mc = parse_mix_code(e.eenheid_code)
        if mc:
            out[mc.code] = _MixTier(
                mc.code, mc.m_threshold, float(e.qty_per_base or 0)
            )
    return list(out.values())


def _verkoop_keuze(
    kaart, eenheden: list, base: str, base_qty: float
) -> Optional[tuple[str, float]]:
    """Branch A (E1): kies de verkoopeenheid waarin de regel naar NAV gaat.

    Primair de kaart-`verkoop_eenheid` (NAV Sales_Unit_of_Measure), mits het
    een geldige eenheid van dit artikel is én het bestelde base-aantal er op
    een geheel aantal in past. Zonder dat veld: afleiden uit ArtikelEenheid,
    maar alleen bij PRECIES ÉÉN gehele niet-mix kandidaat (artikel 238601
    heeft b.v. PALLET33 én 'EXW PAL33', beide 33/base — twee kandidaten is
    geen keuze maar een gok). Geen keuze -> None; de caller dwingt dan de
    base-eenheid expliciet af.
    """
    per_code = {
        (e.eenheid_code or "").strip().upper(): float(e.qty_per_base or 0)
        for e in eenheden
    }

    def _heel(per: float) -> Optional[int]:
        if per <= 0:
            return None
        n = base_qty / per
        return int(round(n)) if n >= 1 and abs(n - round(n)) <= _PALLET_TOL else None

    code = ((kaart.verkoop_eenheid if kaart else "") or "").strip()
    if code and code.upper() != (base or "").upper():
        per = per_code.get(code.upper(), 0.0)
        if per > 0 and _heel(per) is not None:
            return code, per
        return None  # veld bekend maar ongeldig/niet-geheel -> expliciete base

    kandidaten = [
        (e.eenheid_code.strip(), float(e.qty_per_base))
        for e in eenheden
        if (e.qty_per_base or 0) > 1
        and not parse_mix_code(e.eenheid_code)
        and (e.eenheid_code or "").strip().upper() != (base or "").upper()
        and _heel(float(e.qty_per_base)) is not None
    ]
    return kandidaten[0] if len(kandidaten) == 1 else None


def _plain_pallet_equiv(
    mix_code: str, eenheden: list, base: str
) -> Optional[tuple[str, float]]:
    """De PLAIN (niet-mix) pallet-eenheid die dezelfde fysieke pallet-maat heeft
    als een mix-staffelcode (zelfde ``qty_per_base``). NAV-kaarten dragen soms
    een mix-code als Sales_Unit_of_Measure (datafout, bv. 23522 -> M1PAL30);
    de juiste verkoopeenheid is dan de canonieke ``PALLET``-UoM van het artikel.

    Voorkeur: een eenheid waarvan de code met ``PALLET`` begint (de canonieke
    pallet-UoM, bv. ``PALLET`` of ``PALLET70``); is die er niet en is er precies
    één plain niet-base eenheid met de juiste maat, dan die. Anders None (ambigu).
    Geeft ``(code, qty_per_base)`` of None.
    """
    mix_qty = next(
        (float(e.qty_per_base or 0) for e in eenheden
         if (e.eenheid_code or "").strip().upper() == mix_code.upper()),
        0.0,
    )
    if mix_qty <= 1:
        return None
    plains = [
        (e.eenheid_code.strip(), float(e.qty_per_base))
        for e in eenheden
        if e.eenheid_code and not parse_mix_code(e.eenheid_code) and not e.is_mix_uom
        and float(e.qty_per_base or 0) == mix_qty
        and e.eenheid_code.strip().upper() != (base or "").upper()
    ]
    pallet = [p for p in plains if p[0].upper().startswith("PALLET")]
    if len(pallet) == 1:
        return pallet[0]
    if pallet:
        exact = [p for p in pallet if p[0].upper() == "PALLET"]
        return exact[0] if len(exact) == 1 else None
    return plains[0] if len(plains) == 1 else None


def _branch_a(regel: dict, art_repo: ArtikelkaartRepo) -> Optional[str]:
    """E1/E2: een niet-mix-regel krijgt ALTIJD een expliciete eenheid + het
    omgerekende aantal in `verkoop_uom_gekozen`/`verkoop_aantal`.

    NAV default een nieuwe orderregel naar de VERKOOPEENHEID van de kaart, niet
    naar de base-eenheid (faalgeval #716: quantity 66 zonder UoM-PATCH werd 66
    PALLET33 = €45.738 i.p.v. 2 PALLET33). Op NAV's default vertrouwen kan dus
    nooit. Een geldige NIET-base bestel-eenheid blijft staan (2-6-fix: "60
    stuks blijft 60 stuks") — de composer PATCHt die al expliciet.

    Returns een review-waarschuwing (str) als de kaart-verkoopeenheid niet
    bruikbaar was (mix-staffelcode als Sales-UoM), anders None.
    """
    art = regel.get("artikelnummer_kwabo_matched")
    if not art:
        return None
    kaart = art_repo.get(art)
    base = ((kaart.basis_eenheid if kaart else "") or "").strip()
    if not kaart or not base:
        return None  # geen mirror-data -> geen veilige keuze mogelijk
    ordered = (regel.get("eenheid") or "").strip()
    if ordered and ordered.upper() != base.upper():
        # Klant koos expliciet een geldige alternatieve eenheid — die blijft
        # staan (composer PATCHt hem al). Wel eventuele STALE afgeleiden uit
        # een eerdere run wissen (B3-herverwerking, #819-rerun): anders pusht
        # de composer de oude verkoop-keuze i.p.v. de gebrugde eenheid.
        regel.pop("verkoop_uom_gekozen", None)
        regel.pop("verkoop_aantal", None)
        return None
    try:
        qty = float(regel.get("hoeveelheid") or 0)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None

    eenheden = art_repo.list_eenheden(art)
    # match_articles viel bij een ONgeldige bestel-eenheid al terug op base;
    # de hoeveelheid staat dan in de oorspronkelijke eenheid. Onbekende codes
    # tellen als base (qty_per_base 1.0) — zelfde aanname als _to_rolls.
    base_qty = qty * _qty_per_base(eenheden, regel.get("eenheid_origineel") or "")

    # PPG #941: een MIX-staffelcode (M{n}PAL{n}, bv. M1PAL30 op artikel 23522)
    # als Sales_Unit_of_Measure is een NAV-datafout — geen geldige
    # verkoopeenheid op een niet-mix-order. Nooit stil als verkoopeenheid
    # zetten: expliciete base + review (zo krijgen drie zusterartikelen niet
    # STUK/M1PAL30/PALLET door een scheve kaart). Een gewone pallet-code
    # (PALLET, PALLET33) is GEEN mix-code en blijft de normale Branch-A-keuze.
    code = ((kaart.verkoop_eenheid or "")).strip()
    if code and is_mix_code(code):
        # Vertaal de mix-staffelcode naar de PLAIN pallet-eenheid (zelfde maat)
        # zodat de regel consistent is met zuster-artikelen (23522 -> PALLET 2,
        # net als 23523) en geen handmatige review vergt. Geen schone vertaling
        # -> base + review-vlag (nooit stil de mix-code zelf gebruiken).
        plain = _plain_pallet_equiv(code, eenheden, base)
        if plain is not None:
            pcode, per = plain
            n = base_qty / per
            if n >= 1 and abs(n - round(n)) <= _PALLET_TOL:
                regel["verkoop_uom_gekozen"] = pcode
                regel["verkoop_aantal"] = int(round(n))
                return None
        regel["verkoop_uom_gekozen"] = base
        regel["verkoop_aantal"] = base_qty
        return (
            f"⚠ VERKOOPEENHEID CONTROLEREN (regel {regel.get('positie')}): artikel "
            f"{art} heeft mix-staffelcode '{code}' als verkoopeenheid in NAV "
            f"en geen eenduidige pallet-eenheid; teruggevallen op '{base}'."
        )

    keuze = _verkoop_keuze(kaart, eenheden, base, base_qty)
    if keuze is not None:
        code, per = keuze
        regel["verkoop_uom_gekozen"] = code
        regel["verkoop_aantal"] = int(round(base_qty / per))
    else:
        regel["verkoop_uom_gekozen"] = base
        regel["verkoop_aantal"] = base_qty
    return None


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
            w = _branch_a(r, art_repo)
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
        # Units-per-pallet is the physical pallet size. Use qty_per_base
        # (authoritative), not the cosmetic PALxx suffix which can have typos
        # (live item 15450). Een artikel kan mixcodes in MEERDERE families
        # hebben (238601: M*PAL33/35/42) — dan kiest de verkoopeenheid van de
        # kaart de juiste familie (M4: "binnen de juiste PAL{Y}-familie").
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
            ambiguous = True  # genuinely inconsistent/incomplete NAV data
        rpp = min(upps)
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

    # Branch A (E1/E2) voor de niet-mix-regels van een mix-klant: ook die
    # moeten met een EXPLICIETE eenheid naar NAV. Mix-regels (incl. de
    # review-gevallen, herkenbaar aan mix_uom_kandidaat) blijven van de
    # mix-logica.
    warnings = list(state.get("validatie_warnings") or [])
    for r in regels_out:
        if "mix_uom_kandidaat" not in r:
            w = _branch_a(r, art_repo)
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
