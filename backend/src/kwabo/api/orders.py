"""Order review REST endpoints."""
from __future__ import annotations

import email
import email.policy
import io
import json
import mimetypes
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session

from kwabo.api.schemas import (
    ApproveRequest,
    OrderDetail,
    OrderSummary,
    PatchOrderRequest,
    RejectRequest,
)
from kwabo.config import settings
from kwabo.db.repository import ArtikelRepo, OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.runner import finalize
from kwabo.utils import utcnow

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _find_eml_path(order_state: dict, email_id: str | None) -> Path | None:
    """Locate the original .eml file for an order: check stored source_path, then scan inbox + processed."""
    sp = order_state.get("source_path") if isinstance(order_state, dict) else None
    if sp:
        p = Path(sp)
        if p.exists():
            return p
    for root in (settings.inbox_path, settings.processed_path):
        if not root.exists():
            continue
        for candidate in root.glob("*.eml"):
            try:
                raw = candidate.read_bytes()
            except OSError:
                continue
            if email_id and email_id in _short_hash(raw):
                return candidate
    return None


def _short_hash(b: bytes) -> str:
    import hashlib

    return hashlib.sha256(b).hexdigest()[:16]


def _extract_attachment_bytes(eml_path: Path, wanted_name: str) -> tuple[bytes, str] | None:
    """Walk the .eml and return (bytes, content_type) matching `wanted_name`.

    Handles direct attachments and files inside ZIP attachments (name "archive.zip:inner.pdf").
    """
    raw = eml_path.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    zip_outer = None
    zip_inner = None
    if ":" in wanted_name:
        zip_outer, zip_inner = wanted_name.split(":", 1)

    for part in msg.walk():
        fname = part.get_filename()
        if not fname:
            continue
        try:
            content = part.get_payload(decode=True)
        except Exception:  # noqa: BLE001
            content = None
        if not content:
            continue

        if zip_outer and fname == zip_outer and fname.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for zn in zf.namelist():
                        if zn == zip_inner:
                            inner_bytes = zf.read(zn)
                            ctype, _ = mimetypes.guess_type(zn)
                            return inner_bytes, ctype or "application/octet-stream"
            except zipfile.BadZipFile:
                return None
        elif fname == wanted_name:
            ctype = part.get_content_type() or "application/octet-stream"
            return content, ctype
    return None


def _to_summary(row) -> OrderSummary:
    warns = json.loads(row.warnings or "[]") if row.warnings else []
    state = json.loads(row.order_state or "{}") if row.order_state else {}
    return OrderSummary(
        id=row.id,
        email_id=row.email_id,
        email_from=row.email_from,
        email_subject=row.email_subject,
        email_date=row.email_date,
        status=row.status,
        is_order=row.is_order,
        klant_nr=row.klant_nr,
        klant_match_confidence=row.klant_match_confidence,
        bestelnummer_klant=row.bestelnummer_klant,
        aantal_regels=row.aantal_regels,
        alle_artikelen_gematcht=row.alle_artikelen_gematcht,
        alle_prijzen_valide=row.alle_prijzen_valide,
        navision_order_nr=row.navision_order_nr,
        warnings_count=len(warns),
        needs_review_count=int(state.get("needs_review_count") or 0),
        parent_log_id=state.get("parent_log_id"),
        sub_order_index=state.get("sub_order_index"),
        created_at=row.created_at,
    )


@router.get("", response_model=list[OrderSummary])
def list_orders(status: Optional[str] = None) -> list[OrderSummary]:
    with Session(engine) as s:
        repo = OrderLogRepo(s)
        rows = repo.list_by_status(status) if status else repo.list_all()
        return [_to_summary(r) for r in rows]


@router.get("/{order_id}", response_model=OrderDetail)
def get_order(order_id: int) -> OrderDetail:
    with Session(engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        warns = json.loads(row.warnings or "[]") if row.warnings else []
        stappen = json.loads(row.stappen_log or "[]") if row.stappen_log else []
        state = json.loads(row.order_state or "{}") if row.order_state else {}
        return OrderDetail(
            id=row.id,
            email_id=row.email_id,
            email_from=row.email_from,
            email_subject=row.email_subject,
            email_date=row.email_date,
            status=row.status,
            is_order=row.is_order,
            klant_nr=row.klant_nr,
            klant_match_confidence=row.klant_match_confidence,
            bestelnummer_klant=row.bestelnummer_klant,
            aantal_regels=row.aantal_regels,
            alle_artikelen_gematcht=row.alle_artikelen_gematcht,
            alle_prijzen_valide=row.alle_prijzen_valide,
            navision_order_nr=row.navision_order_nr,
            warnings_count=len(warns),
            needs_review_count=int(state.get("needs_review_count") or 0),
            parent_log_id=state.get("parent_log_id"),
            sub_order_index=state.get("sub_order_index"),
            warnings=warns,
            stappen_log=stappen,
            order_state=state,
            created_at=row.created_at,
        )


@router.patch("/{order_id}")
def patch_order(order_id: int, body: PatchOrderRequest) -> dict:
    with Session(engine) as s:
        repo = OrderLogRepo(s)
        row = repo.get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}
        if body.klant_nr is not None:
            state["klant_match"] = {
                **(state.get("klant_match") or {}),
                "navision_klantnr": body.klant_nr,
                "match_confidence": 1.0,
                "match_bron": "manual",
            }
            row.klant_nr = body.klant_nr
        if body.orderregels is not None:
            state["orderregels"] = body.orderregels
            row.aantal_regels = len(body.orderregels)
            row.alle_artikelen_gematcht = all(
                r.get("artikelnummer_kwabo_matched") for r in body.orderregels
            )
        if body.afleveradres is not None:
            state["afleveradres"] = body.afleveradres
        if body.opmerkingen is not None:
            state["opmerkingen"] = body.opmerkingen
        row.order_state = json.dumps(state, default=str)
        row.updated_at = utcnow()
        s.add(row)
        s.commit()
        return {"ok": True, "id": order_id}


@router.post("/{order_id}/approve")
async def approve_order(order_id: int, body: ApproveRequest, force: bool = False) -> dict:
    from kwabo.api.preview import _all_needs_review_paths
    from kwabo.utils.logging import log

    with Session(engine) as s:
        repo = OrderLogRepo(s)
        row = repo.get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}

        # Gate: refuse if needs_review_fields not empty AND not force=true
        missing = _all_needs_review_paths(state)
        if missing and not force:
            raise HTTPException(
                422,
                detail={
                    "error": "needs_review",
                    "message": f"{len(missing)} velden vereisen aanvulling",
                    "fields": missing,
                },
            )

        if body.corrections:
            state["review_corrections"] = body.corrections
            _save_corrections(s, state, body.corrections)
        state["review_status"] = "approved"
        state["reviewer"] = body.reviewer
        state["order_log_id"] = order_id
        if force:
            state["force_approved"] = True
            log.info(
                "approve_forced", order_id=order_id, reviewer=body.reviewer,
                missing_fields=missing,
            )
        row.order_state = json.dumps(state, default=str)
        row.status = "approved"
        row.reviewer = body.reviewer
        row.reviewed_at = utcnow()
        row.correcties = json.dumps(
            {**(body.corrections or {}), "force": force, "missing_at_approve": missing},
            default=str,
        )
        s.add(row)
        s.commit()

    final_state = await finalize(state)
    return {
        "ok": True,
        "navision_order_nr": final_state.get("navision_order_nr"),
        "status": "pushed",
        "forced": force,
    }


@router.post("/{order_id}/reject")
def reject_order(order_id: int, body: RejectRequest) -> dict:
    with Session(engine) as s:
        repo = OrderLogRepo(s)
        row = repo.get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        row.status = "rejected"
        row.reviewer = body.reviewer
        row.reviewed_at = utcnow()
        row.correcties = json.dumps({"rejection_reason": body.reason}, default=str)
        s.add(row)
        s.commit()
        return {"ok": True}


@router.get("/{order_id}/bijlagen")
def download_attachment(
    order_id: int,
    naam: str = Query(..., description="Filename of the attachment to fetch"),
    disposition: str = Query("inline", pattern="^(inline|attachment)$"),
) -> Response:
    with Session(engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}
        email_id = row.email_id

    eml = _find_eml_path(state, email_id)
    if not eml:
        raise HTTPException(
            404,
            "Originele .eml niet gevonden — bestand verwijderd uit inbox/processed?",
        )

    result = _extract_attachment_bytes(eml, naam)
    if not result:
        raise HTTPException(404, f"Bijlage '{naam}' niet gevonden in e-mail")

    data, ctype = result
    # Voor veilige Content-Disposition headers met non-ASCII filenames: RFC5987
    display_name = naam.split(":")[-1] if ":" in naam else naam
    disp = f'{disposition}; filename="{display_name}"; filename*=UTF-8\'\'{quote(display_name)}'
    return Response(
        content=data,
        media_type=ctype,
        headers={"Content-Disposition": disp, "Cache-Control": "no-cache"},
    )


def _save_corrections(session: Session, state: dict, corrections: dict) -> None:
    klant_nr = (state.get("klant_match") or {}).get("navision_klantnr")
    if not klant_nr:
        return
    repo = ArtikelRepo(session)
    for corr in corrections.get("artikel_correcties") or []:
        klant_art = corr.get("artikelnummer_klant")
        kwabo_new = corr.get("kwabo_artikelnr_nieuw") or corr.get("artikelnummer_kwabo_matched")
        if klant_art and kwabo_new:
            repo.upsert_mapping(klant_nr, klant_art, kwabo_new, corr.get("omschrijving"))
            repo.add_history(
                klant_nr=klant_nr,
                klant_artikelnr=klant_art,
                klant_omschrijving=corr.get("omschrijving"),
                kwabo_artikelnr=kwabo_new,
                match_methode="manual",
                was_correctie=True,
            )
