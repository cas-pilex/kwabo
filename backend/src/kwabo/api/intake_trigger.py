"""Trigger intake on emails dropped into inbox_dir OR upload direct."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from kwabo.config import settings
from kwabo.graph.runner import _raw_email_to_state, run_on_eml
from kwabo.integrations.email_client import FileDropEmailClient, parse_eml_bytes

router = APIRouter(prefix="/api/intake", tags=["intake"])


@router.post("/scan")
async def scan_inbox() -> dict:
    client = FileDropEmailClient()
    processed = []
    errors = []
    for raw in client.list_new():
        try:
            state = _raw_email_to_state(raw)
            from kwabo.graph.graph import get_ingest_app
            from kwabo.graph.runner import _run_extras
            app = get_ingest_app()
            result = await app.ainvoke(state)
            extras = await _run_extras(result, raw)
            processed.append({
                "email_id": raw.email_id,
                "log_id": result.get("order_log_id"),
                "sub_orders": [e.get("order_log_id") for e in extras],
            })
            client.mark_seen(raw.email_id)
        except Exception as e:  # noqa: BLE001
            errors.append({"email_id": raw.email_id, "error": str(e)[:200]})
    return {"processed": processed, "errors": errors}


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
