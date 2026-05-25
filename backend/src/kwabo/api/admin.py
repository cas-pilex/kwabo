"""Admin operations endpoints: NAV master-data sync, DB introspection.

These endpoints require the standard admin auth (Bearer token from
/api/auth/login). They exist so an operator can trigger maintenance ops
from curl/dashboard without needing Railway shell access.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, func

from kwabo.config import settings
from kwabo.db.models import (
    Artikelkaart,
    ArtikelKruisverwijzing,
    Klantenkaart,
)
from kwabo.db.session import engine
from kwabo.integrations.navision_api import get_navision_client
from kwabo.integrations.navision_nav2018 import Nav2018ODataClient
from kwabo.utils import utcnow
from kwabo.utils.logging import log

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- response shapes ----------


class SyncReport(BaseModel):
    domain: str
    fetched: int
    upserted: int
    skipped: int
    skipped_reasons: dict[str, int]
    sample_keys: list[str]  # keys seen on the first NAV row, for debugging


class NavSyncResponse(BaseModel):
    mode: str
    dry_run: bool
    domains: list[SyncReport]
    db_counts: dict[str, int]


class DbCounts(BaseModel):
    klanten: int
    artikelen: int
    kruisverwijzingen: int


# ---------- helpers: NAV row -> DB model ----------


def _str_or_none(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _float_or_none(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _customer_to_klantenkaart(row: dict, existing: Optional[Klantenkaart]) -> Klantenkaart:
    """Map a PLX_Customer row to a Klantenkaart. If `existing` is given,
    overwrite NAV-authoritative fields but preserve user-edited ones
    (aliases-set is_4plus stays untouched; email_bestelling stays).
    """
    nav_nr = str(row.get("No"))
    naam = _str_or_none(row.get("Name") or row.get("Name_2")) or nav_nr
    email = _str_or_none(row.get("E_Mail"))
    telefoon = _str_or_none(row.get("Phone_No") or row.get("Phone_No_"))
    taal = _str_or_none(row.get("Language_Code")) or "NL"
    krediet = _float_or_none(row.get("Credit_Limit_LCY"))
    betaling = _str_or_none(row.get("Payment_Terms_Code"))

    if existing is not None:
        existing.naam = naam
        # Only overwrite email if NAV has a non-empty value (preserve user edits otherwise).
        if email:
            existing.email = email
        if telefoon:
            existing.telefoon = telefoon
        existing.taal = taal
        existing.kredietlimiet = krediet
        existing.betalingsconditie = betaling
        existing.updated_at = utcnow()
        return existing
    return Klantenkaart(
        nav_klantnr=nav_nr,
        naam=naam,
        email=email,
        telefoon=telefoon,
        taal=taal,
        kredietlimiet=krediet,
        betalingsconditie=betaling,
        mixprijzen=False,
    )


def _item_to_artikelkaart(row: dict, existing: Optional[Artikelkaart]) -> Artikelkaart:
    nr = str(row.get("No"))
    naam = (
        _str_or_none(row.get("Description"))
        or _str_or_none(row.get("Description_2"))
        or nr
    )
    uom = _str_or_none(row.get("Base_Unit_of_Measure")) or _str_or_none(
        row.get("Base_UoM_Code")
    ) or "STUK"
    if existing is not None:
        existing.naam = naam
        existing.basis_eenheid = uom
        existing.updated_at = utcnow()
        return existing
    return Artikelkaart(kwabo_artikelnr=nr, naam=naam, basis_eenheid=uom, mixprijzen=False)


def _itemref_to_kruisverwijzing(row: dict) -> Optional[ArtikelKruisverwijzing]:
    """PLX_ItemReference fields per NAV 2018 table 5717 OData-naming:
    Reference_Type, Reference_Type_No, Reference_No (customer's SKU),
    Item_No (Kwabo's article), Unit_of_Measure.
    Only emit when all three required fields are present and Reference_Type
    is Customer.
    """
    rtype = _str_or_none(row.get("Reference_Type"))
    klant_nr = _str_or_none(row.get("Reference_Type_No"))
    klant_art = _str_or_none(row.get("Reference_No"))
    kwabo_art = _str_or_none(row.get("Item_No"))
    if not (klant_nr and klant_art and kwabo_art):
        return None
    if rtype and rtype.lower() not in ("customer", "klant", ""):
        return None  # Vendor references etc. — skip
    return ArtikelKruisverwijzing(
        klant_nr=klant_nr,
        klant_artikelnr=klant_art,
        kwabo_artikelnr=kwabo_art,
        eenheid_klant=_str_or_none(row.get("Unit_of_Measure")),
        bron=rtype or "customer",
    )


# ---------- per-domain sync (nav2018 path) ----------


async def _fetch_collection_safe(
    client: Nav2018ODataClient, entity: str
) -> tuple[list[dict], Optional[str]]:
    try:
        rows = await client.get_collection(entity)
        return rows, None
    except Exception as exc:  # noqa: BLE001
        log.exception("nav_sync_fetch_failed", entity=entity)
        return [], f"{type(exc).__name__}: {exc}"


async def _sync_customers(
    client: Nav2018ODataClient, session: Session, dry_run: bool
) -> SyncReport:
    rows, err = await _fetch_collection_safe(client, client.page_customer)
    sample_keys = sorted(rows[0].keys()) if rows else []
    skipped = {"no_nav_nr": 0, "error": 0}
    if err:
        return SyncReport(
            domain="customers", fetched=0, upserted=0, skipped=0,
            skipped_reasons={"fetch_error": 1, "msg": 0}, sample_keys=[],
        )
    upserted = 0
    for r in rows:
        if not r.get("No"):
            skipped["no_nav_nr"] += 1
            continue
        if dry_run:
            upserted += 1
            continue
        nav_nr = str(r["No"])
        existing = session.exec(
            select(Klantenkaart).where(Klantenkaart.nav_klantnr == nav_nr)
        ).first()
        try:
            obj = _customer_to_klantenkaart(r, existing)
            session.add(obj)
            upserted += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("nav_sync_customer_row_failed", nav_nr=nav_nr)
            skipped["error"] += 1
    if not dry_run:
        session.commit()
    return SyncReport(
        domain="customers", fetched=len(rows), upserted=upserted,
        skipped=sum(skipped.values()), skipped_reasons=skipped, sample_keys=sample_keys,
    )


async def _sync_items(
    client: Nav2018ODataClient, session: Session, dry_run: bool
) -> SyncReport:
    rows, err = await _fetch_collection_safe(client, client.page_item)
    sample_keys = sorted(rows[0].keys()) if rows else []
    skipped = {"no_nr": 0, "error": 0}
    if err:
        return SyncReport(
            domain="items", fetched=0, upserted=0, skipped=0,
            skipped_reasons={"fetch_error": 1}, sample_keys=[],
        )
    upserted = 0
    for r in rows:
        if not r.get("No"):
            skipped["no_nr"] += 1
            continue
        if dry_run:
            upserted += 1
            continue
        nr = str(r["No"])
        existing = session.get(Artikelkaart, nr)
        try:
            obj = _item_to_artikelkaart(r, existing)
            session.add(obj)
            upserted += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("nav_sync_item_row_failed", nr=nr)
            skipped["error"] += 1
    if not dry_run:
        session.commit()
    return SyncReport(
        domain="items", fetched=len(rows), upserted=upserted,
        skipped=sum(skipped.values()), skipped_reasons=skipped, sample_keys=sample_keys,
    )


async def _sync_cross_ref(
    client: Nav2018ODataClient, session: Session, dry_run: bool
) -> SyncReport:
    rows, err = await _fetch_collection_safe(client, client.page_item_reference)
    sample_keys = sorted(rows[0].keys()) if rows else []
    skipped = {"incomplete": 0, "non_customer": 0, "error": 0}
    if err:
        return SyncReport(
            domain="cross_ref", fetched=0, upserted=0, skipped=0,
            skipped_reasons={"fetch_error": 1}, sample_keys=[],
        )
    upserted = 0
    for r in rows:
        try:
            obj = _itemref_to_kruisverwijzing(r)
        except Exception:  # noqa: BLE001
            log.exception("nav_sync_xref_row_failed")
            skipped["error"] += 1
            continue
        if obj is None:
            # Distinguish whether we skipped due to missing fields or wrong type.
            if not r.get("Reference_Type") or str(r.get("Reference_Type")).lower() in (
                "customer", "klant", ""
            ):
                skipped["incomplete"] += 1
            else:
                skipped["non_customer"] += 1
            continue
        if dry_run:
            upserted += 1
            continue
        # Composite-PK upsert: delete existing row then add fresh.
        existing = session.get(
            ArtikelKruisverwijzing, (obj.klant_nr, obj.klant_artikelnr)
        )
        if existing is not None:
            existing.kwabo_artikelnr = obj.kwabo_artikelnr
            existing.eenheid_klant = obj.eenheid_klant
            existing.bron = obj.bron
            session.add(existing)
        else:
            session.add(obj)
        upserted += 1
    if not dry_run:
        session.commit()
    return SyncReport(
        domain="cross_ref", fetched=len(rows), upserted=upserted,
        skipped=sum(skipped.values()), skipped_reasons=skipped, sample_keys=sample_keys,
    )


# ---------- endpoints ----------


@router.get("/db-counts", response_model=DbCounts)
def db_counts() -> DbCounts:
    with Session(engine) as s:
        n_k = s.exec(select(func.count()).select_from(Klantenkaart)).one()
        n_a = s.exec(select(func.count()).select_from(Artikelkaart)).one()
        n_x = s.exec(select(func.count()).select_from(ArtikelKruisverwijzing)).one()
    return DbCounts(klanten=n_k, artikelen=n_a, kruisverwijzingen=n_x)


@router.post("/nav-sync", response_model=NavSyncResponse)
async def nav_sync(
    domains: str = "customers,items,cross_ref",
    dry_run: bool = False,
) -> NavSyncResponse:
    """Sync NAV master data into the local mirror tables.

    Query params:
      domains  comma-separated subset of {customers, items, cross_ref}.
               Default: all three.
      dry_run  if true, fetch from NAV but skip DB writes (returns the
               counts we *would* upsert).

    Only supports nav2018 mode for now. For NAVISION_MODE=real, use the
    sync_navision_masters.py CLI script directly.
    """
    if settings.navision_mode != "nav2018":
        raise HTTPException(
            400,
            f"nav-sync via HTTP only supports navision_mode=nav2018 "
            f"(current: {settings.navision_mode}). "
            f"For 'real' mode, run scripts/sync_navision_masters.py via CLI.",
        )

    selected = {d.strip() for d in domains.split(",") if d.strip()}
    valid = {"customers", "items", "cross_ref"}
    unknown = selected - valid
    if unknown:
        raise HTTPException(400, f"unknown domains: {sorted(unknown)}. Valid: {sorted(valid)}")
    if not selected:
        selected = valid

    client = get_navision_client()
    if not isinstance(client, Nav2018ODataClient):
        raise HTTPException(
            500,
            f"Expected Nav2018ODataClient, got {type(client).__name__}. "
            f"Restart with NAVISION_MODE=nav2018.",
        )

    log.info("nav_sync_start", domains=sorted(selected), dry_run=dry_run)
    reports: list[SyncReport] = []
    with Session(engine) as session:
        if "customers" in selected:
            reports.append(await _sync_customers(client, session, dry_run))
        if "items" in selected:
            reports.append(await _sync_items(client, session, dry_run))
        if "cross_ref" in selected:
            reports.append(await _sync_cross_ref(client, session, dry_run))

    counts = db_counts()
    log.info(
        "nav_sync_done", dry_run=dry_run,
        domains={r.domain: {"fetched": r.fetched, "upserted": r.upserted} for r in reports},
        db_counts=counts.model_dump(),
    )
    return NavSyncResponse(
        mode=settings.navision_mode,
        dry_run=dry_run,
        domains=reports,
        db_counts=counts.model_dump(),
    )
