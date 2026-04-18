"""Prijsafspraken CRUD + Excel import voor artikel-mappings en prijzen."""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

import openpyxl
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from kwabo.db.models import KlantenkaartArtikel, Prijsafspraak
from kwabo.db.session import engine

router = APIRouter(prefix="/api/klanten", tags=["prijsafspraken"])


class PrijsIn(BaseModel):
    kwabo_artikelnr: str
    prijs: float
    korting_pct: float = 0.0
    type: str = "standaard"
    min_hoeveelheid: Optional[float] = None
    geldig_van: Optional[date] = None
    geldig_tot: Optional[date] = None


class PrijsOut(PrijsIn):
    id: int
    klant_nr: str


@router.get("/{nav_nr}/prijsafspraken", response_model=list[PrijsOut])
def list_prijsafspraken(nav_nr: str) -> list[PrijsOut]:
    with Session(engine) as s:
        rows = s.exec(select(Prijsafspraak).where(Prijsafspraak.klant_nr == nav_nr)).all()
        return [
            PrijsOut(
                id=r.id, klant_nr=r.klant_nr, kwabo_artikelnr=r.kwabo_artikelnr,
                prijs=r.prijs, korting_pct=r.korting_pct or 0, type=r.type,
                min_hoeveelheid=r.min_hoeveelheid, geldig_van=r.geldig_van, geldig_tot=r.geldig_tot,
            )
            for r in rows
        ]


@router.post("/{nav_nr}/prijsafspraken", response_model=PrijsOut)
def add_prijsafspraak(nav_nr: str, body: PrijsIn) -> PrijsOut:
    with Session(engine) as s:
        p = Prijsafspraak(
            klant_nr=nav_nr, kwabo_artikelnr=body.kwabo_artikelnr, prijs=body.prijs,
            korting_pct=body.korting_pct, type=body.type,
            min_hoeveelheid=body.min_hoeveelheid,
            geldig_van=body.geldig_van, geldig_tot=body.geldig_tot,
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        return PrijsOut(
            id=p.id, klant_nr=p.klant_nr, kwabo_artikelnr=p.kwabo_artikelnr,
            prijs=p.prijs, korting_pct=p.korting_pct or 0, type=p.type,
            min_hoeveelheid=p.min_hoeveelheid, geldig_van=p.geldig_van, geldig_tot=p.geldig_tot,
        )


@router.delete("/{nav_nr}/prijsafspraken/{prijs_id}")
def delete_prijsafspraak(nav_nr: str, prijs_id: int) -> dict:
    with Session(engine) as s:
        p = s.get(Prijsafspraak, prijs_id)
        if not p or p.klant_nr != nav_nr:
            raise HTTPException(404, "Prijsafspraak niet gevonden")
        s.delete(p)
        s.commit()
        return {"ok": True}


@router.post("/{nav_nr}/import-excel")
async def import_excel(nav_nr: str, file: UploadFile) -> dict:
    """Import artikel-mappings en/of prijsafspraken vanuit Excel.

    Verwachte kolommen (headers exact, case-insensitive, in row 1):
      klant_artikelnr   | kwabo_artikelnr  | omschrijving | prijs     | korting_pct | geldig_tot
      (verplicht)       | (verplicht)      | (optioneel)  | (opt.)    | (opt.)      | (opt.)

    Elke rij leidt tot: (a) UPSERT in klantenkaart_artikelen en
    (b) indien `prijs` is ingevuld: UPSERT in prijsafspraken.
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Alleen .xlsx/.xls")
    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(400, "Lege Excel")
    headers = [str(h or "").strip().lower() for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers)}
    need = {"klant_artikelnr", "kwabo_artikelnr"}
    missing = need - set(headers)
    if missing:
        raise HTTPException(400, f"Kolommen ontbreken: {sorted(missing)}")

    mappings_upserted = 0
    prijzen_upserted = 0
    errors: list[str] = []
    with Session(engine) as s:
        for rn, row in enumerate(rows[1:], start=2):
            def cell(name: str):
                i = idx.get(name)
                return row[i] if i is not None and i < len(row) else None

            klant_art = cell("klant_artikelnr")
            kwabo_art = cell("kwabo_artikelnr")
            if not klant_art or not kwabo_art:
                errors.append(f"rij {rn}: klant/kwabo artikelnr leeg")
                continue

            existing = s.exec(
                select(KlantenkaartArtikel).where(
                    (KlantenkaartArtikel.klant_nr == nav_nr)
                    & (KlantenkaartArtikel.klant_artikelnr == str(klant_art))
                )
            ).first()
            if existing:
                existing.kwabo_artikelnr = str(kwabo_art)
                if cell("omschrijving"):
                    existing.omschrijving = str(cell("omschrijving"))
                s.add(existing)
            else:
                s.add(
                    KlantenkaartArtikel(
                        klant_nr=nav_nr,
                        klant_artikelnr=str(klant_art),
                        kwabo_artikelnr=str(kwabo_art),
                        omschrijving=str(cell("omschrijving")) if cell("omschrijving") else None,
                    )
                )
            mappings_upserted += 1

            prijs = cell("prijs")
            if prijs is not None:
                try:
                    prijs_f = float(prijs)
                except (TypeError, ValueError):
                    errors.append(f"rij {rn}: prijs '{prijs}' niet numeriek")
                    continue
                korting = cell("korting_pct")
                korting_f = 0.0
                if korting is not None:
                    try:
                        korting_f = float(korting)
                    except (TypeError, ValueError):
                        pass
                existing_p = s.exec(
                    select(Prijsafspraak).where(
                        (Prijsafspraak.klant_nr == nav_nr)
                        & (Prijsafspraak.kwabo_artikelnr == str(kwabo_art))
                    )
                ).first()
                if existing_p:
                    existing_p.prijs = prijs_f
                    existing_p.korting_pct = korting_f
                    if cell("geldig_tot"):
                        existing_p.geldig_tot = cell("geldig_tot")
                    s.add(existing_p)
                else:
                    s.add(
                        Prijsafspraak(
                            klant_nr=nav_nr,
                            kwabo_artikelnr=str(kwabo_art),
                            prijs=prijs_f,
                            korting_pct=korting_f,
                            geldig_tot=cell("geldig_tot"),
                        )
                    )
                prijzen_upserted += 1
        s.commit()

    return {
        "ok": True,
        "mappings_upserted": mappings_upserted,
        "prijzen_upserted": prijzen_upserted,
        "errors": errors,
    }
