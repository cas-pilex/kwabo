"""Compose order — persist current state to order_log with status='review'."""
from __future__ import annotations

import json
from datetime import datetime

from kwabo.utils import utcnow
from typing import Any

from sqlmodel import Session

from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState
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
        "order_state": json.dumps(_serialisable_state(state), default=str),
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
        "beslissing": f"Order-concept opgeslagen (log_id={log_id}, status={new_status})",
        "details": {"regels": len(regels), "warnings": len(warnings), "status": new_status},
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    log.info("compose_order", email_id=state.get("email_id"), log_id=log_id, regels=len(regels))
    return {**state, "order_log_id": log_id, "review_status": "pending", "stappen_log": steps}
