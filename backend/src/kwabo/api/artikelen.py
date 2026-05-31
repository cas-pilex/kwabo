"""Artikel-zoek voor de review-combobox — bediend vanuit de lokale NAV-mirror.

Voorheen ging dit bij élke aanroep naar live Navision OData (zonder $top), waardoor
iedere order-detailpagina ~15s blokkeerde terwijl NAV zijn volledige itemcatalogus
streamde om er 50 terug te geven. De Artikelkaart-mirror (gesynct vanuit NAV) levert
dezelfde data in milliseconden uit Postgres. Valt alleen terug op live NAV als de
mirror nog leeg is (verse dev-DB / mock).
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import Session, select

from kwabo.api.schemas import ItemOut
from kwabo.db import session as db_session
from kwabo.db.models import Artikelkaart
from kwabo.integrations.navision_api import get_navision_client

router = APIRouter(prefix="/api/artikelen", tags=["artikelen"])

_SEARCH_LIMIT = 50


@router.get("/search", response_model=list[ItemOut])
async def search(q: str | None = None) -> list[ItemOut]:
    # Resolve engine via the module (niet bij import) zodat tests die
    # db_session.engine overriden de juiste DB raken.
    with Session(db_session.engine) as s:
        stmt = select(Artikelkaart)
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                func.lower(Artikelkaart.kwabo_artikelnr).like(like)
                | func.lower(Artikelkaart.naam).like(like)
            )
        rows = s.exec(stmt.limit(_SEARCH_LIMIT)).all()
        mirror_populated = s.exec(select(Artikelkaart).limit(1)).first() is not None
    if rows or mirror_populated:
        return [ItemOut(number=r.kwabo_artikelnr, displayName=r.naam) for r in rows]
    # Mirror leeg (verse/dev-DB): val terug op live/mock NAV zodat de combobox
    # ook vóór de eerste sync werkt.
    nav = get_navision_client()
    items = await nav.search_items(beschrijving=q)
    return [
        ItemOut(number=i["number"], displayName=i.get("displayName", ""))
        for i in items[:_SEARCH_LIMIT]
    ]
