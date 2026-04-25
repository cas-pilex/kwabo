"""Pure-types module describing the shape of trigger-aware NAV operations.

The "stepwise" NAV client (see RealNavisionClient.create_sales_order_stepwise
and MockNavisionClient.create_sales_order_stepwise) executes a chronologically
ordered list of NavOperation entries — a POST on /salesOrders, then a series
of single-field PATCHes — so that every NAV OnValidate / OnInsert trigger
fires exactly as if a human typed the values into the NAV UI.

Keep this file logic-free. The codebase otherwise leans on plain dicts, so we
use TypedDicts here to stay consistent and to avoid adding pydantic just for
typing.
"""
from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class NavOperation(TypedDict):
    """A single NAV write operation in a stepwise create-order plan.

    Fields:
      op:      "POST" or "PATCH". POSTs create entities; PATCHes update one
               field at a time so NAV's OnValidate triggers fire per field.
      path:    Resource path relative to /companies({id})/. May contain a
               literal "{id}" placeholder which is substituted with the
               id of the most-recently-POSTed parent entity (sales order
               for /salesOrders/... operations, sales-order line for
               /salesOrderLines/... operations).
      body:    For POST: the minimal seed fields that NAV requires — for
               /salesOrders that means {customerNumber: ...} only, for
               /salesOrderLines that means {lineType, itemNumber} only.
               For PATCH: EXACTLY one key. The stepwise client asserts this.
      label:   Human-readable description of the step (used in logs and
               in the dashboard preview, e.g. "Verzendadres kiezen
               (Ship-to Code)").
      expects: Optional. List of fields NAV must auto-fill after the step.
               When present on a PATCH, the stepwise client re-GETs the
               affected resource to capture/verify the autofilled values;
               when absent on a PATCH we skip the re-GET to minimise API
               round-trips.
    """

    op: Literal["POST", "PATCH"]
    path: str
    body: dict
    label: str
    expects: NotRequired[dict]


class NavOpResult(TypedDict):
    """The outcome of executing a single NavOperation.

    autofilled holds the diff between the post-operation server record and
    the body we sent — i.e. the fields NAV's triggers populated for us.
    error is set ONLY when the operation failed; the stepwise client stops
    executing further ops after the first error.
    """

    operation: NavOperation
    status: int
    response_body: dict
    autofilled: dict
    error: NotRequired[str]


class StepwiseResult(TypedDict):
    """Aggregate result returned from create_sales_order_stepwise."""

    sales_order_id: str
    sales_order_number: str
    operation_results: list[NavOpResult]
    nav_autofilled: dict
