"""Mirror-backed read-only Navision-stub voor OFFLINE faithful matching-meting.

`get_item` / `search_items` / `search_customers` lezen uit de GESYNCDE lokale
mirror (artikelkaarten / klantenkaarten) i.p.v. de demo-MockNAV. Daardoor meet
de klant- en artikel-matching tegen de ECHTE prod-masterdata — zonder live
NAV-credentials én zonder de demo-vervuiling (10001–10016) die de gewone mock
in de matching injecteert.

Bedoeld voor validatie/diagnose (`NAVISION_MODE=mirror`). De push-/stepwise-kant
erft ongewijzigd van de mock: offline pushen we niet, en als een test toch pusht
gedraagt hij zich als de mock. Dit is GEEN productie-transport.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from kwabo.db.models import Artikelkaart, Klantenkaart
from kwabo.db.session import engine
from kwabo.integrations.navision_api import MockNavisionClient


class MirrorNavisionClient(MockNavisionClient):
    """Leest masterdata-lookups uit de lokale mirror i.p.v. de demo-seed."""

    async def get_item(self, nr: str) -> Optional[dict]:
        if not nr:
            return None
        with Session(engine) as s:
            k = s.get(Artikelkaart, str(nr))
        if k is None:
            return None
        return {"number": k.kwabo_artikelnr, "displayName": k.naam}

    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]:
        with Session(engine) as s:
            rows = s.exec(select(Artikelkaart)).all()
        items = [{"number": k.kwabo_artikelnr, "displayName": k.naam or ""} for k in rows]
        if not beschrijving:
            return items
        q = beschrijving.lower()
        # Substring-voorfilter, net als de mock; lege hit → caller valt terug op
        # search_items() (alle items) voor de fuzzy-stap.
        return [i for i in items if q in i["displayName"].lower()]

    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        with Session(engine) as s:
            rows = s.exec(select(Klantenkaart)).all()
        out: list[dict] = []
        for k in rows:
            row = {
                "number": k.nav_klantnr,
                "displayName": k.naam or "",
                "email": k.email or "",
                # _candidate_address leest deze (PLX-veldnaamvarianten):
                "Post_Code": k.postcode or "",
                "City": k.plaats or "",
            }
            em = email.lower() if email else None
            if em and (
                (k.email or "").lower() == em or (k.email_bestelling or "").lower() == em
            ):
                out.append(row)
                continue
            if naam and naam.lower() in (k.naam or "").lower():
                out.append(row)
        return out
