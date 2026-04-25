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
_INCOMING_DOC_ID_PLACEHOLDER = re.compile(r"\{incoming_document_id\}")


# Body-key convention for the stepwise clients:
# Keys whose name begins with an underscore are "markers" — directives the
# composer leaves in the body for the stepwise client to interpret (e.g.
# `_attachment_path` in an /attachments POST tells the client to read the
# named file from disk and substitute it for the actual upload payload).
# These keys are NEVER sent to NAV; both the mock and real clients strip
# them before transport, and the per-op invariant checks below ignore them
# entirely. This mirrors how the mock already strips `_customer_mixprijzen`
# / `_item_mixprijzen` flags from response bodies.
def _public_keys(body: dict) -> list[str]:
    return [k for k in body.keys() if not k.startswith("_")]


def _assert_op_invariants(idx: int, op: NavOperation) -> None:
    """Strict per-operation contract checks. Raises ValueError on violation.

    Enforced rules (counts ignore keys whose name begins with `_`):
      * method must be POST or PATCH
      * path must start with '/'
      * POST /salesOrders body must contain exactly {'customerNumber'}
      * POST .../salesOrderLines body must contain exactly
        {'lineType', 'itemNumber'}
      * PATCH body must contain exactly one (non-underscore) key
    """
    method = op["op"]
    raw_path = op["path"]
    body = op.get("body") or {}
    public_keys = _public_keys(body)
    if method not in ("POST", "PATCH"):
        raise ValueError(f"op[{idx}]: unsupported method {method!r}")
    if not raw_path.startswith("/"):
        raise ValueError(f"op[{idx}]: path must start with '/', got {raw_path!r}")
    if method == "POST":
        if raw_path == "/salesOrders":
            if public_keys != ["customerNumber"]:
                raise ValueError(
                    f"op[{idx}]: POST /salesOrders body must contain exactly "
                    f"'customerNumber'; got {sorted(public_keys)}"
                )
        elif raw_path.endswith("/salesOrderLines"):
            allowed = {"lineType", "itemNumber"}
            if set(public_keys) != allowed:
                raise ValueError(
                    f"op[{idx}]: POST {raw_path} body must contain exactly "
                    f"{sorted(allowed)}; got {sorted(public_keys)}"
                )
    elif method == "PATCH":
        if len(public_keys) != 1:
            raise ValueError(
                f"op[{idx}]: PATCH body must contain exactly one key; got {sorted(public_keys)}"
            )


def _substitute_path(
    path: str,
    current_id: str,
    incoming_document_id: str = "",
) -> str:
    """Replace path placeholders. Raises if a required parent is missing.

    Supported placeholders:
      * `{id}` — substituted with `current_id`. Caller decides whether that
        is the most-recently-POSTed sales-order id or sales-order-line id
        based on the path being executed.
      * `{incoming_document_id}` — substituted with the id captured from the
        most-recently-POSTed `/incomingDocuments` response. Only the
        attachment-upload step needs this; if the placeholder appears but
        no incoming-document POST has run we raise ValueError, same as `{id}`.
    """
    out = path
    if "{id}" in out:
        if not current_id:
            raise ValueError(
                f"path {path!r} contains {{id}} but no parent id has been created yet"
            )
        out = _ID_PLACEHOLDER.sub(current_id, out)
    if "{incoming_document_id}" in out:
        if not incoming_document_id:
            raise ValueError(
                f"path {path!r} contains {{incoming_document_id}} but no "
                f"/incomingDocuments POST has run yet"
            )
        out = _INCOMING_DOC_ID_PLACEHOLDER.sub(incoming_document_id, out)
    return out


def _substitute_body_values(body: dict, incoming_document_id: str = "") -> dict:
    """Return a copy of `body` with placeholder string values resolved.

    Today the only supported placeholder is the literal string
    `"{incoming_document_id}"`, which is replaced with the id captured from
    the most-recently-POSTed `/incomingDocuments` response. The composer
    emits this for the `incomingDocumentNumber` PATCH because the id is
    not known at compose time.

    If the placeholder appears but no incoming-document POST has run, we
    raise ValueError so the caller surfaces a clear error rather than
    sending the literal placeholder over the wire.
    """
    out: dict = {}
    for k, v in body.items():
        if isinstance(v, str) and v == "{incoming_document_id}":
            if not incoming_document_id:
                raise ValueError(
                    f"body field {k!r} contains {{incoming_document_id}} but no "
                    f"/incomingDocuments POST has run yet"
                )
            out[k] = incoming_document_id
        else:
            out[k] = v
    return out


def _strip_marker_keys(body: dict) -> dict:
    """Drop keys whose name begins with `_` (composer-side directives).

    Marker keys travel with the operation so the stepwise client can act
    on them (e.g. `_attachment_path` -> read file from disk) but they are
    NEVER serialized to NAV.
    """
    return {k: v for k, v in body.items() if not k.startswith("_")}


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
