"""Test-only endpoints. Only mounted when KWABO_TEST_MODE=on."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete

from kwabo.config import settings
from kwabo.db.session import engine

router = APIRouter(prefix="/api/testing", tags=["testing"])


@router.post("/reset")
async def reset() -> dict:
    """Truncate all dynamic tables and re-seed. Only allowed in test mode."""
    if getattr(settings, "test_mode", "off") != "on":
        raise HTTPException(status_code=403, detail="not in test mode")

    from kwabo.db.models import ArtikelMatchingHistory, OrderLog

    with Session(engine) as s:
        s.exec(delete(OrderLog))
        s.exec(delete(ArtikelMatchingHistory))
        s.commit()
        # Re-seed to ensure klanten/artikel-mappings/prijsafspraken are present
        from kwabo.db.seed import seed as seed_fn

        seed_fn(s)
    return {"ok": True}


class SeedOrderBody(BaseModel):
    order_state: dict[str, Any]
    email_id: Optional[str] = None
    email_from: Optional[str] = None
    email_subject: Optional[str] = None
    status: str = "review"
    # Optionele DB-warnings (row.warnings). In mock-mode produceert de pipeline
    # de bron-doc-skip-warning niet (de mock koppelt het document wél), dus
    # e2e-tests die de bron-doc-banner checken zetten 'm hier expliciet.
    warnings: Optional[list[str]] = None


@router.post("/seed-order")
async def seed_order(body: SeedOrderBody) -> dict:
    """Plant een OrderLog-rij met een gegeven order_state (e2e-fixtures).

    Hiermee kunnen Playwright-tests ECHTE order-states (uit
    tests/test_data/states/) in de review-UI zetten zonder de
    LLM-pipeline te draaien — geen ANTHROPIC_API_KEY nodig.
    """
    if getattr(settings, "test_mode", "off") != "on":
        raise HTTPException(status_code=403, detail="not in test mode")

    from kwabo.db.repository import OrderLogRepo

    st = body.order_state
    with Session(engine) as s:
        row = OrderLogRepo(s).create(
            email_id=body.email_id or st.get("email_id") or "e2e-seed",
            order_state=json.dumps(st),
        )
        row.email_from = body.email_from or st.get("email_from")
        row.email_subject = body.email_subject or st.get("email_subject")
        row.status = body.status
        row.klant_nr = (st.get("klant_match") or {}).get("navision_klantnr")
        row.aantal_regels = len(st.get("orderregels") or [])
        row.alle_artikelen_gematcht = st.get("alle_artikelen_gematcht")
        if body.warnings is not None:
            row.warnings = json.dumps(body.warnings)
        s.add(row)
        s.commit()
        return {"id": row.id}
