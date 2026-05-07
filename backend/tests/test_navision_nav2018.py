"""Unit tests for the NAV 2018 OData V4 client.

Focus: URL shape + body translation. We stub httpx with respx so the
tests run offline; covering the actual NAV server is end-to-end work
that depends on Cas's credentials and is documented separately."""
from __future__ import annotations

import httpx
import pytest
import respx

from kwabo.integrations.nav_operations import NavOperation
from kwabo.integrations.navision_nav2018 import (
    Nav2018ODataClient,
    _quote_company,
    _quote_key,
    _translate_body,
)


BASE = "https://nav.example.com:1153/ST-1/ODataV4"
COMPANY = "Kopie 2023 Kwabo Techniek B.V."
COMPANY_PATH = "Kopie%202023%20Kwabo%20Techniek%20B.V."


def _client(http_client: httpx.AsyncClient) -> Nav2018ODataClient:
    return Nav2018ODataClient(
        base_url=BASE,
        company=COMPANY,
        username="user",
        password="key",
        verify_ssl=False,
        http_client=http_client,
    )


def test_quote_company_url_encodes_spaces_and_dots():
    out = _quote_company(COMPANY)
    assert out == COMPANY_PATH


def test_quote_company_doubles_single_quotes():
    out = _quote_company("D'Antonio's Co")
    # Single quotes inside the literal must be doubled per OData spec, then
    # the percent-encoder turns them into %27.
    assert out == "D%27%27Antonio%27%27s%20Co"


def test_quote_key_doubles_single_quotes():
    assert _quote_key("PO'12'34") == "PO''12''34"


def test_translate_body_renames_known_keys_and_passes_through_unknown():
    out = _translate_body(
        {"customerNumber": "10009", "shipToCode": "MAIN", "weirdField": "x"},
        {"customerNumber": "Sell_to_Customer_No", "shipToCode": "Ship_to_Code"},
    )
    assert out == {
        "Sell_to_Customer_No": "10009",
        "Ship_to_Code": "MAIN",
        "weirdField": "x",
    }


@pytest.mark.asyncio
@respx.mock
async def test_stepwise_post_uses_company_path_and_translates_field():
    expected_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder"
    route = respx.post(expected_url).mock(
        return_value=httpx.Response(
            201,
            json={
                "No": "SO12345",
                "Sell_to_Customer_No": "10009",
                "Sell_to_Customer_Name": "L. De Vos sa/nv",
            },
        ),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        ops: list[NavOperation] = [
            {
                "op": "POST",
                "path": "/salesOrders",
                "body": {"customerNumber": "10009"},
                "label": "header",
            },
        ]
        result = await client.create_sales_order_stepwise(ops)

    assert route.called
    sent = route.calls.last.request
    assert sent.url == expected_url
    assert b'"Sell_to_Customer_No":"10009"' in sent.content
    assert result["sales_order_number"] == "SO12345"


@pytest.mark.asyncio
@respx.mock
async def test_stepwise_patch_uses_record_url_with_string_key():
    post_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder"
    patch_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder('SO12345')"
    respx.post(post_url).mock(
        return_value=httpx.Response(201, json={"No": "SO12345"}),
    )
    patch = respx.patch(patch_url).mock(
        return_value=httpx.Response(200, json={"No": "SO12345", "Ship_to_Code": "MAIN"}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        ops: list[NavOperation] = [
            {
                "op": "POST",
                "path": "/salesOrders",
                "body": {"customerNumber": "10009"},
                "label": "header",
            },
            {
                "op": "PATCH",
                "path": "/salesOrders({id})",
                "body": {"shipToCode": "MAIN"},
                "label": "ship-to",
            },
        ]
        result = await client.create_sales_order_stepwise(ops)

    assert patch.called
    sent = patch.calls.last.request
    assert sent.url == patch_url
    # Field rename applied.
    assert b'"Ship_to_Code":"MAIN"' in sent.content
    # No errors on either op.
    errors = [r for r in result["operation_results"] if r.get("error")]
    assert errors == []


@pytest.mark.asyncio
@respx.mock
async def test_stepwise_skips_incoming_documents_op():
    """NAV 2018 incoming-documents flow isn't implemented; the op must be
    skipped with a clear error rather than crashing the whole order."""
    post_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder"
    respx.post(post_url).mock(
        return_value=httpx.Response(201, json={"No": "SO12345"}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        ops: list[NavOperation] = [
            {
                "op": "POST",
                "path": "/salesOrders",
                "body": {"customerNumber": "10009"},
                "label": "header",
            },
            {
                "op": "POST",
                "path": "/incomingDocuments",
                "body": {"description": "x", "vendorName": "y"},
                "label": "skip",
            },
        ]
        result = await client.create_sales_order_stepwise(ops)

    skipped = [
        r for r in result["operation_results"]
        if r.get("error") and "incomingDocuments" in r["error"]
    ]
    assert len(skipped) == 1
    # Header op succeeded.
    successful = [r for r in result["operation_results"] if r.get("status") == 201]
    assert len(successful) == 1


@pytest.mark.asyncio
@respx.mock
async def test_stepwise_dedup_by_external_doc_no():
    """Re-pushing the same email must short-circuit when NAV already has
    a sales-order with the matching External_Document_No."""
    list_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder"
    # OData returns a `value` array on the GET probe.
    respx.get(list_url).mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"No": "SO_EXISTING", "External_Document_No": "PO123"}]},
        ),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        ops: list[NavOperation] = [
            {
                "op": "POST",
                "path": "/salesOrders",
                "body": {"customerNumber": "10009"},
                "label": "header",
            },
            {
                "op": "PATCH",
                "path": "/salesOrders({id})",
                "body": {"externalDocumentNumber": "PO123"},
                "label": "ext-doc",
            },
        ]
        result = await client.create_sales_order_stepwise(ops)

    assert result["sales_order_number"] == "SO_EXISTING"
    # Dedup short-circuits BEFORE any POST/PATCH runs.
    assert result["operation_results"] == []


@pytest.mark.asyncio
@respx.mock
async def test_probe_reports_status_and_url_on_success():
    expected_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder?$top=1"
    respx.get(expected_url).mock(
        return_value=httpx.Response(200, json={"value": []}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.probe()
    assert result["ok"] is True
    assert result["status"] == 200
    assert result["company"] == COMPANY


@pytest.mark.asyncio
@respx.mock
async def test_probe_reports_failure_on_401():
    expected_url = f"{BASE}/Company('{COMPANY_PATH}')/PLX_SalesOrder?$top=1"
    respx.get(expected_url).mock(
        return_value=httpx.Response(401, text="Unauthorized"),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.probe()
    assert result["ok"] is False
    assert result["status"] == 401
