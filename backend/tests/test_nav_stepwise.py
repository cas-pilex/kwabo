"""Tests for the trigger-aware stepwise NAV client (T3).

These tests are hermetic — they never hit a real NAV. The MockNavisionClient
tests exercise the in-memory trigger emulation; the RealNavisionClient tests
use httpx.MockTransport to verify exact wire shapes.
"""
from __future__ import annotations

import base64
from typing import Optional

import httpx
import pytest


# --------------------------------------------------------------------------
# RealNavisionClient.patch — defensive single-field invariant
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_patch_rejects_multi_field_body():
    from kwabo.integrations.navision_real import RealNavisionClient

    client = RealNavisionClient(
        base_url="https://nav.example.com/api",
        company_id="00000000-0000-0000-0000-000000000000",
        auth_mode="basic",
        username="u",
        password="p",
    )
    try:
        with pytest.raises(ValueError, match="exactly one field"):
            await client.patch("/salesOrders(abc)", {"a": 1, "b": 2})
        with pytest.raises(ValueError, match="exactly one field"):
            await client.patch("/salesOrders(abc)", {})
    finally:
        await client.aclose()


# --------------------------------------------------------------------------
# MockNavisionClient stepwise — happy path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_stepwise_simple_order_autofills_via_triggers(tmp_path):
    """Single customer + single item + ship-to-code: trigger emulation
    must populate description, unitOfMeasureCode, unitPrice and the
    address fields, none of which we explicitly send."""
    from kwabo.integrations.navision_api import MockNavisionClient

    client = MockNavisionClient(out_dir=tmp_path)
    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001"},
         "label": "Klant kiezen (Sell-to Customer No.)"},
        {"op": "PATCH", "path": "/salesOrders({id})",
         "body": {"shipToCode": "DC-EAST"},
         "label": "Verzendadres kiezen (Ship-to Code)",
         "expects": {"shipToAddress": "Logistiekpark 12"}},
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": "1515155"},
         "label": "Regel toevoegen (Line Item)"},
        {"op": "PATCH", "path": "/salesOrderLines({id})",
         "body": {"quantity": 5},
         "label": "Aantal invullen"},
    ]
    result = await client.create_sales_order_stepwise(ops)

    # No errors anywhere.
    for r in result["operation_results"]:
        assert "error" not in r, r

    assert len(result["operation_results"]) == 4
    assert result["sales_order_id"]
    assert result["sales_order_number"].startswith("SO-")

    # POST /salesOrders trigger fill: customer name, payment terms, currency.
    so_post = result["operation_results"][0]
    assert so_post["response_body"]["sellToCustomerName"] == "Ferney Diabolo B.V."
    assert "paymentTermsCode" in so_post["autofilled"]
    assert "currencyCode" in so_post["autofilled"]

    # PATCH shipToCode trigger fill: address fields.
    ship_patch = result["operation_results"][1]
    assert ship_patch["response_body"]["shipToCity"] == "Apeldoorn"
    assert ship_patch["response_body"]["shipToAddress"] == "Logistiekpark 12"
    assert "shipToCity" in ship_patch["autofilled"]

    # POST /salesOrderLines trigger fill: description, UoM, unitPrice.
    line_post = result["operation_results"][2]
    body = line_post["response_body"]
    assert body["description"] == "Ferney stucloper 120cm"
    assert body["unitOfMeasureCode"] == "ROL"
    assert body["unitPrice"] == 100.0
    assert "description" in line_post["autofilled"]
    assert "unitOfMeasureCode" in line_post["autofilled"]
    assert "unitPrice" in line_post["autofilled"]

    # No mix discount — quantity below threshold.
    qty_patch = result["operation_results"][3]
    # Re-GET wasn't requested for this op, so autofilled is empty;
    # but the response_body holds the line.
    assert qty_patch["response_body"]["unitPrice"] == 100.0

    # Persisted to disk.
    files = list(tmp_path.glob("SO-*.json"))
    assert len(files) == 1


# --------------------------------------------------------------------------
# MockNavisionClient stepwise — mixprijzen pricing rule
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_stepwise_mixprijzen_quantity_triggers_discount(tmp_path):
    from kwabo.integrations.navision_api import (
        MOCK_MIX_DISCOUNT_FACTOR,
        MOCK_MIX_THRESHOLD,
        MockNavisionClient,
    )

    client = MockNavisionClient(out_dir=tmp_path)
    # 10001 + 1515155 are both mixprijzen=True.
    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001"}, "label": "klant"},
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": "1515155"}, "label": "regel"},
        {"op": "PATCH", "path": "/salesOrderLines({id})",
         "body": {"quantity": MOCK_MIX_THRESHOLD},
         "label": "aantal",
         "expects": {"unitPrice": "discounted"}},
    ]
    result = await client.create_sales_order_stepwise(ops)

    qty_patch = result["operation_results"][2]
    expected = round(100.0 * MOCK_MIX_DISCOUNT_FACTOR, 4)
    assert qty_patch["response_body"]["unitPrice"] == expected
    # Same scenario but with a non-mix customer should NOT discount.
    client2 = MockNavisionClient(out_dir=tmp_path)
    ops2 = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10002"}, "label": "klant"},
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": "1515155"}, "label": "regel"},
        {"op": "PATCH", "path": "/salesOrderLines({id})",
         "body": {"quantity": MOCK_MIX_THRESHOLD}, "label": "aantal"},
    ]
    result2 = await client2.create_sales_order_stepwise(ops2)
    qty_patch2 = result2["operation_results"][2]
    assert qty_patch2["response_body"]["unitPrice"] == 100.0


# --------------------------------------------------------------------------
# MockNavisionClient stepwise — stop-on-error semantics
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_stepwise_stops_on_first_error(tmp_path):
    from kwabo.integrations.navision_api import MockNavisionClient

    client = MockNavisionClient(out_dir=tmp_path)

    # Force the third op (index 2) to fail.
    def predicate(idx: int, op: dict) -> Optional[str]:
        if idx == 2:
            return "simulated NAV failure on PATCH #3"
        return None

    client._fail_predicate = predicate

    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001"}, "label": "klant"},
        {"op": "PATCH", "path": "/salesOrders({id})",
         "body": {"shipToCode": "DC-EAST"}, "label": "verzendadres"},
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": "1515155"}, "label": "regel"},
        {"op": "PATCH", "path": "/salesOrderLines({id})",
         "body": {"quantity": 5}, "label": "aantal"},
    ]
    result = await client.create_sales_order_stepwise(ops)

    assert len(result["operation_results"]) == 3
    assert "error" in result["operation_results"][2]
    assert result["operation_results"][2]["error"] == "simulated NAV failure on PATCH #3"
    # Earlier ops succeeded — partial state is preserved.
    assert "error" not in result["operation_results"][0]
    assert "error" not in result["operation_results"][1]


# --------------------------------------------------------------------------
# MockNavisionClient stepwise — invariant violations
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_stepwise_rejects_multi_field_post_to_sales_orders(tmp_path):
    from kwabo.integrations.navision_api import MockNavisionClient

    client = MockNavisionClient(out_dir=tmp_path)
    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001", "externalDocumentNumber": "PO-123"},
         "label": "bad header"},
    ]
    result = await client.create_sales_order_stepwise(ops)
    assert "error" in result["operation_results"][0]
    assert "customerNumber" in result["operation_results"][0]["error"]


@pytest.mark.asyncio
async def test_mock_stepwise_rejects_multi_field_patch(tmp_path):
    from kwabo.integrations.navision_api import MockNavisionClient

    client = MockNavisionClient(out_dir=tmp_path)
    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001"}, "label": "klant"},
        {"op": "PATCH", "path": "/salesOrders({id})",
         "body": {"shipToCode": "DC-EAST", "shipToCity": "Apeldoorn"},
         "label": "bad multi-field PATCH"},
    ]
    result = await client.create_sales_order_stepwise(ops)
    assert len(result["operation_results"]) == 2
    assert "error" in result["operation_results"][1]


# --------------------------------------------------------------------------
# MockNavisionClient — new master-data + incoming-document endpoints
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_master_data_endpoints():
    from kwabo.integrations.navision_api import MockNavisionClient

    client = MockNavisionClient()

    ship = await client.get_ship_to_addresses("10001")
    assert {s["code"] for s in ship} == {"MAIN", "DC-EAST"}

    uoms = await client.get_item_uoms("1515155")
    codes = [u["code"] for u in uoms]
    assert "ROL" in codes and "PAL" in codes

    refs = await client.get_item_references(customer_no="10001")
    assert refs and refs[0]["referenceNo"] == "FER-STUC-120"

    refs_all = await client.get_item_references()
    assert len(refs_all) >= 1


@pytest.mark.asyncio
async def test_mock_incoming_document_attachment_roundtrip():
    from kwabo.integrations.navision_api import MockNavisionClient

    client = MockNavisionClient()
    doc = await client.create_incoming_document(
        description="Inkomende order PO-123", vendor_name="Ferney Diabolo B.V."
    )
    assert doc["id"]
    payload = b"fake-pdf-bytes"
    result = await client.attach_to_incoming_document(
        doc["id"], "PO-123.pdf", payload, "application/pdf"
    )
    assert result["fileName"] == "PO-123.pdf"
    assert result["mediaType"] == "application/pdf"
    decoded = base64.b64decode(result["content"])
    assert decoded == payload


# --------------------------------------------------------------------------
# RealNavisionClient.create_sales_order_stepwise — wire-shape verification
# --------------------------------------------------------------------------


def _make_real_client_with_transport(handler):
    """Build a RealNavisionClient pinned to an httpx.MockTransport."""
    from kwabo.integrations.navision_real import RealNavisionClient

    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    client = RealNavisionClient(
        base_url="https://nav.example.com/api",
        company_id="00000000-0000-0000-0000-000000000000",
        auth_mode="basic",
        username="u",
        password="p",
        http_client=http,
    )
    return client


@pytest.mark.asyncio
async def test_real_stepwise_sends_correct_endpoints_and_bodies():
    """Verify the exact NAV endpoints + per-op bodies that go over the wire."""
    captured: list[dict] = []
    fake_order_id = "11111111-1111-1111-1111-111111111111"
    fake_line_id = "22222222-2222-2222-2222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "method": request.method,
            "url": str(request.url),
            "body": request.content.decode("utf-8") if request.content else "",
        })
        # Route the responses.
        path = request.url.path
        if request.method == "POST" and path.endswith("/salesOrders"):
            return httpx.Response(
                201, json={"id": fake_order_id, "number": "SO-100001",
                           "customerNumber": "10001",
                           "sellToCustomerName": "Ferney Diabolo B.V.",
                           "paymentTermsCode": "30D"},
            )
        if request.method == "POST" and path.endswith("/salesOrderLines"):
            return httpx.Response(
                201, json={"id": fake_line_id, "lineType": "Item",
                           "itemNumber": "1515155",
                           "description": "Ferney stucloper 120cm",
                           "unitOfMeasureCode": "ROL", "unitPrice": 100.0},
            )
        if request.method == "PATCH":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": "unexpected"})

    client = _make_real_client_with_transport(handler)
    try:
        ops = [
            {"op": "POST", "path": "/salesOrders",
             "body": {"customerNumber": "10001"}, "label": "klant"},
            {"op": "PATCH", "path": "/salesOrders({id})",
             "body": {"shipToCode": "DC-EAST"}, "label": "verzendadres"},
            {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
             "body": {"lineType": "Item", "itemNumber": "1515155"}, "label": "regel"},
            {"op": "PATCH", "path": "/salesOrderLines({id})",
             "body": {"quantity": 5}, "label": "aantal"},
        ]
        result = await client.create_sales_order_stepwise(ops)
    finally:
        await client.aclose()

    # Errors propagated up?
    for r in result["operation_results"]:
        assert "error" not in r, r

    # Map: which call?       expected method    expected URL suffix    expected JSON body
    import json as _json
    expected = [
        ("POST",
         "/companies(00000000-0000-0000-0000-000000000000)/salesOrders",
         {"customerNumber": "10001"}),
        ("PATCH",
         f"/companies(00000000-0000-0000-0000-000000000000)/salesOrders({fake_order_id})",
         {"shipToCode": "DC-EAST"}),
        ("POST",
         f"/companies(00000000-0000-0000-0000-000000000000)/salesOrders({fake_order_id})/salesOrderLines",
         {"lineType": "Item", "itemNumber": "1515155"}),
        ("PATCH",
         f"/companies(00000000-0000-0000-0000-000000000000)/salesOrderLines({fake_line_id})",
         {"quantity": 5}),
    ]
    assert len(captured) == len(expected)
    for got, (m, suffix, body) in zip(captured, expected):
        assert got["method"] == m, got
        assert got["url"].endswith(suffix), got["url"]
        assert _json.loads(got["body"]) == body, got["body"]


@pytest.mark.asyncio
async def test_real_stepwise_stops_on_http_error():
    """Inject an HTTP 500 on the second op; the third op must NOT be sent."""
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path.endswith("/salesOrders"):
            return httpx.Response(201, json={"id": "abc", "number": "SO-1"})
        if request.method == "PATCH":
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(404)

    client = _make_real_client_with_transport(handler)
    try:
        ops = [
            {"op": "POST", "path": "/salesOrders",
             "body": {"customerNumber": "10001"}, "label": "klant"},
            {"op": "PATCH", "path": "/salesOrders({id})",
             "body": {"shipToCode": "DC-EAST"}, "label": "verzendadres"},
            {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
             "body": {"lineType": "Item", "itemNumber": "1515155"},
             "label": "should not be sent"},
        ]
        result = await client.create_sales_order_stepwise(ops)
    finally:
        await client.aclose()

    assert len(result["operation_results"]) == 2
    assert "error" in result["operation_results"][1]
    # Only 2 HTTP calls were attempted.
    assert len(captured) == 2


# --------------------------------------------------------------------------
# RealNavisionClient.attach_to_incoming_document — request shape
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_attach_to_incoming_document_uses_base64_patch():
    """Stub creation -> base64 PATCH content."""
    captured: list[dict] = []
    attach_id = "33333333-3333-3333-3333-333333333333"

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({
            "method": request.method,
            "path": request.url.path,
            "body": request.content,
        })
        if request.method == "POST" and request.url.path.endswith("/attachments"):
            return httpx.Response(201, json={"id": attach_id, "fileName": "x.pdf"})
        if request.method == "PATCH":
            return httpx.Response(204)
        return httpx.Response(404)

    client = _make_real_client_with_transport(handler)
    try:
        result = await client.attach_to_incoming_document(
            "doc-1", "x.pdf", b"hello-world", "application/pdf"
        )
    finally:
        await client.aclose()

    assert result["fileName"] == "x.pdf"
    assert result["mediaType"] == "application/pdf"

    # Two calls: stub create then base64 PATCH.
    assert len(captured) == 2
    assert captured[0]["method"] == "POST"
    assert captured[0]["path"].endswith("/incomingDocuments(doc-1)/attachments")
    assert captured[1]["method"] == "PATCH"
    assert captured[1]["path"].endswith(f"/incomingDocuments(doc-1)/attachments({attach_id})")

    # The PATCH body must contain `content` as base64.
    import json as _json
    patch_body = _json.loads(captured[1]["body"])
    assert set(patch_body.keys()) == {"content"}
    assert base64.b64decode(patch_body["content"]) == b"hello-world"
