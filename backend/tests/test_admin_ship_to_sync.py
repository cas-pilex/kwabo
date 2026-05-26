"""Tests for the admin PLX_ShipToAddress sync path (nav2018 / OData V4)."""
from __future__ import annotations

import httpx
import pytest
from sqlmodel import select

from kwabo.api.admin import _ship_to_to_record, _sync_ship_to
from kwabo.db.models import KlantenkaartShipTo
from kwabo.integrations.navision_nav2018 import Nav2018ODataClient


# --- helpers ---


def _make_nav_client(rows: list[dict]) -> Nav2018ODataClient:
    """Build a Nav2018ODataClient whose HTTP layer is faked to always reply
    with `rows` for the PLX_ShipToAddress collection request.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": rows})

    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return Nav2018ODataClient(
        base_url="https://nav.test/ODataV4",
        company="Test Co",
        username="u",
        password="p",
        verify_ssl=False,
        http_client=http,
    )


# --- _ship_to_to_record (pure mapping) ---


def test_record_mapping_happy_path():
    row = {
        "Customer_No": "50000",
        "Code": "STUTTGART",
        "Name": "Lager Stuttgart",
        "Address": "Industriestrasse 7",
        "Post_Code": "34134",
        "City": "Stuttgart",
        "Country_Region_Code": "DE",
    }
    obj = _ship_to_to_record(row, None)
    assert obj is not None
    assert obj.klant_nr == "50000"
    assert obj.ship_to_code == "STUTTGART"
    assert obj.naam == "Lager Stuttgart"
    assert obj.straat == "Industriestrasse 7"
    assert obj.postcode == "34134"
    assert obj.plaats == "Stuttgart"
    assert obj.land == "DE"
    assert obj.is_default is False


def test_record_mapping_accepts_alternative_field_names():
    """PLX_ShipToAddress field names are not formally documented; accept the
    common alternatives so a NAV-side rename doesn't silently drop sync rows."""
    row = {
        "CustomerNo": "50000",
        "Ship_to_Code": "MAIN",
        "Name_2": "Hoofdvestiging",
        "Address_Line_1": "Hoofdstraat 1",
        "PostCode": "1000 AA",
        "City": "Amsterdam",
        "Country_Code": "NL",
    }
    obj = _ship_to_to_record(row, None)
    assert obj is not None
    assert obj.klant_nr == "50000"
    assert obj.ship_to_code == "MAIN"
    assert obj.naam == "Hoofdvestiging"
    assert obj.straat == "Hoofdstraat 1"
    assert obj.postcode == "1000 AA"
    assert obj.land == "NL"


def test_record_mapping_returns_none_without_klant_or_code():
    assert _ship_to_to_record({"Code": "X"}, None) is None
    assert _ship_to_to_record({"Customer_No": "50000"}, None) is None
    assert _ship_to_to_record({}, None) is None


def test_record_mapping_updates_existing_row():
    existing = KlantenkaartShipTo(
        klant_nr="50000",
        ship_to_code="STUT",
        naam="stale",
        straat="stale",
        postcode="00000",
        plaats="stale",
        land="??",
        is_default=True,
    )
    row = {
        "Customer_No": "50000",
        "Code": "STUT",
        "Name": "Frisch",
        "Address": "Neue 1",
        "Post_Code": "34134",
        "City": "Stuttgart",
        "Country_Region_Code": "DE",
    }
    obj = _ship_to_to_record(row, existing)
    assert obj is existing  # in-place update preserves the row identity
    assert obj.naam == "Frisch"
    assert obj.straat == "Neue 1"
    assert obj.postcode == "34134"
    # is_default is not exposed by PLX so we leave the prior value alone.
    assert obj.is_default is True


# --- _sync_ship_to (DB + HTTP) ---


@pytest.mark.asyncio
async def test_sync_writes_new_rows(session):
    rows = [
        {
            "Customer_No": "50000",
            "Code": "STUT",
            "Name": "Stuttgart",
            "Address": "Industriestrasse 7",
            "Post_Code": "34134",
            "City": "Stuttgart",
            "Country_Region_Code": "DE",
        },
        {
            "Customer_No": "50001",
            "Code": "BERLIN",
            "Name": "Berlin",
            "Address": "Hauptstr 1",
            "Post_Code": "10115",
            "City": "Berlin",
            "Country_Region_Code": "DE",
        },
    ]
    client = _make_nav_client(rows)
    report = await _sync_ship_to(client, session, dry_run=False)
    assert report.fetched == 2
    assert report.upserted == 2
    assert report.skipped == 0

    saved = session.exec(select(KlantenkaartShipTo)).all()
    assert {(r.klant_nr, r.ship_to_code) for r in saved} == {
        ("50000", "STUT"),
        ("50001", "BERLIN"),
    }


@pytest.mark.asyncio
async def test_sync_skips_rows_without_klant_or_code(session):
    rows = [
        {"Code": "X"},               # missing klant_nr
        {"Customer_No": "50000"},    # missing code
        {
            "Customer_No": "50000", "Code": "STUT",
            "Name": "x", "Address": "x", "Post_Code": "1",
            "City": "x", "Country_Region_Code": "NL",
        },
    ]
    client = _make_nav_client(rows)
    report = await _sync_ship_to(client, session, dry_run=False)
    assert report.fetched == 3
    assert report.upserted == 1
    assert report.skipped == 2
    assert report.skipped_reasons["no_klant_nr"] == 1
    assert report.skipped_reasons["no_code"] == 1


@pytest.mark.asyncio
async def test_sync_is_idempotent_across_double_run(session):
    row = {
        "Customer_No": "50000", "Code": "STUT",
        "Name": "Stuttgart", "Address": "Strasse 1",
        "Post_Code": "34134", "City": "Stuttgart",
        "Country_Region_Code": "DE",
    }
    client1 = _make_nav_client([row])
    await _sync_ship_to(client1, session, dry_run=False)
    client2 = _make_nav_client([row])
    await _sync_ship_to(client2, session, dry_run=False)
    saved = session.exec(select(KlantenkaartShipTo)).all()
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_dry_run_does_not_write(session):
    client = _make_nav_client(
        [{
            "Customer_No": "50000", "Code": "STUT",
            "Name": "x", "Address": "x", "Post_Code": "1",
            "City": "x", "Country_Region_Code": "NL",
        }]
    )
    report = await _sync_ship_to(client, session, dry_run=True)
    assert report.upserted == 1  # counts what WOULD be upserted
    saved = session.exec(select(KlantenkaartShipTo)).all()
    assert saved == []
