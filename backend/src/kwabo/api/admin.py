"""Admin operations endpoints: NAV master-data sync, DB introspection.

These endpoints require the standard admin auth (Bearer token from
/api/auth/login). They exist so an operator can trigger maintenance ops
from curl/dashboard without needing Railway shell access.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, func, delete

from kwabo.config import settings
from kwabo.db.models import (
    Artikelkaart,
    ArtikelEenheid,
    ArtikelKruisverwijzing,
    Klantenkaart,
    KlantenkaartShipTo,
)
from kwabo.db.session import engine
from kwabo.integrations.navision_api import nav_client_scope
from kwabo.integrations.navision_nav2018 import Nav2018ODataClient
from kwabo.utils import utcnow
from kwabo.utils.logging import log
from kwabo.utils.mixcode import is_mix_code

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
    artikel_eenheden: int = 0


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
    # Vestigingsadres — kiest de juiste franchise-vestiging op het leveradres
    # (PontMeyer Heerenveen vs Zwaag) en toont de plaats in de UI. Tolerant van
    # NAV-veldnaamvarianten, net als de ship-to-mapping.
    plaats = _str_or_none(row.get("City") or row.get("Plaats"))
    postcode = _str_or_none(row.get("Post_Code") or row.get("PostCode"))
    krediet = _float_or_none(row.get("Credit_Limit_LCY"))
    betaling = _str_or_none(row.get("Payment_Terms_Code"))
    # Customer mix-price flag. Live NAV audit (Kopie 2026) confirmed PLX_Customer
    # exposes this as `Mix_Prices_Allowed`; the other keys are tolerant fallbacks.
    # _nav_bool returns False for unknown keys, so the feature stays inert if the
    # field is ever renamed.
    mix = _nav_bool(
        row,
        "Mix_Prices_Allowed",
        "Mixprijzen",
        "Mix_Prices",
        "Kwabo_Mixprijzen",
        "Field50013",
    )

    if existing is not None:
        existing.naam = naam
        # Only overwrite email if NAV has a non-empty value (preserve user edits otherwise).
        if email:
            existing.email = email
        if telefoon:
            existing.telefoon = telefoon
        existing.taal = taal
        existing.plaats = plaats
        existing.postcode = postcode
        existing.kredietlimiet = krediet
        existing.betalingsconditie = betaling
        existing.mixprijzen = mix
        existing.updated_at = utcnow()
        return existing
    return Klantenkaart(
        nav_klantnr=nav_nr,
        naam=naam,
        email=email,
        telefoon=telefoon,
        taal=taal,
        plaats=plaats,
        postcode=postcode,
        kredietlimiet=krediet,
        betalingsconditie=betaling,
        mixprijzen=mix,
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
    # NAV Item "Sales Unit of Measure": de eenheid waarnaar NAV een nieuwe
    # orderregel default — sturend voor de Branch-A-eenheidskeuze (#716).
    verkoop = (
        _str_or_none(row.get("Sales_Unit_of_Measure"))
        or _str_or_none(row.get("Sales_UoM_Code"))
        or _str_or_none(row.get("salesUnitOfMeasure"))
    )
    if existing is not None:
        existing.naam = naam
        existing.basis_eenheid = uom
        existing.verkoop_eenheid = verkoop
        existing.updated_at = utcnow()
        return existing
    return Artikelkaart(kwabo_artikelnr=nr, naam=naam, basis_eenheid=uom,
                        verkoop_eenheid=verkoop, mixprijzen=False)


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


# Same mix-UOM heuristic as scripts/sync_navision_masters.py: an explicit NAV
# flag wins, otherwise the UOM code itself signals a mix unit. Keep the pattern
# conservative (MIX/MENG) — "M1"/"M2" are meter-based units, NOT mix units, so
# we do NOT pattern-match a leading "M<digit>" to avoid false positives.
_MIX_UOM_PATTERN = re.compile(r"\bMIX\b|MENG", re.IGNORECASE)


def _nav_bool(row: dict, *keys: str) -> bool:
    """NAV exposes flags as bool / "true"/"false" / "Yes"/"No" / 0/1."""
    for k in keys:
        if k in row:
            v = row[k]
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            s = str(v).strip().lower()
            if s in ("true", "yes", "ja", "1"):
                return True
            if s in ("false", "no", "nee", "0", ""):
                return False
    return False


def _item_uom_is_mix(row: dict, code: str) -> bool:
    if _nav_bool(row, "Mix_UoM", "MixUoM", "Is_Mix_UoM", "Kwabo_Mix"):
        return True
    # The real staffel codes are M{n}PAL{r} (e.g. M33PAL35) — recognise those.
    if code and is_mix_code(code):
        return True
    return bool(code and _MIX_UOM_PATTERN.search(code))


def _item_uom_to_record(
    row: dict, existing: Optional[ArtikelEenheid]
) -> Optional[ArtikelEenheid]:
    """Map a PLX_ItemUnitOfMeasure row (NAV table 5404) to ArtikelEenheid.

    Tolerant of NAV field-name variants — the exact OData property names for
    this page in the Kopie 2026 environment must be verified live, so we
    accept the common alternatives and skip rows missing a key field.
    """
    artikelnr = _str_or_none(
        row.get("Item_No") or row.get("ItemNo") or row.get("Item")
    )
    code = _str_or_none(
        row.get("Code")
        or row.get("Unit_of_Measure_Code")
        or row.get("UnitOfMeasureCode")
    )
    if not artikelnr or not code:
        return None
    qty = _float_or_none(
        row.get("Qty_per_Unit_of_Measure")
        or row.get("QtyperUnitofMeasure")
        or row.get("Qty_per_Unit")
    )
    if qty is None or qty <= 0:
        qty = 1.0
    is_mix = _item_uom_is_mix(row, code)
    if existing is not None:
        existing.qty_per_base = float(qty)
        existing.is_mix_uom = is_mix
        return existing
    return ArtikelEenheid(
        kwabo_artikelnr=artikelnr,
        eenheid_code=code,
        qty_per_base=float(qty),
        is_mix_uom=is_mix,
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


def _item_uom_keys(r: dict) -> tuple[Optional[str], Optional[str]]:
    artikelnr = _str_or_none(r.get("Item_No") or r.get("ItemNo") or r.get("Item"))
    code = _str_or_none(
        r.get("Code") or r.get("Unit_of_Measure_Code") or r.get("UnitOfMeasureCode")
    )
    return artikelnr, code


def _ingest_item_uoms(rows: list[dict], dry_run: bool, sample_keys: list[str]) -> SyncReport:
    """BLOCKING DB ingest for item_uoms — runs in a worker thread via
    asyncio.to_thread with its OWN Session, so the DB write never blocks the
    event loop (and /api/health stays responsive, so Railway doesn't restart
    the container mid-sync). Uses a bulk clear+insert for speed.
    """
    skipped = {"no_artikelnr": 0, "no_code": 0, "error": 0}
    upserted = 0

    if dry_run:
        for r in rows:
            artikelnr, code = _item_uom_keys(r)
            if not artikelnr:
                skipped["no_artikelnr"] += 1
            elif not code:
                skipped["no_code"] += 1
            else:
                upserted += 1
        return SyncReport(
            domain="item_uoms", fetched=len(rows), upserted=upserted,
            skipped=sum(skipped.values()), skipped_reasons=skipped,
            sample_keys=sample_keys,
        )

    # Build the desired rows in memory first, de-duplicated by PK (NAV can
    # return the same (item, code) twice — last wins, matching the old
    # session.get upsert). Then write in BULK: one DELETE + one executemany
    # INSERT. Per-row ORM get/add issued ~13k individual statements to
    # Supabase (15-20 min, lock-prone); the bulk path is a short transaction
    # of seconds.
    by_key: dict[tuple[str, str], ArtikelEenheid] = {}
    for r in rows:
        artikelnr, code = _item_uom_keys(r)
        if not artikelnr:
            skipped["no_artikelnr"] += 1
            continue
        if not code:
            skipped["no_code"] += 1
            continue
        try:
            obj = _item_uom_to_record(r, None)
            if obj is None:
                skipped["error"] += 1
                continue
            by_key[(artikelnr, code)] = obj
        except Exception:  # noqa: BLE001
            log.exception(
                "nav_sync_item_uom_row_failed", artikelnr=artikelnr, code=code
            )
            skipped["error"] += 1

    objs = list(by_key.values())
    with Session(engine) as s:
        # Full-mirror refresh: clear then bulk-insert. Brief empty window is
        # safe — match_articles falls back to the base unit + review if a UoM
        # isn't found, and the window is only the few seconds of this write.
        s.exec(delete(ArtikelEenheid))
        s.bulk_save_objects(objs)
        s.commit()
    upserted = len(objs)

    return SyncReport(
        domain="item_uoms", fetched=len(rows), upserted=upserted,
        skipped=sum(skipped.values()), skipped_reasons=skipped,
        sample_keys=sample_keys,
    )


async def _sync_item_uoms(
    client: Nav2018ODataClient, session: Session, dry_run: bool
) -> SyncReport:
    """Mirror PLX_ItemUnitOfMeasure (NAV table 5404) into ArtikelEenheid.

    This is the data match_articles needs to validate the customer's ordered
    unit (e.g. keep "STUK" instead of forcing the article's default "PAL"),
    and apply_mixprijzen needs to find mix UOMs. The page is a flat PLX page,
    so we read it like _sync_ship_to rather than per-item sub-collections.

    The DB ingest (largest domain, ~13k rows) is offloaded to a worker thread
    so it never blocks the event loop / healthcheck.
    """
    rows, err = await _fetch_collection_safe(client, client.page_item_uom)
    if err:
        return SyncReport(
            domain="item_uoms", fetched=0, upserted=0, skipped=0,
            skipped_reasons={"fetch_error": 1}, sample_keys=[], fetch_error=err,
        )
    sample_keys = sorted(rows[0].keys()) if rows else []
    return await asyncio.to_thread(_ingest_item_uoms, rows, dry_run, sample_keys)


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
        n_uom = s.exec(select(func.count()).select_from(ArtikelEenheid)).one()
    return DbCounts(
        klanten=n_k, artikelen=n_a, kruisverwijzingen=n_x, ship_to_adressen=n_st,
        artikel_eenheden=n_uom,
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
        # Fase 4 (§12.D.2): de job draait als losse asyncio-task zonder
        # omliggende pipeline-scope; zonder scope lekte hier één
        # httpx.AsyncClient (+ open TLS-sockets) per sync-run — ook op het
        # faalpad. De scope sluit de client gegarandeerd via aclose().
        async with nav_client_scope() as client:
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
                if "item_uoms" in selected:
                    job["progress"]["current"] = "item_uoms"
                    reports.append(await _sync_item_uoms(client, session, dry_run))
                    job["progress"]["item_uoms"] = reports[-1].model_dump()
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
    valid = {"customers", "items", "cross_ref", "ship_to", "item_uoms"}
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
