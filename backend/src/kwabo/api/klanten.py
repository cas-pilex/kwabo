"""Klanten + artikelmapping endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from kwabo.api.schemas import KlantOut, MappingIn, MappingOut
from kwabo.db.models import Klantenkaart
from kwabo.db.repository import ArtikelRepo, KlantRepo
from kwabo.db.session import engine

router = APIRouter(prefix="/api/klanten", tags=["klanten"])


@router.get("", response_model=list[KlantOut])
def list_klanten() -> list[KlantOut]:
    with Session(engine) as s:
        return [
            KlantOut(
                nav_klantnr=k.nav_klantnr,
                naam=k.naam,
                email=k.email,
                email_bestelling=k.email_bestelling,
                taal=k.taal,
                is_4plus=k.is_4plus,
            )
            for k in KlantRepo(s).all()
        ]


@router.get("/{nav_nr}", response_model=KlantOut)
def get_klant(nav_nr: str) -> KlantOut:
    with Session(engine) as s:
        k = KlantRepo(s).by_nav_nr(nav_nr)
        if not k:
            raise HTTPException(404, "Klant niet gevonden")
        return KlantOut(
            nav_klantnr=k.nav_klantnr,
            naam=k.naam,
            email=k.email,
            email_bestelling=k.email_bestelling,
            taal=k.taal,
            is_4plus=k.is_4plus,
        )


@router.patch("/{nav_nr}", response_model=KlantOut)
def patch_klant(nav_nr: str, body: dict) -> KlantOut:
    with Session(engine) as s:
        k = KlantRepo(s).by_nav_nr(nav_nr)
        if not k:
            raise HTTPException(404, "Klant niet gevonden")
        for field in ("naam", "email", "email_bestelling", "taal"):
            if field in body:
                setattr(k, field, body[field])
        s.add(k)
        s.commit()
        s.refresh(k)
        return KlantOut(
            nav_klantnr=k.nav_klantnr,
            naam=k.naam,
            email=k.email,
            email_bestelling=k.email_bestelling,
            taal=k.taal,
            is_4plus=k.is_4plus,
        )


@router.get("/{nav_nr}/artikelen", response_model=list[MappingOut])
def list_mappings(nav_nr: str) -> list[MappingOut]:
    with Session(engine) as s:
        return [
            MappingOut(
                id=m.id,
                klant_nr=m.klant_nr,
                klant_artikelnr=m.klant_artikelnr,
                kwabo_artikelnr=m.kwabo_artikelnr,
                omschrijving=m.omschrijving,
            )
            for m in ArtikelRepo(s).mappings_for(nav_nr)
        ]


@router.post("/{nav_nr}/artikelen", response_model=MappingOut)
def add_mapping(nav_nr: str, body: MappingIn) -> MappingOut:
    with Session(engine) as s:
        m = ArtikelRepo(s).upsert_mapping(
            nav_nr, body.klant_artikelnr, body.kwabo_artikelnr, body.omschrijving
        )
        return MappingOut(
            id=m.id,
            klant_nr=m.klant_nr,
            klant_artikelnr=m.klant_artikelnr,
            kwabo_artikelnr=m.kwabo_artikelnr,
            omschrijving=m.omschrijving,
        )
