"""Apply mixprijzen node (T7).

Runs after `match_articles` (so every regel has its `kwabo_artikelnr_matched`
resolved where possible) and before `validate_prices`.

Responsibility scope is intentionally narrow: NAV's own mix-codeunit owns the
actual mix-price calculation. This node only:

1. Decides whether mix-pricing applies at all by checking the customer's
   ``mixprijzen`` flag on the klantenkaart mirror. If the customer is not
   mix-eligible, ``state["mixprijzen_actief"]`` is set to ``False`` and the
   node short-circuits.
2. For each regel whose matched ``Artikelkaart.mixprijzen`` is true, picks
   the right mix unit-of-measure (UOM) so NAV will trigger its mix codeunit:

   - 0 mix-UOMs defined → flag ``mix_uom:<positie>`` for review and leave
     ``regel["mix_uom_gekozen"]`` as ``None``.
   - 1 mix-UOM → auto-pick.
   - >=2 mix-UOMs → score by minimal residue of
     ``regel.hoeveelheid / qty_per_base`` against the nearest whole "staffel"
     unit. Lowest residue wins. ``mix_uom_kandidaat`` carries the full
     ranked list so the dashboard can show alternates.

State writes:

- ``mixprijzen_actief``: ``True`` if at least one regel got a mix-UOM
  selection, otherwise ``False``.
- ``regel["mix_uom_kandidaat"]``: list of candidate UOM codes (ranked, best
  first) — only set on regels we actually evaluated.
- ``regel["mix_uom_gekozen"]``: chosen UOM code, or ``None`` when ambiguous
  / no mix-UOMs defined.
- ``needs_review_fields``: ``mix_uom:<positie>`` entries when no mix-UOM
  could be chosen for an artikel that needs one.

Like ``select_ship_to``, the node accepts injectable repos for tests so we
do not need to monkeypatch the module-level engine.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from kwabo.db.models import ArtikelEenheid
from kwabo.db.repository import ArtikelkaartRepo, KlantRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log


def _list_mix_uoms(session: Session, kwabo_artikelnr: str) -> list[ArtikelEenheid]:
    return list(
        session.exec(
            select(ArtikelEenheid).where(
                (ArtikelEenheid.kwabo_artikelnr == kwabo_artikelnr)
                & (ArtikelEenheid.is_mix_uom == True)  # noqa: E712 — sqlmodel filter
            )
        ).all()
    )


def _choose_uom(
    mix_uoms: list[ArtikelEenheid], hoeveelheid: float
) -> tuple[list[str], Optional[str]]:
    """Return ``(ranked_candidates, chosen)``.

    With 1 candidate we auto-pick. With multiple, rank by the residue of
    ``hoeveelheid / qty_per_base`` against the nearest whole staffel unit
    (lower residue = better fit). UOMs with non-positive ``qty_per_base``
    are skipped; if all are skipped we return all candidate codes ranked
    in their original order with ``chosen=None`` so the caller can flag
    review.
    """
    if len(mix_uoms) == 1:
        code = mix_uoms[0].eenheid_code
        return [code], code

    scored: list[tuple[str, float]] = []
    for u in mix_uoms:
        if u.qty_per_base <= 0:
            continue
        mix_units = hoeveelheid / u.qty_per_base
        residue = abs(mix_units - round(mix_units))
        scored.append((u.eenheid_code, residue))

    if not scored:
        return [u.eenheid_code for u in mix_uoms], None

    scored.sort(key=lambda x: x[1])
    return [code for code, _ in scored], scored[0][0]


def _evaluate(
    state: dict,
    klant_repo: KlantRepo,
    artikelkaart_repo: ArtikelkaartRepo,
    session: Session,
) -> dict:
    new_state = dict(state)
    new_state["mixprijzen_actief"] = False

    klant_match = state.get("klant_match") or {}
    klant_nr = klant_match.get("navision_klantnr")
    if not klant_nr:
        return new_state

    klant_record = klant_repo.by_nav_nr(klant_nr)
    if not klant_record or not klant_record.mixprijzen:
        # Customer not mix-eligible — short-circuit, leave regels untouched.
        log.info(
            "apply_mixprijzen",
            email_id=state.get("email_id"),
            klant_nr=klant_nr,
            klant_mix=False,
            mixprijzen_actief=False,
        )
        return new_state

    needs_review = list(state.get("needs_review_fields") or [])
    regels_in = state.get("orderregels") or []
    regels_out: list[dict] = []
    n_actief = 0
    n_review = 0

    for regel in regels_in:
        r = dict(regel)
        kwabo_nr = r.get("artikelnummer_kwabo_matched")
        if not kwabo_nr:
            regels_out.append(r)
            continue

        artikel = artikelkaart_repo.get(kwabo_nr)
        if not artikel or not artikel.mixprijzen:
            regels_out.append(r)
            continue

        mix_uoms = _list_mix_uoms(session, kwabo_nr)
        if not mix_uoms:
            r["mix_uom_kandidaat"] = None
            r["mix_uom_gekozen"] = None
            entry = f"mix_uom:{r.get('positie')}"
            if entry not in needs_review:
                needs_review.append(entry)
            n_review += 1
            regels_out.append(r)
            continue

        hoeveelheid = float(r.get("hoeveelheid") or 0)
        ranked, chosen = _choose_uom(mix_uoms, hoeveelheid)
        r["mix_uom_kandidaat"] = ranked
        r["mix_uom_gekozen"] = chosen
        if chosen is None:
            entry = f"mix_uom:{r.get('positie')}"
            if entry not in needs_review:
                needs_review.append(entry)
            n_review += 1
        else:
            n_actief += 1
        regels_out.append(r)

    new_state["orderregels"] = regels_out
    new_state["mixprijzen_actief"] = n_actief > 0
    if needs_review != (state.get("needs_review_fields") or []):
        new_state["needs_review_fields"] = needs_review
        new_state["needs_review_count"] = len(needs_review)

    log.info(
        "apply_mixprijzen",
        email_id=state.get("email_id"),
        klant_nr=klant_nr,
        klant_mix=True,
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
    """Pick the mix-UOM per mix-eligible regel; flag review when ambiguous.

    Tests can inject ``repo_klant``/``repo_artikelkaart`` and ``session`` (all
    bound to the same DB) to exercise the node without monkeypatching the
    module-level engine. In production, when nothing is injected, the node
    opens its own session against ``kwabo.db.session.engine`` — mirroring the
    pattern in ``select_ship_to_node`` and ``match_articles_node``.
    """
    if repo_klant is not None and repo_artikelkaart is not None and session is not None:
        return _evaluate(state, repo_klant, repo_artikelkaart, session)

    with Session(engine) as s:
        klant_repo = repo_klant or KlantRepo(s)
        artikelkaart_repo = repo_artikelkaart or ArtikelkaartRepo(s)
        return _evaluate(state, klant_repo, artikelkaart_repo, s)
