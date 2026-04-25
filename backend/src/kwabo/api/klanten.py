"""Klanten + artikelmapping endpoints."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import Session, select

from kwabo.api.schemas import (
    AliasIn,
    AliasOut,
    KlantDocumentDetail,
    KlantDocumentOut,
    KlantOut,
    MappingIn,
    MappingOut,
)
from kwabo.db.models import KlantDocument, Klantenkaart
from kwabo.db.repository import ArtikelRepo, KlantRepo
from kwabo.db.session import engine
from kwabo.integrations.document_extractor import extract_text

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


@router.get("/{nav_nr}/aliases", response_model=list[AliasOut])
def list_aliases(nav_nr: str) -> list[AliasOut]:
    with Session(engine) as s:
        return [
            AliasOut(id=a.id, klant_nr=a.klant_nr, email=a.email, label=a.label)
            for a in KlantRepo(s).list_aliases(nav_nr)
        ]


@router.post("/{nav_nr}/aliases", response_model=AliasOut)
def add_alias(nav_nr: str, body: AliasIn) -> AliasOut:
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Geldig e-mailadres vereist")
    with Session(engine) as s:
        k = KlantRepo(s).by_nav_nr(nav_nr)
        if not k:
            raise HTTPException(404, "Klant niet gevonden")
        a = KlantRepo(s).add_alias(nav_nr, email, body.label)
        return AliasOut(id=a.id, klant_nr=a.klant_nr, email=a.email, label=a.label)


@router.delete("/{nav_nr}/aliases/{alias_id}")
def delete_alias(nav_nr: str, alias_id: int) -> dict:
    with Session(engine) as s:
        ok = KlantRepo(s).delete_alias(alias_id)
        if not ok:
            raise HTTPException(404, "Alias niet gevonden")
        return {"ok": True}


# ---------- Klant-documenten (klantkaart PDF/Excel/Word upload) ----------

MAX_DOC_SIZE = 25 * 1024 * 1024  # 25 MB


def _doc_to_summary(d: KlantDocument) -> KlantDocumentOut:
    return KlantDocumentOut(
        id=d.id or 0,
        klant_nr=d.klant_nr,
        filename=d.filename,
        doc_type=d.doc_type,
        mime_type=d.mime_type,
        size_bytes=d.size_bytes,
        notes=d.notes,
        created_at=d.created_at,
        text_preview=(d.text_content or "")[:500],
    )


@router.get("/{nav_nr}/documenten", response_model=list[KlantDocumentOut])
def list_documenten(nav_nr: str) -> list[KlantDocumentOut]:
    with Session(engine) as s:
        rows = s.exec(
            select(KlantDocument)
            .where(KlantDocument.klant_nr == nav_nr)
            .order_by(KlantDocument.created_at.desc())
        ).all()
        return [_doc_to_summary(r) for r in rows]


@router.get("/{nav_nr}/documenten/{doc_id}", response_model=KlantDocumentDetail)
def get_document(nav_nr: str, doc_id: int) -> KlantDocumentDetail:
    with Session(engine) as s:
        d = s.get(KlantDocument, doc_id)
        if not d or d.klant_nr != nav_nr:
            raise HTTPException(404, "Document niet gevonden")
        return KlantDocumentDetail(
            id=d.id or 0,
            klant_nr=d.klant_nr,
            filename=d.filename,
            doc_type=d.doc_type,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            notes=d.notes,
            created_at=d.created_at,
            text_preview=(d.text_content or "")[:500],
            text_content=d.text_content or "",
        )


@router.post("/{nav_nr}/documenten", response_model=KlantDocumentOut)
async def upload_document(
    nav_nr: str,
    file: UploadFile = File(...),
) -> KlantDocumentOut:
    with Session(engine) as s:
        k = KlantRepo(s).by_nav_nr(nav_nr)
        if not k:
            raise HTTPException(404, "Klant niet gevonden")

    filename = file.filename or "document"
    content = await file.read()
    if len(content) > MAX_DOC_SIZE:
        raise HTTPException(413, f"Bestand te groot (max {MAX_DOC_SIZE // (1024 * 1024)} MB)")

    doc_type, text = extract_text(filename, content)

    with Session(engine) as s:
        row = KlantDocument(
            klant_nr=nav_nr,
            filename=filename,
            doc_type=doc_type,
            mime_type=file.content_type,
            size_bytes=len(content),
            text_content=text,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return _doc_to_summary(row)


@router.delete("/{nav_nr}/documenten/{doc_id}")
def delete_document(nav_nr: str, doc_id: int) -> dict:
    with Session(engine) as s:
        d = s.get(KlantDocument, doc_id)
        if not d or d.klant_nr != nav_nr:
            raise HTTPException(404, "Document niet gevonden")
        s.delete(d)
        s.commit()
        return {"ok": True}
