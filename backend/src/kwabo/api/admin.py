"""Admin operations endpoints: NAV master-data sync, DB introspection.

These endpoints require the standard admin auth (Bearer token from
/api/auth/login). They exist so an operator can trigger maintenance ops
from curl/dashboard without needing Railway shell access.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, func

from kwabo.config import settings
from kwabo.db.models import (
    Artikelkaart,
    ArtikelKruisverwijzing,
    Klantenkaart,
    KlantenkaartShipTo,
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
    fetch_error: Optional[str] = None  # populated when get_collection raised


class NavSyncResponse(BaseModel):
    mode: str
    dry_run: bool
    domains: list[SyncReport]
    db_counts: dict[str, int]


class DbCounts(BaseModel):
    klanten: int
    artikelen: int
    kruisverwijzingen: int
    ship_to_adressen: int


class JobStartResponse(BaseModel):
    job_id: str
    state: str
    detail: str


class JobStatusResponse(BaseModel):
    job_id: str
    state: str  # pending | running | done | failed
    started_at: float
    finished_at: Optional[float]
    progress: dict  # arbitrary per-domain counts
    result: Optional[NavSyncResponse]
    error: Optional[str]


# Module-level job registry. Restarted on uvicorn restart — that's fine,
# sync jobs are short-lived and we use this only to poll a single in-flight
# job from curl.
_JOBS: dict[str, dict] = {}


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


def _ship_to_to_record(
    row: dict, existing: Optional[KlantenkaartShipTo]
) -> Optional[KlantenkaartShipTo]:
    """Map a PLX_ShipToAddress row to KlantenkaartShipTo. Tolerant of NAV
    field-name variants because PLX_ShipToAddress isn't formally documented
    for the Kopie 2026 environment — we accept the common alternatives and
    fall back to empty strings (the model declares NOT NULL).
    """
    klant_nr = _str_or_none(
        row.get("Customer_No") or row.get("CustomerNo") or row.get("Customer")
    )
    code = _str_or_none(row.get("Code") or row.get("Ship_to_Code"))
    if not klant_nr or not code:
        return None
    naam = _str_or_none(row.get("Name") or row.get("Name_2")) or ""
    straat = (
        _str_or_none(
            row.get("Address")
            or row.get("Address_1")
            or row.get("Address_Line_1")
        )
        or ""
    )
    postcode = _str_or_none(row.get("Post_Code") or row.get("PostCode")) or ""
    plaats = _str_or_none(row.get("City")) or ""
    land = (
        _str_or_none(
            row.get("Country_Region_Code")
            or row.get("Country_Code")
            or row.get("Country")
        )
        or ""
    )
    if existing is not None:
        existing.naam = naam
        existing.straat = straat
        existing.postcode = postcode
        existing.plaats = plaats
        existing.land = land
        return existing
    return KlantenkaartShipTo(
        klant_nr=klant_nr,
        ship_to_code=code,
        naam=naam,
        straat=straat,
        postcode=postcode,
        plaats=plaats,
        land=land,
        is_default=False,
    )


def _itemref_to_kruisverwijzing(row: dict) -> Optional[ArtikelKruisverwijzing]:
    """PLX_ItemReference (NAV 2018 table 5717, Item Cross Reference) uses the
    legacy Cross_Reference_* naming in OData V4. Per probe of Kopie 2026:
      Cross_Reference_Type    e.g. "Customer", "Vendor", ""
      Cross_Reference_Type_No customer or vendor number
      Cross_Reference_No      the customer's/vendor's own SKU
      Item_No                 Kwabo's article
      Unit_of_Measure         optional UOM hint
    Only emit when all three required fields are present AND Reference_Type
    is Customer (vendor refs we don't mirror).
    """
    rtype = _str_or_none(row.get("Cross_Reference_Type") or row.get("Reference_Type"))
    klant_nr = _str_or_none(
        row.get("Cross_Reference_Type_No") or row.get("Reference_Type_No")
    )
    klant_art = _str_or_none(row.get("Cross_Reference_No") or row.get("Reference_No"))
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


# Yield the event loop every N rows during DB ingest so /api/health (and
# other HTTP requests) keep responding while a multi-thousand-row sync is
# in flight. session.commit() is sync I/O, so we batch commits too.
SYNC_CHUNK_SIZE = 100


async def _sync_customers(
    client: Nav2018ODataClient, session: Session, dry_run: bool
) -> SyncReport:
    rows, err = await _fetch_collection_safe(client, client.page_customer)
    sample_keys = sorted(rows[0].keys()) if rows else []
    skipped = {"no_nav_nr": 0, "error": 0}
    if err:
        return SyncReport(
            domain="customers", fetched=0, upserted=0, skipped=0,
            skipped_reasons={"fetch_error": 1}, sample_keys=[], fetch_error=err,
        )
    upserted = 0
    for i, r in enumerate(rows):
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
        # Periodically commit + yield so other HTTP requests get a slice
        # of the event loop. 100-row batches keep partial state small if
        # the sync is cancelled mid-flight (Railway restart, kill, etc.).
        if not dry_run and (i + 1) % SYNC_CHUNK_SIZE == 0:
            session.commit()
            await asyncio.sleep(0)
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
            skipped_reasons={"fetch_error": 1}, sample_keys=[], fetch_error=err,
        )
    upserted = 0
    for i, r in enumerate(rows):
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
        if not dry_run and (i + 1) % SYNC_CHUNK_SIZE == 0:
            session.commit()
            await asyncio.sleep(0)
    if not dry_run:
        session.commit()
    return SyncReport(
        domain="items", fetched=len(rows), upserted=upserted,
        skipped=sum(skipped.values()), skipped_reasons=skipped, sample_keys=sample_keys,
    )


async def _sync_ship_to(
    client: Nav2018ODataClient, session: Session, dry_run: bool
) -> SyncReport:
    rows, err = await _fetch_collection_safe(client, client.page_ship_to)
    sample_keys = sorted(rows[0].keys()) if rows else []
    skipped = {"no_klant_nr": 0, "no_code": 0, "error": 0}
    if err:
        return SyncReport(
            domain="ship_to", fetched=0, upserted=0, skipped=0,
            skipped_reasons={"fetch_error": 1}, sample_keys=[], fetch_error=err,
        )
    upserted = 0
    for i, r in enumerate(rows):
        try:
            klant_nr = _str_or_none(
                r.get("Customer_No") or r.get("CustomerNo") or r.get("Customer")
            )
            code = _str_or_none(r.get("Code") or r.get("Ship_to_Code"))
        except Exception:  # noqa: BLE001
            skipped["error"] += 1
            continue
        if not klant_nr:
            skipped["no_klant_nr"] += 1
            continue
        if not code:
            skipped["no_code"] += 1
            continue
        if dry_run:
            upserted += 1
            continue
        existing = session.get(KlantenkaartShipTo, (klant_nr, code))
        try:
            obj = _ship_to_to_record(r, existing)
            if obj is None:
                # _ship_to_to_record already returned None for missing required
                # fields — shouldn't happen here since we pre-checked above,
                # but guard for completeness.
                skipped["error"] += 1
                continue
            session.add(obj)
            upserted += 1
        except Exception:  # noqa: BLE001
            log.exception(
                "nav_sync_ship_to_row_failed", klant_nr=klant_nr, code=code
            )
            skipped["error"] += 1
        if not dry_run and (i + 1) % SYNC_CHUNK_SIZE == 0:
            session.commit()
            await asyncio.sleep(0)
    if not dry_run:
        session.commit()
    return SyncReport(
        domain="ship_to", fetched=len(rows), upserted=upserted,
        skipped=sum(skipped.values()), skipped_reasons=skipped,
        sample_keys=sample_keys,
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
            skipped_reasons={"fetch_error": 1}, sample_keys=[], fetch_error=err,
        )
    upserted = 0
    for i, r in enumerate(rows):
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
        if not dry_run and (i + 1) % SYNC_CHUNK_SIZE == 0:
            session.commit()
            await asyncio.sleep(0)
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
        n_st = s.exec(select(func.count()).select_from(KlantenkaartShipTo)).one()
    return DbCounts(
        klanten=n_k, artikelen=n_a, kruisverwijzingen=n_x, ship_to_adressen=n_st
    )


@router.post("/purge-demo-seed")
def purge_demo_seed_endpoint() -> dict:
    """Verwijder de demo-seed klanten (10001-10016) + mappings/prijzen uit de
    DB. Nodig in productie: die demo-klanten dragen de e-mailadressen van echte
    order-mails en routeren de match naar een NAV-nummer dat niet bestaat →
    push faalt. Idempotent."""
    from kwabo.db.seed import purge_demo_seed

    with Session(engine) as s:
        removed = purge_demo_seed(s)
    log.info("purge_demo_seed", **removed)
    return {"ok": True, "removed": removed}


async def _run_sync_job(job_id: str, selected: set[str], dry_run: bool) -> None:
    """Background worker. Updates _JOBS[job_id] as it goes; never raises
    to caller (errors are recorded on the job)."""
    job = _JOBS[job_id]
    try:
        client = get_navision_client()
        if not isinstance(client, Nav2018ODataClient):
            raise RuntimeError(
                f"Expected Nav2018ODataClient, got {type(client).__name__}"
            )
        reports: list[SyncReport] = []
        with Session(engine) as session:
            if "customers" in selected:
                job["progress"]["current"] = "customers"
                reports.append(await _sync_customers(client, session, dry_run))
                job["progress"]["customers"] = reports[-1].model_dump()
            if "items" in selected:
                job["progress"]["current"] = "items"
                reports.append(await _sync_items(client, session, dry_run))
                job["progress"]["items"] = reports[-1].model_dump()
            if "cross_ref" in selected:
                job["progress"]["current"] = "cross_ref"
                reports.append(await _sync_cross_ref(client, session, dry_run))
                job["progress"]["cross_ref"] = reports[-1].model_dump()
            if "ship_to" in selected:
                job["progress"]["current"] = "ship_to"
                reports.append(await _sync_ship_to(client, session, dry_run))
                job["progress"]["ship_to"] = reports[-1].model_dump()
        counts = db_counts()
        job["result"] = NavSyncResponse(
            mode=settings.navision_mode,
            dry_run=dry_run,
            domains=reports,
            db_counts=counts.model_dump(),
        ).model_dump()
        job["state"] = "done"
        log.info(
            "nav_sync_done", job_id=job_id, dry_run=dry_run,
            domains={r.domain: {"fetched": r.fetched, "upserted": r.upserted} for r in reports},
            db_counts=counts.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("nav_sync_job_failed", job_id=job_id)
        job["state"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["finished_at"] = time.time()


@router.post("/nav-sync", response_model=JobStartResponse, status_code=202)
async def nav_sync_start(
    domains: str = "customers,items,cross_ref",
    dry_run: bool = False,
) -> JobStartResponse:
    """Start a NAV master-data sync in the background.

    Returns immediately with a job_id; poll GET /api/admin/nav-sync/{job_id}
    for progress. Avoids tying up the HTTP worker for 30+ seconds and
    bypasses Railway's proxy request-timeout.
    """
    if settings.navision_mode != "nav2018":
        raise HTTPException(
            400,
            f"nav-sync via HTTP only supports navision_mode=nav2018 "
            f"(current: {settings.navision_mode}).",
        )
    selected = {d.strip() for d in domains.split(",") if d.strip()}
    valid = {"customers", "items", "cross_ref", "ship_to"}
    unknown = selected - valid
    if unknown:
        raise HTTPException(400, f"unknown domains: {sorted(unknown)}. Valid: {sorted(valid)}")
    if not selected:
        selected = valid

    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {
        "job_id": job_id,
        "state": "running",
        "started_at": time.time(),
        "finished_at": None,
        "progress": {"selected": sorted(selected), "dry_run": dry_run, "current": None},
        "result": None,
        "error": None,
    }
    log.info("nav_sync_started", job_id=job_id, domains=sorted(selected), dry_run=dry_run)
    asyncio.create_task(_run_sync_job(job_id, selected, dry_run))
    return JobStartResponse(
        job_id=job_id,
        state="running",
        detail=f"poll GET /api/admin/nav-sync/{job_id}",
    )


@router.get("/nav-sync/{job_id}", response_model=JobStatusResponse)
def nav_sync_status(job_id: str) -> JobStatusResponse:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, f"unknown job_id: {job_id}")
    return JobStatusResponse(**job)


@router.get("/nav-sync", response_model=list[JobStatusResponse])
def nav_sync_list() -> list[JobStatusResponse]:
    """List all in-memory sync jobs (cleared on uvicorn restart)."""
    return [JobStatusResponse(**j) for j in _JOBS.values()]
