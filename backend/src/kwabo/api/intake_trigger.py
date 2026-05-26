"""Trigger intake on emails dropped into inbox_dir OR upload direct."""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from kwabo.config import settings
from kwabo.graph.runner import _raw_email_to_state, run_on_eml
from kwabo.integrations.email_client import get_email_client, parse_eml_bytes
from kwabo.utils.logging import log

router = APIRouter(prefix="/api/intake", tags=["intake"])

# Stop processing new emails once the scan has been running this long.
# Railway request timeout is ~5 min; we cut at 4 min so we can return a
# meaningful response with partial=true and the reviewer can re-scan.
SCAN_WALL_CLOCK_BUDGET_SECONDS = 240


@router.post("/scan")
async def scan_inbox() -> dict:
    client = get_email_client()
    start = time.monotonic()
    processed = []
    errors = []
    aborted_for_time = False
    emails = client.list_new()
    log.info("intake_scan_start", batch_size=len(emails))
    for raw in emails:
        if time.monotonic() - start > SCAN_WALL_CLOCK_BUDGET_SECONDS:
            log.warning(
                "intake_scan_wall_clock_cut",
                processed=len(processed),
                remaining=len(emails) - len(processed) - len(errors),
            )
            aborted_for_time = True
            break
        try:
            state = _raw_email_to_state(raw)
            from kwabo.graph.graph import get_ingest_app
            from kwabo.graph.runner import _run_extras
            app = get_ingest_app()
            t0 = time.monotonic()
            result = await app.ainvoke(state)
            extras = await _run_extras(result, raw)
            dt = time.monotonic() - t0
            log.info(
                "intake_scan_email_ok",
                email_id=raw.email_id,
                log_id=result.get("order_log_id"),
                duration_s=round(dt, 2),
            )
            processed.append({
                "email_id": raw.email_id,
                "log_id": result.get("order_log_id"),
                "sub_orders": [e.get("order_log_id") for e in extras],
            })
            client.mark_seen(raw.email_id)
        except Exception as e:  # noqa: BLE001
            log.exception("intake_scan_email_failed", email_id=raw.email_id)
            errors.append({"email_id": raw.email_id, "error": str(e)[:200]})
    log.info(
        "intake_scan_done",
        processed=len(processed),
        errors=len(errors),
        partial=aborted_for_time,
        duration_s=round(time.monotonic() - start, 2),
    )
    return {
        "processed": processed,
        "errors": errors,
        "partial": aborted_for_time,
        "batch_size": len(emails),
    }


@router.post("/upload")
async def upload_eml(file: UploadFile) -> dict:
    if not file.filename or not file.filename.lower().endswith(".eml"):
        raise HTTPException(400, "Only .eml accepted")
    content = await file.read()
    raw = parse_eml_bytes(content)
    state = _raw_email_to_state(raw)
    from kwabo.graph.graph import get_ingest_app
    app = get_ingest_app()
    result = await app.ainvoke(state)
    return {"email_id": raw.email_id, "log_id": result.get("order_log_id")}


@router.post("/run-file")
async def run_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"File not found: {path}")
    state = await run_on_eml(p)
    return {"email_id": state.get("email_id"), "log_id": state.get("order_log_id")}
