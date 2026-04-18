"""Mock & Replay Navision clients."""
from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_mock_customer_lookup():
    from kwabo.integrations.navision_api import MockNavisionClient
    c = MockNavisionClient()
    res = await c.search_customers(email="purchaseorders@ferney.nl")
    assert res and res[0]["number"] == "10001"


@pytest.mark.asyncio
async def test_mock_sales_order_persisted(tmp_path):
    from kwabo.integrations.navision_api import MockNavisionClient
    c = MockNavisionClient(out_dir=tmp_path)
    result = await c.create_sales_order(
        {"customerNumber": "10001", "externalDocumentNumber": "PO-XYZ"},
        [{"itemNumber": "1515", "quantity": 10, "unitOfMeasureCode": "ROL"}],
    )
    assert result["number"].startswith("SO-")
    files = list(tmp_path.glob("SO-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["header"]["customerNumber"] == "10001"
    assert data["lines"][0]["itemNumber"] == "1515"


@pytest.mark.asyncio
async def test_replay_client(fixtures_dir):
    from kwabo.integrations.navision_real import ReplayNavisionClient
    c = ReplayNavisionClient(fixtures_dir / "navision_replay.json")
    res = await c.search_customers(email="purchaseorders@ferney.nl")
    assert res and res[0]["number"] == "10001"
    item = await c.get_item("1515155")
    assert item and "Ferney" in item["displayName"]
    order = await c.create_sales_order({"customerNumber": "10001"}, [{"itemNumber": "1515155", "quantity": 1}])
    assert order["number"].startswith("SO-REPLAY-")
