"""Mock NAV prices a line from the chosen M-code (table-7002 mirror)."""
from __future__ import annotations

from kwabo.integrations.navision_api import MockNavisionClient


def _client_with_line(tmp_path, uom: str) -> tuple[MockNavisionClient, str]:
    c = MockNavisionClient(out_dir=tmp_path)
    c._orders["SO1"] = {
        "id": "SO1",
        "_customer_mixprijzen": True,
        "lines": [
            {
                "id": "L1",
                "itemNumber": "1515155",
                "unitOfMeasureCode": uom,
                "_item_mixprijzen": True,
            }
        ],
    }
    return c, "L1"


def test_mix_code_uom_patch_sets_active_price(tmp_path):
    c, line_id = _client_with_line(tmp_path, "ROL")
    out = c._patch_sales_order_line(line_id, {"unitOfMeasureCode": "M1PAL24"})
    assert out["unitOfMeasureCode"] == "M1PAL24"
    assert out["unitPrice"] == 2400.0  # from MOCK_SALES_PRICES (item 1515155)


def test_mix_price_for_lookup(tmp_path):
    c = MockNavisionClient(out_dir=tmp_path)
    assert c._mix_price_for("1515155", "M7PAL24") == 2300.0
    assert c._mix_price_for("1515155", "NOPE") is None
    # All_Customers fallback row in the fixture.
    assert c._mix_price_for("SOFTBREATH-PALLET", "M1PAL35") == 500.0
