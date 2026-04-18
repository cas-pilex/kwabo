"""Push to Navision (mock or real)."""
from __future__ import annotations

import json
from datetime import datetime

from kwabo.utils import utcnow

from sqlmodel import Session

from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState
from kwabo.integrations.navision_api import build_sales_order_payload, get_navision_client
from kwabo.utils.logging import log


async def push_navision_node(state: OrderState) -> OrderState:
    nav = get_navision_client()
    payload = build_sales_order_payload(dict(state))
    header = payload["header"]
    lines = payload["lines"]
    result = await nav.create_sales_order(header, lines)
    order_nr = result["number"]
    log.info("push_navision", email_id=state.get("email_id"), navision_order_nr=order_nr, lines=len(lines))

    with Session(engine) as s:
        repo = OrderLogRepo(s)
        if state.get("order_log_id"):
            repo.update(
                state["order_log_id"],
                navision_order_nr=order_nr,
                status="pushed",
            )

    stap = {
        "stap": "push_navision",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"Verkooporder {order_nr} aangemaakt",
        "details": {"order_id": result["id"], "regels": len(lines)},
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    return {
        **state,
        "navision_order_nr": order_nr,
        "navision_status": "Draft",
        "stappen_log": steps,
    }


async def send_confirmation_node(state: OrderState) -> OrderState:
    from kwabo.integrations.mail_sender import get_mail_sender, render_confirmation

    klant = state.get("klant_match") or {}
    to_email = state.get("email_from") or ""
    # Extract bare email from "Name <addr>" format
    import re
    m = re.search(r"[\w\.\-\+]+@[\w\.\-]+", to_email)
    to_addr = m.group(0) if m else to_email

    subject, body = render_confirmation(
        klant_naam=klant.get("klantnaam") or "",
        bestelnr_klant=state.get("bestelnummer_klant"),
        navision_order_nr=state.get("navision_order_nr"),
    )

    mail_sent = False
    try:
        sender = get_mail_sender()
        await sender.send(to_addr, subject, body)
        mail_sent = True
    except Exception as e:  # noqa: BLE001
        log.error("send_confirmation_failed", error=str(e)[:200], to=to_addr)

    stap = {
        "stap": "send_confirmation",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"{'Bevestiging verstuurd' if mail_sent else 'Bevestiging gelogd (mail-mode)'} voor {state.get('navision_order_nr')} → {to_addr}",
        "details": {"to": to_addr, "mail_sent": mail_sent, "subject": subject},
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)
    log.info("send_confirmation", email_id=state.get("email_id"), navision_order_nr=state.get("navision_order_nr"), to=to_addr, mail_sent=mail_sent)
    return {**state, "stappen_log": steps}
