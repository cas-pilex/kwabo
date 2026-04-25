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

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
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
from kwabo.db.models import ArtikelPalletKennis
from kwabo.db.repository import ArtikelRepo, OrderLogRepo, PalletKennisRepo
from kwabo.db.session import engine
from kwabo.graph.runner import finalize
from kwabo.utils import utcnow
from kwabo.utils.pallet_logic import PALLET_ARTIKELNR, compute_europallet

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
        # T10: persist europallet feedback to artikel_pallet_kennis. The
        # approval is a single human signal — we record it with confidence
        # 0.6 so the next dashboard pass can override.
        _persist_pallet_feedback(s, state, reviewer=body.reviewer)
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


# ---------------------------------------------------------------------------
# T10: incoming-document upload + pallet-feedback persistence
# ---------------------------------------------------------------------------

# 10 MB max for an incoming document (email/PDF/image). Anything bigger is
# almost certainly noise — and we don't want to balloon the data dir.
MAX_INCOMING_DOC_SIZE = 10 * 1024 * 1024
ALLOWED_INCOMING_DOC_TYPES = {
    "application/pdf",
    "message/rfc822",
    "text/plain",
    "image/png",
    "image/jpeg",
}


def _pallet_contributors(regels: list[dict]) -> list[tuple[str, str]]:
    """Return the (kwabo_artikelnr, eenheid_upper) pairs from the regels that
    a europallet-compute would consider as candidates.

    Used by approve to decide which artikel_pallet_kennis rows to upsert.
    Mirrors the filter in ``compute_europallet``: matched artikelnr present,
    not the pallet artikel itself, qty > 0.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for regel in regels or []:
        kwabo_nr = regel.get("artikelnummer_kwabo_matched")
        if not kwabo_nr or kwabo_nr == PALLET_ARTIKELNR:
            continue
        eenheid = (regel.get("eenheid") or "").upper()
        if not eenheid:
            continue
        try:
            qty = float(regel.get("hoeveelheid") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        key = (kwabo_nr, eenheid)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs


def _persist_pallet_feedback(
    session: Session, state: dict, *, reviewer: Optional[str] = None
) -> None:
    """Persist europallet feedback to artikel_pallet_kennis on approval (T10).

    Two cases:
      - ``state["europallet_regel"]`` is present: the approver agreed a
        pallet line is correct. Mark each contributing item with
        ``pallet_required=True``. Preserve ``per_pallet`` if a kennis row
        exists; otherwise default to 24 (matches the heuristic).
      - ``state["europallet_regel"]`` is None *but* re-running the compute
        on the saved regels would have produced one: the human (or the
        review UI) explicitly removed it. Record ``pallet_required=False``
        so the next time around we don't re-suggest a pallet for those
        items.

    confidence = 0.6 in both cases — this is one human signal, not the
    final word. ``bevestigd_door`` falls back to "dashboard-approve" when
    the request didn't carry a reviewer.
    """
    regels = state.get("orderregels") or []
    contributors = _pallet_contributors(regels)
    if not contributors:
        return

    repo = PalletKennisRepo(session)
    europallet = state.get("europallet_regel")
    bevestigd_door = reviewer or "dashboard-approve"
    now = utcnow()

    if europallet:
        for kwabo_nr, eenheid in contributors:
            existing = repo.lookup(kwabo_nr, eenheid)
            per_pallet = existing.per_pallet if existing else 24
            repo.upsert(
                ArtikelPalletKennis(
                    kwabo_artikelnr=kwabo_nr,
                    eenheid=eenheid,
                    pallet_required=True,
                    per_pallet=per_pallet,
                    confidence=0.6,
                    laatst_bevestigd_op=now,
                    bevestigd_door=bevestigd_door,
                )
            )
        return

    # europallet_regel is None — only record explicit "no pallet" feedback
    # when compute_europallet WOULD have produced one for this state. That
    # signals the human deliberately suppressed it (vs. the order simply
    # not needing a pallet). We re-run compute against the same repo so
    # any existing kennis is honoured.
    would_have_added = compute_europallet(state, repo=repo)
    if not would_have_added:
        return

    for kwabo_nr, eenheid in contributors:
        existing = repo.lookup(kwabo_nr, eenheid)
        per_pallet = existing.per_pallet if existing else 24
        repo.upsert(
            ArtikelPalletKennis(
                kwabo_artikelnr=kwabo_nr,
                eenheid=eenheid,
                pallet_required=False,
                per_pallet=per_pallet,
                confidence=0.6,
                laatst_bevestigd_op=now,
                bevestigd_door=bevestigd_door,
            )
        )


@router.post("/{order_id}/incoming-doc")
async def upload_incoming_document(
    order_id: int, file: UploadFile = File(...)
) -> dict:
    """Upload the original email/PDF/image as an incoming document for an order.

    Stores under ``data/incoming_documents/{order_id}/<sanitized_filename>``
    and writes the absolute path to ``state["incoming_document_path"]`` —
    matching how ``state["source_path"]`` is stored. The push_navision
    pipeline (T9) reads this slot when composing /incomingDocuments ops.
    """
    with Session(engine) as s:
        repo = OrderLogRepo(s)
        row = repo.get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_INCOMING_DOC_TYPES:
        raise HTTPException(
            400,
            f"Content-type '{content_type or 'unknown'}' niet toegestaan. "
            f"Toegestaan: {', '.join(sorted(ALLOWED_INCOMING_DOC_TYPES))}",
        )

    content = await file.read()
    if len(content) > MAX_INCOMING_DOC_SIZE:
        raise HTTPException(
            413,
            f"Bestand te groot (max {MAX_INCOMING_DOC_SIZE // (1024 * 1024)} MB)",
        )

    # Sanitize filename — `Path(...).name` strips any directory components,
    # so "../etc/passwd" collapses to "passwd". Fall back to a generic name
    # if the upload didn't include one.
    safe_name = Path(file.filename or "document").name or "document"

    target_dir = settings.incoming_documents_path / str(order_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    target_path.write_bytes(content)

    saved_path = str(target_path.resolve())
    with Session(engine) as s:
        repo = OrderLogRepo(s)
        row = repo.get(order_id)
        if not row:
            # Race: row was deleted between the two reads. Not worth
            # special-casing further than a clean 404.
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}
        state["incoming_document_path"] = saved_path
        row.order_state = json.dumps(state, default=str)
        row.updated_at = utcnow()
        s.add(row)
        s.commit()

    return {
        "saved_path": saved_path,
        "file_size": len(content),
        "content_type": content_type,
    }
