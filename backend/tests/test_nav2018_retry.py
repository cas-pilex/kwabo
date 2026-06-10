"""Fase 4 (B2): retry/backoff voor idempotente GETs in Nav2018ODataClient.

Transiente 429/5xx/transportfouten op GETs worden opnieuw geprobeerd
(exponentieel, Retry-After gerespecteerd); POST/PATCH nooit (niet idempotent —
een herhaalde order-POST zou dubbele orders maken). Alles via
httpx.MockTransport geïnjecteerd in de constructor (geen echte sockets).
"""
from __future__ import annotations

import httpx
import pytest

from kwabo.integrations import navision_nav2018
from kwabo.integrations.navision_nav2018 import Nav2018ODataClient

ITEM_OK = {"value": [{"No": "238601", "Description": "Quality Covers"}]}


def make_client(handler, **kw) -> Nav2018ODataClient:
    return Nav2018ODataClient(
        base_url="http://nav.test/ODataV4",
        company="Kopie 2026",
        username="u",
        password="p",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kw,
    )


@pytest.mark.asyncio
async def test_get_retryt_429_en_slaagt(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429)
        return httpx.Response(200, json=ITEM_OK)

    client = make_client(handler, retry_base_delay=0)
    item = await client.get_item("238601")
    assert item is not None and item["number"] == "238601"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_400_wordt_niet_geretryd():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = make_client(handler, retry_base_delay=0)
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_item("238601")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_post_en_patch_worden_nooit_geretryd():
    """Niet-idempotent: een geretryde POST kan een dubbele NAV-order maken."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = make_client(handler, retry_base_delay=0)
    with pytest.raises(httpx.HTTPStatusError):
        await client._post("http://nav.test/ODataV4/PLX_SalesOrder", {"x": 1})
    assert calls["n"] == 1

    calls["n"] = 0
    with pytest.raises(httpx.HTTPStatusError):
        await client._patch("http://nav.test/ODataV4/PLX_SalesOrder('A')", {"x": 1})
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_transportfout_wordt_geretryd():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json=ITEM_OK)

    client = make_client(handler, retry_base_delay=0)
    item = await client.get_item("238601")
    assert item is not None
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_after_header_wordt_gerespecteerd(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(navision_nav2018.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=ITEM_OK)

    client = make_client(handler, retry_base_delay=0)
    item = await client.get_item("238601")
    assert item is not None
    assert slept == [7.0]  # header wint van (0s) exponentiële backoff


@pytest.mark.asyncio
async def test_paginatie_nextlink_retryt_ook():
    calls = {"n": 0, "next_fails": 0}
    page1 = {"value": [{"No": "1"}],
             "@odata.nextLink": "http://nav.test/ODataV4/PLX_Item?$skiptoken=1"}
    page2 = {"value": [{"No": "2"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "skiptoken" in str(request.url):
            calls["next_fails"] += 1
            if calls["next_fails"] == 1:
                return httpx.Response(503)
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    client = make_client(handler, retry_base_delay=0)
    rows = await client.get_collection("PLX_Item")
    assert [r["No"] for r in rows] == ["1", "2"]
    assert calls["n"] == 3  # pagina 1 + (503 + 200) op de nextLink


@pytest.mark.asyncio
async def test_uitputting_na_drie_pogingen():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = make_client(handler, retry_base_delay=0)
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_item("238601")
    assert calls["n"] == 3  # default nav_get_retry_attempts = 3
