"""Production NAV 2018 OData V4 client.

The Kwabo test environment exposes Pilex-customised NAV 2018 pages over
OData V4 with Basic auth (Web Service Access Key). This is structurally
different from Business Central's modern API:

  Business Central                 NAV 2018 OData V4
  ----------------                 -----------------
  /companies({guid})/salesOrders   /Company('Display Name')/PLX_SalesOrder
  Bearer token (OAuth)             Basic auth (user + access key)
  GUID record keys                 Composite or No-string keys
  camelCase fields                 Underscored field names

The contract with the rest of the app stays the same: this client
implements `create_sales_order_stepwise` so push_navision can feed it
the abstract operation list composed by `compose_navision_operations`,
and the trigger-aware single-field PATCH invariants enforced upstream
still hold.

Endpoints expected on the NAV side (configurable via env):
  PLX_SalesOrder       — sales-order header page
  PLX_SalesOrderLines  — sales-order lines page
  PLX_Customer         — customers (read-only here, used by master sync)
  PLX_Item             — items
  PLX_ItemReference    — item cross references
  PLX_ShipToAddress    — ship-to addresses
  PLX_ItemUnitOfMeasure — item UoMs

Auth probe summary (run once during onboarding to pick the right port):
  port 1153 (ODataV4) → Basic auth → THIS CLIENT
  port 1143 (OData v2) → Digest auth → not supported (use port 1153)
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Optional

import httpx

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
from kwabo.utils.logging import log


# Mapping from the abstract path/field names used by compose_navision_operations
# (BC-shaped) to NAV 2018 page/field names. The composer emits paths like
# "/salesOrders" and bodies like {"customerNumber": ...}; this client rewrites
# them to "/PLX_SalesOrder" and {"Sell_to_Customer_No": ...} at execute-time.
#
# Fields that have no NAV 2018 equivalent (e.g. composer markers) are stripped
# before transport by `_strip_marker_keys` — they never get this far.
_DEFAULT_FIELD_MAP = {
    # Header fields
    "customerNumber": "Sell_to_Customer_No",
    "shipToCode": "Ship_to_Code",
    "externalDocumentNumber": "External_Document_No",
    "requestedDeliveryDate": "Requested_Delivery_Date",
    "shipmentDate": "Shipment_Date",
    "incomingDocumentNumber": "Incoming_Document_Entry_No",
    # Line fields
    "lineType": "Type",
    "itemNumber": "No",
    "unitOfMeasureCode": "Unit_of_Measure_Code",
    "quantity": "Quantity",
}

# Reverse map for autofill diff readability.
_REVERSE_FIELD_MAP = {v: k for k, v in _DEFAULT_FIELD_MAP.items()}


def _translate_body(body: dict, field_map: dict[str, str]) -> dict:
    """Translate camelCase composer keys → NAV 2018 underscored keys.

    Unknown keys pass through unchanged so future fields don't require a
    code change here; the operator can extend the env-side mapping if a new
    field needs renaming.
    """
    return {field_map.get(k, k): v for k, v in body.items()}


def _detranslate_record(record: dict) -> dict:
    """For autofill diffs only: NAV 2018 keys → camelCase so logs match the
    rest of the codebase. Unknown keys pass through.
    """
    return {_REVERSE_FIELD_MAP.get(k, k): v for k, v in record.items()}


def _quote_company(name: str) -> str:
    """OData V4 percent-encodes the literal company name inside Company('...').

    Single quotes inside the name itself need to be doubled, per OData spec;
    the URL-encoder takes care of spaces, dots and unicode."""
    safe = name.replace("'", "''")
    return urllib.parse.quote(safe, safe="")


def _quote_key(key: str) -> str:
    """OData V4 string-key in path: PLX_SalesOrder('SO12345').

    Same single-quote-doubling rule. Numeric keys could be passed unquoted but
    we always quote — NAV 2018 No-fields are strings even when they look
    numeric.
    """
    return key.replace("'", "''")


class Nav2018ODataClient:
    """NAV 2018 OData V4 client implementing the same contract as
    `RealNavisionClient` (BC-flavoured) so push_navision is mode-agnostic."""

    def __init__(
        self,
        base_url: str | None = None,
        company: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool | None = None,
        page_sales_order: str | None = None,
        page_sales_order_lines: str | None = None,
        page_customer: str | None = None,
        page_item: str | None = None,
        page_item_reference: str | None = None,
        page_ship_to: str | None = None,
        page_item_uom: str | None = None,
        field_map: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        from kwabo.config import settings

        self.base_url = (base_url or settings.nav_base_url).rstrip("/")
        self.company = company or settings.nav_company
        self.username = username or settings.nav_username
        self.password = password or settings.nav_password
        self.verify_ssl = settings.nav_verify_ssl if verify_ssl is None else verify_ssl

        self.page_sales_order = page_sales_order or settings.nav_page_sales_order
        self.page_sales_order_lines = (
            page_sales_order_lines or settings.nav_page_sales_order_lines
        )
        self.page_customer = page_customer or settings.nav_page_customer
        self.page_item = page_item or settings.nav_page_item
        self.page_item_reference = page_item_reference or settings.nav_page_item_reference
        self.page_ship_to = page_ship_to or settings.nav_page_ship_to
        self.page_item_uom = page_item_uom or settings.nav_page_item_uom
        self.field_map = field_map or _DEFAULT_FIELD_MAP

        self._client = http_client or httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    # ---------- URL building ----------
    #
    # NAV 2018 in the Kopie 2026 deployment requires the `?company=<name>`
    # querystring form rather than the `Company('<name>')/PAGE` path form.
    # Some PLX_* pages refuse the path form entirely (Internal_CompanyNotFound
    # or 404) while accepting the querystring form. We standardise on the
    # querystring form everywhere — it works for plain pages (Customer) and
    # PLX_* pages alike, verified live against Kopie 2026.

    def _entity_url(self, entity: str) -> str:
        """Full URL to an entity collection, e.g. PLX_SalesOrder. The company
        is added via params=, not the path, by _get/_post/_patch."""
        return f"{self.base_url}/{entity}"

    def _record_url(self, entity: str, key: str) -> str:
        """Full URL to a single record, e.g. PLX_SalesOrder('SO12345')."""
        return f"{self.base_url}/{entity}('{_quote_key(key)}')"

    def _default_params(self) -> dict[str, str]:
        """Querystring that must travel on every request to NAV 2018: tells
        the server which company database to read/write against."""
        return {"company": self.company}

    def _merge_params(self, extra: dict | None) -> dict:
        merged = self._default_params()
        if extra:
            merged.update(extra)
        return merged

    # ---------- HTTP ----------

    def _auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self.username, self.password)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, url: str, params: dict | None = None) -> dict:
        resp = await self._client.get(
            url,
            params=self._merge_params(params),
            headers=self._headers(),
            auth=self._auth(),
        )
        # Treat 404 on a master-data read as "no record" rather than crashing
        # the pipeline. Real-world cause: a PLX_ page is exposed by NAV
        # (returns 401 unauth-challenge) but the service-account lacks
        # table-level Read permission, which NAV reports as 404 on the
        # filtered query. The order-intake should still flow through to
        # the review queue with a "no match" warning instead of dying with
        # HTTP 500 to the API caller.
        if resp.status_code == 404:
            log.warning(
                "nav_page_404",
                url=url,
                hint="page exposed but no data returned — check service-account table permissions in NAV",
            )
            return {}
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _post(self, url: str, body: dict) -> dict:
        resp = await self._client.post(
            url,
            params=self._default_params(),
            json=body,
            headers={**self._headers(), "If-Match": "*"},
            auth=self._auth(),
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _patch(self, url: str, body: dict) -> tuple[int, dict]:
        resp = await self._client.patch(
            url,
            params=self._default_params(),
            json=body,
            headers={**self._headers(), "If-Match": "*"},
            auth=self._auth(),
        )
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return resp.status_code, {}
        return resp.status_code, resp.json()

    # ---------- Master-data lookups (read-only) ----------

    async def get_customer(self, nr: str) -> Optional[dict]:
        url = self._entity_url(self.page_customer)
        res = await self._get(url, {"$filter": f"No eq '{nr}'"})
        items = res.get("value") or []
        return items[0] if items else None

    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        url = self._entity_url(self.page_customer)
        filters = []
        if email:
            filters.append(f"E_Mail eq '{email}'")
        if naam:
            filters.append(f"contains(Name,'{naam}')")
        params = {"$filter": " or ".join(filters)} if filters else None
        res = await self._get(url, params)
        return res.get("value") or []

    async def get_item(self, nr: str) -> Optional[dict]:
        url = self._entity_url(self.page_item)
        res = await self._get(url, {"$filter": f"No eq '{nr}'"})
        items = res.get("value") or []
        return items[0] if items else None

    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]:
        url = self._entity_url(self.page_item)
        params = {"$filter": f"contains(Description,'{beschrijving}')"} if beschrijving else None
        res = await self._get(url, params)
        return res.get("value") or []

    async def get_collection(self, entity: str, params: dict | None = None) -> list[dict]:
        """Page through an entire entity collection following @odata.nextLink."""
        url = self._entity_url(entity)
        out: list[dict] = []
        page = await self._get(url, params)
        out.extend(page.get("value") or [])
        next_link = page.get("@odata.nextLink") or page.get("odata.nextLink")
        while next_link:
            resp = await self._client.get(next_link, headers=self._headers(), auth=self._auth())
            # Mirror _get's 404 tolerance: a misconfigured page that
            # disappears mid-pagination should yield "no more rows", not
            # bring down a master-sync script.
            if resp.status_code == 404:
                log.warning("nav_page_404_in_pagination", url=next_link)
                break
            resp.raise_for_status()
            page = resp.json()
            out.extend(page.get("value") or [])
            next_link = page.get("@odata.nextLink") or page.get("odata.nextLink")
        return out

    # ---------- Connectivity probe ----------

    async def list_services(self) -> list[dict]:
        """Fetch the OData service document at the ODataV4 root and return
        the list of published entity sets. NAV 2018 puts the service document
        at the unprefixed root (NOT under Company('...')) — verified live
        against Kopie 2026.

        Returns [] on 404 / parse errors rather than raising; this is purely
        diagnostic and must never bring down the dashboard.
        """
        url = f"{self.base_url}/"
        try:
            resp = await self._client.get(
                url, headers=self._headers(), auth=self._auth()
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("value") or []
        except Exception as exc:  # noqa: BLE001
            log.warning("nav_list_services_failed", url=url, error=str(exc))
            return []

    async def probe(self, page: str | None = None) -> dict:
        """Lightweight reachability check. Returns a status dict that the
        dashboard renders on a diagnostic page. Never raises — all failures
        are reported as `ok=False` with a reason.

        `page` lets the operator probe any PLX_* page individually — useful
        when PLX_SalesOrder works but PLX_Item / PLX_Customer return 404 or
        empty data, which we hit in the Kopie 2026 environment.
        """
        target_page = page or self.page_sales_order
        url_base = self._entity_url(target_page)
        try:
            params = self._merge_params({"$top": "1"})
            resp = await self._client.get(
                url_base, params=params, headers=self._headers(), auth=self._auth()
            )
            return {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "url": str(resp.url),
                "page": target_page,
                "company": self.company,
                "preview": (resp.text or "")[:300],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "status": 0,
                "url": url_base,
                "page": target_page,
                "company": self.company,
                "error": f"{type(exc).__name__}: {exc}",
            }

    # ---------- Path translation (BC-style → NAV 2018) ----------
    # The composer emits paths like `/salesOrders` and `/salesOrders({id})`.
    # This client converts them at execute-time so the upstream invariant
    # checks stay BC-shaped (one canonical contract, two transports).

    _BC_RE_SALES_ORDERS = re.compile(r"^/?salesOrders$")
    _BC_RE_SALES_ORDER_BY_ID = re.compile(r"^/?salesOrders\(([^)]+)\)$")
    _BC_RE_SALES_ORDER_LINES = re.compile(r"^/?salesOrders\(([^)]+)\)/salesOrderLines$")
    _BC_RE_SALES_ORDER_LINE_BY_ID = re.compile(r"^/?salesOrderLines\(([^)]+)\)$")

    def _translate_path(self, bc_path: str, line_keys: dict[str, str]) -> str:
        """BC-shaped path → NAV 2018 OData V4 absolute URL.

        line_keys maps a BC line-id placeholder to a NAV 2018 line-record key
        we captured after the line POST. Empty for header ops."""
        if self._BC_RE_SALES_ORDERS.match(bc_path):
            return self._entity_url(self.page_sales_order)
        m = self._BC_RE_SALES_ORDER_BY_ID.match(bc_path)
        if m:
            return self._record_url(self.page_sales_order, m.group(1))
        m = self._BC_RE_SALES_ORDER_LINES.match(bc_path)
        if m:
            # NAV 2018 typically exposes lines as their own page; we POST to
            # the lines collection and let NAV link via Document_No on the
            # body. The composer always sets Document_No via the substituted
            # parent id at execute-time (handled by _enrich_line_body below).
            return self._entity_url(self.page_sales_order_lines)
        m = self._BC_RE_SALES_ORDER_LINE_BY_ID.match(bc_path)
        if m:
            line_id = m.group(1)
            line_key = line_keys.get(line_id, line_id)
            return self._record_url(self.page_sales_order_lines, line_key)
        # Incoming-documents are NAV 2018 standard pages but composer-side
        # markers (`/incomingDocuments`, `/attachments`) are skipped here:
        # NAV 2018 attachment workflow differs from BC and we don't support
        # it on this transport yet. The composer can be configured to omit
        # those ops when navision_mode=nav2018 (see push_navision_node).
        raise ValueError(
            f"NAV 2018 client does not support path {bc_path!r}. "
            f"Either add a translation rule or skip this op in the composer."
        )

    # ---------- Stepwise execute ----------

    async def create_sales_order_stepwise(
        self, operations: list[NavOperation]
    ) -> StepwiseResult:
        """Execute the abstract op list against NAV 2018.

        Per-op invariants (single-field PATCH, lineType+itemNumber-only POST,
        etc.) are enforced by `_assert_op_invariants` exactly as in the BC
        client. The only NAV 2018 specifics handled here are URL shape and
        field-name translation.
        """
        results: list[NavOpResult] = []
        autofilled_union: dict = {}
        sales_order_no: str = ""  # NAV 2018 uses No (string) as primary key
        last_line_key: str = ""
        # Map from "synthetic line id" (the str(uuid.uuid4()) the composer-side
        # would have used) to the NAV 2018 line-record key (Document_No,Line_No).
        line_keys: dict[str, str] = {}

        # Idempotency: short-circuit when externalDocumentNumber already exists.
        external = _extract_external_doc_number(list(operations))
        if external:
            try:
                url = self._entity_url(self.page_sales_order)
                page = await self._get(
                    url,
                    {"$filter": f"External_Document_No eq '{external}'", "$top": "1"},
                )
                value = (page or {}).get("value") or []
                if value:
                    e = value[0]
                    log.info(
                        "nav2018_dedup_skip",
                        external_doc=external,
                        found_no=e.get("No"),
                    )
                    return StepwiseResult(
                        sales_order_id=e.get("No", ""),
                        sales_order_number=e.get("No", ""),
                        operation_results=[],
                        nav_autofilled={"_dedup": external},
                    )
            except Exception as exc:  # noqa: BLE001
                # Dedup probe is best-effort; never block the create on a
                # bad probe. Log and continue.
                log.warning("nav2018_dedup_probe_failed", error=str(exc)[:200])

        for idx, op in enumerate(operations):
            method = op["op"]
            raw_path = op["path"]
            body = op.get("body") or {}

            # Skip incoming-doc operations on NAV 2018 (not implemented).
            if "/incomingDocuments" in raw_path or raw_path.startswith("/incomingDocuments"):
                results.append(
                    NavOpResult(
                        operation=op,
                        status=0,
                        response_body={},
                        autofilled={},
                        error="incomingDocuments skipped: NAV 2018 path not yet implemented",
                    )
                )
                continue

            try:
                _assert_op_invariants(idx, op)
            except ValueError as exc:
                results.append(
                    NavOpResult(
                        operation=op,
                        status=0,
                        response_body={},
                        autofilled={},
                        error=str(exc),
                    )
                )
                return StepwiseResult(
                    sales_order_id=sales_order_no,
                    sales_order_number=sales_order_no,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )

            # Substitute the BC `{id}` placeholder against the captured NAV 2018
            # No (sales order) or last line key.
            substitution_id = (
                last_line_key
                if ("/salesOrderLines(" in raw_path or raw_path.startswith("/salesOrderLines"))
                else sales_order_no
            )
            try:
                bc_path = _substitute_path(raw_path, substitution_id, "")
            except ValueError as exc:
                results.append(
                    NavOpResult(
                        operation=op,
                        status=0,
                        response_body={},
                        autofilled={},
                        error=str(exc),
                    )
                )
                return StepwiseResult(
                    sales_order_id=sales_order_no,
                    sales_order_number=sales_order_no,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )

            # Strip composer markers (none on this path today, future-proof).
            try:
                resolved_body = _substitute_body_values(body, "")
            except ValueError as exc:
                results.append(
                    NavOpResult(
                        operation=op,
                        status=0,
                        response_body={},
                        autofilled={},
                        error=str(exc),
                    )
                )
                return StepwiseResult(
                    sales_order_id=sales_order_no,
                    sales_order_number=sales_order_no,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )
            wire_body_bc = _strip_marker_keys(resolved_body)
            wire_body_nav = _translate_body(wire_body_bc, self.field_map)

            # For line POSTs, NAV 2018 needs Document_No on the body to link
            # the line to its parent header. The composer doesn't emit it
            # because BC's URL nesting does that automatically.
            if method == "POST" and "/salesOrderLines" in bc_path and bc_path.endswith(
                "/salesOrderLines"
            ):
                if not sales_order_no:
                    err = "cannot POST line: parent sales-order No not captured yet"
                    results.append(
                        NavOpResult(
                            operation=op,
                            status=0,
                            response_body={},
                            autofilled={},
                            error=err,
                        )
                    )
                    return StepwiseResult(
                        sales_order_id=sales_order_no,
                        sales_order_number=sales_order_no,
                        operation_results=results,
                        nav_autofilled=autofilled_union,
                    )
                wire_body_nav.setdefault("Document_No", sales_order_no)
                # NAV 2018 also wants Document_Type=Order for sales-order lines.
                wire_body_nav.setdefault("Document_Type", "Order")

            # Translate path → absolute NAV 2018 URL.
            try:
                target_url = self._translate_path(bc_path, line_keys)
            except ValueError as exc:
                results.append(
                    NavOpResult(
                        operation=op,
                        status=0,
                        response_body={},
                        autofilled={},
                        error=str(exc),
                    )
                )
                return StepwiseResult(
                    sales_order_id=sales_order_no,
                    sales_order_number=sales_order_no,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )

            # Execute the request.
            try:
                if method == "POST":
                    server = await self._post(target_url, wire_body_nav)
                    status = 201
                    # Capture record keys for follow-up PATCHes.
                    if bc_path.lstrip("/") == "salesOrders":
                        sales_order_no = server.get("No") or sales_order_no
                    elif bc_path.endswith("/salesOrderLines"):
                        # NAV 2018 lines have a composite key (Document_No,Line_No).
                        # OData V4 expresses this in the path as
                        # PLX_SalesOrderLines(Document_No='SO',Line_No=10000).
                        # We synthesise that composite key string here so the
                        # `{id}` substitution downstream resolves to it.
                        line_no = server.get("Line_No")
                        doc_no = server.get("Document_No") or sales_order_no
                        if line_no is not None:
                            composite = (
                                f"Document_Type='Order',Document_No='{_quote_key(doc_no)}',"
                                f"Line_No={line_no}"
                            )
                            last_line_key = composite
                            line_keys[str(line_no)] = composite
                    autofilled = _diff_autofilled(wire_body_nav, server)
                    results.append(
                        NavOpResult(
                            operation=op,
                            status=status,
                            response_body=_detranslate_record(server),
                            autofilled=_detranslate_record(autofilled),
                        )
                    )
                    autofilled_union.update(_detranslate_record(autofilled))
                else:  # PATCH
                    status, server = await self._patch(target_url, wire_body_nav)
                    patch_autofilled: dict = {}
                    if op.get("expects"):
                        if not server:
                            try:
                                server = await self._get(target_url)
                            except Exception:  # noqa: BLE001
                                server = {}
                        patch_autofilled = _diff_autofilled(wire_body_nav, server)
                    results.append(
                        NavOpResult(
                            operation=op,
                            status=status,
                            response_body=_detranslate_record(server) if server else {},
                            autofilled=_detranslate_record(patch_autofilled),
                        )
                    )
                    autofilled_union.update(_detranslate_record(patch_autofilled))
            except Exception as exc:
                err_msg = self._format_http_error(exc)
                response_status = (
                    getattr(getattr(exc, "response", None), "status_code", 0) or 0
                )
                response_body_text = ""
                resp = getattr(exc, "response", None)
                if resp is not None:
                    try:
                        response_body_text = resp.text
                    except Exception:  # noqa: BLE001
                        response_body_text = ""
                results.append(
                    NavOpResult(
                        operation=op,
                        status=response_status,
                        response_body={},
                        autofilled={},
                        error=err_msg,
                    )
                )
                log.error(
                    "nav2018_stepwise_failure",
                    op_index=idx,
                    op_label=op.get("label"),
                    op_method=method,
                    op_path=raw_path,
                    target_url=target_url,
                    request_body=wire_body_nav,
                    response_status=response_status,
                    response_body=response_body_text[:2000],
                    error_type=type(exc).__name__,
                    error=err_msg,
                )
                return StepwiseResult(
                    sales_order_id=sales_order_no,
                    sales_order_number=sales_order_no,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )

        return StepwiseResult(
            sales_order_id=sales_order_no,
            sales_order_number=sales_order_no,
            operation_results=results,
            nav_autofilled=autofilled_union,
        )

    @staticmethod
    def _format_http_error(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                body = exc.response.json()
            except Exception:  # noqa: BLE001
                body = exc.response.text
            return f"HTTP {exc.response.status_code}: {body}"
        return f"{type(exc).__name__}: {exc}"

    # Compatibility shim: legacy create_sales_order endpoint.
    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict:
        """Bulk path retained for parity with the BC client API surface.

        The pipeline does NOT call this in normal operation — push_navision
        uses the stepwise route. This is here so that direct integrations
        and a few legacy tests still type-check against NavisionClient."""
        body = _translate_body(header, self.field_map)
        url = self._entity_url(self.page_sales_order)
        created = await self._post(url, body)
        order_no = created.get("No")
        for line in lines:
            line_body = _translate_body(line, self.field_map)
            line_body.setdefault("Document_No", order_no)
            line_body.setdefault("Document_Type", "Order")
            await self._post(self._entity_url(self.page_sales_order_lines), line_body)
        return {
            "id": order_no,
            "number": order_no,
            "status": "Released",
            "header": header,
            "lines": lines,
        }

    async def aclose(self) -> None:
        await self._client.aclose()
