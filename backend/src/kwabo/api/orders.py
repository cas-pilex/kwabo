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


def _resolve_eml_bytes(order_state: dict, email_id: str | None) -> bytes | None:
    """Locate and return the raw .eml bytes for an order.

    Lookup order (Fase 2 — Supabase Storage canoniek):
      1. ``state.incoming_document_storage_key`` — Supabase Storage object.
         Survives Railway redeploys (ephemere FS-fix). Authoritative for
         orders created on or after Fase 2 deploy.
      2. ``state.incoming_document_path`` — legacy local-disk path. Still
         honored for orders created before Fase 2 + as dev/docker fallback
         when Supabase isn't configured. Loses on Railway after redeploy.
      3. ``state.source_path`` — file-drop / replay mails have a real path
         here. Graph mails store ``graph://<id>`` which we skip on disk.
      4. inbox + processed dirs scanned by short-hash — legacy file-drop
         fallback (pre-incoming-document era).

    Returns None when nothing works — caller surfaces a 404 with a honest
    error message (not the misleading "verwijderd uit inbox/processed").
    """
    if isinstance(order_state, dict):
        # 1) Supabase Storage — the new canonical source.
        sk = order_state.get("incoming_document_storage_key")
        if sk:
            try:
                from kwabo.integrations.supabase_storage import get_supabase_storage

                client = get_supabase_storage()
                if client is not None:
                    return client.get_object(sk)
            except Exception:  # noqa: BLE001
                # Don't swallow silently — log and fall through to disk so
                # an unhealthy Supabase doesn't take the dashboard down.
                from kwabo.utils.logging import log as _log
                _log.warning(
                    "supabase_storage_get_failed",
                    storage_key=sk,
                    hint="falling back to legacy disk lookup",
                )
        # 2) Legacy disk path.
        idp = order_state.get("incoming_document_path")
        if idp:
            p = Path(idp)
            if p.exists():
                try:
                    return p.read_bytes()
                except OSError:
                    pass
        # 3) source_path (file-drop / replay).
        sp = order_state.get("source_path")
        if sp and not sp.startswith("graph://"):
            p = Path(sp)
            if p.exists():
                try:
                    return p.read_bytes()
                except OSError:
                    pass
    # 4) Short-hash scan of inbox / processed.
    for root in (settings.inbox_path, settings.processed_path):
        if not root.exists():
            continue
        for candidate in root.glob("*.eml"):
            try:
                raw = candidate.read_bytes()
            except OSError:
                continue
            if email_id and email_id in _short_hash(raw):
                return raw
    return None


def _short_hash(b: bytes) -> str:
    import hashlib

    return hashlib.sha256(b).hexdigest()[:16]


def _extract_attachment_bytes(raw_eml: bytes, wanted_name: str) -> tuple[bytes, str] | None:
    """Walk the .eml bytes and return (bytes, content_type) matching `wanted_name`.

    Handles direct attachments and files inside ZIP attachments (name
    "archive.zip:inner.pdf"). Takes bytes (not a Path) so callers that
    resolve the source from Supabase Storage don't need to round-trip
    through a tempfile.
    """
    msg = email.message_from_bytes(raw_eml, policy=email.policy.default)

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

        # Recompose nav_operations from the CURRENT state. The pipeline
        # already composed once during compose_order_node, but reviewer
        # edits via /patch-field clear that cache (see preview.py) so the
        # push uses fresh ops that reflect any manual changes.
        try:
            from kwabo.integrations.navision_steps import compose_navision_operations
            state["nav_operations"] = list(compose_navision_operations(state))
        except ValueError as exc:
            # Compose refuses header-only orders (no matched lines). Surface
            # as a 422 with the same shape as needs_review failures so the
            # frontend can show it.
            raise HTTPException(
                422,
                detail={
                    "error": "compose_failed",
                    "message": str(exc),
                },
            )
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

    # Self-learning: a successful push means a human approved these mappings.
    # Record them so future identical lines auto-match. Never let a learning
    # write break the (already-succeeded) push response.
    if nav_status != "failed":
        try:
            with Session(engine) as s2:
                _learn_from_approved(s2, final_state)
        except Exception:  # noqa: BLE001
            log.exception("learn_from_approved_failed", order_id=order_id)

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

    raw_eml = _resolve_eml_bytes(state, email_id)
    if not raw_eml:
        # Honest message: voor Graph-mails op een net-gedeployde Railway
        # zonder Supabase Storage ligt het bestand er gewoon niet meer.
        # Onderscheid 'no source at all' van 'attachment niet in source'.
        raise HTTPException(
            404,
            "Bron-document niet meer beschikbaar (storage leeg of niet "
            "geconfigureerd). Configureer SUPABASE_URL + "
            "SUPABASE_SERVICE_ROLE_KEY voor persistente .eml-opslag, of "
            "upload het document opnieuw via 'Bron-document'.",
        )

    result = _extract_attachment_bytes(raw_eml, naam)
    if not result:
        raise HTTPException(404, f"Bijlage '{naam}' niet gevonden in e-mail")

    data, ctype = result
    # Voor veilige Content-Disposition headers met non-ASCII filenames: RFC5987.
    # Plus: non-safe-inline content-types worden force-downloaded (zie
    # _safe_response_headers — defense-in-depth tegen stored-XSS via
    # reviewer-uploaded HTML/SVG).
    display_name = naam.split(":")[-1] if ":" in naam else naam
    _, headers = _safe_response_headers(ctype, disposition, display_name)
    return Response(
        content=data,
        media_type=ctype,
        headers=headers,
    )


def _learn_from_approved(session: Session, state: dict) -> None:
    """Feed the self-learning loop from the FINAL approved state.

    The dashboard applies reviewer article-edits via /patch-field (it does NOT
    send an approve `corrections` body), so the authoritative klant-SKU -> kwabo
    mappings live in order_state.orderregels. Record every line that has both a
    customer SKU and a matched kwabo article so the next identical line
    auto-matches via klantenkaart/history instead of falling back to fuzzy.
    Reuses _save_corrections (klant_nr guard included)."""
    correcties = [
        {
            "artikelnummer_klant": r.get("artikelnummer_klant"),
            "artikelnummer_kwabo_matched": r.get("artikelnummer_kwabo_matched"),
            "omschrijving": r.get("omschrijving"),
        }
        for r in (state.get("orderregels") or [])
        if r.get("artikelnummer_klant") and r.get("artikelnummer_kwabo_matched")
    ]
    if correcties:
        _save_corrections(session, state, {"artikel_correcties": correcties})


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

    # Persist via Supabase first (canoniek, Railway-deploy-proof). Fall back
    # to local disk when Supabase isn't configured — same pattern as
    # _persist_source_eml.
    from kwabo.integrations.supabase_storage import get_supabase_storage
    from kwabo.utils.logging import log as _log

    storage_client = get_supabase_storage()
    storage_key: Optional[str] = None
    saved_path: Optional[str] = None

    if storage_client is not None:
        try:
            storage_key = f"by_order/{order_id}/{safe_name}"
            storage_client.put_object(storage_key, content, content_type)
            _log.info(
                "incoming_doc_uploaded_supabase",
                order_id=order_id,
                storage_key=storage_key,
                size_bytes=len(content),
            )
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "incoming_doc_supabase_failed",
                order_id=order_id,
                error=str(exc)[:300],
                hint="falling back to local disk",
            )
            storage_key = None

    if storage_key is None:
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
        if storage_key:
            state["incoming_document_storage_key"] = storage_key
            # Clear any legacy disk-path so the download-resolver uses the
            # new Supabase key, not a stale disk reference that may not even
            # exist anymore after a Railway redeploy.
            state.pop("incoming_document_path", None)
        if saved_path:
            state["incoming_document_path"] = saved_path
        # Reviewer-facing filename for the dashboard + download-token route.
        # Sentinel "incoming-doc" is the canonical token-naam for the new
        # download route (one doc per order; bound to that literal).
        state["incoming_document_filename"] = safe_name
        state["incoming_document_content_type"] = content_type
        row.order_state = json.dumps(state, default=str)
        row.updated_at = utcnow()
        s.add(row)
        s.commit()

    return {
        "saved_path": saved_path or storage_key or "",
        "storage_key": storage_key,
        "file_size": len(content),
        "content_type": content_type,
        "filename": safe_name,
    }


# ---------------------------------------------------------------------------
# /incoming-doc download (Fase 3): publieke route + token-mint
# ---------------------------------------------------------------------------


INCOMING_DOC_TOKEN_NAAM = "incoming-doc"
"""Sentinel-naam voor de HMAC-token van de incoming-doc download. Per order
is er maar één incoming-doc; vaste literal voorkomt dat het token mee
verandert als de reviewer een nieuwe upload doet (token blijft geldig
voor de hele upload-slot, niet voor één specifiek bestand)."""


def _content_type_for(name: str, fallback: str | None = None) -> str:
    """Detect content-type by file extension, with fallback for unknown types."""
    ctype, _ = mimetypes.guess_type(name or "")
    return ctype or fallback or "application/octet-stream"


# Types we trust to render inline in a same-origin browser tab. Everything
# else is force-downloaded (Content-Disposition: attachment) regardless of
# what the caller asked for, plus nosniff + sandbox CSP to neutralise any
# HTML/SVG/JS that slipped through upload validation. Defense-in-depth
# against stored-XSS via reviewer-uploaded bron-documenten.
SAFE_INLINE_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
}


def _safe_response_headers(
    content_type: str, disposition: str, filename: str
) -> tuple[str, dict[str, str]]:
    """Build (resolved_disposition, headers) for a same-origin file serve.

    - Non-safe-inline content-types are force-downgraded to 'attachment'
      so the browser saves instead of rendering (kills stored-XSS via
      uploaded text/html, image/svg+xml, etc.).
    - X-Content-Type-Options: nosniff prevents Chrome from sniffing a
      "text/plain" file as HTML even when contents look like markup.
    - Content-Security-Policy: sandbox isolates any embedded iframe view
      (no scripts, no same-origin requests).
    """
    effective_disposition = disposition
    ct_lower = (content_type or "").lower().split(";", 1)[0].strip()
    if effective_disposition == "inline" and ct_lower not in SAFE_INLINE_CONTENT_TYPES:
        effective_disposition = "attachment"
    disp_header = (
        f'{effective_disposition}; filename="{filename}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return effective_disposition, {
        "Content-Disposition": disp_header,
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
    }


@router.post(
    "/{order_id}/incoming-doc-token", response_model=AttachmentTokenResponse
)
def mint_incoming_doc_token(
    order_id: int, body: AttachmentTokenRequest
) -> AttachmentTokenResponse:
    """Mint a short-lived signed URL token for the order's incoming document.

    Token is bound to (order_id, INCOMING_DOC_TOKEN_NAAM, disposition). The
    `naam` field on AttachmentTokenRequest is ignored — there's only one
    incoming-doc per order, addressed via state.incoming_document_*."""
    if body.disposition not in ("inline", "attachment"):
        raise HTTPException(400, "disposition must be 'inline' or 'attachment'")
    token, exp = _sign_attachment_token(
        order_id,
        INCOMING_DOC_TOKEN_NAAM,
        body.disposition,
        settings.signed_url_ttl_seconds,
    )
    return AttachmentTokenResponse(token=token, expires_at=exp)


@router_public.get("/{order_id}/incoming-doc/file")
def download_incoming_doc(
    order_id: int,
    disposition: str = Query("inline", pattern="^(inline|attachment)$"),
    token: str = Query(..., description="Signed URL token van /incoming-doc-token"),
) -> Response:
    """Serve the reviewer-uploaded source document (PDF/JPG/EML).

    Resolves bytes from Supabase Storage when `incoming_document_storage_key`
    is set, otherwise from the legacy local-disk path. Returns the file with
    correct content-type and disposition headers — same pattern as the
    /bijlagen route but for losse uploads i.p.v. .eml-attachments.
    """
    if not _verify_attachment_token(
        token, order_id, INCOMING_DOC_TOKEN_NAAM, disposition
    ):
        raise HTTPException(401, "Ongeldige of verlopen download-token")

    with Session(engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order not found")
        state = json.loads(row.order_state or "{}") if row.order_state else {}

    storage_key = state.get("incoming_document_storage_key")
    disk_path = state.get("incoming_document_path")
    filename = state.get("incoming_document_filename") or "incoming-doc"
    stored_ctype = state.get("incoming_document_content_type")

    data: bytes | None = None
    if storage_key:
        try:
            from kwabo.integrations.supabase_storage import get_supabase_storage

            client = get_supabase_storage()
            if client is not None:
                data = client.get_object(storage_key)
        except Exception:  # noqa: BLE001
            from kwabo.utils.logging import log as _log
            _log.warning(
                "incoming_doc_supabase_get_failed",
                order_id=order_id,
                storage_key=storage_key,
                hint="falling back to legacy disk path",
            )
    if data is None and disk_path:
        p = Path(disk_path)
        if p.exists():
            try:
                data = p.read_bytes()
                # Filename fallback uit disk-path als state het niet kent.
                if not state.get("incoming_document_filename"):
                    filename = p.name
            except OSError:
                data = None

    if data is None:
        raise HTTPException(
            404,
            "Geen bron-document op deze order. Upload via 'Bron-document' "
            "in het dashboard, of configureer SUPABASE_URL voor persistente "
            "opslag.",
        )

    # Use extension-derived content-type, not the stored one — the upload
    # endpoint stored whatever Content-Type the browser sent, which is
    # client-controllable. Extension-derived is server-decided. Stored
    # value only used as fallback for application/octet-stream extensions.
    ctype = _content_type_for(filename, fallback=stored_ctype)
    _, headers = _safe_response_headers(ctype, disposition, filename)
    return Response(
        content=data,
        media_type=ctype,
        headers=headers,
    )
