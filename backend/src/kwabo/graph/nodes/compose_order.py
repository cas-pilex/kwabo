"""Compose order — persist current state to order_log with status='review'.

Also composes the trigger-aware NAV operation list (via T4's
`compose_navision_operations`) and stores it in `state["nav_operations"]`.
The dashboard's navision-preview endpoint reads that list to show the
reviewer exactly which POST/PATCHes will fire when push_navision runs.
We never execute those operations here — that's push_navision's job after
the human approves the order. This node's responsibility is purely
"freeze the prepared payload + persist a review row".
"""
from __future__ import annotations

import json
from datetime import datetime

from kwabo.utils import utcnow
from typing import Any

from sqlmodel import Session

from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState
from kwabo.integrations.navision_steps import compose_navision_operations
from kwabo.utils.logging import log


def _serialisable_state(state: OrderState) -> dict[str, Any]:
    """Strip raw bytes from bijlagen so the state can be JSON-serialised + re-loaded."""
    out: dict[str, Any] = {}
    for k, v in state.items():
        if k == "bijlagen":
            out[k] = [
                {kk: vv for kk, vv in (b or {}).items() if kk != "raw"}
                for b in (v or [])
            ]
        else:
            out[k] = v
    return out


async def compose_order_node(state: OrderState) -> OrderState:
    klant = state.get("klant_match") or {}
    warnings = state.get("validatie_warnings") or []
    regels = state.get("orderregels") or []
    # Status: "not_order" (classify rejected), else "review"
    new_status = "review" if state.get("is_order") else "not_order"

    # Compose the chronologically ordered NAV operation list. Pure function
    # over state — safe to call here even when validation gates haven't
    # passed; the dashboard preview shows reviewers the planned ops while
    # they fix problems. Returns [] if there's no matched customer (in
    # which case push_navision will refuse to run anyway).
    nav_operations: list[dict] = []
    if state.get("is_order"):
        try:
            nav_operations = list(compose_navision_operations(dict(state)))
        except Exception as exc:  # noqa: BLE001
            # Compose is pure but defensive: bad state shouldn't crash the
            # pre-review save. We log + leave nav_operations empty; the
            # reviewer + push_navision both surface the missing list.
            log.error(
                "compose_navision_operations_failed",
                email_id=state.get("email_id"),
                error=f"{type(exc).__name__}: {exc}"[:200],
            )
            nav_operations = []

    state_for_save = {**state, "nav_operations": nav_operations}

    payload = {
        "email_id": state.get("email_id"),
        "email_from": state.get("email_from"),
        "email_subject": state.get("email_subject"),
        "email_date": state.get("email_date"),
        "status": new_status,
        "is_order": state.get("is_order"),
        "classificatie_confidence": state.get("classificatie_confidence"),
        "klant_nr": klant.get("navision_klantnr"),
        "klant_match_confidence": klant.get("match_confidence"),
        "klant_match_methode": klant.get("match_bron"),
        "bestelnummer_klant": state.get("bestelnummer_klant"),
        "aantal_regels": len(regels),
        "alle_artikelen_gematcht": state.get("alle_artikelen_gematcht"),
        "alle_prijzen_valide": state.get("alle_prijzen_valide"),
        "warnings": json.dumps(warnings, default=str),
        "stappen_log": json.dumps(state.get("stappen_log") or [], default=str),
        "order_state": json.dumps(_serialisable_state(state_for_save), default=str),
    }

    with Session(engine) as s:
        repo = OrderLogRepo(s)
        existing = repo.by_email(state.get("email_id") or "")
        if existing:
            repo.update(existing.id, **payload)
            log_id = existing.id
        else:
            row = repo.create(**payload)
            log_id = row.id

    stap = {
        "stap": "compose_order",
        "timestamp": utcnow().isoformat(),
        "beslissing": (
            f"Order-concept opgeslagen (log_id={log_id}, status={new_status}, "
            f"nav_operations={len(nav_operations)})"
        ),
        "details": {
            "regels": len(regels),
            "warnings": len(warnings),
            "status": new_status,
            "nav_operations_count": len(nav_operations),
        },
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    log.info(
        "compose_order",
        email_id=state.get("email_id"),
        log_id=log_id,
        regels=len(regels),
        nav_operations=len(nav_operations),
    )
    return {
        **state,
        "order_log_id": log_id,
        "review_status": "pending",
        "nav_operations": nav_operations,
        "stappen_log": steps,
    }
