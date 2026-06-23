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

import re
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


def _order_signal_text(state: dict) -> str:
    """All free text we can read the delivery LOCATION from: subject, sender,
    body, and the attachment text (the PDF where the klantnaam+vestiging is
    printed, e.g. 'Pontmeyer Heerenveen'), plus any explicit afleveradres.
    Lower-cased for word matching."""
    parts = [
        state.get("email_subject") or "",
        state.get("email_from") or "",
        state.get("email_body") or "",
    ]
    for b in state.get("bijlagen") or []:
        parts.append((b or {}).get("inhoud_tekst") or "")
    afl = state.get("afleveradres") or {}
    parts += [str(afl.get("naam") or ""), str(afl.get("plaats") or ""), str(afl.get("straat") or "")]
    return " ".join(parts).lower()


def _word_in(text: str, term: str | None) -> bool:
    term = (term or "").strip().lower()
    if not term:
        return False
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def _distinct_name_hits(
    candidates: list[KlantenkaartShipTo], signal: str
) -> list[KlantenkaartShipTo]:
    """Candidates whose DISTINGUISHING name token (the part that differs
    between locations, e.g. 'heerenveen' in 'Pontmeyer Heerenveen') appears
    in the order text. Tokens shared by all candidates ('pontmeyer') don't
    discriminate and are ignored."""
    token_sets = [_tokens(getattr(c, "naam", None)) for c in candidates]
    common = set.intersection(*token_sets) if token_sets and all(token_sets) else set()
    hits: list[KlantenkaartShipTo] = []
    for c, toks in zip(candidates, token_sets):
        distinct = {t for t in (toks - common) if len(t) >= 3}
        if any(_word_in(signal, t) for t in distinct):
            hits.append(c)
    return hits


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
    signal = _order_signal_text(state)

    def _choose(chosen_code: str, reason: str, **extra) -> dict:
        new_state["ship_to_gekozen"] = chosen_code
        log.info(
            "select_ship_to",
            email_id=state.get("email_id"),
            klant_nr=(state.get("klant_match") or {}).get("navision_klantnr"),
            n_candidates=len(candidates),
            chosen=chosen_code,
            reason=reason,
            **extra,
        )
        return new_state

    # (0) Sterkste, meest specifieke leversignaal: een UNIEKE kandidaat met
    # exact de afleveradres-postcode. Die wint vóór de order-tekst-heuristiek —
    # anders kan een stad die toevallig elders in de order-tekst staat (BAUHAUS
    # #944: de factuurstad 'Bunnik' in de PDF) de juiste leverpostcode
    # (7559 SR Hengelo, óók een kandidaat) overstemmen.
    addr_pc = _normalize_postcode(afleveradres.get("postcode"))
    if addr_pc:
        pc_hits = [c for c in candidates
                   if _normalize_postcode(getattr(c, "postcode", None)) == addr_pc]
        if len(pc_hits) == 1:
            return _choose(pc_hits[0].ship_to_code, "afleveradres_postcode_exact",
                           postcode=pc_hits[0].postcode)

    # (1) Primary, per Cas: a multi-location customer prints the vestiging in
    # the order/PDF (the klantnaam, e.g. "Pontmeyer Heerenveen"). Match each
    # candidate's CITY against the order text. Auto-pick ONLY when exactly one
    # city is named — never guess between Heerenveen and Arnhem.
    plaats_hits = [c for c in candidates if _word_in(signal, getattr(c, "plaats", None))]
    if len(plaats_hits) == 1:
        return _choose(plaats_hits[0].ship_to_code, "plaats_in_order_text",
                       plaats=plaats_hits[0].plaats)

    # (2) Else a distinguishing NAME token (the differing part) in the order text.
    if not plaats_hits:
        token_hits = _distinct_name_hits(candidates, signal)
        if len(token_hits) == 1:
            return _choose(token_hits[0].ship_to_code, "naam_token_in_order_text",
                           naam=token_hits[0].naam)

    # (3) Explicit drop-ship afleveradres scoring (postcode/plaats/naam/straat).
    scored = [(c, _score_ship_to(c, afleveradres)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_score = scored[0][1]
    tied = [c for c, s in scored if s == top_score]
    if len(tied) == 1 and top_score > 0:
        return _choose(tied[0].ship_to_code, "afleveradres_score", top_score=top_score)

    # (4) Ambiguous → flag for review. We deliberately do NOT fall back to the
    # first/default location: shipping Heerenveen's order to Arnhem is worse
    # than asking the reviewer to pick. (Cas: "niet de eerste beste pakken".)
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
