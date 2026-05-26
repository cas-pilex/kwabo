"""Convenience runner: parse an .eml and run the ingest graph to review state."""
from __future__ import annotations

from pathlib import Path

from kwabo.graph.graph import get_finalize_app, get_ingest_app, get_sub_order_app
from kwabo.graph.nodes.extract import _build_state_from_extract
from kwabo.graph.state import OrderState, new_state
from kwabo.integrations.email_client import parse_eml_file
from kwabo.utils.logging import log


def _raw_email_to_state(raw) -> OrderState:
    bijlagen = []
    for b in raw.bijlagen:
        # Keep raw bytes so the Vision-extractor can re-encode the PDF as a document block.
        bijlagen.append(
            {
                "naam": b.naam,
                "type": b.type,
                "inhoud_tekst": b.inhoud_tekst,
                "raw": b.raw,
            }
        )
    return new_state(
        email_id=raw.email_id,
        email_from=raw.email_from,
        email_subject=raw.email_subject,
        email_body=raw.email_body,
        email_date=raw.email_date,
        bijlagen=bijlagen,
        source_path=raw.source_path,
    )


async def _run_extras(primary: OrderState, raw) -> list[OrderState]:
    """Run the sub-order graph for each extra order returned by LLM as array."""
    from kwabo.utils import utcnow

    extras = primary.get("extra_orders_raw") or []
    if not extras:
        return []
    sub_app = get_sub_order_app()
    results: list[OrderState] = []
    primary_email_id = primary.get("email_id") or ""
    primary_log_id = primary.get("order_log_id")
    # Copy parent's intake/classify/extract stappen_log so sub-order audit is complete
    parent_steps = [s for s in (primary.get("stappen_log") or []) if s.get("stap") in ("intake", "classify", "extract")]

    for idx, extra_parsed in enumerate(extras, start=2):
        # Per-sub isolation: a crashing sub-order MUST NOT propagate to the
        # caller. /api/intake/scan calls mark_seen AFTER _run_extras returns;
        # if one sub crashes the exception would skip mark_seen and the
        # primary mail gets re-processed → duplicate primary in DB. Catch
        # locally, log, continue with the next sub.
        try:
            flat, meta, needs = _build_state_from_extract(extra_parsed, raw)
            spawn_step = {
                "stap": "multi_order_spawn",
                "timestamp": utcnow().isoformat(),
                "beslissing": f"Afgesplitst als sub-order {idx} uit parent log_id={primary_log_id}",
                "details": {"parent_email_id": primary_email_id, "parent_log_id": primary_log_id, "sub_index": idx},
            }
            sub_state: OrderState = {
                **_raw_email_to_state(raw),
                **flat,
                "email_id": f"{primary_email_id}#sub{idx}",
                "email_subject": f"{primary.get('email_subject') or ''} (sub-order {idx})",
                "is_order": True,
                "classificatie_confidence": primary.get("classificatie_confidence"),
                "_meta": meta,
                "needs_review_fields": needs,
                "needs_review_count": len(needs),
                "stappen_log": [*parent_steps, spawn_step],
                "parent_log_id": primary_log_id,
                "sub_order_index": idx,
            }
            log.info(
                "multi_order_spawn", parent_email_id=primary_email_id,
                parent_log_id=primary_log_id, sub_email_id=sub_state["email_id"], sub_index=idx,
            )
            res = await sub_app.ainvoke(sub_state)
            results.append(res)
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "sub_order_crashed",
                parent_email_id=primary_email_id,
                parent_log_id=primary_log_id,
                sub_index=idx,
                exc_type=type(exc).__name__,
                exc_msg=str(exc)[:300],
            )
            # Continue with the remaining sub-orders.
    return results


async def run_on_eml(path: str | Path) -> OrderState:
    """Run ingest on a single .eml. Also processes extra sub-orders from multi-order mails.

    Returns the primary state (extras are persisted separately in order_log).
    """
    raw = parse_eml_file(path)
    state = _raw_email_to_state(raw)
    app = get_ingest_app()
    primary = await app.ainvoke(state)
    await _run_extras(primary, raw)
    return primary


async def finalize(state: OrderState) -> OrderState:
    app = get_finalize_app()
    return await app.ainvoke(state)
