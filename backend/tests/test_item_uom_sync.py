"""Item-UOM sync mapper: PLX_ItemUnitOfMeasure row -> ArtikelEenheid, plus
the mix-UOM heuristic. Pure unit tests (no NAV, no DB)."""
from __future__ import annotations

from sqlmodel import Session

import kwabo.api.admin as admin
from kwabo.api.admin import _item_uom_is_mix, _item_uom_to_record, _ingest_item_uoms
from kwabo.db.models import ArtikelEenheid


def test_maps_basic_row():
    rec = _item_uom_to_record(
        {"Item_No": "1001", "Code": "PAL", "Qty_per_Unit_of_Measure": "60"}, None
    )
    assert rec is not None
    assert rec.kwabo_artikelnr == "1001"
    assert rec.eenheid_code == "PAL"
    assert rec.qty_per_base == 60.0


def test_tolerates_field_name_variants():
    rec = _item_uom_to_record(
        {"ItemNo": "1001", "Unit_of_Measure_Code": "STUK", "Qty_per_Unit": "1"}, None
    )
    assert rec is not None
    assert rec.eenheid_code == "STUK"
    assert rec.qty_per_base == 1.0


def test_missing_item_or_code_skipped():
    assert _item_uom_to_record({"Code": "PAL"}, None) is None
    assert _item_uom_to_record({"Item_No": "1001"}, None) is None


def test_non_positive_qty_defaults_to_one():
    rec = _item_uom_to_record(
        {"Item_No": "1001", "Code": "STUK", "Qty_per_Unit_of_Measure": "0"}, None
    )
    assert rec.qty_per_base == 1.0


def test_ingest_dry_run_counts():
    rows = [
        {"Item_No": "1", "Code": "PAL", "Qty_per_Unit_of_Measure": "60"},
        {"Code": "X"},        # no item -> skipped
        {"Item_No": "2"},     # no code -> skipped
    ]
    rep = _ingest_item_uoms(rows, dry_run=True, sample_keys=[])
    assert rep.fetched == 3
    assert rep.upserted == 1
    assert rep.skipped_reasons["no_artikelnr"] == 1
    assert rep.skipped_reasons["no_code"] == 1


def test_ingest_real_populates_table(session, monkeypatch):
    # _ingest_item_uoms opens its own Session(engine); point that at the test DB.
    monkeypatch.setattr(admin, "engine", session.get_bind())
    rows = [
        {"Item_No": "9001", "Code": "PAL", "Qty_per_Unit_of_Measure": "60"},
        {"Item_No": "9001", "Code": "STUK", "Qty_per_Unit_of_Measure": "1"},
    ]
    rep = _ingest_item_uoms(rows, dry_run=False, sample_keys=["Item_No"])
    assert rep.upserted == 2
    with Session(session.get_bind()) as s:
        got = s.get(ArtikelEenheid, ("9001", "PAL"))
        assert got is not None and got.qty_per_base == 60.0


def test_mix_uom_detection():
    # Explicit NAV flag is the reliable signal (codes like "M2 PAL35" carry no
    # consistent text marker, and "M1"/"M2" are meter units, not mix units).
    assert _item_uom_is_mix({"Mix_UoM": "Yes"}, "M2 PAL35") is True
    assert _item_uom_is_mix({}, "MIX") is True
    assert _item_uom_is_mix({}, "MENGPAL") is True
    assert _item_uom_is_mix({"Mix_UoM": "Yes"}, "PAL") is True
    # No flag + no MIX/MENG text -> not auto-flagged (avoids M1/M2 false hits).
    assert _item_uom_is_mix({}, "M2 PAL35") is False
    assert _item_uom_is_mix({}, "STUK") is False
    assert _item_uom_is_mix({}, "PAL") is False
