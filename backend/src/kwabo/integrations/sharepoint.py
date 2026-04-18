"""SharePoint klantenkaart integration via Microsoft Graph API.

Downloads klantenkaart Excel files from SharePoint and syncs
artikel-mappings + prijsafspraken into the local DB.

Requires Azure AD app registration with Sites.Read.All + Files.Read.All.
Config via env: SP_TENANT_ID, SP_CLIENT_ID, SP_CLIENT_SECRET, SP_SITE_ID, SP_DRIVE_ID.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

import httpx
import openpyxl
from sqlmodel import Session

from kwabo.db.models import KlantenkaartArtikel, Prijsafspraak
from kwabo.db.repository import ArtikelRepo
from kwabo.utils.logging import log


class SharePointClient:
    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        site_id: str | None = None,
        drive_id: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id or os.getenv("SP_TENANT_ID", "")
        self.client_id = client_id or os.getenv("SP_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("SP_CLIENT_SECRET", "")
        self.site_id = site_id or os.getenv("SP_SITE_ID", "")
        self.drive_id = drive_id or os.getenv("SP_DRIVE_ID", "")
        self._token: Optional[str] = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            return self._token

    async def download_file(self, file_path: str) -> bytes:
        """Download a file from the configured SharePoint drive by path."""
        token = await self._get_token()
        encoded_path = file_path.replace("/", ":/")
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root:/{encoded_path}:/content"
        async with httpx.AsyncClient() as c:
            resp = await c.get(url, headers={"Authorization": f"Bearer {token}"}, follow_redirects=True)
            resp.raise_for_status()
            return resp.content

    async def list_files(self, folder_path: str = "") -> list[dict]:
        token = await self._get_token()
        if folder_path:
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root:/{folder_path}:/children"
        else:
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root/children"
        async with httpx.AsyncClient() as c:
            resp = await c.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json().get("value", [])


def sync_from_excel(session: Session, klant_nr: str, xlsx_bytes: bytes) -> dict:
    """Parse an Excel file and upsert mappings + prijsafspraken for the given klant.

    Expected columns (case-insensitive, row 1):
      klant_artikelnr | kwabo_artikelnr | omschrijving | prijs | korting_pct | geldig_tot
    """
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"mappings": 0, "prijzen": 0, "errors": ["Lege Excel"]}
    headers = [str(h or "").strip().lower() for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers)}
    if "klant_artikelnr" not in idx or "kwabo_artikelnr" not in idx:
        return {"mappings": 0, "prijzen": 0, "errors": [f"Kolommen ontbreken. Gevonden: {headers}"]}
    repo = ArtikelRepo(session)
    mappings = 0
    prijzen = 0
    errors: list[str] = []
    for rn, row in enumerate(rows[1:], start=2):
        def cell(name):
            i = idx.get(name)
            return row[i] if i is not None and i < len(row) else None
        ka = cell("klant_artikelnr")
        kw = cell("kwabo_artikelnr")
        if not ka or not kw:
            errors.append(f"rij {rn}: leeg")
            continue
        repo.upsert_mapping(klant_nr, str(ka), str(kw), str(cell("omschrijving") or ""))
        mappings += 1
        prijs = cell("prijs")
        if prijs is not None:
            try:
                from sqlmodel import select
                existing = session.exec(
                    select(Prijsafspraak).where(
                        (Prijsafspraak.klant_nr == klant_nr) & (Prijsafspraak.kwabo_artikelnr == str(kw))
                    )
                ).first()
                if existing:
                    existing.prijs = float(prijs)
                    session.add(existing)
                else:
                    session.add(Prijsafspraak(klant_nr=klant_nr, kwabo_artikelnr=str(kw), prijs=float(prijs)))
                prijzen += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"rij {rn}: prijs error {e}")
    session.commit()
    log.info("sharepoint_sync", klant_nr=klant_nr, mappings=mappings, prijzen=prijzen, errors=len(errors))
    return {"mappings": mappings, "prijzen": prijzen, "errors": errors}
