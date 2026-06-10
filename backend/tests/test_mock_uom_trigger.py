"""Regression tests for Bug 2: MockNavisionClient mix-discount must respect UOM.

Real NAV's mix-staffel codeunit only applies the staffel-pricing discount when
the line's `unitOfMeasureCode` is the configured mix-UOM (i.e. the alternate
UOM whose `qtyPerUnitOfMeasure` > 1.0). Applying the discount based on
quantity alone — regardless of UOM — masks composer bugs where the wrong UOM
PATCH is emitted: the mock would still cheerfully discount, but real NAV
would not, producing a price mismatch on go-live.

These tests pin the corrected mock behaviour:
  * UOM = base (qtyPerUnitOfMeasure == 1.0) AND quantity above threshold
        -> NO discount (matches real NAV).
  * UOM = mix (qtyPerUnitOfMeasure > 1.0) AND quantity above threshold
        -> discount applied.
  * No UOM PATCH at all (line keeps default base UOM) AND quantity above
    threshold -> NO discount (would otherwise hide composer bugs).
"""
from __future__ import annotations

import pytest

from kwabo.integrations.nav_mock_fixtures import (
    MOCK_MIX_DISCOUNT_FACTOR,
    MOCK_MIX_THRESHOLD,
    MOCK_PRICES,
)
from kwabo.integrations.navision_api import MockNavisionClient


# Mix-prijzen fixture: customer 10001 + item 1515155 are both mixprijzen=True
# in MOCK_CUSTOMERS / MOCK_ITEMS. Item 1515155 has UoMs ROL (base, qty=1.0)
# and PAL (mix, qty=24.0) registered in MOCK_ITEM_UOMS.
CUSTOMER_NR = "10001"
ITEM_NR = "1515155"
BASE_UOM = "ROL"
MIX_UOM = "PAL"
QTY_ABOVE_THRESHOLD = MOCK_MIX_THRESHOLD + 6  # 30
BASE_PRICE = MOCK_PRICES[ITEM_NR]
DISCOUNTED_PRICE = round(BASE_PRICE * MOCK_MIX_DISCOUNT_FACTOR, 4)


def _ops_for(uom: str | None, quantity: int) -> list[dict]:
    """Compose a minimal stepwise sequence for one mix-eligible line."""
    ops: list[dict] = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": CUSTOMER_NR}, "label": "header"},
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": ITEM_NR}, "label": "line"},
    ]
    if uom is not None:
        ops.append({
            "op": "PATCH", "path": "/salesOrderLines({id})",
            "body": {"unitOfMeasureCode": uom}, "label": "uom",
        })
    ops.append({
        "op": "PATCH", "path": "/salesOrderLines({id})",
        "body": {"quantity": quantity}, "label": "qty",
    })
    return ops


def _final_line_price(client: MockNavisionClient) -> float:
    """Read the unitPrice off the (single) line in the (single) order."""
    assert len(client._orders) == 1, "expected exactly one order"
    order = next(iter(client._orders.values()))
    assert len(order["lines"]) == 1, "expected exactly one line"
    return order["lines"][0]["unitPrice"]


@pytest.mark.asyncio
async def test_mix_discount_skipped_when_uom_is_base(tmp_path):
    """PATCH UOM = base ROL + quantity above threshold -> NO discount.

    This is the hard part: today's mock applies discount on quantity alone,
    which would mask composer bugs that emit the wrong UOM. After the fix,
    the mock requires UOM == mix-UOM before discounting.
    """
    client = MockNavisionClient(out_dir=tmp_path)
    ops = _ops_for(uom=BASE_UOM, quantity=QTY_ABOVE_THRESHOLD)
    result = await client.create_sales_order_stepwise(ops)
    for r in result["operation_results"]:
        assert "error" not in r, f"unexpected op error: {r}"
    assert _final_line_price(client) == BASE_PRICE


@pytest.mark.asyncio
async def test_mix_discount_applied_when_uom_is_mix(tmp_path):
    """PATCH UOM = mix PAL + quantity above threshold -> discount applies."""
    client = MockNavisionClient(out_dir=tmp_path)
    ops = _ops_for(uom=MIX_UOM, quantity=QTY_ABOVE_THRESHOLD)
    result = await client.create_sales_order_stepwise(ops)
    for r in result["operation_results"]:
        assert "error" not in r, f"unexpected op error: {r}"
    assert _final_line_price(client) == DISCOUNTED_PRICE


@pytest.mark.asyncio
async def test_mix_discount_skipped_without_uom_patch(tmp_path):
    """No UOM PATCH at all -> line keeps the item's base UOM -> NO discount.

    A composer bug that forgets to emit the UOM PATCH would, under the old
    mock, still get the discount because the mock only checked quantity.
    With the fix the line stays at the base UOM and the discount is skipped,
    surfacing the upstream bug.
    """
    client = MockNavisionClient(out_dir=tmp_path)
    ops = _ops_for(uom=None, quantity=QTY_ABOVE_THRESHOLD)
    result = await client.create_sales_order_stepwise(ops)
    for r in result["operation_results"]:
        assert "error" not in r, f"unexpected op error: {r}"
    assert _final_line_price(client) == BASE_PRICE


# ---- Fase 3 (E1/E3): eerlijke UoM-emulatie op het #716-faalgeval ----------
# Echte NAV default een NIEUWE regel naar de Sales Unit of Measure van de
# artikelkaart (order #716: regel 238601 kwam op PALLET33, 33/pallet), en
# weigert een UoM-code die niet in de Item-UoM-tabel staat (de ROL-400).
# De mock moet beide nadoen, anders bewijzen onze tests niets.

ITEM_716 = "238601"


def _ops_716(uom: str | None, quantity: float) -> list[dict]:
    ops: list[dict] = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": CUSTOMER_NR}, "label": "header"},
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": ITEM_716}, "label": "line"},
    ]
    if uom is not None:
        ops.append({"op": "PATCH", "path": "/salesOrderLines({id})",
                    "body": {"unitOfMeasureCode": uom}, "label": "uom"})
    ops.append({"op": "PATCH", "path": "/salesOrderLines({id})",
                "body": {"quantity": quantity}, "label": "qty"})
    return ops


def _final_line(client: MockNavisionClient) -> dict:
    order = next(iter(client._orders.values()))
    return order["lines"][0]


@pytest.mark.asyncio
async def test_line_post_default_is_verkoopeenheid_niet_base(tmp_path):
    """Faalgeval #716 geëmuleerd: POST line + quantity 66 ZONDER UoM-PATCH ->
    de regel staat in PALLET33 (NAV's default = Sales UoM) met quantity 66 —
    oftewel 66 pallets. Dit is de val waar de composer nooit meer in mag
    trappen (Branch A stuurt altijd een expliciete UoM-PATCH)."""
    client = MockNavisionClient(out_dir=tmp_path)
    result = await client.create_sales_order_stepwise(_ops_716(None, 66.0))
    for r in result["operation_results"]:
        assert "error" not in r, f"unexpected op error: {r}"
    line = _final_line(client)
    assert line["unitOfMeasureCode"] == "PALLET33"
    assert line["quantity"] == 66.0  # = 66 PALLETS: de stille factor-33-fout


@pytest.mark.asyncio
async def test_expliciete_branch_a_patches_geven_2_pallet33(tmp_path):
    """De fix end-to-end op de mock: UoM-PATCH PALLET33 + quantity 2 ->
    regel staat correct in 2 × PALLET33."""
    client = MockNavisionClient(out_dir=tmp_path)
    result = await client.create_sales_order_stepwise(_ops_716("PALLET33", 2))
    for r in result["operation_results"]:
        assert "error" not in r, f"unexpected op error: {r}"
    line = _final_line(client)
    assert line["unitOfMeasureCode"] == "PALLET33"
    assert line["quantity"] == 2


@pytest.mark.asyncio
async def test_ongeldige_uom_code_geeft_400(tmp_path):
    """E3: een UoM-code die niet in de Item-UoM-tabel staat (ROL voor 238601)
    -> 400 + stop-on-error, zoals echte NAV. Items zonder mock-UoM-data
    blijven alles accepteren (geen data = niet te valideren)."""
    client = MockNavisionClient(out_dir=tmp_path)
    result = await client.create_sales_order_stepwise(_ops_716("ROL", 66.0))
    statuses = [r["status"] for r in result["operation_results"]]
    assert 400 in statuses, f"verwachtte 400 op ROL-PATCH, kreeg {statuses}"
    fout = next(r for r in result["operation_results"] if r["status"] == 400)
    assert "ROL" in (fout.get("error") or "")
    # stop-on-error: de quantity-PATCH erna is nooit uitgevoerd
    assert len(result["operation_results"]) == 3


@pytest.mark.asyncio
async def test_mix_discount_skipped_when_quantity_below_threshold(tmp_path):
    """UOM = mix PAL but quantity below threshold -> NO discount.

    Verifies the threshold component of the rule is intact even with the
    UOM tightening: both UOM and quantity must qualify.
    """
    client = MockNavisionClient(out_dir=tmp_path)
    ops = _ops_for(uom=MIX_UOM, quantity=MOCK_MIX_THRESHOLD - 1)
    result = await client.create_sales_order_stepwise(ops)
    for r in result["operation_results"]:
        assert "error" not in r, f"unexpected op error: {r}"
    assert _final_line_price(client) == BASE_PRICE
