"""Select ship-to node (T5).

Runs after `match_customer`. Given the resolved klant, fetch their ship-to
addresses from the local NAV mirror (table klantenkaart_ship_to populated by
T2 master-sync), score each candidate against the email's afleveradres, and
select the best match.

Outcomes written to state:
- ``ship_to_kandidaten`` — full list of candidate dicts (for dashboard display)
- ``ship_to_gekozen`` — the chosen ship_to_code, or ``None`` if no clear winner
- ``needs_review_fields`` — appended with ``ship_to_gekozen`` when ambiguous

Notes:
- 0 records → no ship-to override; NAV will fall back to the customer's
  default address. ``ship_to_gekozen`` is set to ``None`` and we do NOT flag
  for review (this is the normal case for many customers).
- 1 record → auto-pick.
- ≥2 records → score, pick top if unambiguous and score > 0.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from kwabo.db.models import KlantenkaartShipTo
from kwabo.db.repository import ShipToRepo
from kwabo.db.session import engine
from kwabo.utils.logging import log


def _normalize_postcode(value: str | None) -> str:
    if not value:
        return ""
    return "".join(value.split()).lower()


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {t for t in value.lower().split() if t}


def _score_ship_to(record: KlantenkaartShipTo, afleveradres: dict) -> int:
    """Heuristic score: postcode (5) > plaats (3) > naam token-overlap (2) > straat (1)."""
    score = 0

    rec_pc = _normalize_postcode(getattr(record, "postcode", None))
    addr_pc = _normalize_postcode(afleveradres.get("postcode"))
    if rec_pc and addr_pc and rec_pc == addr_pc:
        score += 5

    rec_plaats = (getattr(record, "plaats", None) or "").lower()
    addr_plaats = (afleveradres.get("plaats") or "").lower()
    if rec_plaats and addr_plaats and (
        rec_plaats in addr_plaats or addr_plaats in rec_plaats
    ):
        score += 3

    rec_naam_tokens = _tokens(getattr(record, "naam", None))
    addr_naam_tokens = _tokens(afleveradres.get("naam"))
    if rec_naam_tokens and addr_naam_tokens and (rec_naam_tokens & addr_naam_tokens):
        score += 2

    rec_straat = (getattr(record, "straat", None) or "").lower()
    addr_straat = (afleveradres.get("straat") or "").lower()
    if rec_straat and addr_straat and (
        rec_straat in addr_straat or addr_straat in rec_straat
    ):
        score += 1

    return score


def _serialize(c: KlantenkaartShipTo) -> dict:
    return {
        "klant_nr": c.klant_nr,
        "ship_to_code": c.ship_to_code,
        "naam": c.naam,
        "straat": c.straat,
        "postcode": c.postcode,
        "plaats": c.plaats,
        "land": c.land,
        "is_default": c.is_default,
    }


async def select_ship_to_node(
    state: dict, *, repo: Optional[ShipToRepo] = None
) -> dict:
    klant_match = state.get("klant_match")
    if not klant_match or not klant_match.get("navision_klantnr"):
        # No klant resolved — nothing to select. Pass through untouched.
        return state

    klant_nr = klant_match["navision_klantnr"]

    # Allow tests / callers to inject a repo bound to their own session. When
    # no repo is supplied, mirror the pattern used by match_customer / match_articles
    # and open a Session against the module-level engine.
    if repo is not None:
        candidates = repo.list_for_klant(klant_nr)
        return _decide(state, candidates)

    with Session(engine) as s:
        candidates = ShipToRepo(s).list_for_klant(klant_nr)
        return _decide(state, candidates)


def _decide(state: dict, candidates: list[KlantenkaartShipTo]) -> dict:
    new_state = dict(state)
    new_state["ship_to_kandidaten"] = [_serialize(c) for c in candidates]

    if len(candidates) == 0:
        # NAV will use the customer's default ship-to. Not a review trigger.
        new_state["ship_to_gekozen"] = None
        log.info(
            "select_ship_to",
            email_id=state.get("email_id"),
            klant_nr=(state.get("klant_match") or {}).get("navision_klantnr"),
            n_candidates=0,
            chosen=None,
        )
        return new_state

    if len(candidates) == 1:
        new_state["ship_to_gekozen"] = candidates[0].ship_to_code
        log.info(
            "select_ship_to",
            email_id=state.get("email_id"),
            klant_nr=(state.get("klant_match") or {}).get("navision_klantnr"),
            n_candidates=1,
            chosen=candidates[0].ship_to_code,
        )
        return new_state

    afleveradres = state.get("afleveradres") or {}
    scored = [(c, _score_ship_to(c, afleveradres)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_score = scored[0][1]
    tied = [c for c, s in scored if s == top_score]

    if len(tied) == 1 and top_score > 0:
        chosen = tied[0].ship_to_code
        new_state["ship_to_gekozen"] = chosen
        log.info(
            "select_ship_to",
            email_id=state.get("email_id"),
            klant_nr=(state.get("klant_match") or {}).get("navision_klantnr"),
            n_candidates=len(candidates),
            chosen=chosen,
            top_score=top_score,
        )
        return new_state

    # Ambiguous → flag for review.
    new_state["ship_to_gekozen"] = None
    needs_review = list(state.get("needs_review_fields") or [])
    if "ship_to_gekozen" not in needs_review:
        needs_review.append("ship_to_gekozen")
    new_state["needs_review_fields"] = needs_review
    new_state["needs_review_count"] = len(needs_review)
    log.info(
        "select_ship_to",
        email_id=state.get("email_id"),
        klant_nr=(state.get("klant_match") or {}).get("navision_klantnr"),
        n_candidates=len(candidates),
        chosen=None,
        top_score=top_score,
        ambiguous=True,
    )
    return new_state
