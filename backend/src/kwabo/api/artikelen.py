"""Navision item search (via mock or real)."""
from __future__ import annotations

from fastapi import APIRouter

from kwabo.api.schemas import ItemOut
from kwabo.integrations.navision_api import get_navision_client

router = APIRouter(prefix="/api/artikelen", tags=["artikelen"])


@router.get("/search", response_model=list[ItemOut])
async def search(q: str | None = None) -> list[ItemOut]:
    nav = get_navision_client()
    items = await nav.search_items(beschrijving=q)
    return [ItemOut(number=i["number"], displayName=i.get("displayName", "")) for i in items[:50]]
