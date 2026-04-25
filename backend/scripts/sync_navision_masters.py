"""Sync NAV master data into the local SQLite mirror tables.

Pulls customers, ship-to addresses, items, item units-of-measure and item
references from NAV via OData v2 and upserts them through the repo layer
defined in `kwabo.db.repository`.

Mirror tables populated:
  customers                       -> klantenkaarten (preserves user fields,
                                     overwrites mixprijzen from NAV)
  customers/shipToAddresses (222) -> klantenkaart_ship_to
  items                           -> artikelkaarten (incl. mixprijzen)
  items/itemUnitsOfMeasure (5703) -> artikel_eenheden
  itemReferences  (5717 / 5728)   -> artikel_kruisverwijzing

Usage:
  python scripts/sync_navision_masters.py            # delta, all domains
  python scripts/sync_navision_masters.py --full     # full reload
  python scripts/sync_navision_masters.py --customers --items
  python scripts/sync_navision_masters.py --dry-run  # logs counts, no DB writes

Mode:
  Default = --delta (incremental on lastModifiedDateTime).
  Last-sync state is persisted at  data/last_sync.json  keyed by domain.

Requires NAVISION_MODE=real — exits 1 otherwise (we never silently fall back
to the mock from a sync job).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session, select  # noqa: E402

from kwabo.config import settings  # noqa: E402
from kwabo.db.models import (  # noqa: E402
    ArtikelEenheid,
    ArtikelKruisverwijzing,
    Artikelkaart,
    Klantenkaart,
    KlantenkaartShipTo,
)
from kwabo.db.repository import (  # noqa: E402
    ArtikelkaartRepo,
    KlantRepo,
    KruisverwijzingRepo,
    ShipToRepo,
)
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.integrations.navision_real import RealNavisionClient  # noqa: E402
from kwabo.utils import utcnow  # noqa: E402
from kwabo.utils.logging import log, setup_logging  # noqa: E402


# Default state file. Tests override via build_syncer(state_path=...).
STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "last_sync.json"

DOMAINS = ("customers", "ship_to", "items", "item_uoms", "cross_ref")

# Heuristic: a UOM whose code matches this is treated as a "mix" UOM. Override
# is also possible if NAV exposes an explicit custom flag (`isMixUom`,
# `kwaboIsMix`). Falls back to False — never True for unknown UOMs.
_MIX_UOM_PATTERN = re.compile(r"\bMIX\b|MENG", re.IGNORECASE)


# ---------- state file ----------


def load_state(path: Path = STATE_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("sync_state_unreadable", path=str(path))
        return {}


def save_state(state: dict[str, str], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


# ---------- field helpers ----------


def _nav_bool(record: dict, *keys: str) -> bool:
    """NAV may expose flags as bool, "true"/"false", "Yes"/"No", 0/1.
    Returns False if no key is present or value is falsy."""
    for k in keys:
        if k in record:
            v = record[k]
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                return v.strip().lower() in ("true", "yes", "y", "1", "ja")
    return False


def _is_mix_uom(record: dict) -> bool:
    """Heuristic per task T2 spec: True if NAV exposes an explicit mix flag,
    or if the unit_of_measure code matches the MIX pattern. Else False."""
    if _nav_bool(record, "isMixUom", "kwaboIsMix", "mixUom"):
        return True
    code = (record.get("code") or record.get("unitOfMeasureCode") or "").strip()
    if code and _MIX_UOM_PATTERN.search(code):
        return True
    return False


def _delta_filter(state_value: Optional[str]) -> Optional[dict]:
    """Build an OData $filter on lastModifiedDateTime, or None for full sync."""
    if not state_value:
        return None
    return {"$filter": f"lastModifiedDateTime gt {state_value}"}


# ---------- domain syncs ----------


class NavMasterSync:
    """Encapsulates one sync run. Bound to a NAV client + DB session."""

    def __init__(
        self,
        client: RealNavisionClient,
        session: Session,
        state: dict[str, str],
        full: bool,
        dry_run: bool,
    ) -> None:
        self.client = client
        self.session = session
        self.state = state
        self.full = full
        self.dry_run = dry_run
        # Highest lastModifiedDateTime observed in this run, per domain.
        self._observed: dict[str, str] = {}

    # ----- helpers -----

    def _params_for(self, domain: str) -> Optional[dict]:
        if self.full:
            return None
        return _delta_filter(self.state.get(domain))

    def _track_modified(self, domain: str, record: dict) -> None:
        ts = record.get("lastModifiedDateTime")
        if not ts:
            return
        prev = self._observed.get(domain)
        if prev is None or ts > prev:
            self._observed[domain] = ts

    def _commit_state(self, domain: str) -> None:
        """Move state cursor forward only on success and only if we saw any
        records this run. Idempotent: re-running is a no-op."""
        observed = self._observed.get(domain)
        if observed:
            self.state[domain] = observed

    # ----- customers -----

    async def sync_customers(self) -> int:
        records = await self.client.get_collection(
            "customers", self._params_for("customers")
        )
        log.info("nav_sync_fetched", domain="customers", count=len(records))
        if self.dry_run:
            for r in records:
                self._track_modified("customers", r)
            return len(records)

        repo = KlantRepo(self.session)
        for r in records:
            nr = r.get("number")
            if not nr:
                continue
            self._track_modified("customers", r)
            existing = repo.by_nav_nr(nr)
            mixprijzen = _nav_bool(r, "mixprijzen", "kwaboMixprijzen", "isMixCustomer")
            if existing is not None:
                # Preserve existing user-edited fields. Only overwrite the
                # NAV-authoritative mixprijzen flag and refresh updated_at.
                existing.mixprijzen = mixprijzen
                existing.updated_at = utcnow()
                # Keep core identity fields fresh too — naam can change in NAV.
                if r.get("displayName"):
                    existing.naam = r["displayName"]
                self.session.add(existing)
            else:
                self.session.add(
                    Klantenkaart(
                        nav_klantnr=nr,
                        naam=r.get("displayName") or nr,
                        email=(r.get("email") or None),
                        telefoon=r.get("phoneNumber"),
                        taal=(r.get("languageCode") or "NL"),
                        kredietlimiet=r.get("creditLimit"),
                        betalingsconditie=r.get("paymentTermsCode"),
                        mixprijzen=mixprijzen,
                    )
                )
        # Direct session.add() for both insert and update paths above — no repo
        # involvement, so this is the only commit and is required.
        self.session.commit()
        self._commit_state("customers")
        return len(records)

    # ----- ship-to -----

    async def sync_ship_to(self) -> int:
        """Per-customer ship-to fetch. NAV exposes shipToAddresses on the
        customer entity (table 222). We sync ship-tos for *all* customers we
        currently know about — delta-mode skips customers that NAV says have
        not changed via the parent customer cursor.
        """
        customer_filter = self._params_for("ship_to")
        # Get the customer list to iterate over. Pull just (id, number) — we
        # need NAV's GUID id for the navigation, plus the klant_nr for FK.
        customers = await self.client.get_collection(
            "customers",
            customer_filter,
        )
        log.info("nav_sync_fetched", domain="ship_to_parents", count=len(customers))

        if self.dry_run:
            total = 0
            for c in customers:
                cid = c.get("id") or c.get("number")
                if not cid:
                    continue
                addrs = await self.client.get_collection(
                    f"customers({cid})/shipToAddresses"
                )
                total += len(addrs)
                for a in addrs:
                    self._track_modified("ship_to", a)
            return total

        repo = ShipToRepo(self.session)
        total = 0
        for c in customers:
            klant_nr = c.get("number")
            cid = c.get("id") or klant_nr
            if not klant_nr or not cid:
                continue
            addrs = await self.client.get_collection(
                f"customers({cid})/shipToAddresses"
            )
            for a in addrs:
                self._track_modified("ship_to", a)
                code = a.get("code") or a.get("shipToCode")
                if not code:
                    continue
                repo.upsert(
                    KlantenkaartShipTo(
                        klant_nr=klant_nr,
                        ship_to_code=code,
                        naam=a.get("name") or "",
                        straat=a.get("addressLine1") or a.get("address") or "",
                        postcode=a.get("postCode") or a.get("postalCode") or "",
                        plaats=a.get("city") or "",
                        land=a.get("country") or "NL",
                        is_default=_nav_bool(a, "isDefault", "default"),
                    )
                )
                total += 1
        # ShipToRepo.upsert() commits internally per row; this trailing commit
        # is a no-op safety net so all five sync_* methods share the same
        # explicit-commit shape.
        self.session.commit()
        self._commit_state("ship_to")
        return total

    # ----- items -----

    async def sync_items(self) -> int:
        records = await self.client.get_collection(
            "items", self._params_for("items")
        )
        log.info("nav_sync_fetched", domain="items", count=len(records))

        if self.dry_run:
            for r in records:
                self._track_modified("items", r)
            return len(records)

        repo = ArtikelkaartRepo(self.session)
        for r in records:
            nr = r.get("number")
            if not nr:
                continue
            self._track_modified("items", r)
            repo.upsert(
                Artikelkaart(
                    kwabo_artikelnr=nr,
                    naam=r.get("displayName") or nr,
                    basis_eenheid=r.get("baseUnitOfMeasureCode") or "STUK",
                    mixprijzen=_nav_bool(
                        r, "mixprijzen", "kwaboMixprijzen", "isMixItem"
                    ),
                    # NAV returns "true"/"false" as strings — both are truthy
                    # in Python str-cast land. Route through _nav_bool for
                    # the same handling as mixprijzen.
                    palletable=_nav_bool(r, "palletable", "kwaboPalletable"),
                )
            )
        # ArtikelkaartRepo.upsert() commits internally per row; this trailing
        # commit keeps the same explicit-commit shape as the other domains.
        self.session.commit()
        self._commit_state("items")
        return len(records)

    # ----- item UOMs -----

    async def sync_item_uoms(self) -> int:
        """Per-item itemUnitsOfMeasure fetch (table 5703)."""
        item_filter = self._params_for("item_uoms")
        items = await self.client.get_collection("items", item_filter)
        log.info("nav_sync_fetched", domain="item_uoms_parents", count=len(items))

        if self.dry_run:
            total = 0
            for it in items:
                iid = it.get("id") or it.get("number")
                if not iid:
                    continue
                uoms = await self.client.get_collection(
                    f"items({iid})/itemUnitsOfMeasure"
                )
                total += len(uoms)
                for u in uoms:
                    self._track_modified("item_uoms", u)
            return total

        total = 0
        for it in items:
            artikelnr = it.get("number")
            iid = it.get("id") or artikelnr
            if not artikelnr or not iid:
                continue
            uoms = await self.client.get_collection(
                f"items({iid})/itemUnitsOfMeasure"
            )
            for u in uoms:
                self._track_modified("item_uoms", u)
                code = u.get("code") or u.get("unitOfMeasureCode")
                if not code:
                    continue
                qty = u.get("qtyPerUnitOfMeasure") or u.get("qtyPerBase") or 1.0
                # Composite-PK upsert via session.merge equivalent: get-or-replace.
                existing = self.session.get(ArtikelEenheid, (artikelnr, code))
                if existing is None:
                    self.session.add(
                        ArtikelEenheid(
                            kwabo_artikelnr=artikelnr,
                            eenheid_code=code,
                            qty_per_base=float(qty),
                            is_mix_uom=_is_mix_uom(u),
                        )
                    )
                else:
                    existing.qty_per_base = float(qty)
                    existing.is_mix_uom = _is_mix_uom(u)
                    self.session.add(existing)
                total += 1
        # Direct session.add() for both insert and update paths above — no repo
        # involvement, so this is the only commit and is required.
        self.session.commit()
        self._commit_state("item_uoms")
        return total

    # ----- item references -----

    async def sync_cross_ref(self) -> int:
        """itemReferences (NAV table 5717, page 5728). Each row maps a
        customer's article-nr to a Kwabo item-nr (and optionally a UOM)."""
        records = await self.client.get_collection(
            "itemReferences", self._params_for("cross_ref")
        )
        log.info("nav_sync_fetched", domain="cross_ref", count=len(records))

        if self.dry_run:
            for r in records:
                self._track_modified("cross_ref", r)
            return len(records)

        repo = KruisverwijzingRepo(self.session)
        total = 0
        for r in records:
            self._track_modified("cross_ref", r)
            klant_nr = (
                r.get("customerNumber")
                or r.get("accountNumber")
                or r.get("sourceNo")
            )
            klant_artikelnr = (
                r.get("referenceNumber")
                or r.get("crossReferenceNumber")
                or r.get("referenceNo")
            )
            kwabo_artikelnr = r.get("itemNumber") or r.get("itemNo")
            if not (klant_nr and klant_artikelnr and kwabo_artikelnr):
                continue
            repo.upsert(
                ArtikelKruisverwijzing(
                    klant_nr=klant_nr,
                    klant_artikelnr=klant_artikelnr,
                    kwabo_artikelnr=kwabo_artikelnr,
                    eenheid_klant=r.get("unitOfMeasureCode") or r.get("uomCode"),
                    bron=r.get("referenceType") or "customer",
                )
            )
            total += 1
        # KruisverwijzingRepo.upsert() commits internally per row; this trailing
        # commit keeps the same explicit-commit shape as the other domains.
        self.session.commit()
        self._commit_state("cross_ref")
        return total


# ---------- orchestration ----------


async def run_sync(
    client: RealNavisionClient,
    session: Session,
    state: dict[str, str],
    *,
    full: bool,
    dry_run: bool,
    domains: set[str],
    on_domain_done: Optional[Callable[[str], None]] = None,
) -> dict[str, int]:
    syncer = NavMasterSync(
        client=client, session=session, state=state, full=full, dry_run=dry_run
    )
    table: dict[str, Callable[[], Awaitable[int]]] = {
        "customers": syncer.sync_customers,
        "ship_to": syncer.sync_ship_to,
        "items": syncer.sync_items,
        "item_uoms": syncer.sync_item_uoms,
        "cross_ref": syncer.sync_cross_ref,
    }
    counts: dict[str, int] = {}
    for d in DOMAINS:
        if d not in domains:
            continue
        counts[d] = await table[d]()
        log.info("nav_sync_domain_done", domain=d, count=counts[d], dry_run=dry_run)
        if on_domain_done is not None:
            on_domain_done(d)
    return counts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sync NAV master data into the local SQLite mirror tables."
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="Full reload — ignore last-sync state")
    mode.add_argument("--delta", action="store_true", help="Incremental sync (default)")

    p.add_argument("--customers", action="store_true", help="Sync customers")
    p.add_argument("--ship-to", action="store_true", help="Sync ship-to addresses")
    p.add_argument("--items", action="store_true", help="Sync items")
    p.add_argument("--item-uoms", action="store_true", help="Sync item UOMs")
    p.add_argument("--cross-ref", action="store_true", help="Sync item references")

    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Make HTTP calls but log counts only — no DB writes, no state save",
    )
    return p.parse_args(argv)


def selected_domains(args: argparse.Namespace) -> set[str]:
    flags = {
        "customers": args.customers,
        "ship_to": args.ship_to,
        "items": args.items,
        "item_uoms": args.item_uoms,
        "cross_ref": args.cross_ref,
    }
    if not any(flags.values()):
        return set(DOMAINS)
    return {k for k, v in flags.items() if v}


async def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)

    if settings.navision_mode != "real":
        log.error(
            "nav_sync_wrong_mode",
            current=settings.navision_mode,
            required="real",
            hint="set NAVISION_MODE=real before running this script",
        )
        return 1

    full = bool(args.full)  # else --delta (default)
    dry_run = bool(args.dry_run)
    domains = selected_domains(args)

    log.info(
        "nav_sync_start",
        full=full,
        dry_run=dry_run,
        domains=sorted(domains),
        state_file=str(STATE_FILE),
    )

    init_db()
    state = load_state()

    # Persist per-domain cursor advances to disk as soon as each domain
    # finishes — so a later domain raising doesn't lose earlier progress.
    # In dry-run we skip disk writes entirely.
    def _persist(_domain: str) -> None:
        if dry_run:
            return
        save_state(state)

    client = RealNavisionClient()
    try:
        with Session(engine) as session:
            counts = await run_sync(
                client,
                session,
                state,
                full=full,
                dry_run=dry_run,
                domains=domains,
                on_domain_done=_persist,
            )
    finally:
        await client.aclose()

    if not dry_run:
        # last_sync_completed_at is purely informational; the per-domain
        # cursors are what gate the next delta query.
        state["_last_run_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

    log.info("nav_sync_done", counts=counts, dry_run=dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
