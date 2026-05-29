"""Trigger intake on emails dropped into inbox_dir OR upload direct."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from sqlmodel import Session

from kwabo.config import settings
from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.runner import _raw_email_to_state, run_on_eml
from kwabo.integrations.email_client import RawEmail, get_email_client, parse_eml_bytes
from kwabo.utils import utcnow
from kwabo.utils.logging import log

router = APIRouter(prefix="/api/intake", tags=["intake"])


def _safe_eml_id(email_id: str | None) -> str:
    """Sanitize an email_id for use as a storage key / filename. Keeps the
    32-char alnum/-/_ rule that the legacy disk path used so existing tests
    and DB rows keep matching."""
    return "".join(c for c in (email_id or "") if c.isalnum() or c in ("-", "_"))[:32] or "source"


def _persist_source_eml(raw_eml: bytes, email_id: str) -> tuple[str | None, str | None]:
    """Persist the source .eml. Returns (storage_key, local_path).

    Fase 2: Supabase Storage is the canonical store; local disk is fallback
    (lokaal/docker dev). For each intake we try Supabase first; on success
    the storage_key is canonical and we DON'T also write to disk (saves IO
    on Railway's ephemere FS). On Supabase fail OR no Supabase configured,
    we write to local disk so the legacy `_find_eml_path` branch keeps
    working — at least until the container restarts.

    Both return-values may be None: that signals total persist-failure and
    the caller MUST set `state["incoming_document_save_failed"]=True` so
    compose/push/UI know the source mail is not retrievable.
    """
    from kwabo.integrations.supabase_storage import get_supabase_storage

    safe_id = _safe_eml_id(email_id)
    storage_client = get_supabase_storage()
    storage_key: str | None = None

    if storage_client is not None:
        try:
            storage_key = f"by_email_id/{safe_id}.eml"
            storage_client.put_object(storage_key, raw_eml, "message/rfc822")
            log.info(
                "intake_source_eml_persisted",
                email_id=email_id,
                storage_key=storage_key,
                size_bytes=len(raw_eml),
            )
            # Canonical store succeeded — skip disk write to save the
            # ephemere-FS shuffle.
            return storage_key, None
        except Exception as exc:  # noqa: BLE001
            log.error(
                "intake_source_eml_supabase_failed",
                email_id=email_id,
                error=str(exc)[:300],
                hint="falling back to local disk; check SUPABASE_URL / SERVICE_ROLE_KEY",
            )
            storage_key = None  # don't claim a key we didn't write

    # Disk fallback path (dev / Supabase-unavailable). Keeps Railway-mode
    # working in degraded form: PDFs are openable until the next restart.
    try:
        target_dir = settings.incoming_documents_path / "by_email_id"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{safe_id}.eml"
        target_path.write_bytes(raw_eml)
        return storage_key, str(target_path.resolve())
    except Exception as exc:  # noqa: BLE001
        log.error(
            "intake_source_eml_save_failed",
            email_id=email_id,
            error=str(exc)[:300],
            target_dir=str(settings.incoming_documents_path / "by_email_id"),
        )
        from kwabo.utils.alerts import alert
        alert(
            "intake_source_eml_save_failed",
            "high",
            {"email_id": email_id, "error": str(exc)[:200]},
        )
        return storage_key, None

# Stop processing new emails once the scan has been running this long.
# Railway request timeout is ~5 min; we cut at 4 min so we can return a
# meaningful response with partial=true and the reviewer can re-scan.
SCAN_WALL_CLOCK_BUDGET_SECONDS = 240

# Poison-pill guard. Een mail die telkens crasht VÓÓR mark_seen blijft
# ongelezen en faalt élke poll-tick opnieuw — dat verbrandt Anthropic-budget
# en blokkeert de queue (precies de prod-situatie van 29-05-2026). Na zoveel
# opeenvolgende fouten quarantainen we de mail (mark_seen + luide alert) zodat
# de loop stopt. In-process teller: herstart reset 'm, dat is acceptabel.
MAX_INTAKE_RETRIES = 3
_intake_failures: dict[str, int] = {}


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
            # Persist BEFORE the pipeline so compose_order sees the path and
            # emits the /incomingDocuments ops. The file lives under
            # by_email_id/ — stable across retries and not log_id-dependent.
            if raw.raw_eml:
                storage_key, saved_path = _persist_source_eml(raw.raw_eml, raw.email_id)
                if storage_key:
                    state["incoming_document_storage_key"] = storage_key
                if saved_path:
                    state["incoming_document_path"] = saved_path
                if not storage_key and not saved_path:
                    # Mark explicitly so compose / push / UI can show that
                    # the source mail is missing. Mail still gets processed
                    # (header + lines) — only attachment retrieval skipped.
                    state["incoming_document_save_failed"] = True
            from kwabo.graph.graph import get_ingest_app
            from kwabo.graph.runner import _run_extras
            from kwabo.integrations.navision_api import nav_client_scope
            app = get_ingest_app()
            t0 = time.monotonic()
            # Fase 4: één NAV-client + httpx.AsyncClient voor de héle
            # pipeline-run (primary + alle sub-orders). Voorheen instantieerde
            # elke node een verse client → socket-leak per request.
            async with nav_client_scope():
                result = await app.ainvoke(state)
                extras = await _run_extras(result, raw)
            log_id = result.get("order_log_id")
            dt = time.monotonic() - t0
            log.info(
                "intake_scan_email_ok",
                email_id=raw.email_id,
                log_id=log_id,
                duration_s=round(dt, 2),
            )
            processed.append({
                "email_id": raw.email_id,
                "log_id": log_id,
                "sub_orders": [e.get("order_log_id") for e in extras],
            })
            client.mark_seen(raw.email_id)
            _intake_failures.pop(raw.email_id, None)  # geslaagd → teller reset
        except Exception as e:  # noqa: BLE001
            log.exception("intake_scan_email_failed", email_id=raw.email_id)
            errors.append({"email_id": raw.email_id, "error": str(e)[:200]})
            n_fail = _intake_failures.get(raw.email_id, 0) + 1
            _intake_failures[raw.email_id] = n_fail
            if n_fail >= MAX_INTAKE_RETRIES:
                # Quarantine: stop de poison-pill loop. mark_seen markeert de
                # mail als gelezen (blijft in de mailbox, dus terugvindbaar),
                # zodat hij niet elke tick opnieuw faalt. Luide alert zodat een
                # mens 'm handmatig kan oppakken.
                try:
                    client.mark_seen(raw.email_id)
                    _intake_failures.pop(raw.email_id, None)
                    log.error(
                        "intake_mail_quarantined",
                        email_id=raw.email_id,
                        failures=n_fail,
                        error=str(e)[:200],
                    )
                    from kwabo.utils.alerts import alert
                    alert(
                        "intake_mail_quarantined",
                        "high",
                        {
                            "email_id": raw.email_id,
                            "failures": n_fail,
                            "error": str(e)[:200],
                        },
                    )
                except Exception:  # noqa: BLE001
                    # mark_seen-fail mag de scan niet kelderen; volgende tick
                    # probeert opnieuw te quarantainen.
                    pass
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
    # Save the .eml BEFORE the pipeline so compose_order picks up
    # incoming_document_path/storage_key and emits the /incomingDocuments ops.
    if raw.raw_eml:
        storage_key, saved_path = _persist_source_eml(raw.raw_eml, raw.email_id)
        if storage_key:
            state["incoming_document_storage_key"] = storage_key
        if saved_path:
            state["incoming_document_path"] = saved_path
        if not storage_key and not saved_path:
            state["incoming_document_save_failed"] = True
    from kwabo.graph.graph import get_ingest_app
    from kwabo.graph.runner import _run_extras
    from kwabo.integrations.navision_api import nav_client_scope
    app = get_ingest_app()
    # Fase 4: één NAV-client voor de hele upload-run, identiek aan /scan.
    async with nav_client_scope():
        result = await app.ainvoke(state)
        # Multi-order mails: extract may emit a JSON array; spawn sub-orders
        # for each extra. Without this, file-drop upload loses sub-orders
        # entirely — /scan calls _run_extras but /upload did not.
        extras = await _run_extras(result, raw)
    return {
        "email_id": raw.email_id,
        "log_id": result.get("order_log_id"),
        "sub_orders": [e.get("order_log_id") for e in extras],
    }


@router.post("/run-file")
async def run_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"File not found: {path}")
    state = await run_on_eml(p)
    return {"email_id": state.get("email_id"), "log_id": state.get("order_log_id")}
