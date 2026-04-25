"""Trigger-aware NAV operation types and their shared invariant helpers.

The "stepwise" NAV client (see RealNavisionClient.create_sales_order_stepwise
and MockNavisionClient.create_sales_order_stepwise) executes a chronologically
ordered list of NavOperation entries — a POST on /salesOrders, then a series
of single-field PATCHes — so that every NAV OnValidate / OnInsert trigger
fires exactly as if a human typed the values into the NAV UI.

The TypedDicts below describe operation/result shapes; the helpers at the
bottom (`_assert_op_invariants`, `_substitute_path`, `_diff_autofilled`)
implement the per-operation contract that BOTH the real and mock stepwise
clients enforce. Keeping them here avoids duplication between the two
clients while still letting nav_operations stay free of any I/O.
"""
from __future__ import annotations

import re
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


# --------- shared helpers (used by both mock and real stepwise paths) ---------
# These are intentionally module-level rather than class methods: the same
# invariants must apply identically across MockNavisionClient and
# RealNavisionClient, and pulling them up here keeps the two clients honest
# without forcing a base class on either.

_ID_PLACEHOLDER = re.compile(r"\{id\}")


def _assert_op_invariants(idx: int, op: NavOperation) -> None:
    """Strict per-operation contract checks. Raises ValueError on violation.

    Enforced rules:
      * method must be POST or PATCH
      * path must start with '/'
      * POST /salesOrders body must contain exactly {'customerNumber'}
      * POST .../salesOrderLines body must contain exactly
        {'lineType', 'itemNumber'}
      * PATCH body must contain exactly one key
    """
    method = op["op"]
    raw_path = op["path"]
    body = op.get("body") or {}
    if method not in ("POST", "PATCH"):
        raise ValueError(f"op[{idx}]: unsupported method {method!r}")
    if not raw_path.startswith("/"):
        raise ValueError(f"op[{idx}]: path must start with '/', got {raw_path!r}")
    if method == "POST":
        if raw_path == "/salesOrders":
            if list(body.keys()) != ["customerNumber"]:
                raise ValueError(
                    f"op[{idx}]: POST /salesOrders body must contain exactly "
                    f"'customerNumber'; got {sorted(body)}"
                )
        elif raw_path.endswith("/salesOrderLines"):
            allowed = {"lineType", "itemNumber"}
            if set(body.keys()) != allowed:
                raise ValueError(
                    f"op[{idx}]: POST {raw_path} body must contain exactly "
                    f"{sorted(allowed)}; got {sorted(body)}"
                )
    elif method == "PATCH":
        if len(body) != 1:
            raise ValueError(
                f"op[{idx}]: PATCH body must contain exactly one key; got {sorted(body)}"
            )


def _substitute_path(path: str, current_id: str) -> str:
    """Replace `{id}` in `path` with `current_id`. Raises if no parent exists."""
    if "{id}" not in path:
        return path
    if not current_id:
        raise ValueError(
            f"path {path!r} contains {{id}} but no parent id has been created yet"
        )
    return _ID_PLACEHOLDER.sub(current_id, path)


def _diff_autofilled(sent_body: dict, server_record: dict) -> dict:
    """Return the fields NAV populated for us via triggers.

    Excludes any field we explicitly sent in the request body (those are
    echoed back by NAV but did not come from a trigger), OData metadata
    keys, and empty defaults that are noise rather than autofill.
    """
    if not isinstance(server_record, dict):
        return {}
    out: dict = {}
    for k, v in server_record.items():
        if k in sent_body or k.startswith("@odata") or k.startswith("_"):
            continue
        if v in (None, "", 0, False, []):
            continue
        out[k] = v
    return out
