"""Order review REST endpoints."""
from __future__ import annotations

import json
from datetime import datetime

from kwabo.utils import utcnow
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from kwabo.api.schemas import (
    ApproveRequest,
    OrderDetail,
    OrderSummary,
    PatchOrderRequest,
    RejectRequest,
)
from kwabo.db.repository import ArtikelRepo, OrderLogRepo
from kwabo.db.session import engine
from kwabo.graph.runner import finalize

router = APIRouter(prefix="/api/orders", tags=["orders"])


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
