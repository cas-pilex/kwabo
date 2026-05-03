"""Navision API protocol + MockNavisionClient + stub for real client."""
from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import Callable, Optional, Protocol

from kwabo.config import settings
from kwabo.integrations.nav_mock_fixtures import (
    MOCK_CUSTOMERS,
    MOCK_ITEM_REFERENCES,
    MOCK_ITEM_UOMS,
    MOCK_ITEMS,
    MOCK_MIX_DISCOUNT_FACTOR,
    MOCK_MIX_THRESHOLD,
    MOCK_PRICES,
    MOCK_SHIP_TOS,
)
from kwabo.integrations.nav_operations import (
    NavOperation,
    NavOpResult,
    StepwiseResult,
    _assert_op_invariants,
    _diff_autofilled,
    _extract_external_doc_number,
    _strip_marker_keys,
    _substitute_body_values,
    _substitute_path,
)


class NavisionClient(Protocol):
    async def get_customer(self, nr: str) -> Optional[dict]: ...
    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]: ...
    async def get_item(self, nr: str) -> Optional[dict]: ...
    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]: ...
    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict: ...


# --------- mock-only helpers (URL parsing for the in-memory PATCH/POST routing) -

def _extract_id(path: str, segment: str) -> str:
    """Extract the id from a path like /salesOrders({id})/salesOrderLines."""
    m = re.search(rf"/{segment}\(([^)]+)\)", path)
    if not m:
        raise ValueError(f"could not extract {segment} id from {path!r}")
    return m.group(1)


def _extract_id_simple(endpoint: str, segment: str) -> str:
    m = re.match(rf"^{segment}\(([^)]+)\)$", endpoint)
    if not m:
        raise ValueError(f"endpoint {endpoint!r} did not match {segment}({{id}})")
    return m.group(1)


class MockNavisionClient:
    """In-memory Navision mock. Persists created orders to JSON on disk.

    The stepwise create_sales_order_stepwise simulates NAV's OnValidate /
    OnInsert trigger behaviour: POSTs return only the seed fields plus
    server-side autofill (customer name, payment terms, default UoM, …),
    and PATCHes that touch trigger-bearing fields cause downstream
    auto-population (e.g. PATCH shipToCode -> shipToAddress, shipToCity,
    shipToPostCode, shipToCountry). This is how we prove our pipeline
    no longer relies on the old multi-field POST that bypassed triggers.
    """

    # Failure injection hooks (used by tests). Set to a callable taking
    # (op_index, op) and returning either None (proceed) or an error string
    # (mock should mark this op as failed and stop the loop).
    _fail_predicate: Optional[Callable[[int, NavOperation], Optional[str]]] = None

    def __init__(self, out_dir: Path | None = None) -> None:
        self.customers = list(MOCK_CUSTOMERS)
        self.items = list(MOCK_ITEMS)
        self.ship_tos = {k: list(v) for k, v in MOCK_SHIP_TOS.items()}
        self.item_uoms = {k: list(v) for k, v in MOCK_ITEM_UOMS.items()}
        self.item_references = list(MOCK_ITEM_REFERENCES)
        self.prices = dict(MOCK_PRICES)
        self.out_dir = (out_dir or (settings.navision_mock_path / "orders")).resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # In-memory store keyed by sales-order id.
        self._orders: dict[str, dict] = {}
        # Incoming-document store (id -> record + attachments).
        self._incoming_documents: dict[str, dict] = {}

    async def get_customer(self, nr: str) -> Optional[dict]:
        return next((c for c in self.customers if c["number"] == nr), None)

    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        results = []
        for c in self.customers:
            if email and c.get("email", "").lower() == email.lower():
                results.append(c)
                continue
            if naam and naam.lower() in c.get("displayName", "").lower():
                results.append(c)
        return results

    async def get_item(self, nr: str) -> Optional[dict]:
        return next((i for i in self.items if i["number"] == nr), None)

    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]:
        if not beschrijving:
            return list(self.items)
        q = beschrijving.lower()
        return [i for i in self.items if q in i.get("displayName", "").lower()]

    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict:
        order_id = str(uuid.uuid4())
        order_nr = f"SO-{order_id[:8].upper()}"
        payload = {
            "id": order_id,
            "number": order_nr,
            "header": header,
            "lines": lines,
            "status": "Draft",
        }
        (self.out_dir / f"{order_nr}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return payload

    # ---------- new master-data lookups ----------

    async def get_ship_to_addresses(self, customer_id: str) -> list[dict]:
        # `customer_id` matches `number` in the mock for simplicity — the
        # real client uses the customer record id (guid). Tests pass the
        # customer number.
        return list(self.ship_tos.get(customer_id, []))

    async def get_item_uoms(self, item_id: str) -> list[dict]:
        return list(self.item_uoms.get(item_id, []))

    async def get_item_references(self, customer_no: str | None = None) -> list[dict]:
        if customer_no is None:
            return list(self.item_references)
        return [
            r for r in self.item_references
            if r.get("referenceType") == "Customer"
            and r.get("referenceTypeNo") == customer_no
        ]

    # ---------- new incoming-document endpoints ----------

    async def create_incoming_document(
        self, description: str, vendor_name: str | None
    ) -> dict:
        doc_id = str(uuid.uuid4())
        rec = {
            "id": doc_id,
            "description": description,
            "vendorName": vendor_name or "",
            "attachments": [],
        }
        self._incoming_documents[doc_id] = rec
        return rec

    async def attach_to_incoming_document(
        self, doc_id: str, filename: str, content: bytes, content_type: str
    ) -> dict:
        doc = self._incoming_documents.get(doc_id)
        if doc is None:
            raise KeyError(f"unknown incoming document {doc_id!r}")
        attachment = {
            "id": str(uuid.uuid4()),
            "fileName": filename,
            "mediaType": content_type,
            "content": base64.b64encode(content).decode("ascii"),
            "status": 200,
        }
        doc["attachments"].append(attachment)
        return attachment

    # ---------- single-field PATCH ----------

    async def patch(self, endpoint: str, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("patch body must be a dict")
        if len(body) != 1:
            raise ValueError(
                f"patch body must contain exactly one field; got {sorted(body)}"
            )
        return self._apply_patch(endpoint.lstrip("/"), body)

    # ---------- stepwise sales-order creation ----------

    async def create_sales_order_stepwise(
        self, operations: list[NavOperation]
    ) -> StepwiseResult:
        results: list[NavOpResult] = []
        autofilled_union: dict = {}
        sales_order_id: str = ""
        sales_order_number: str = ""
        last_line_id: str = ""
        last_incoming_doc_id: str = ""

        # Idempotency guard: if the composed ops set an externalDocumentNumber
        # and we already have a stored order with that number, short-circuit.
        # Real NAV's unique-key constraint would otherwise fail the second push.
        external = _extract_external_doc_number(list(operations))
        if external:
            existing = next(
                (
                    o for o in self._orders.values()
                    if o.get("externalDocumentNumber") == external
                ),
                None,
            )
            if existing:
                return {
                    "sales_order_id": existing["id"],
                    "sales_order_number": existing["number"],
                    "operation_results": [],
                    "nav_autofilled": {"_dedup": external},
                }

        for idx, op in enumerate(operations):
            method = op["op"]
            raw_path = op["path"]
            body = op.get("body") or {}

            # Per-op invariants — same rules as the real client.
            try:
                _assert_op_invariants(idx, op)
            except ValueError as exc:
                results.append({
                    "operation": op,
                    "status": 0,
                    "response_body": {},
                    "autofilled": {},
                    "error": str(exc),
                })
                return {
                    "sales_order_id": sales_order_id,
                    "sales_order_number": sales_order_number,
                    "operation_results": results,
                    "nav_autofilled": autofilled_union,
                }

            substitution_id = (
                last_line_id
                if ("/salesOrderLines(" in raw_path or raw_path.startswith("/salesOrderLines"))
                else sales_order_id
            )
            try:
                path = _substitute_path(raw_path, substitution_id, last_incoming_doc_id)
            except ValueError as exc:
                results.append({
                    "operation": op,
                    "status": 0,
                    "response_body": {},
                    "autofilled": {},
                    "error": str(exc),
                })
                return {
                    "sales_order_id": sales_order_id,
                    "sales_order_number": sales_order_number,
                    "operation_results": results,
                    "nav_autofilled": autofilled_union,
                }

            # Failure injection hook — used by tests to verify stop-on-error.
            if self._fail_predicate is not None:
                forced = self._fail_predicate(idx, op)
                if forced:
                    results.append({
                        "operation": op,
                        "status": 500,
                        "response_body": {},
                        "autofilled": {},
                        "error": forced,
                    })
                    return {
                        "sales_order_id": sales_order_id,
                        "sales_order_number": sales_order_number,
                        "operation_results": results,
                        "nav_autofilled": autofilled_union,
                    }

            # Resolve placeholder body values + strip composer-side marker keys
            # (`_attachment_path`, etc.) before handing to the in-memory router.
            try:
                resolved_body = _substitute_body_values(body, last_incoming_doc_id)
            except ValueError as exc:
                results.append({
                    "operation": op,
                    "status": 0,
                    "response_body": {},
                    "autofilled": {},
                    "error": str(exc),
                })
                return {
                    "sales_order_id": sales_order_id,
                    "sales_order_number": sales_order_number,
                    "operation_results": results,
                    "nav_autofilled": autofilled_union,
                }
            wire_body = _strip_marker_keys(resolved_body)

            try:
                if method == "POST":
                    server, status = self._apply_post(path, wire_body, body)
                    if path == "/salesOrders":
                        sales_order_id = server["id"]
                        sales_order_number = server["number"]
                    elif path.endswith("/salesOrderLines"):
                        last_line_id = server["id"]
                    elif path == "/incomingDocuments":
                        last_incoming_doc_id = server["id"]
                    autofilled = _diff_autofilled(wire_body, server)
                    results.append({
                        "operation": op,
                        "status": status,
                        "response_body": server,
                        "autofilled": autofilled,
                    })
                    autofilled_union.update(autofilled)
                else:  # PATCH
                    server = self._apply_patch(path.lstrip("/"), wire_body)
                    patch_autofilled: dict = {}
                    if op.get("expects"):
                        patch_autofilled = _diff_autofilled(wire_body, server)
                    results.append({
                        "operation": op,
                        "status": 200,
                        "response_body": server,
                        "autofilled": patch_autofilled,
                    })
                    autofilled_union.update(patch_autofilled)
            except Exception as exc:
                results.append({
                    "operation": op,
                    "status": 0,
                    "response_body": {},
                    "autofilled": {},
                    "error": f"{type(exc).__name__}: {exc}",
                })
                return {
                    "sales_order_id": sales_order_id,
                    "sales_order_number": sales_order_number,
                    "operation_results": results,
                    "nav_autofilled": autofilled_union,
                }

        # Persist the final order (matches the legacy mock's on-disk record).
        if sales_order_id and sales_order_id in self._orders:
            order_snapshot = self._orders[sales_order_id]
            (self.out_dir / f"{sales_order_number}.json").write_text(
                json.dumps(order_snapshot, indent=2, default=str), encoding="utf-8"
            )

        return {
            "sales_order_id": sales_order_id,
            "sales_order_number": sales_order_number,
            "operation_results": results,
            "nav_autofilled": autofilled_union,
        }

    # ---------- internal: per-endpoint trigger emulation ----------

    def _apply_post(
        self, path: str, body: dict, raw_body: dict | None = None
    ) -> tuple[dict, int]:
        # `body` is what we'd send to NAV (markers stripped, placeholders
        # resolved). `raw_body` retains composer-side markers like
        # `_attachment_path` so endpoints that need them (attachment upload)
        # can read them. For ordinary endpoints raw_body is unused.
        raw_body = raw_body if raw_body is not None else body
        if path == "/salesOrders":
            return self._post_sales_order(body), 201
        if path.endswith("/salesOrderLines"):
            # path looks like /salesOrders({id})/salesOrderLines
            order_id = _extract_id(path, "salesOrders")
            return self._post_sales_order_line(order_id, body), 201
        if path == "/incomingDocuments":
            return self._post_incoming_document(body), 201
        if path.endswith("/attachments") and "/incomingDocuments(" in path:
            doc_id = _extract_id(path, "incomingDocuments")
            return self._post_incoming_document_attachment(doc_id, body, raw_body), 201
        raise ValueError(f"mock POST not implemented for path {path!r}")

    def _post_incoming_document(self, body: dict) -> dict:
        """In-memory mirror of `create_incoming_document` for the stepwise path."""
        doc_id = str(uuid.uuid4())
        rec = {
            "id": doc_id,
            "description": body.get("description", ""),
            "vendorName": body.get("vendorName", ""),
            "attachments": [],
        }
        self._incoming_documents[doc_id] = rec
        return rec

    def _post_incoming_document_attachment(
        self, doc_id: str, body: dict, raw_body: dict
    ) -> dict:
        """Attach a file to an incoming document via the stepwise path.

        The composer hides the file path in `_attachment_path` (a marker
        key stripped before the wire body reaches NAV). When that marker
        is present we read the file from disk; otherwise we fall back to
        the explicit `content_base64` field if the caller has already
        encoded the bytes.
        """
        doc = self._incoming_documents.get(doc_id)
        if doc is None:
            raise ValueError(f"unknown incoming document {doc_id!r}")
        filename = body.get("fileName", "")
        attachment_path = raw_body.get("_attachment_path")
        if attachment_path:
            content_bytes = Path(attachment_path).read_bytes()
        elif body.get("content_base64"):
            content_bytes = base64.b64decode(body["content_base64"])
        else:
            content_bytes = b""
        attachment = {
            "id": str(uuid.uuid4()),
            "fileName": filename,
            "content": base64.b64encode(content_bytes).decode("ascii"),
            "status": 201,
        }
        doc["attachments"].append(attachment)
        return attachment

    def _post_sales_order(self, body: dict) -> dict:
        cust_no = body["customerNumber"]
        cust = next((c for c in self.customers if c["number"] == cust_no), None)
        if cust is None:
            raise ValueError(f"unknown customer {cust_no!r}")
        order_id = str(uuid.uuid4())
        order_nr = f"SO-{order_id[:8].upper()}"
        # NAV trigger emulation: customer-driven autofill.
        rec = {
            "id": order_id,
            "number": order_nr,
            "customerNumber": cust_no,
            "sellToCustomerName": cust["displayName"],
            "paymentTermsCode": cust.get("paymentTermsCode", ""),
            "currencyCode": cust.get("currencyCode", "EUR"),
            "shipToCode": cust.get("shipToCode", "MAIN"),
            "languageCode": cust.get("languageCode", "NLD"),
            "status": "Draft",
            "lines": [],
            "_customer_mixprijzen": cust.get("mixprijzen", False),
        }
        self._orders[order_id] = rec
        # Return a shallow copy without the private flag.
        return {k: v for k, v in rec.items() if not k.startswith("_")}

    def _post_sales_order_line(self, order_id: str, body: dict) -> dict:
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"unknown sales order {order_id!r}")
        item_no = body["itemNumber"]
        item = next((i for i in self.items if i["number"] == item_no), None)
        if item is None:
            raise ValueError(f"unknown item {item_no!r}")
        line_id = str(uuid.uuid4())
        line = {
            "id": line_id,
            "documentId": order_id,
            "lineType": body["lineType"],
            "itemNumber": item_no,
            "description": item["displayName"],
            "unitOfMeasureCode": item.get("baseUnitOfMeasureCode", "STUK"),
            "unitPrice": self.prices.get(item_no, 0.0),
            "quantity": 0,
            "_item_mixprijzen": item.get("mixprijzen", False),
        }
        order["lines"].append(line)
        return {k: v for k, v in line.items() if not k.startswith("_")}

    def _apply_patch(self, endpoint: str, body: dict) -> dict:
        # Endpoint forms we handle:
        #   salesOrders({id})            -> header field PATCH
        #   salesOrderLines({id})        -> line field PATCH
        if endpoint.startswith("salesOrders(") and "/" not in endpoint:
            order_id = _extract_id_simple(endpoint, "salesOrders")
            return self._patch_sales_order(order_id, body)
        if endpoint.startswith("salesOrderLines(") and "/" not in endpoint:
            line_id = _extract_id_simple(endpoint, "salesOrderLines")
            return self._patch_sales_order_line(line_id, body)
        raise ValueError(f"mock PATCH not implemented for endpoint {endpoint!r}")

    def _patch_sales_order(self, order_id: str, body: dict) -> dict:
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"unknown sales order {order_id!r}")
        (key, value), = body.items()
        order[key] = value
        # Trigger emulation: shipToCode change -> autofill address fields.
        if key == "shipToCode":
            cust_no = order["customerNumber"]
            ship = next(
                (s for s in self.ship_tos.get(cust_no, []) if s["code"] == value),
                None,
            )
            if ship:
                order["shipToName"] = ship["name"]
                order["shipToAddress"] = ship["address"]
                order["shipToCity"] = ship["city"]
                order["shipToPostCode"] = ship["postCode"]
                order["shipToCountry"] = ship["country"]
        return {k: v for k, v in order.items() if not k.startswith("_")}

    def _patch_sales_order_line(self, line_id: str, body: dict) -> dict:
        # Find the line across all known orders.
        for order in self._orders.values():
            for line in order["lines"]:
                if line["id"] == line_id:
                    (key, value), = body.items()
                    line[key] = value
                    # Trigger emulation: quantity change -> mix-discount rule.
                    # Real NAV's mix-staffel codeunit only fires when the line's
                    # UOM is a registered mix-UOM (qtyPerUnitOfMeasure > 1.0).
                    # Discounting on quantity alone would hide composer bugs
                    # where the wrong UOM is patched.
                    if key == "quantity":
                        cust_mix = order.get("_customer_mixprijzen", False)
                        item_mix = line.get("_item_mixprijzen", False)
                        current_uom = line.get("unitOfMeasureCode", "")
                        is_mix_uom = self._is_mix_uom_for_item(
                            line["itemNumber"], current_uom
                        )
                        if (
                            cust_mix and item_mix and is_mix_uom
                            and isinstance(value, (int, float))
                            and value >= MOCK_MIX_THRESHOLD
                        ):
                            base = self.prices.get(line["itemNumber"], 0.0)
                            line["unitPrice"] = round(
                                base * MOCK_MIX_DISCOUNT_FACTOR, 4
                            )
                    return {k: v for k, v in line.items() if not k.startswith("_")}
        raise ValueError(f"unknown sales-order line {line_id!r}")

    def _is_mix_uom_for_item(self, item_number: str, uom_code: str) -> bool:
        """True iff the UOM code is registered as a mix-UOM for the item.

        An alternate UOM with qtyPerUnitOfMeasure > 1.0 counts. Items without
        UoM fixtures fall back to "any UOM qualifies" so we don't break items
        that simply lack mock data; items that have only a base UOM also
        qualify (the base is the only UOM the item supports)."""
        uoms = self.item_uoms.get(item_number, [])
        if not uoms:
            return True
        alternates = [u for u in uoms if u.get("qtyPerUnitOfMeasure", 1.0) > 1.0]
        if not alternates:
            return True
        return any(u.get("code") == uom_code for u in alternates)


def get_navision_client() -> NavisionClient:
    mode = settings.navision_mode
    if mode == "mock":
        return MockNavisionClient()
    if mode == "replay":
        from kwabo.integrations.navision_real import ReplayNavisionClient
        from pathlib import Path
        fixture = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "navision_replay.json"
        return ReplayNavisionClient(fixture)
    if mode == "real":
        from kwabo.integrations.navision_real import RealNavisionClient
        return RealNavisionClient()
    raise ValueError(f"Unknown NAVISION_MODE: {mode}")


# `build_sales_order_payload` removed in T9. Callers now use
# `kwabo.integrations.navision_steps.compose_navision_operations` to build the
# trigger-aware NavOperation list, which both push_navision (executes via
# create_sales_order_stepwise) and the /api/orders/{id}/navision-preview
# endpoint (returns to the dashboard) share.
