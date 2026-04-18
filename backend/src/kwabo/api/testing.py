"""Test-only endpoint to reset DB state. Only mounted when KWABO_TEST_MODE=on."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
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
