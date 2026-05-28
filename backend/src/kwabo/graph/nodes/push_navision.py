"""Push to Navision (mock or real) — trigger-aware stepwise execution.

This node consumes `state["nav_operations"]` (composed in compose_order
via T4's `compose_navision_operations`) and executes them sequentially
against the active NAV client through `create_sales_order_stepwise`. The
stepwise client stops at the first error — see T3. The full per-op
result list is preserved on state for the audit trail and dashboard.

Failure semantics:
  * No nav_operations on state -> mark order as `failed` (compose was
    expected to populate this list; missing means an upstream problem).
  * Any operation_result with `error` -> mark order as `failed`. We log
    every op_result so the dashboard can replay the audit trail.
  * Otherwise: mark `pushed` and capture sales_order_number on the row.
"""
from __future__ import annotations

import json
from datetime import datetime

from kwabo.utils import utcnow

from sqlmodel import Session

from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState
from kwabo.integrations.navision_api import get_navision_client
from kwabo.utils.logging import log


def _serialise_op_results(results: list[dict]) -> list[dict]:
    """Drop raw bytes / heavy fields so op-results survive json.dumps."""
    out = []
    for r in results or []:
        out.append({
            "operation": {
                # Keep all keys except 'body'; for 'body' keep only dicts so
                # JSON serialization stays clean (drops None/raw strings).
                k: v for k, v in (r.get("operation") or {}).items()
                if k != "body" or isinstance(v, dict)
            },
            "status": r.get("status"),
            "response_body": r.get("response_body") or {},
            "autofilled": r.get("autofilled") or {},
            **({"error": r["error"]} if r.get("error") else {}),
        })
    return out


def _mark_failed(state: OrderState, reason: str, op_results: list[dict]) -> OrderState:
    """Common path for failed pushes: log row update, audit step, state echo."""
    serialised = _serialise_op_results(op_results)
    log.error(
        "push_navision_failed",
        email_id=state.get("email_id"),
        order_log_id=state.get("order_log_id"),
        reason=reason,
        op_results=serialised,
    )

    stap = {
        "stap": "push_navision",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"Push afgebroken: {reason}",
        "details": {
            "reason": reason,
            "op_results": serialised,
            "op_count": len(op_results or []),
        },
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)
    errors = list(state.get("errors") or [])
    errors.append(f"push_navision: {reason}")

    if state.get("order_log_id"):
        # Same reason as the success path: persist the trail so /nav-debug
        # has something to show. Without this, a "failed" badge in the UI
        # has no operations log behind it.
        import json as _json
        with Session(engine) as s:
            repo = OrderLogRepo(s)
            row = repo.get(state["order_log_id"])
            if row is not None:
                persisted = _json.loads(row.order_state or "{}") if row.order_state else {}
                persisted["navision_status"] = "failed"
                persisted["nav_operation_results"] = serialised
                persisted["stappen_log"] = steps
                persisted["errors"] = errors
                row.order_state = _json.dumps(persisted, default=str)
                row.status = "failed"
                row.updated_at = utcnow()
                s.add(row)
                s.commit()

    return {
        **state,
        "navision_status": "failed",
        "nav_operation_results": op_results or [],
        "stappen_log": steps,
        "errors": errors,
    }


async def push_navision_node(state: OrderState) -> OrderState:
    nav_operations = state.get("nav_operations") or []
    if not nav_operations:
        return _mark_failed(state, "no nav_operations on state", [])

    nav = get_navision_client()
    try:
        result = await nav.create_sales_order_stepwise(nav_operations)
    except Exception as exc:  # noqa: BLE001
        return _mark_failed(state, f"client raised {type(exc).__name__}: {exc}", [])

    op_results = list(result.get("operation_results") or [])
    autofilled = dict(result.get("nav_autofilled") or {})
    sales_order_id = result.get("sales_order_id") or ""
    sales_order_number = result.get("sales_order_number") or ""

    failed_ops = [r for r in op_results if r.get("error")]
    if failed_ops:
        # Stop-on-error semantics: at least one op failed. Mark the row
        # failed but preserve every op_result for audit/replay.
        first_error = failed_ops[0].get("error", "unknown")
        state_with_results = {
            **state,
            "nav_operation_results": op_results,
            "nav_autofilled": autofilled,
        }
        return _mark_failed(
            state_with_results,
            f"NAV op failed: {first_error}",
            op_results,
        )

    log.info(
        "push_navision",
        email_id=state.get("email_id"),
        navision_order_nr=sales_order_number,
        sales_order_id=sales_order_id,
        ops=len(op_results),
        autofilled=list(autofilled.keys()),
    )

    stap = {
        "stap": "push_navision",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"Verkooporder {sales_order_number} aangemaakt via {len(op_results)} NAV-operaties",
        "details": {
            "sales_order_id": sales_order_id,
            "sales_order_number": sales_order_number,
            "op_count": len(op_results),
            "autofilled_keys": list(autofilled.keys()),
        },
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    serialised_ops = _serialise_op_results(op_results)
    if state.get("order_log_id"):
        # Persist the full operation trail + autofill to order_state. Without
        # this, /api/orders/{id}/nav-debug shows an empty list because the
        # repo.update() above only writes a few columns. The trail is the
        # primary forensic artefact when a reviewer wants to know what
        # actually went over the wire.
        import json as _json
        with Session(engine) as s:
            repo = OrderLogRepo(s)
            row = repo.get(state["order_log_id"])
            if row is not None:
                persisted = _json.loads(row.order_state or "{}") if row.order_state else {}
                persisted["navision_status"] = "Draft"
                persisted["navision_order_nr"] = sales_order_number
                persisted["nav_operation_results"] = serialised_ops
                persisted["nav_autofilled"] = autofilled
                persisted["stappen_log"] = steps
                serialized = _json.dumps(persisted, default=str)
                # Observability: orders that balloon past ~500KB indicate
                # something is accumulating (huge PDF text, append-only logs)
                # and will hurt review-page load. Log so we can alert.
                size_kb = len(serialized) / 1024
                if size_kb > 500:
                    log.warning(
                        "state_json_large",
                        order_log_id=state["order_log_id"],
                        size_kb=round(size_kb, 1),
                    )
                    from kwabo.utils.alerts import alert
                    alert(
                        "state_json_large",
                        "warning",
                        {
                            "order_log_id": state["order_log_id"],
                            "size_kb": round(size_kb, 1),
                        },
                    )
                row.order_state = serialized
                row.navision_order_nr = sales_order_number
                row.status = "pushed"
                row.updated_at = utcnow()
                s.add(row)
                s.commit()

    return {
        **state,
        "navision_order_nr": sales_order_number,
        "navision_status": "Draft",
        "nav_operation_results": op_results,
        "nav_autofilled": autofilled,
        "stappen_log": steps,
    }


async def send_confirmation_node(state: OrderState) -> OrderState:
    from kwabo.integrations.mail_sender import get_mail_sender, render_confirmation

    # If push_navision failed, skip the confirmation: nothing to confirm.
    if state.get("navision_status") == "failed" or not state.get("navision_order_nr"):
        stap = {
            "stap": "send_confirmation",
            "timestamp": utcnow().isoformat(),
            "beslissing": "Geen bevestiging — push_navision is mislukt of leverde geen ordernummer op",
            "details": {"skipped": True},
        }
        steps = list(state.get("stappen_log") or [])
        steps.append(stap)
        return {**state, "stappen_log": steps}

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
