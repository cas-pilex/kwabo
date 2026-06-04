"""Tests for VerkoopprijsRepo — verkoopsoort cascade + date window + parsing."""
from __future__ import annotations

from datetime import date

from kwabo.db.models import Verkoopprijs
from kwabo.db.repository import VerkoopprijsRepo


def _add(session, **kw) -> None:
    session.add(Verkoopprijs(**kw))
    session.commit()


def _repo(session) -> VerkoopprijsRepo:
    return VerkoopprijsRepo(session)


ON = date(2026, 6, 1)


def test_customer_tier_wins(session):
    _add(session, sales_type="Customer", sales_code="C1", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=10.0)
    _add(session, sales_type="Customer_Price_Group", sales_code="G1", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=20.0)
    _add(session, sales_type="All_Customers", sales_code="", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=30.0)
    rows = _repo(session).active_rows(kwabo_artikelnr="A", klant_nr="C1", prijsgroep="G1", on_date=ON)
    assert {r.prijs for r in rows} == {10.0}  # only Customer tier


def test_group_tier_when_no_customer(session):
    _add(session, sales_type="Customer_Price_Group", sales_code="G1", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=20.0)
    _add(session, sales_type="All_Customers", sales_code="", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=30.0)
    rows = _repo(session).active_rows(kwabo_artikelnr="A", klant_nr="C1", prijsgroep="G1", on_date=ON)
    assert {r.prijs for r in rows} == {20.0}


def test_all_customers_fallthrough(session):
    _add(session, sales_type="All_Customers", sales_code="", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=30.0)
    rows = _repo(session).active_rows(kwabo_artikelnr="A", klant_nr="C1", prijsgroep="G1", on_date=ON)
    assert {r.prijs for r in rows} == {30.0}


def test_no_prijsgroep_skips_group_tier(session):
    _add(session, sales_type="Customer_Price_Group", sales_code="G1", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=20.0)
    _add(session, sales_type="All_Customers", sales_code="", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=30.0)
    rows = _repo(session).active_rows(kwabo_artikelnr="A", klant_nr="C1", prijsgroep=None, on_date=ON)
    assert {r.prijs for r in rows} == {30.0}  # group skipped, falls to All


def test_date_window_excludes_expired_and_future(session):
    _add(session, sales_type="Customer", sales_code="C1", kwabo_artikelnr="A", eenheid_code="M1PAL30",
         prijs=10.0, geldig_tot=date(2026, 1, 1))  # expired
    _add(session, sales_type="Customer", sales_code="C1", kwabo_artikelnr="A", eenheid_code="M7PAL30",
         prijs=11.0, geldig_van=date(2026, 12, 1))  # future
    rows = _repo(session).active_rows(kwabo_artikelnr="A", klant_nr="C1", prijsgroep=None, on_date=ON)
    assert rows == []


def test_normal_price_and_mix_codes(session):
    _add(session, sales_type="Customer", sales_code="C1", kwabo_artikelnr="A", eenheid_code="", prijs=5.0)
    _add(session, sales_type="Customer", sales_code="C1", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=10.0)
    _add(session, sales_type="Customer", sales_code="C1", kwabo_artikelnr="A", eenheid_code="M1PAL30", prijs=10.0)  # dup
    repo = _repo(session)
    rows = repo.active_rows(kwabo_artikelnr="A", klant_nr="C1", prijsgroep=None, on_date=ON)
    assert repo.normal_price(rows) == 5.0
    codes = repo.mix_codes(rows)
    assert [c.code for c in codes] == ["M1PAL30"]  # deduped, normal row excluded
