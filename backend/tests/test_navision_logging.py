"""Regression tests for NAV stepwise observability.

When a stepwise op fails on real NAV we need every breadcrumb necessary to
post-mortem the failure: the request body we sent, the response status and
body we got back, the exception type, and the operation context (label,
method, path, index in the op-list). Without these the first real-NAV
errors during go-live are blind.

This file pins the structured-log shape emitted by the except-block in
`RealNavisionClient.create_sales_order_stepwise`.
"""
from __future__ import annotations

import httpx
import pytest
import structlog

from kwabo.integrations.navision_real import RealNavisionClient


@pytest.mark.asyncio
async def test_stepwise_logs_full_diagnostic_on_failure():
    """Force a 500 on the first PATCH; assert the structured log entry
    contains every field a debugger would want."""
    # Mock NAV: header POST succeeds, the externalDocumentNumber PATCH 500s.
    captured_request_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        # Bug 4 dedup-guard does a GET salesOrders first. Return empty so
        # the stepwise client proceeds.
        if request.method == "GET" and request.url.path.endswith("/salesOrders"):
            return httpx.Response(200, json={"value": []})
        if request.method == "POST" and request.url.path.endswith("/salesOrders"):
            return httpx.Response(
                201,
                json={"id": "so-1", "number": "SO-LOG-1",
                      "customerNumber": "10001"},
            )
        if request.method == "PATCH":
            try:
                import json as _json
                captured_request_bodies.append(_json.loads(request.content))
            except Exception:
                captured_request_bodies.append({})
            return httpx.Response(
                500,
                json={"error": {"code": "Internal_Error",
                                "message": "synthetic 500 from staging"}},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url="https://nav.example/test",
    )
    client = RealNavisionClient(
        base_url="https://nav.example/test/api/v2.0",
        company_id="test-co",
        auth_mode="basic",
        username="u",
        password="p",
        http_client=http_client,
    )

    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001"}, "label": "klant kiezen"},
        {"op": "PATCH", "path": "/salesOrders({id})",
         "body": {"externalDocumentNumber": "PO-LOG-1"},
         "label": "PO-nummer klant"},
    ]

    with structlog.testing.capture_logs() as logs:
        result = await client.create_sales_order_stepwise(ops)

    await http_client.aclose()

    # Result records the failure on the second op.
    op_results = result["operation_results"]
    assert len(op_results) == 2
    assert "error" not in op_results[0]
    assert op_results[1].get("error"), "second op should have errored"
    assert op_results[1]["status"] == 500

    # Find the failure log line. structlog's testing capture surfaces every
    # bound call as a dict.
    failure_logs = [r for r in logs if r.get("event") == "nav_stepwise_failure"]
    assert failure_logs, f"no nav_stepwise_failure log found; saw: {logs!r}"
    rec = failure_logs[-1]

    # Every diagnostic field a post-mortem needs.
    assert rec.get("op_index") == 1
    assert rec.get("op_label") == "PO-nummer klant"
    assert rec.get("op_method") == "PATCH"
    assert rec.get("op_path") == "/salesOrders({id})"
    # Request body — the exact data we sent NAV.
    assert rec.get("request_body") == {"externalDocumentNumber": "PO-LOG-1"}
    # Response details — what NAV gave back.
    assert rec.get("response_status") == 500
    response_body = rec.get("response_body")
    assert response_body, "response_body must be captured"
    assert "synthetic 500" in str(response_body)
    # Error classification.
    assert rec.get("error_type") == "HTTPStatusError"
    assert rec.get("error_message"), "error_message must be set"


@pytest.mark.asyncio
async def test_stepwise_log_truncates_huge_response_bodies():
    """A pathological 100KB error body must not flood the log; truncate at
    a reasonable upper bound (we cap around 2KB)."""
    huge = "x" * 100_000

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/salesOrders"):
            return httpx.Response(500, text=huge)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        transport=transport, base_url="https://nav.example/test"
    )
    client = RealNavisionClient(
        base_url="https://nav.example/test/api/v2.0",
        company_id="test-co",
        auth_mode="basic",
        username="u",
        password="p",
        http_client=http_client,
    )

    ops = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": "10001"}, "label": "klant kiezen"},
    ]

    with structlog.testing.capture_logs() as logs:
        await client.create_sales_order_stepwise(ops)

    await http_client.aclose()

    failure_logs = [r for r in logs if r.get("event") == "nav_stepwise_failure"]
    assert failure_logs
    rec = failure_logs[-1]
    body_str = str(rec.get("response_body", ""))
    assert len(body_str) <= 2500, (
        f"response_body in log must be truncated; got {len(body_str)} chars"
    )
