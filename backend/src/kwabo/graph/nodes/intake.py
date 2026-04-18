"""Intake node: stamp audit log for email intake."""
from __future__ import annotations

from datetime import datetime

from kwabo.utils import utcnow

from kwabo.graph.state import OrderState
from kwabo.utils.logging import log


async def intake_node(state: OrderState) -> OrderState:
    bijlagen = state.get("bijlagen") or []
    stap = {
        "stap": "intake",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"E-mail opgehaald, {len(bijlagen)} bijlagen geëxtraheerd",
        "details": {"bijlage_namen": [b.get("naam") for b in bijlagen]},
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)
    log.info(
        "intake",
        email_id=state.get("email_id"),
        from_=state.get("email_from"),
        subject=(state.get("email_subject") or "")[:60],
        bijlagen=len(bijlagen),
    )
    return {**state, "stappen_log": steps}
