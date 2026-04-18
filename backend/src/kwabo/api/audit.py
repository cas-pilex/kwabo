"""Audit log + stats endpoints."""
from __future__ import annotations

import json
from collections import Counter
from typing import Optional

from fastapi import APIRouter
from sqlmodel import Session

from kwabo.api.schemas import OrderDetail, StatsOut
from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[OrderDetail])
def list_audit(status: Optional[str] = None) -> list[OrderDetail]:
    with Session(engine) as s:
        rows = OrderLogRepo(s).list_by_status(status) if status else OrderLogRepo(s).list_all()
        out = []
        for r in rows:
            warns = json.loads(r.warnings or "[]") if r.warnings else []
            stappen = json.loads(r.stappen_log or "[]") if r.stappen_log else []
            state = json.loads(r.order_state or "{}") if r.order_state else {}
            out.append(
                OrderDetail(
                    id=r.id,
                    email_id=r.email_id,
                    email_from=r.email_from,
                    email_subject=r.email_subject,
                    email_date=r.email_date,
                    status=r.status,
                    is_order=r.is_order,
                    klant_nr=r.klant_nr,
                    klant_match_confidence=r.klant_match_confidence,
                    bestelnummer_klant=r.bestelnummer_klant,
                    aantal_regels=r.aantal_regels,
                    alle_artikelen_gematcht=r.alle_artikelen_gematcht,
                    alle_prijzen_valide=r.alle_prijzen_valide,
                    navision_order_nr=r.navision_order_nr,
                    warnings_count=len(warns),
                    needs_review_count=int(state.get("needs_review_count") or 0),
                    parent_log_id=state.get("parent_log_id"),
                    sub_order_index=state.get("sub_order_index"),
                    warnings=warns,
                    stappen_log=stappen,
                    order_state=state,
                    created_at=r.created_at,
                )
            )
        return out


@router.get("/stats", response_model=StatsOut)
def stats() -> StatsOut:
    with Session(engine) as s:
        rows = OrderLogRepo(s).list_all()
        if not rows:
            return StatsOut(total_orders=0, by_status={}, auto_match_pct=0.0, avg_confidence=None)
        by_status = Counter(r.status for r in rows)
        auto = sum(1 for r in rows if r.alle_artikelen_gematcht)
        confs = [r.klant_match_confidence for r in rows if r.klant_match_confidence is not None]
        return StatsOut(
            total_orders=len(rows),
            by_status=dict(by_status),
            auto_match_pct=round(auto / len(rows) * 100, 1),
            avg_confidence=round(sum(confs) / len(confs), 2) if confs else None,
        )
