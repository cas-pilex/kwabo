"""sales_prices sync: PLX_SalesPrice row -> Verkoopprijs mapper + ingest."""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

import kwabo.api.admin as admin
from kwabo.api.admin import (
    _date_or_none,
    _ingest_sales_prices,
    _normalize_sales_type,
    _sales_price_to_record,
    _sync_sales_prices,
)
from kwabo.db.models import Verkoopprijs


def test_maps_basic_mix_row():
    rec = _sales_price_to_record(
        {
            "Item_No": "23545", "Sales_Type": "Customer", "Sales_Code": "60203",
            "Unit_of_Measure_Code": "M33PAL35", "Unit_Price": "592.5",
            "Minimum_Quantity": "0", "Starting_Date": "2026-01-01", "Ending_Date": "",
        }
    )
    assert rec is not None
    assert rec.kwabo_artikelnr == "23545"
    assert rec.sales_type == "Customer"
    assert rec.sales_code == "60203"
    assert rec.eenheid_code == "M33PAL35"
    assert rec.prijs == 592.5
    assert rec.is_mix is True
    assert rec.geldig_van == date(2026, 1, 1)
    assert rec.geldig_tot is None


def test_empty_uom_is_normal_price():
    rec = _sales_price_to_record(
        {"Item_No": "23545", "Sales_Type": "Customer", "Sales_Code": "60203",
         "Unit_of_Measure_Code": "", "Unit_Price": "18.40"}
    )
    assert rec.eenheid_code == ""
    assert rec.is_mix is False


def test_field_name_tolerance():
    rec = _sales_price_to_record(
        {"ItemNo": "X", "SalesType": "All_Customers", "UnitOfMeasureCode": "M1PAL30",
         "UnitPrice": "5"}
    )
    assert rec is not None
    assert rec.kwabo_artikelnr == "X"
    assert rec.sales_type == "All_Customers"
    assert rec.eenheid_code == "M1PAL30"


def test_missing_item_skipped():
    assert _sales_price_to_record({"Sales_Type": "Customer"}) is None


def test_sentinel_date_is_none():
    assert _date_or_none("0001-01-01") is None
    assert _date_or_none("") is None
    assert _date_or_none(None) is None
    assert _date_or_none("2026-06-01") == date(2026, 6, 1)


def test_normalize_sales_type_variants():
    assert _normalize_sales_type("Customer") == "Customer"
    assert _normalize_sales_type("Customer Price Group") == "Customer_Price_Group"
    assert _normalize_sales_type("all customers") == "All_Customers"
    assert _normalize_sales_type(None) == "All_Customers"


def test_ingest_dry_run_counts():
    rows = [
        {"Item_No": "1", "Unit_of_Measure_Code": "M1PAL30", "Unit_Price": "10"},
        {"Sales_Type": "Customer"},  # no item -> skipped
    ]
    rep = _ingest_sales_prices(rows, dry_run=True, sample_keys=[])
    assert rep.fetched == 2
    assert rep.upserted == 1
    assert rep.skipped_reasons["no_item"] == 1


def test_ingest_real_full_mirror(session, monkeypatch):
    monkeypatch.setattr(admin, "engine", session.get_bind())
    # Pre-existing stale row should be cleared by the full-mirror refresh.
    with Session(session.get_bind()) as s:
        s.add(Verkoopprijs(sales_type="Customer", sales_code="OLD",
                           kwabo_artikelnr="OLD", eenheid_code="", prijs=1.0))
        s.commit()
    rows = [
        {"Item_No": "A", "Sales_Type": "Customer", "Sales_Code": "C1",
         "Unit_of_Measure_Code": "M1PAL30", "Unit_Price": "10"},
        {"Item_No": "A", "Sales_Type": "Customer", "Sales_Code": "C1",
         "Unit_of_Measure_Code": "", "Unit_Price": "5"},
    ]
    rep = _ingest_sales_prices(rows, dry_run=False, sample_keys=["Item_No"])
    assert rep.upserted == 2
    with Session(session.get_bind()) as s:
        all_rows = list(s.exec(select(Verkoopprijs)).all())
        assert len(all_rows) == 2  # OLD gone
        assert {r.kwabo_artikelnr for r in all_rows} == {"A"}


class _FakeClient:
    page_sales_price = "PLX_SalesPrice"

    async def get_collection(self, entity):
        raise RuntimeError("404 not published")


@pytest.mark.asyncio
async def test_sync_404_degrades_gracefully(session):
    rep = await _sync_sales_prices(_FakeClient(), session, dry_run=False)
    assert rep.fetched == 0
    assert rep.upserted == 0
    assert rep.fetch_error is not None
    assert rep.skipped_reasons.get("fetch_error") == 1
