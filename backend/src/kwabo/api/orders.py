"""Order review REST endpoints."""
from __future__ import annotations

import base64
import email
import email.policy
import hashlib
import hmac
import io
import json
import mimetypes
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
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
# Public router for attachment downloads. The reviewer opens PDFs in a new
# tab via <a target="_blank">, which cannot carry a Bearer header. Auth on
# this route is enforced by a short-lived HMAC token in the query string
# (minted via POST /{id}/bijlagen-token on the auth-gated router).
router_public = APIRouter(prefix="/api/orders", tags=["orders-public"])


# --------------------------------------------------------------------------
# Signed-URL helpers (attachment downloads)
# --------------------------------------------------------------------------


def _attachment_secret() -> str:
    """Resolve the HMAC secret. Empty signed_url_secret falls back to
    jwt_secret with a static salt — rotating jwt_secret already invalidates
    download tokens alongside sessions, which is the safer default."""
    if settings.signed_url_secret:
        return settings.signed_url_secret
    return f"{settings.jwt_secret}::attachment"


def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(data: str) -> bytes:
    pad = 4 - (len(data) % 4)
    if pad and pad != 4:
        data = data + ("=" * pad)
    return base64.urlsafe_b64decode(data)


def _sign_attachment_token(
    order_id: int, naam: str, disposition: str, ttl: int
) -> tuple[str, int]:
    """Mint a token binding (order_id, naam, disposition) until exp.

    Returns (token, exp_unix_seconds).
    """
    exp = int(time.time()) + ttl
    payload = {"oid": order_id, "n": naam, "d": disposition, "exp": exp}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(
        _attachment_secret().encode("utf-8"), raw, hashlib.sha256
    ).digest()
    return f"{_b64u_encode(raw)}.{_b64u_encode(sig)}", exp


def _verify_attachment_token(
    token: str, order_id: int, naam: str, disposition: str
) -> bool:
    """Validate a token against the expected (order_id, naam, disposition)
    and ensure it has not expired."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
        raw = _b64u_decode(body_b64)
        actual_sig = _b64u_decode(sig_b64)
    except (ValueError, Exception):  # noqa: BLE001
        return False
    expected_sig = hmac.new(
        _attachment_secret().encode("utf-8"), raw, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected_sig, actual_sig):
        return False
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("oid") != order_id:
        return False
    if payload.get("n") != naam:
        return False
    if payload.get("d") != disposition:
        return False
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        return False
    return True


class AttachmentTokenRequest(BaseModel):
    naam: str
    disposition: str = "inline"


class AttachmentTokenResponse(BaseModel):
    token: str
    expires_at: int


def _find_eml_path(order_state: dict, email_id: str | None) -> Path | None:
    """Locate the original .eml file for an order.

    Lookup order:
      1. state.incoming_document_path — set by intake_trigger for new orders
         (auto-save under data/incoming_documents/by_email_id/<email_id>.eml).
         This is the authoritative location for Graph-ingested mails.
      2. state.source_path — file-drop / replay mails have this set to a
         real filesystem path. Graph mails store "graph://<id>" here which
         won't exist on disk — fall through.
      3. inbox + processed dirs scanned by short-hash — legacy fallback for
         file-drop pre-incoming-document era.
    """
    if isinstance(order_state, dict):
        idp = order_state.get("incoming_document_path")
        if idp:
            p = Path(idp)
            if p.exists():
                return p
        sp = order_state.get("source_path")
        if sp and not sp.startswith("graph://"):
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
    nav_status = final_state.get("navision_status") or (
        "pushed" if final_state.get("navision_order_nr") else "failed"
    )
    op_results = list(final_state.get("nav_operation_results") or [])
    first_error: Optional[str] = None
    for op in op_results:
        if op.get("error"):
            first_error = str(op["error"])[:500]
            break
    if not first_error:
        # `errors` may also carry the failure reason from push_navision_node.
        for err in final_state.get("errors") or []:
            if isinstance(err, str) and err.startswith("push_navision:"):
                first_error = err[len("push_navision:"):].strip()[:500]
                break
    return {
        "ok": nav_status != "failed",
        "navision_order_nr": final_state.get("navision_order_nr"),
        "status": "pushed" if nav_status != "failed" else "failed",
        "nav_status": nav_status,
        "nav_error": first_error,
        "nav_operation_count": len(op_results),
        "nav_failed_op_count": sum(1 for op in op_results if op.get("error")),
        "forced": force,
    }


@router.delete("/{order_id}")
def delete_order(order_id: int, confirm: bool = False) -> dict:
    """Hard-delete an order log row. Requires ?confirm=true to avoid
    accidental wipes via curl typos. Used for test-order cleanup; production
    orders should typically be `rejected` instead."""
    if not confirm:
        raise HTTPException(
            400,
            "Hard delete vereist ?confirm=true. Overweeg POST /reject voor "
            "productie-orders zodat de audit-trail behouden blijft.",
        )
    with Session(engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        s.delete(row)
        s.commit()
    return {"ok": True, "deleted_id": order_id}


@router.get("/{order_id}/nav-debug")
def nav_debug(order_id: int) -> dict:
    """Return the full NAV operation-results trail for a pushed/failed order.

    Used by the reviewer to inspect why a push failed (or, for a successful
    push, to see the exact POST/PATCH chain that ran). Auth-gated; only the
    reviewer should see this depth of detail.
    """
    with Session(engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}
    return {
        "order_id": order_id,
        "status": row.status,
        "navision_order_nr": row.navision_order_nr,
        "navision_status": state.get("navision_status"),
        "errors": state.get("errors") or [],
        "nav_autofilled": state.get("nav_autofilled") or {},
        "nav_operation_results": state.get("nav_operation_results") or [],
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


@router.post(
    "/{order_id}/bijlagen-token", response_model=AttachmentTokenResponse
)
def mint_attachment_token(
    order_id: int, body: AttachmentTokenRequest
) -> AttachmentTokenResponse:
    """Mint a short-lived signed URL token for a specific attachment.

    The reviewer's browser then GETs `/api/orders/{id}/bijlagen?...&token=...`
    via `<a target="_blank">` — that GET is on `router_public` and validates
    the token instead of requiring a Bearer header (which doesn't travel
    cross-tab). TTL comes from settings.signed_url_ttl_seconds (default 5 min).
    """
    if body.disposition not in ("inline", "attachment"):
        raise HTTPException(400, "disposition must be 'inline' or 'attachment'")
    token, exp = _sign_attachment_token(
        order_id, body.naam, body.disposition, settings.signed_url_ttl_seconds
    )
    return AttachmentTokenResponse(token=token, expires_at=exp)


@router_public.get("/{order_id}/bijlagen")
def download_attachment(
    order_id: int,
    naam: str = Query(..., description="Filename of the attachment to fetch"),
    disposition: str = Query("inline", pattern="^(inline|attachment)$"),
    token: str = Query(..., description="Signed URL token from /bijlagen-token"),
) -> Response:
    if not _verify_attachment_token(token, order_id, naam, disposition):
        raise HTTPException(401, "Ongeldige of verlopen download-token")
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
    # Browsers often label .eml uploads as octet-stream because no MIME db
    # entry exists. We accept it conditionally: only when the filename ends
    # in a known-safe extension. See _is_safe_octet_stream below.
    "application/octet-stream",
}

# Extensions allowed when content_type is application/octet-stream — keeps
# random binaries out of the inbox.
SAFE_OCTET_STREAM_EXTENSIONS = {".eml", ".pdf", ".png", ".jpg", ".jpeg", ".txt"}


def _is_safe_octet_stream(content_type: str, filename: str) -> bool:
    if content_type != "application/octet-stream":
        return True
    ext = Path(filename or "").suffix.lower()
    return ext in SAFE_OCTET_STREAM_EXTENSIONS


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
    if not _is_safe_octet_stream(content_type, file.filename or ""):
        raise HTTPException(
            400,
            f"Bestand '{file.filename or 'onbekend'}' heeft content-type "
            f"application/octet-stream maar de extensie staat niet in de "
            f"veilige lijst {sorted(SAFE_OCTET_STREAM_EXTENSIONS)}.",
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
