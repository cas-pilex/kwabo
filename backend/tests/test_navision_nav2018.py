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
async def test_stepwise_post_uses_company_querystring_and_translates_field():
    """NAV 2018 in Kopie 2026 needs `?company=...` querystring, not
    `Company('...')/` path prefix — discovered when PLX_Item / PLX_Customer
    returned 404 under the path-style URL but worked with querystring."""
    base_url_for_post = f"{BASE}/PLX_SalesOrder"
    route = respx.post(url__startswith=base_url_for_post).mock(
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
    assert sent.url.path.endswith("/PLX_SalesOrder")
    assert "Company(" not in str(sent.url)  # old path-style URL forbidden
    assert sent.url.params.get("company") == COMPANY
    assert b'"Sell_to_Customer_No":"10009"' in sent.content
    assert result["sales_order_number"] == "SO12345"


@pytest.mark.asyncio
@respx.mock
async def test_stepwise_patch_uses_record_url_with_string_key():
    post_url = f"{BASE}/PLX_SalesOrder"
    patch_url_base = f"{BASE}/PLX_SalesOrder('SO12345')"
    respx.post(url__startswith=post_url).mock(
        return_value=httpx.Response(201, json={"No": "SO12345"}),
    )
    patch = respx.patch(url__startswith=patch_url_base).mock(
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
    assert sent.url.path.endswith("/PLX_SalesOrder('SO12345')")
    assert sent.url.params.get("company") == COMPANY
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
    post_url = f"{BASE}/PLX_SalesOrder"
    respx.post(url__startswith=post_url).mock(
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
    list_url = f"{BASE}/PLX_SalesOrder"
    # OData returns a `value` array on the GET probe.
    respx.get(url__startswith=list_url).mock(
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
    base = f"{BASE}/PLX_SalesOrder"
    respx.get(url__startswith=base).mock(
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
    base = f"{BASE}/PLX_SalesOrder"
    respx.get(url__startswith=base).mock(
        return_value=httpx.Response(401, text="Unauthorized"),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.probe()
    assert result["ok"] is False
    assert result["status"] == 401


# Diagnostic capability: when Kopie 2026 returns 200 on PLX_SalesOrder but
# empty on item/customer searches, the operator needs a way to probe each
# page individually to distinguish "page returns 404", "page returns 401",
# and "page returns 200 with empty value array" (= no master data).


@pytest.mark.asyncio
@respx.mock
async def test_probe_accepts_explicit_page_override():
    """Probe must accept any page name and hit that page's URL."""
    base = f"{BASE}/PLX_Item"
    respx.get(url__startswith=base).mock(
        return_value=httpx.Response(200, json={"value": [{"No": "X"}]}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.probe(page="PLX_Item")
    assert result["ok"] is True
    assert result["status"] == 200
    assert result["page"] == "PLX_Item"
    assert result["url"].startswith(base)
    assert "company=" in result["url"]


@pytest.mark.asyncio
@respx.mock
async def test_probe_distinguishes_empty_200_from_404_in_preview():
    """Empty-but-200 must show `"value":[]` in preview so the operator can
    tell apart "page works, no data yet" from "page missing / no access"."""
    base = f"{BASE}/PLX_Item"
    respx.get(url__startswith=base).mock(
        return_value=httpx.Response(200, json={"value": []}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.probe(page="PLX_Item")
    assert result["ok"] is True
    assert result["status"] == 200
    assert "\"value\":[]" in result["preview"] or '"value": []' in result["preview"]


@pytest.mark.asyncio
@respx.mock
async def test_probe_reports_404_distinctly_with_page_override():
    base = f"{BASE}/PLX_Item"
    respx.get(url__startswith=base).mock(
        return_value=httpx.Response(404, text="Not Found"),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.probe(page="PLX_Item")
    assert result["ok"] is False
    assert result["status"] == 404
    assert result["page"] == "PLX_Item"


# Listing published web services — to debug Kopie 2026 where the page naming
# convention is inconsistent (Customer works, PLX_Customer doesn't, etc.). The
# OData service document at the company root returns the canonical list.


@pytest.mark.asyncio
@respx.mock
async def test_list_services_returns_service_document_entries():
    """NAV 2018 service document lives at OData root (NOT under Company('...'))
    — verified live against Kopie 2026. Parse it for the canonical service
    names actually exposed by the server."""
    service_doc_url = f"{BASE}/"
    respx.get(service_doc_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.context": f"{BASE}/$metadata",
                "value": [
                    {"name": "Customer", "kind": "EntitySet", "url": "Customer"},
                    {"name": "PLX_SalesOrder", "kind": "EntitySet", "url": "PLX_SalesOrder"},
                    {"name": "PLX_Item", "kind": "EntitySet", "url": "PLX_Item"},
                ],
            },
        ),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        services = await client.list_services()
    names = [s["name"] for s in services]
    assert "Customer" in names
    assert "PLX_SalesOrder" in names
    assert "PLX_Item" in names


@pytest.mark.asyncio
@respx.mock
async def test_list_services_returns_empty_on_404_without_crashing():
    service_doc_url = f"{BASE}/"
    respx.get(service_doc_url).mock(return_value=httpx.Response(404, text="Not Found"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        services = await client.list_services()
    assert services == []


# --- 404 graceful handling on master-data lookups ----------------------------
#
# Real-world bug observed against Kopie 2026 NAV: PLX_SalesOrder works (200)
# but PLX_Item returns 404 for filter queries — page exists but service-account
# can't reach it. Without graceful handling, the 404 crashes the LangGraph
# pipeline mid-flight (raise_for_status), bubbling as a 500 to the API caller.
# A single missing master-data lookup must not break order intake; degrade to
# "no match" instead.


@pytest.mark.asyncio
@respx.mock
async def test_get_item_returns_none_on_404():
    """When PLX_Item is misconfigured and returns 404, get_item must return
    None instead of raising — match_articles falls back to other strategies."""
    item_url = f"{BASE}/PLX_Item"
    respx.get(url__startswith=item_url).mock(return_value=httpx.Response(404, text="Not Found"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.get_item("804600")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_search_items_returns_empty_list_on_404():
    """search_items returning [] on 404 lets the matcher fall back to fuzzy
    description matching or flag for review."""
    item_url = f"{BASE}/PLX_Item"
    respx.get(url__startswith=item_url).mock(return_value=httpx.Response(404, text="Not Found"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.search_items(beschrijving="topcoat")
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_search_items_normalizes_nav_field_names():
    """PLX_Item exposes NAV-native field names (No, Description). Downstream
    code (artikelen API ItemOut, match_articles fuzzy) expects the BC aliases
    (number, displayName). The client must add them without losing originals.
    """
    item_url = f"{BASE}/PLX_Item"
    respx.get(url__startswith=item_url).mock(
        return_value=httpx.Response(200, json={"value": [
            {"No": "10010", "Description": "Materiaalslang 19x7", "Type": "Inventory"},
            {"No": "10011", "Description_2": "Only desc2 set"},
        ]})
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.search_items(beschrijving="slang")
    assert result[0]["number"] == "10010"
    assert result[0]["displayName"] == "Materiaalslang 19x7"
    assert result[0]["No"] == "10010"  # original preserved
    assert result[0]["Type"] == "Inventory"
    assert result[1]["number"] == "10011"
    assert result[1]["displayName"] == "Only desc2 set"  # fallback to Description_2


@pytest.mark.asyncio
@respx.mock
async def test_get_item_normalizes_nav_field_names():
    """Same normalization for the single-item lookup."""
    item_url = f"{BASE}/PLX_Item"
    respx.get(url__startswith=item_url).mock(
        return_value=httpx.Response(200, json={"value": [
            {"No": "20020", "Description": "Klem 12mm"},
        ]})
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.get_item("20020")
    assert result["number"] == "20020"
    assert result["displayName"] == "Klem 12mm"
    assert result["No"] == "20020"


@pytest.mark.asyncio
@respx.mock
async def test_search_customers_normalizes_nav_field_names():
    """PLX_Customer exposes No/Name/E_Mail. match_customer reads number/displayName.
    Aliases must be added without losing the NAV originals."""
    cust_url = f"{BASE}/PLX_Customer"
    respx.get(url__startswith=cust_url).mock(
        return_value=httpx.Response(200, json={"value": [
            {"No": "50000", "Name": "Groenhart Centraal Magazijn", "E_Mail": "orders@groenhart.nl"},
            {"No": "50010", "Name_2": "Only Name_2"},
        ]})
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.search_customers(email="orders@groenhart.nl")
    assert result[0]["number"] == "50000"
    assert result[0]["displayName"] == "Groenhart Centraal Magazijn"
    assert result[0]["email"] == "orders@groenhart.nl"
    assert result[0]["No"] == "50000"  # original preserved
    assert result[0]["E_Mail"] == "orders@groenhart.nl"  # original preserved
    assert result[1]["number"] == "50010"
    assert result[1]["displayName"] == "Only Name_2"  # falls back to Name_2


@pytest.mark.asyncio
@respx.mock
async def test_search_customers_returns_empty_list_on_404():
    """Same robustness applies to customer lookup."""
    cust_url = f"{BASE}/PLX_Customer"
    respx.get(url__startswith=cust_url).mock(return_value=httpx.Response(404, text="Not Found"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.search_customers(email="x@y.nl")
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_get_collection_returns_empty_list_on_404():
    """get_collection is used by master-sync scripts; 404 should yield []
    not crash the script."""
    url = f"{BASE}/PLX_ItemReference"
    respx.get(url__startswith=url).mock(return_value=httpx.Response(404, text="Not Found"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        result = await client.get_collection("PLX_ItemReference")
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_get_still_raises_on_500_for_real_server_errors():
    """500-class errors are real bugs in NAV or our request; do NOT swallow
    them — let the caller see the failure and surface it to logs/UI."""
    url = f"{BASE}/PLX_Item"
    respx.get(url__startswith=url).mock(return_value=httpx.Response(500, text="Server boom"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_item("804600")


@pytest.mark.asyncio
@respx.mock
async def test_get_still_raises_on_401_for_auth_errors():
    """401 indicates credential problems and must NOT be silently swallowed
    — the operator needs to see an obvious failure to fix the auth setup."""
    url = f"{BASE}/PLX_Item"
    respx.get(url__startswith=url).mock(return_value=httpx.Response(401, text="Unauthorized"))
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_item("804600")


@pytest.mark.asyncio
@respx.mock
async def test_company_querystring_is_added_to_get_requests():
    """Core invariant of the URL-convention switch: every NAV request carries
    `?company=<name>` so NAV 2018 can route to the right tenant data."""
    base = f"{BASE}/PLX_Item"
    route = respx.get(url__startswith=base).mock(
        return_value=httpx.Response(200, json={"value": []}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        await client.search_items(beschrijving="x")
    sent = route.calls.last.request
    assert sent.url.params.get("company") == COMPANY
    # And $filter is preserved alongside it (not overwritten).
    assert "$filter" in sent.url.params


@pytest.mark.asyncio
@respx.mock
async def test_company_querystring_is_added_to_post_and_patch():
    """POST and PATCH must also carry the company querystring."""
    post_route = respx.post(url__startswith=f"{BASE}/PLX_SalesOrder").mock(
        return_value=httpx.Response(201, json={"No": "SO99"}),
    )
    patch_route = respx.patch(url__startswith=f"{BASE}/PLX_SalesOrder('SO99')").mock(
        return_value=httpx.Response(200, json={"No": "SO99"}),
    )
    async with httpx.AsyncClient() as raw:
        client = _client(raw)
        ops: list[NavOperation] = [
            {"op": "POST", "path": "/salesOrders",
             "body": {"customerNumber": "10009"}, "label": "h"},
            {"op": "PATCH", "path": "/salesOrders({id})",
             "body": {"shipToCode": "MAIN"}, "label": "s"},
        ]
        await client.create_sales_order_stepwise(ops)
    assert post_route.calls.last.request.url.params.get("company") == COMPANY
    assert patch_route.calls.last.request.url.params.get("company") == COMPANY
