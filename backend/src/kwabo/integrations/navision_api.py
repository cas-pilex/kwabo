"""Navision API protocol + MockNavisionClient + stub for real client."""
from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Callable, Optional, Protocol

from kwabo.config import settings
from kwabo.integrations.nav_operations import (
    NavOperation,
    NavOpResult,
    StepwiseResult,
)


class NavisionClient(Protocol):
    async def get_customer(self, nr: str) -> Optional[dict]: ...
    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]: ...
    async def get_item(self, nr: str) -> Optional[dict]: ...
    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]: ...
    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict: ...


# Seed gebaseerd op de 17 voorbeelden. Mock = in-memory + persist naar json.
# `mixprijzen` flags drive the trigger-aware mock pricing rule (see
# MockNavisionClient.create_sales_order_stepwise): mix-discount applies only
# when BOTH the customer and the item carry the mixprijzen flag AND the line
# quantity reaches the pallet-staffel threshold.
MOCK_CUSTOMERS: list[dict] = [
    {"number": "10001", "displayName": "Ferney Diabolo B.V.", "email": "purchaseorders@ferney.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": True},
    {"number": "10002", "displayName": "TABS / PontMeyer", "email": "supplychain@tabsholland.nl",
     "paymentTermsCode": "14D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10003", "displayName": "Isero Ijzerwaren B.V.", "email": "fransvanvliet@isero.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": True},
    {"number": "10004", "displayName": "BMN Bouwmaterialen", "email": "jeroen.vanschooten@bmn.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10005", "displayName": "Omtzigt Bouw", "email": "kg@omtzigt-bouwmaterialen.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10006", "displayName": "Driessen Verf b.v.", "email": "bestellenhelmond@driessenverf.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10007", "displayName": "Stukbouw B.V.", "email": "willy@stukbouw.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10008", "displayName": "Enka Bouwmaterialen", "email": "e.sun@enkabouwmarkt.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10009", "displayName": "Connect Products GmbH", "email": "patricia@connectproducts.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10010", "displayName": "Storch-Ciret GmbH", "email": "s.wilke@storch-ciret.com",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10011", "displayName": "Kirchner GmbH", "email": "tobias.leyhausen@kirchner-online.com",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10012", "displayName": "Werkzeuge Dietrich GmbH & Co. KG", "email": "malte.klippstein@werkzeuge-dietrich.de",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10013", "displayName": "Bugel AG", "email": "r.carvalho@bugel.ch",
     "paymentTermsCode": "30D", "currencyCode": "CHF", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10014", "displayName": "BAUHAUS", "email": "supplier@bahag.com",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10015", "displayName": "Tectis OU", "email": "maarjaliisa.nomm@tectis.ee",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "ENU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10016", "displayName": "L. De Vos sa/nv", "email": "anja@lucdevos.be",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLB",
     "shipToCode": "MAIN", "mixprijzen": False},
]

MOCK_ITEMS: list[dict] = [
    {"number": "1515155", "displayName": "Ferney stucloper 120cm",
     "baseUnitOfMeasureCode": "ROL", "mixprijzen": True},
    {"number": "228321", "displayName": "TABS hoeknaald 260cm",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "2597768", "displayName": "Isero topcoat 20kg",
     "baseUnitOfMeasureCode": "EMMER", "mixprijzen": True},
    {"number": "201291", "displayName": "BMN pallet 1",
     "baseUnitOfMeasureCode": "PAL", "mixprijzen": False},
    {"number": "83461", "displayName": "BMN kist statiegeld",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "122338", "displayName": "BAUHAUS product",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "47323", "displayName": "Tectis Proshield private label",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "975097", "displayName": "L. De Vos Greenboard B1 75m2",
     "baseUnitOfMeasureCode": "M2", "mixprijzen": False},
    {"number": "CICS-100-25", "displayName": "Werkzeuge Dietrich coating",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-OMTZIGT", "displayName": "Omtzigt product",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-DRIESSEN", "displayName": "Driessen Verf product",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-KIRCHNER-238534", "displayName": "Kirchner FORCH editie",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-BUGEL", "displayName": "Bugel Zwitserse editie",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "SOFTBREATH-PALLET", "displayName": "Softbreath pallet",
     "baseUnitOfMeasureCode": "PAL", "mixprijzen": True},
]


# Default unit price per item, used by the mock's POST /salesOrderLines trigger
# emulation. Keep small — only items that the new tests touch need entries.
MOCK_PRICES: dict[str, float] = {
    "1515155": 100.0,
    "228321": 12.5,
    "2597768": 80.0,
    "201291": 250.0,
    "975097": 35.0,
    "SOFTBREATH-PALLET": 500.0,
}


# Pallet-staffel mix discount kicks in once a single line reaches this
# quantity AND both customer + item are mixprijzen=True.
MOCK_MIX_THRESHOLD: int = 24
MOCK_MIX_DISCOUNT_FACTOR: float = 0.9


# Ship-to addresses keyed by customer number. Each customer has at least
# the implicit "MAIN" address; some have extras to exercise the dropdown.
MOCK_SHIP_TOS: dict[str, list[dict]] = {
    "10001": [
        {"code": "MAIN", "name": "Ferney Diabolo B.V.",
         "address": "Industrieweg 1", "city": "Amsterdam",
         "postCode": "1000 AA", "country": "NL"},
        {"code": "DC-EAST", "name": "Ferney DC Oost",
         "address": "Logistiekpark 12", "city": "Apeldoorn",
         "postCode": "7300 BB", "country": "NL"},
    ],
    "10003": [
        {"code": "MAIN", "name": "Isero HQ",
         "address": "IJzerstraat 5", "city": "Rotterdam",
         "postCode": "3000 CC", "country": "NL"},
    ],
    "10013": [
        {"code": "MAIN", "name": "Bugel AG",
         "address": "Hauptstrasse 9", "city": "Zürich",
         "postCode": "8000", "country": "CH"},
    ],
}


# Item UoMs keyed by item number. The base UoM is repeated here with
# qtyPerUnitOfMeasure=1.0; alternates carry their conversion factor.
MOCK_ITEM_UOMS: dict[str, list[dict]] = {
    "1515155": [
        {"code": "ROL", "qtyPerUnitOfMeasure": 1.0},
        {"code": "PAL", "qtyPerUnitOfMeasure": 24.0},
    ],
    "228321": [
        {"code": "STUK", "qtyPerUnitOfMeasure": 1.0},
        {"code": "DOOS", "qtyPerUnitOfMeasure": 50.0},
    ],
    "2597768": [
        {"code": "EMMER", "qtyPerUnitOfMeasure": 1.0},
        {"code": "PAL", "qtyPerUnitOfMeasure": 33.0},
    ],
}


# Item references (cross-references): customer-specific item codes that map
# to a Kwabo item number. Used by the order-review UI to suggest a match
# when the email shows the customer's own SKU.
MOCK_ITEM_REFERENCES: list[dict] = [
    {"itemNumber": "1515155", "referenceType": "Customer",
     "referenceTypeNo": "10001", "referenceNo": "FER-STUC-120"},
    {"itemNumber": "2597768", "referenceType": "Customer",
     "referenceTypeNo": "10003", "referenceNo": "ISE-TC-20"},
]


# --------- shared helpers (used by both mock and real stepwise paths) ----------
import re as _re  # noqa: E402

_ID_PLACEHOLDER = _re.compile(r"\{id\}")


def _assert_op_invariants(idx: int, op: NavOperation) -> None:
    """Strict per-operation contract checks. Raises ValueError on violation."""
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
    if "{id}" not in path:
        return path
    if not current_id:
        raise ValueError(
            f"path {path!r} contains {{id}} but no parent id has been created yet"
        )
    return _ID_PLACEHOLDER.sub(current_id, path)


def _diff_autofilled(sent_body: dict, server_record: dict) -> dict:
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


def _extract_id(path: str, segment: str) -> str:
    """Extract the id from a path like /salesOrders({id})/salesOrderLines."""
    m = _re.search(rf"/{segment}\(([^)]+)\)", path)
    if not m:
        raise ValueError(f"could not extract {segment} id from {path!r}")
    return m.group(1)


def _extract_id_simple(endpoint: str, segment: str) -> str:
    m = _re.match(rf"^{segment}\(([^)]+)\)$", endpoint)
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
                path = _substitute_path(raw_path, substitution_id)
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

            try:
                if method == "POST":
                    server, status = self._apply_post(path, body)
                    if path == "/salesOrders":
                        sales_order_id = server["id"]
                        sales_order_number = server["number"]
                    elif path.endswith("/salesOrderLines"):
                        last_line_id = server["id"]
                    autofilled = _diff_autofilled(body, server)
                    results.append({
                        "operation": op,
                        "status": status,
                        "response_body": server,
                        "autofilled": autofilled,
                    })
                    autofilled_union.update(autofilled)
                else:  # PATCH
                    server = self._apply_patch(path.lstrip("/"), body)
                    autofilled: dict = {}
                    if op.get("expects"):
                        autofilled = _diff_autofilled(body, server)
                    results.append({
                        "operation": op,
                        "status": 200,
                        "response_body": server,
                        "autofilled": autofilled,
                    })
                    autofilled_union.update(autofilled)
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

    def _apply_post(self, path: str, body: dict) -> tuple[dict, int]:
        if path == "/salesOrders":
            return self._post_sales_order(body), 201
        if path.endswith("/salesOrderLines"):
            # path looks like /salesOrders({id})/salesOrderLines
            order_id = _extract_id(path, "salesOrders")
            return self._post_sales_order_line(order_id, body), 201
        raise ValueError(f"mock POST not implemented for path {path!r}")

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
                    if key == "quantity":
                        cust_mix = order.get("_customer_mixprijzen", False)
                        item_mix = line.get("_item_mixprijzen", False)
                        if (
                            cust_mix and item_mix
                            and isinstance(value, (int, float))
                            and value >= MOCK_MIX_THRESHOLD
                        ):
                            base = self.prices.get(line["itemNumber"], 0.0)
                            line["unitPrice"] = round(
                                base * MOCK_MIX_DISCOUNT_FACTOR, 4
                            )
                    # Trigger emulation: unitOfMeasureCode change -> ensure
                    # the UoM exists for this item (defensive; doesn't change
                    # price in our simplified mock).
                    return {k: v for k, v in line.items() if not k.startswith("_")}
        raise ValueError(f"unknown sales-order line {line_id!r}")


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


def build_sales_order_payload(state: dict) -> dict:
    """Build the exact header + lines that will be POSTed to Navision.

    Shared by `push_navision` and the `/api/orders/{id}/navision-preview` endpoint
    so that the dashboard preview is byte-identical to what gets pushed.
    """
    from kwabo.utils.eenheid_mapping import normalize_eenheid

    klant = state.get("klant_match") or {}
    header: dict = {
        "customerNumber": klant.get("navision_klantnr"),
        "externalDocumentNumber": state.get("bestelnummer_klant", "") or "",
        "requestedDeliveryDate": state.get("gewenste_leverdatum"),
    }
    ship = state.get("afleveradres")
    if ship:
        header.update(
            {
                "shipToName": ship.get("naam", ""),
                "shipToAddressLine1": ship.get("straat", ""),
                "shipToCity": ship.get("plaats", ""),
                "shipToPostCode": ship.get("postcode", ""),
                "shipToCountry": ship.get("land", "NL"),
            }
        )
    if state.get("opmerkingen"):
        header["comment"] = state["opmerkingen"]
    if state.get("afleverinstructies"):
        header["shippingInstructions"] = state["afleverinstructies"]

    lines: list[dict] = []
    for r in state.get("orderregels") or []:
        if not r.get("artikelnummer_kwabo_matched"):
            continue
        line = {
            "itemNumber": r["artikelnummer_kwabo_matched"],
            "quantity": r.get("hoeveelheid"),
            "unitOfMeasureCode": normalize_eenheid(r.get("eenheid")),
        }
        if r.get("prijs_per_eenheid") is not None and r.get("prijs_validated") is True:
            line["unitPrice"] = r["prijs_per_eenheid"]
        if r.get("leverdatum_regel"):
            line["shipmentDate"] = r["leverdatum_regel"]
        if r.get("opmerkingen"):
            line["description2"] = r["opmerkingen"]
        lines.append(line)

    return {"header": header, "lines": lines}
