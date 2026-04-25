"""Tests for scripts/sync_navision_masters.py.

Hermetic — every NAV HTTP call is intercepted by an `httpx.MockTransport`
that fakes a tiny in-memory NAV OData v2 server. No network access ever
happens.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlmodel import select

from kwabo.db.models import (
    ArtikelEenheid,
    ArtikelKruisverwijzing,
    Artikelkaart,
    Klantenkaart,
    KlantenkaartShipTo,
)
from kwabo.integrations.navision_real import RealNavisionClient

# --- Load the script as a module ---------------------------------------------
# It lives in backend/scripts/ which is not on the Python path, so we import
# it by file path. This way the tests can call its inner functions directly.
SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "sync_navision_masters.py"
)
_spec = importlib.util.spec_from_file_location(
    "sync_navision_masters", SCRIPT_PATH
)
sync_mod = importlib.util.module_from_spec(_spec)
sys.modules["sync_navision_masters"] = sync_mod
_spec.loader.exec_module(sync_mod)  # type: ignore[union-attr]


# --- Fake NAV server ----------------------------------------------------------


class FakeNavServer:
    """Pretends to be NAV OData v2.

    Routes the script needs:
      GET /companies({cid})/customers                    [+ optional $filter]
      GET /companies({cid})/customers({id})/shipToAddresses
      GET /companies({cid})/items                        [+ optional $filter]
      GET /companies({cid})/items({id})/itemUnitsOfMeasure
      GET /companies({cid})/itemReferences               [+ optional $filter]

    `customers` / `items` support a `$filter=lastModifiedDateTime gt X`
    clause — used to verify delta mode is wired correctly.
    """

    def __init__(
        self,
        customers: list[dict],
        ship_to_by_customer_id: dict[str, list[dict]],
        items: list[dict],
        uoms_by_item_id: dict[str, list[dict]],
        item_references: list[dict],
    ) -> None:
        self.customers = customers
        self.ship_to_by_customer_id = ship_to_by_customer_id
        self.items = items
        self.uoms_by_item_id = uoms_by_item_id
        self.item_references = item_references
        self.calls: list[str] = []  # full request URLs, for assertions

    def _filter_by_modified(
        self, rows: list[dict], filter_str: str | None
    ) -> list[dict]:
        if not filter_str:
            return rows
        # "lastModifiedDateTime gt 2024-01-01T00:00:00Z"
        marker = "lastModifiedDateTime gt "
        idx = filter_str.find(marker)
        if idx < 0:
            return rows
        cutoff = filter_str[idx + len(marker):].strip().strip("'\"")
        # Strip trailing OData operators that we don't model.
        for sep in (" and ", " or "):
            if sep in cutoff:
                cutoff = cutoff.split(sep, 1)[0].strip().strip("'\"")
        return [r for r in rows if (r.get("lastModifiedDateTime") or "") > cutoff]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        url = urlparse(str(request.url))
        path = url.path
        qs = parse_qs(url.query)
        filt = qs.get("$filter", [None])[0]

        # /companies({cid})/customers   or   .../customers({id})/shipToAddresses
        if "/customers" in path and "shipToAddresses" in path:
            # extract id between customers( ... )
            cid = path.split("customers(", 1)[1].split(")", 1)[0]
            return _odata(self.ship_to_by_customer_id.get(cid, []))
        if path.endswith("/customers"):
            return _odata(self._filter_by_modified(self.customers, filt))

        # items
        if "/items" in path and "itemUnitsOfMeasure" in path:
            iid = path.split("items(", 1)[1].split(")", 1)[0]
            return _odata(self.uoms_by_item_id.get(iid, []))
        if path.endswith("/items"):
            return _odata(self._filter_by_modified(self.items, filt))

        # itemReferences
        if path.endswith("/itemReferences"):
            return _odata(self._filter_by_modified(self.item_references, filt))

        return httpx.Response(404, json={"error": f"unmocked {path}"})


def _odata(rows: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"value": rows, "@odata.context": "fake"},
    )


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
def fake_server() -> FakeNavServer:
    customers = [
        {
            "id": "cust-a-id",
            "number": "10001",
            "displayName": "Ferney Diabolo B.V.",
            "email": "purchaseorders@ferney.nl",
            "phoneNumber": "+31 10 123 4567",
            "creditLimit": 50000.0,
            "paymentTermsCode": "30D",
            "languageCode": "NL",
            "mixprijzen": False,
            "lastModifiedDateTime": "2024-06-01T10:00:00Z",
        },
        {
            "id": "cust-b-id",
            "number": "10002",
            "displayName": "TABS / PontMeyer",
            "email": "supplychain@tabsholland.nl",
            "phoneNumber": None,
            "creditLimit": 25000.0,
            "paymentTermsCode": "14D",
            "languageCode": "NL",
            "mixprijzen": True,
            "lastModifiedDateTime": "2024-07-15T08:30:00Z",
        },
    ]
    ship_to_by_customer_id = {
        "cust-a-id": [
            {
                "code": "UTR",
                "name": "Vestiging Utrecht",
                "addressLine1": "Industrieweg 1",
                "postCode": "3500 AA",
                "city": "Utrecht",
                "country": "NL",
                "isDefault": True,
                "lastModifiedDateTime": "2024-06-01T10:00:00Z",
            },
            {
                "code": "AMS",
                "name": "Vestiging Amsterdam",
                "addressLine1": "Havenkade 22",
                "postCode": "1000 AB",
                "city": "Amsterdam",
                "country": "NL",
                "isDefault": False,
                "lastModifiedDateTime": "2024-06-01T10:00:00Z",
            },
        ],
        "cust-b-id": [
            {
                "code": "MAIN",
                "name": "TABS Centraal Magazijn",
                "addressLine1": "Logistieklaan 5",
                "postCode": "5000 ZZ",
                "city": "Tilburg",
                "country": "NL",
                "isDefault": True,
                "lastModifiedDateTime": "2024-07-15T08:30:00Z",
            },
        ],
    }
    items = [
        {
            "id": "item-1-id",
            "number": "1515155",
            "displayName": "Ferney stucloper 120cm",
            "baseUnitOfMeasureCode": "ROL",
            "mixprijzen": True,
            "palletable": True,
            "lastModifiedDateTime": "2024-06-10T09:00:00Z",
        },
        {
            "id": "item-2-id",
            "number": "228321",
            "displayName": "TABS hoeknaald",
            "baseUnitOfMeasureCode": "STUK",
            "mixprijzen": False,
            "palletable": None,
            "lastModifiedDateTime": "2024-07-20T11:00:00Z",
        },
    ]
    uoms_by_item_id = {
        "item-1-id": [
            {"code": "ROL", "qtyPerUnitOfMeasure": 1.0},
            {"code": "PAL", "qtyPerUnitOfMeasure": 24.0},
            {"code": "MIX-DOOS", "qtyPerUnitOfMeasure": 12.0},
        ],
        "item-2-id": [
            {"code": "STUK", "qtyPerUnitOfMeasure": 1.0},
        ],
    }
    item_references = [
        {
            "customerNumber": "10001",
            "referenceNumber": "23532",
            "itemNumber": "1515155",
            "unitOfMeasureCode": "ROL",
            "referenceType": "customer",
            "lastModifiedDateTime": "2024-06-10T09:00:00Z",
        },
        {
            "customerNumber": "10002",
            "referenceNumber": "K700100007",
            "itemNumber": "228321",
            "unitOfMeasureCode": "STUK",
            "referenceType": "customer",
            "lastModifiedDateTime": "2024-07-20T11:00:00Z",
        },
    ]
    return FakeNavServer(
        customers=customers,
        ship_to_by_customer_id=ship_to_by_customer_id,
        items=items,
        uoms_by_item_id=uoms_by_item_id,
        item_references=item_references,
    )


@pytest.fixture
def nav_client(fake_server: FakeNavServer) -> RealNavisionClient:
    transport = httpx.MockTransport(fake_server.handle)
    http = httpx.AsyncClient(transport=transport)
    return RealNavisionClient(
        base_url="https://nav.test/api/v2.0",
        company_id="test-company",
        auth_mode="basic",
        username="u",
        password="p",
        verify_ssl=False,
        http_client=http,
    )


def _make_syncer(
    nav_client: RealNavisionClient,
    session,
    *,
    full: bool = True,
    dry_run: bool = False,
    state: dict[str, str] | None = None,
) -> Any:
    return sync_mod.NavMasterSync(
        client=nav_client,
        session=session,
        state=dict(state or {}),
        full=full,
        dry_run=dry_run,
    )


# --- Tests --------------------------------------------------------------------


async def test_customers_sync_inserts_new_and_toggles_mixprijzen(
    session, nav_client, fake_server
):
    # Pre-existing klant 10001 from seed has mixprijzen=False. NAV says False
    # too, but klant 10002 (also seeded) — NAV says True. After sync the seeded
    # rows must reflect the NAV-side mixprijzen flag.
    pre_10001 = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10001")
    ).first()
    pre_10002 = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10002")
    ).first()
    assert pre_10001 is not None
    assert pre_10002 is not None
    # Force a non-NAV starting value for 10002 to verify we flip it.
    pre_10002.mixprijzen = False
    session.add(pre_10002)
    session.commit()
    pre_10002_id = pre_10002.id

    syncer = _make_syncer(nav_client, session, full=True)
    n = await syncer.sync_customers()
    assert n == 2

    post_10001 = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10001")
    ).first()
    post_10002 = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10002")
    ).first()
    assert post_10001 is not None
    assert post_10002 is not None
    # Same row — no duplicate insert.
    assert post_10002.id == pre_10002_id
    # NAV-authoritative mixprijzen propagated.
    assert post_10001.mixprijzen is False
    assert post_10002.mixprijzen is True
    # Pre-existing user data is preserved (email/email_bestelling not clobbered).
    assert post_10001.email == "purchaseorders@ferney.nl"


async def test_customers_sync_inserts_new_klant(session, nav_client, fake_server):
    # Add a customer NAV knows about that the seed doesn't have.
    fake_server.customers.append(
        {
            "id": "cust-99-id",
            "number": "99999",
            "displayName": "Brand New Klant N.V.",
            "email": "new@klant.nl",
            "languageCode": "NL",
            "mixprijzen": False,
            "lastModifiedDateTime": "2024-08-01T10:00:00Z",
        }
    )
    syncer = _make_syncer(nav_client, session, full=True)
    await syncer.sync_customers()
    new = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "99999")
    ).first()
    assert new is not None
    assert new.naam == "Brand New Klant N.V."
    assert new.email == "new@klant.nl"


async def test_ship_to_sync_writes_multiple_per_customer(
    session, nav_client, fake_server
):
    syncer = _make_syncer(nav_client, session, full=True)
    n = await syncer.sync_ship_to()
    assert n == 3  # 2 for cust-a, 1 for cust-b

    rows_a = session.exec(
        select(KlantenkaartShipTo).where(KlantenkaartShipTo.klant_nr == "10001")
    ).all()
    rows_b = session.exec(
        select(KlantenkaartShipTo).where(KlantenkaartShipTo.klant_nr == "10002")
    ).all()
    assert {r.ship_to_code for r in rows_a} == {"UTR", "AMS"}
    assert {r.ship_to_code for r in rows_b} == {"MAIN"}

    utr = next(r for r in rows_a if r.ship_to_code == "UTR")
    assert utr.naam == "Vestiging Utrecht"
    assert utr.straat == "Industrieweg 1"
    assert utr.postcode == "3500 AA"
    assert utr.plaats == "Utrecht"
    assert utr.land == "NL"
    assert utr.is_default is True


async def test_items_and_uoms_sync(session, nav_client):
    syncer = _make_syncer(nav_client, session, full=True)
    n_items = await syncer.sync_items()
    assert n_items == 2

    karten = session.exec(select(Artikelkaart)).all()
    by_nr = {a.kwabo_artikelnr: a for a in karten}
    assert "1515155" in by_nr
    assert by_nr["1515155"].naam == "Ferney stucloper 120cm"
    assert by_nr["1515155"].basis_eenheid == "ROL"
    assert by_nr["1515155"].mixprijzen is True
    assert by_nr["1515155"].palletable is True
    assert by_nr["228321"].mixprijzen is False
    # NAV emitted palletable=None — _nav_bool maps that to False (same
    # missing-/null-value behaviour as mixprijzen).
    assert by_nr["228321"].palletable is False

    n_uoms = await syncer.sync_item_uoms()
    assert n_uoms == 4  # 3 + 1
    eenheden = session.exec(
        select(ArtikelEenheid).where(ArtikelEenheid.kwabo_artikelnr == "1515155")
    ).all()
    by_code = {e.eenheid_code: e for e in eenheden}
    assert set(by_code) == {"ROL", "PAL", "MIX-DOOS"}
    assert by_code["MIX-DOOS"].is_mix_uom is True
    assert by_code["MIX-DOOS"].qty_per_base == 12.0
    assert by_code["ROL"].is_mix_uom is False
    assert by_code["PAL"].is_mix_uom is False


async def test_items_palletable_string_false_becomes_python_false(
    session, nav_client, fake_server
):
    """Regression: NAV emits booleans as the strings "true"/"false". A naive
    bool() cast made "false" truthy. We must funnel palletable through
    _nav_bool just like mixprijzen, so the string "false" lands as Python
    False (not True) in the artikelkaarten mirror."""
    fake_server.items[:] = [
        {
            "id": "item-str-false",
            "number": "STR-FALSE",
            "displayName": "String-false palletable",
            "baseUnitOfMeasureCode": "STUK",
            "mixprijzen": "false",
            "palletable": "false",
            "lastModifiedDateTime": "2024-08-01T00:00:00Z",
        },
        {
            "id": "item-str-true",
            "number": "STR-TRUE",
            "displayName": "String-true palletable",
            "baseUnitOfMeasureCode": "STUK",
            "mixprijzen": "true",
            "palletable": "true",
            "lastModifiedDateTime": "2024-08-01T00:00:00Z",
        },
    ]
    syncer = _make_syncer(nav_client, session, full=True)
    n = await syncer.sync_items()
    assert n == 2

    by_nr = {
        a.kwabo_artikelnr: a for a in session.exec(select(Artikelkaart)).all()
    }
    # The bug: bool("false") is True. With _nav_bool we land on False.
    assert by_nr["STR-FALSE"].palletable is False
    assert by_nr["STR-FALSE"].mixprijzen is False
    # Sanity-check the truthy direction also still works.
    assert by_nr["STR-TRUE"].palletable is True
    assert by_nr["STR-TRUE"].mixprijzen is True


async def test_cross_ref_sync(session, nav_client):
    syncer = _make_syncer(nav_client, session, full=True)
    n = await syncer.sync_cross_ref()
    assert n == 2

    rows = session.exec(select(ArtikelKruisverwijzing)).all()
    by_key = {(r.klant_nr, r.klant_artikelnr): r for r in rows}
    assert ("10001", "23532") in by_key
    a = by_key[("10001", "23532")]
    assert a.kwabo_artikelnr == "1515155"
    assert a.eenheid_klant == "ROL"
    assert a.bron == "customer"
    b = by_key[("10002", "K700100007")]
    assert b.kwabo_artikelnr == "228321"


async def test_delta_mode_only_fetches_modified_records(
    session, nav_client, fake_server
):
    # Cursor between the two customers' last-modified timestamps.
    state = {
        "customers": "2024-07-01T00:00:00Z",
        "items": "2024-07-01T00:00:00Z",
        "cross_ref": "2024-07-01T00:00:00Z",
    }
    syncer = _make_syncer(nav_client, session, full=False, state=state)

    n_cust = await syncer.sync_customers()
    # Only 10002 (2024-07-15) is later than the cutoff — 10001 (2024-06-01) is not.
    assert n_cust == 1
    # The mocked endpoint received the OData $filter clause (httpx may encode
    # spaces as either '+' or '%20' depending on the URL path component).
    assert any(
        "lastModifiedDateTime+gt+" in c
        or "lastModifiedDateTime%20gt%20" in c
        or "lastModifiedDateTime gt " in c
        for c in fake_server.calls
    )

    n_items = await syncer.sync_items()
    assert n_items == 1  # only item-2 (2024-07-20)

    n_refs = await syncer.sync_cross_ref()
    assert n_refs == 1  # only the 2024-07-20 reference

    # Cursor must advance to the newest timestamp we observed in this run.
    assert syncer._observed["customers"] == "2024-07-15T08:30:00Z"
    assert syncer._observed["items"] == "2024-07-20T11:00:00Z"


async def test_full_mode_fetches_everything_ignoring_state(
    session, nav_client, fake_server
):
    state = {"customers": "2099-01-01T00:00:00Z"}  # would exclude all in delta
    syncer = _make_syncer(nav_client, session, full=True, state=state)
    n = await syncer.sync_customers()
    assert n == 2
    # No $filter must have been sent — full mode bypasses state.
    cust_calls = [c for c in fake_server.calls if "/customers?" in c or c.endswith("/customers")]
    assert cust_calls
    for c in cust_calls:
        assert "lastModifiedDateTime" not in c


async def test_dry_run_makes_http_calls_but_no_db_writes(
    session, nav_client, fake_server
):
    syncer = _make_syncer(nav_client, session, full=True, dry_run=True)

    n_cust = await syncer.sync_customers()
    n_ship = await syncer.sync_ship_to()
    n_items = await syncer.sync_items()
    n_uoms = await syncer.sync_item_uoms()
    n_refs = await syncer.sync_cross_ref()

    # All counts non-zero — confirms HTTP calls happened.
    assert n_cust == 2
    assert n_ship == 3
    assert n_items == 2
    assert n_uoms == 4
    assert n_refs == 2
    # Each domain must have hit the wire.
    assert any("/customers" in c for c in fake_server.calls)
    assert any("/items" in c for c in fake_server.calls)
    assert any("/itemReferences" in c for c in fake_server.calls)
    assert any("shipToAddresses" in c for c in fake_server.calls)
    assert any("itemUnitsOfMeasure" in c for c in fake_server.calls)

    # But: no NAV-mirror table got rows beyond the seed's own data.
    assert session.exec(select(Artikelkaart)).all() == []
    assert session.exec(select(ArtikelEenheid)).all() == []
    assert session.exec(select(KlantenkaartShipTo)).all() == []
    assert session.exec(select(ArtikelKruisverwijzing)).all() == []


async def test_idempotent_double_run(session, nav_client):
    # Run twice in succession — second run must not duplicate rows.
    syncer1 = _make_syncer(nav_client, session, full=True)
    await syncer1.sync_items()
    await syncer1.sync_item_uoms()
    await syncer1.sync_ship_to()
    await syncer1.sync_cross_ref()

    n_items_1 = len(session.exec(select(Artikelkaart)).all())
    n_uoms_1 = len(session.exec(select(ArtikelEenheid)).all())
    n_ship_1 = len(session.exec(select(KlantenkaartShipTo)).all())
    n_refs_1 = len(session.exec(select(ArtikelKruisverwijzing)).all())

    syncer2 = _make_syncer(nav_client, session, full=True)
    await syncer2.sync_items()
    await syncer2.sync_item_uoms()
    await syncer2.sync_ship_to()
    await syncer2.sync_cross_ref()

    assert len(session.exec(select(Artikelkaart)).all()) == n_items_1
    assert len(session.exec(select(ArtikelEenheid)).all()) == n_uoms_1
    assert len(session.exec(select(KlantenkaartShipTo)).all()) == n_ship_1
    assert len(session.exec(select(ArtikelKruisverwijzing)).all()) == n_refs_1


# --- CLI / main() shape -------------------------------------------------------


def test_main_exits_1_when_navision_mode_not_real(monkeypatch, capsys):
    # conftest sets NAVISION_MODE=mock — but settings has already been read.
    # Patch the cached settings then ensure the script sees the patched value.
    import kwabo.config as cfg

    monkeypatch.setattr(cfg.settings, "navision_mode", "mock")
    sync_mod.settings = cfg.settings  # ensure script sees the patched value

    import asyncio as _asyncio

    rc = _asyncio.run(sync_mod.main(argv=["--customers"]))
    assert rc == 1


def test_selected_domains_default_is_all():
    args = sync_mod.parse_args([])
    assert sync_mod.selected_domains(args) == set(sync_mod.DOMAINS)


def test_selected_domains_specific_flags():
    args = sync_mod.parse_args(["--customers", "--items"])
    assert sync_mod.selected_domains(args) == {"customers", "items"}


def test_state_roundtrip(tmp_path):
    p = tmp_path / "last_sync.json"
    sync_mod.save_state({"customers": "2024-01-02T00:00:00Z"}, p)
    assert sync_mod.load_state(p) == {"customers": "2024-01-02T00:00:00Z"}


def test_load_state_missing_is_empty(tmp_path):
    assert sync_mod.load_state(tmp_path / "nope.json") == {}


def test_is_mix_uom_pattern_match():
    assert sync_mod._is_mix_uom({"code": "MIX-DOOS"}) is True
    assert sync_mod._is_mix_uom({"code": "MENGSEL"}) is True
    assert sync_mod._is_mix_uom({"code": "ROL"}) is False
    # explicit flag wins even if code doesn't match
    assert sync_mod._is_mix_uom({"code": "DOOS", "isMixUom": True}) is True
    # bool-ish strings
    assert sync_mod._is_mix_uom({"code": "DOOS", "kwaboIsMix": "true"}) is True
    assert sync_mod._is_mix_uom({"code": "DOOS", "kwaboIsMix": "false"}) is False
