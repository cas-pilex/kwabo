"""Regression tests for Bug 4: stepwise sales-order create must dedup on
externalDocumentNumber.

The legacy `create_sales_order` already had this guard (navision_real.py:226-239),
but `create_sales_order_stepwise` — the path the new pipeline uses — did not.
That meant a re-push of the same email would unique-key-violate on real NAV
and produce a confusing error rather than the expected idempotent return.

The fix runs the dedup check before executing any operation, by inspecting the
composed op-list for an externalDocumentNumber PATCH and querying NAV (mock or
real) for a pre-existing record. If found, we return a deduped StepwiseResult
without executing any further operations.
"""
from __future__ import annotations

import pytest

from kwabo.integrations.navision_api import MockNavisionClient


CUSTOMER_NR = "10001"
ITEM_NR = "1515155"
EXTERNAL_DOC_NR = "PO-DEDUP-1"


def _ops_for_external(external: str | None) -> list[dict]:
    """A minimal stepwise sequence with optional externalDocumentNumber."""
    ops: list[dict] = [
        {"op": "POST", "path": "/salesOrders",
         "body": {"customerNumber": CUSTOMER_NR}, "label": "header"},
    ]
    if external is not None:
        ops.append({
            "op": "PATCH", "path": "/salesOrders({id})",
            "body": {"externalDocumentNumber": external},
            "label": f"PO {external}",
        })
    ops.extend([
        {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
         "body": {"lineType": "Item", "itemNumber": ITEM_NR}, "label": "line"},
        {"op": "PATCH", "path": "/salesOrderLines({id})",
         "body": {"quantity": 5}, "label": "qty"},
    ])
    return ops


@pytest.mark.asyncio
async def test_stepwise_dedup_returns_existing_order_on_repush(tmp_path):
    """Pushing the same composed ops twice must re-use the first order, not
    create a second header with the same externalDocumentNumber."""
    client = MockNavisionClient(out_dir=tmp_path)
    ops = _ops_for_external(EXTERNAL_DOC_NR)

    first = await client.create_sales_order_stepwise(ops)
    for r in first["operation_results"]:
        assert "error" not in r, f"first push errored: {r}"
    assert first["sales_order_number"], "first push must produce a number"
    first_number = first["sales_order_number"]

    # Second push with the same op-list should detect the duplicate and
    # return the existing order's identity without executing any ops.
    second = await client.create_sales_order_stepwise(ops)
    assert second["sales_order_number"] == first_number, (
        "second push must return the same sales-order number (dedup)"
    )
    # Only one underlying record was created.
    assert len(client._orders) == 1, (
        "expected exactly one stored order after re-push, "
        f"got {len(client._orders)}"
    )
    # The deduped result reports it took the dedup path: no ops executed.
    assert second["operation_results"] == [] or all(
        r.get("status") == 200 and "deduped" in str(r.get("response_body", "")).lower()
        or r.get("dedup", False)
        for r in second["operation_results"]
    ), (
        "deduped result should signal dedup either via empty ops list "
        "or per-op dedup markers; got: "
        f"{second['operation_results']!r}"
    )


@pytest.mark.asyncio
async def test_stepwise_no_dedup_when_external_doc_number_absent(tmp_path):
    """No externalDocumentNumber in the ops -> no dedup query -> two pushes
    produce two distinct orders."""
    client = MockNavisionClient(out_dir=tmp_path)
    ops = _ops_for_external(None)

    first = await client.create_sales_order_stepwise(ops)
    second = await client.create_sales_order_stepwise(ops)
    assert first["sales_order_number"] != second["sales_order_number"], (
        "without externalDocumentNumber, the second push must create a new order"
    )
    assert len(client._orders) == 2


@pytest.mark.asyncio
async def test_stepwise_no_dedup_when_external_doc_number_differs(tmp_path):
    """Two pushes with different externalDocumentNumber -> two distinct orders."""
    client = MockNavisionClient(out_dir=tmp_path)
    first = await client.create_sales_order_stepwise(_ops_for_external("PO-A"))
    second = await client.create_sales_order_stepwise(_ops_for_external("PO-B"))
    assert first["sales_order_number"] != second["sales_order_number"]
    assert len(client._orders) == 2
