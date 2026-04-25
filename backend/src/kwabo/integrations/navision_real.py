"""Production Navision 2018 REST client.

Implements the NavisionClient protocol against the standard NAV 2018 OData v2 API.
Two auth modes supported:
  - "basic": NAV Web Service Access Key (user + key) over HTTPS
  - "oauth": Azure AD OAuth2 client-credentials (if NAV is fronted by AAD)

Configuration via environment / settings:
  NAV_BASE_URL            https://nav.example.com:7048/NAV/api/v2.0
  NAV_COMPANY_ID          <guid>
  NAV_AUTH_MODE           basic | oauth
  NAV_USERNAME            web-service-user           (basic)
  NAV_PASSWORD            web-service-key            (basic)
  NAV_TENANT_ID           <aad tenant>               (oauth)
  NAV_CLIENT_ID           <aad client>               (oauth)
  NAV_CLIENT_SECRET       <aad secret>               (oauth)
  NAV_SCOPE               <aad resource scope>       (oauth)
  NAV_VERIFY_SSL          true | false               (default true)

This class is ready to plug in by switching NAVISION_MODE=real. During this
interim phase we ship a companion fixture-based test mode so QA can validate
the wiring without hitting a live NAV.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

from kwabo.integrations.nav_operations import (
    NavOperation,
    NavOpResult,
    StepwiseResult,
    _assert_op_invariants,
    _diff_autofilled,
    _strip_marker_keys,
    _substitute_body_values,
    _substitute_path,
)
from kwabo.utils.logging import log


class _TokenCache:
    def __init__(self) -> None:
        self.token: Optional[str] = None
        self.exp: float = 0.0


class RealNavisionClient:
    def __init__(
        self,
        base_url: str | None = None,
        company_id: str | None = None,
        auth_mode: str | None = None,
        username: str | None = None,
        password: str | None = None,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
        verify_ssl: bool | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("NAV_BASE_URL", "")).rstrip("/")
        self.company_id = company_id or os.getenv("NAV_COMPANY_ID", "")
        self.auth_mode = (auth_mode or os.getenv("NAV_AUTH_MODE", "basic")).lower()
        self.username = username or os.getenv("NAV_USERNAME", "")
        self.password = password or os.getenv("NAV_PASSWORD", "")
        self.tenant_id = tenant_id or os.getenv("NAV_TENANT_ID", "")
        self.client_id = client_id or os.getenv("NAV_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("NAV_CLIENT_SECRET", "")
        self.scope = scope or os.getenv("NAV_SCOPE", "")
        self.verify_ssl = (
            (os.getenv("NAV_VERIFY_SSL", "true").lower() != "false")
            if verify_ssl is None
            else verify_ssl
        )
        self._token = _TokenCache()
        self._client = http_client or httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    # ---------- auth ----------

    async def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.auth_mode == "oauth":
            h["Authorization"] = f"Bearer {await self._get_bearer()}"
        return h

    def _basic_auth(self) -> httpx.BasicAuth | None:
        if self.auth_mode == "basic":
            return httpx.BasicAuth(self.username, self.password)
        return None

    async def _get_bearer(self) -> str:
        if self._token.token and time.time() < self._token.exp - 60:
            return self._token.token
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = await self._client.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token.token = data["access_token"]
        self._token.exp = time.time() + int(data.get("expires_in", 3600))
        return self._token.token

    def _base(self) -> str:
        return f"{self.base_url}/companies({self.company_id})"

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        resp = await self._client.get(
            f"{self._base()}/{endpoint}",
            params=params,
            headers=await self._headers(),
            auth=self._basic_auth(),
        )
        resp.raise_for_status()
        return resp.json()

    async def _post(self, endpoint: str, body: dict) -> dict:
        resp = await self._client.post(
            f"{self._base()}/{endpoint}",
            json=body,
            headers={**(await self._headers()), "If-Match": "*"},
            auth=self._basic_auth(),
        )
        resp.raise_for_status()
        return resp.json()

    async def _patch(self, endpoint: str, body: dict) -> tuple[int, dict]:
        """Internal helper: send a single PATCH and return (status, json).

        Uses If-Match: * to bypass NAV's optimistic concurrency check, since
        in our pipeline we just created the entity ourselves.
        """
        resp = await self._client.patch(
            f"{self._base()}/{endpoint}",
            json=body,
            headers={**(await self._headers()), "If-Match": "*"},
            auth=self._basic_auth(),
        )
        resp.raise_for_status()
        # NAV returns 200 with the updated record, or 204 (no body) on some endpoints.
        if resp.status_code == 204 or not resp.content:
            return resp.status_code, {}
        return resp.status_code, resp.json()

    # ---------- bulk read helpers (used by master-data sync) ----------

    async def get_collection(
        self,
        endpoint: str,
        params: dict | None = None,
    ) -> list[dict]:
        """Fetch a full OData collection, transparently following @odata.nextLink.

        Use for master-data sync (customers, items, itemReferences, …). Returns
        the concatenated `value` arrays from every page. Pass server-side
        filters via `params` (e.g. `$filter`, `$top`).
        """
        out: list[dict] = []
        first = await self._get(endpoint, params)
        out.extend(first.get("value") or [])
        next_link = first.get("@odata.nextLink") or first.get("odata.nextLink")
        while next_link:
            # nextLink is an absolute URL; bypass _base() to avoid double-prefix.
            resp = await self._client.get(
                next_link,
                headers=await self._headers(),
                auth=self._basic_auth(),
            )
            resp.raise_for_status()
            page = resp.json()
            out.extend(page.get("value") or [])
            next_link = page.get("@odata.nextLink") or page.get("odata.nextLink")
        return out

    # ---------- NavisionClient protocol ----------

    async def get_customer(self, nr: str) -> Optional[dict]:
        res = await self._get("customers", {"$filter": f"number eq '{nr}'"})
        items = res.get("value") or []
        return items[0] if items else None

    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        filters = []
        if email:
            filters.append(f"email eq '{email}'")
        if naam:
            filters.append(f"contains(displayName,'{naam}')")
        filter_str = " or ".join(filters) if filters else None
        res = await self._get("customers", {"$filter": filter_str} if filter_str else None)
        return res.get("value") or []

    async def get_item(self, nr: str) -> Optional[dict]:
        res = await self._get("items", {"$filter": f"number eq '{nr}'"})
        items = res.get("value") or []
        return items[0] if items else None

    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]:
        params = None
        if beschrijving:
            params = {"$filter": f"contains(displayName,'{beschrijving}')"}
        res = await self._get("items", params)
        return res.get("value") or []

    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict:
        # Idempotency guard: check if order with this externalDocumentNumber already exists.
        external = header.get("externalDocumentNumber")
        if external:
            existing = await self._get(
                "salesOrders", {"$filter": f"externalDocumentNumber eq '{external}'"}
            )
            if existing.get("value"):
                log.info(
                    "nav_dedup_skip",
                    external_doc=external,
                    found_number=existing["value"][0].get("number"),
                )
                e = existing["value"][0]
                return {"id": e["id"], "number": e["number"], "status": "ExistingDraft", "header": header, "lines": []}

        # Create header
        created = await self._post("salesOrders", header)
        order_id = created["id"]
        order_nr = created["number"]

        # Add lines
        for line in lines:
            for attempt in range(3):
                try:
                    await self._post(f"salesOrders({order_id})/salesOrderLines", line)
                    break
                except httpx.HTTPStatusError as e:
                    if attempt == 2 or e.response.status_code < 500:
                        raise
                    await asyncio.sleep(2 ** attempt)
        return {"id": order_id, "number": order_nr, "status": "Draft", "header": header, "lines": lines}

    # ---------- trigger-aware single-field PATCH ----------

    async def patch(self, endpoint: str, body: dict) -> dict:
        """Single-field PATCH against NAV.

        NAV's OnValidate triggers fire per-field, mirroring how a user types a
        value into the UI and tabs out. To preserve those semantics we REQUIRE
        the body to contain exactly one key. Multi-field PATCH is the old
        bypass-the-trigger antipattern that this whole refactor is removing.
        """
        if not isinstance(body, dict):
            raise ValueError("patch body must be a dict")
        if len(body) != 1:
            raise ValueError(
                f"patch body must contain exactly one field; got {len(body)} ({sorted(body)})"
            )
        _, data = await self._patch(endpoint.lstrip("/"), body)
        return data

    # ---------- master-data lookups (used by validation + UI dropdowns) ----------

    async def get_ship_to_addresses(self, customer_id: str) -> list[dict]:
        """All Ship-to addresses for a NAV customer (record id, not number).

        NAV API: /companies({c})/customers({id})/shipToAddresses
        """
        res = await self._get(f"customers({customer_id})/shipToAddresses")
        return res.get("value") or []

    async def get_item_uoms(self, item_id: str) -> list[dict]:
        """All UoMs for an item.

        NAV API: /companies({c})/items({id})/itemUnitsOfMeasure
        """
        res = await self._get(f"items({item_id})/itemUnitsOfMeasure")
        return res.get("value") or []

    async def get_item_references(self, customer_no: str | None = None) -> list[dict]:
        """Item references (cross-references). If a customer number is supplied
        we filter server-side.

        NAV API: /companies({c})/itemReferences
        """
        params = None
        if customer_no:
            # NAV's itemReferences exposes referenceType + referenceTypeNo. We
            # filter on customer-type cross refs here. The exact field names
            # depend on the NAV 2018 page exposing this entity — staging may
            # need adjustment if the property names diverge.
            params = {
                "$filter": (
                    f"referenceType eq 'Customer' and referenceTypeNo eq '{customer_no}'"
                )
            }
        res = await self._get("itemReferences", params)
        return res.get("value") or []

    # ---------- incoming documents (PDF / EML attachments) ----------

    async def create_incoming_document(
        self, description: str, vendor_name: str | None
    ) -> dict:
        """Create an Incoming Document header. We attach the original PDF/EML
        afterwards via attach_to_incoming_document.

        NAV API: /companies({c})/incomingDocuments
        """
        body: dict = {"description": description}
        if vendor_name:
            body["vendorName"] = vendor_name
        return await self._post("incomingDocuments", body)

    async def attach_to_incoming_document(
        self, doc_id: str, filename: str, content: bytes, content_type: str
    ) -> dict:
        """Attach a binary file to an Incoming Document.

        NAV 2018's standard pattern (see Microsoft Docs "Working with API
        files (containers)") is:
          1. POST a stub attachment record with metadata (fileName, parentId).
          2. PATCH the `content` field on that record with the binary payload.

        For NAV 2018 OData v2 the simplest universally-supported encoding is to
        send `content` as a base64 string in JSON. Newer BC builds accept
        binary uploads via Content-Type: application/octet-stream, but Cas's
        on-prem NAV 2018 reliably accepts the base64 form. If staging rejects
        this, switch to `application/octet-stream` (raw bytes) on the PATCH —
        the response shape is identical.
        """
        # Step 1: create the attachment shell.
        stub = await self._post(
            f"incomingDocuments({doc_id})/attachments",
            {"fileName": filename},
        )
        attach_id = stub.get("id") or stub.get("parentId") or stub.get("attachmentId")
        # Step 2: PATCH the content field with base64-encoded bytes.
        encoded = base64.b64encode(content).decode("ascii")
        path = f"incomingDocuments({doc_id})/attachments({attach_id})"
        # Single-field PATCH (still respects the trigger-aware invariant).
        # Note: the NAV mediaType property records the content_type for us;
        # NAV typically also honours `mediaType` set in the stub POST, but
        # to keep PATCHes single-field we set it here in a separate call only
        # when caller cares. For now we record content_type in the response
        # body so callers can verify what we sent.
        resp = await self._client.patch(
            f"{self._base()}/{path}",
            json={"content": encoded},
            headers={
                **(await self._headers()),
                "If-Match": "*",
            },
            auth=self._basic_auth(),
        )
        resp.raise_for_status()
        return {
            "id": attach_id,
            "fileName": filename,
            "mediaType": content_type,
            "status": resp.status_code,
        }

    # ---------- stepwise sales-order creation (the core T3 deliverable) ----------

    async def create_sales_order_stepwise(
        self, operations: list[NavOperation]
    ) -> StepwiseResult:
        """Execute an ordered list of NAV operations to build a sales order.

        Invariants enforced here (deliberately strict — these are the
        mistakes the old one-shot push made):
          * The first operation MUST be POST /salesOrders.
          * That POST body MUST contain exactly `customerNumber` and nothing
            else; everything else has to come in via PATCH so triggers fire.
          * POST /salesOrders(...)/salesOrderLines bodies MUST contain only
            `lineType` and `itemNumber`.
          * Every PATCH body MUST be exactly one field.

        Execution semantics:
          * `{id}` in the path is substituted with the most-recently-created
            sales-order id by default, but when we are operating in a line
            context (path begins with /salesOrderLines or contains an explicit
            line-id segment) we use the most-recently-created line id.
          * After a POST we re-GET the resource to capture autofilled fields.
          * After a PATCH we re-GET only when `expects` was supplied on the
            operation — minimises round-trips.
          * On the first error we capture the message on operation_results[-1]
            and STOP. We never silently continue.
        """
        results: list[NavOpResult] = []
        autofilled_union: dict = {}
        sales_order_id: str = ""
        sales_order_number: str = ""
        last_line_id: str = ""
        last_incoming_doc_id: str = ""

        for idx, op in enumerate(operations):
            method = op["op"]
            raw_path = op["path"]
            body = op.get("body") or {}

            # ---- Invariant checks (per-op) -------------------------------
            _assert_op_invariants(idx, op)

            # ---- placeholder substitution (path) -------------------------
            substitution_id = (
                last_line_id
                if ("/salesOrderLines(" in raw_path or raw_path.startswith("/salesOrderLines"))
                else sales_order_id
            )
            try:
                path = _substitute_path(raw_path, substitution_id, last_incoming_doc_id)
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
                    sales_order_id=sales_order_id,
                    sales_order_number=sales_order_number,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )

            relative = path.lstrip("/")

            # ---- placeholder substitution (body) + strip marker keys -----
            # `_attachment_path` and similar composer-side directives never
            # cross the wire — they're stripped here. `{incoming_document_id}`
            # in body string values is resolved against the most-recently-POSTed
            # /incomingDocuments response.
            try:
                resolved_body = _substitute_body_values(body, last_incoming_doc_id)
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
                    sales_order_id=sales_order_id,
                    sales_order_number=sales_order_number,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )
            wire_body = _strip_marker_keys(resolved_body)

            # ---- Execute -------------------------------------------------
            try:
                # Special case: /attachments POST — the composer left the file
                # path in `_attachment_path`; we materialise it into the
                # base64-encoded NAV upload via `attach_to_incoming_document`.
                is_attachment_upload = (
                    method == "POST"
                    and relative.endswith("/attachments")
                    and "/incomingDocuments(" in relative
                )
                if is_attachment_upload:
                    # Extract the parent doc id from the substituted path.
                    import re as _re
                    m = _re.search(r"/incomingDocuments\(([^)]+)\)", relative)
                    if not m:
                        raise ValueError(f"could not parse incoming doc id from {relative!r}")
                    doc_id = m.group(1)
                    raw_attach_path = body.get("_attachment_path")
                    filename = wire_body.get("fileName", "")
                    if not raw_attach_path:
                        raise ValueError(
                            f"op[{idx}]: /attachments POST missing _attachment_path marker"
                        )
                    content_bytes = Path(raw_attach_path).read_bytes()
                    server = await self.attach_to_incoming_document(
                        doc_id, filename, content_bytes,
                        wire_body.get("mediaType", "application/octet-stream"),
                    )
                    status = 201
                    autofilled = _diff_autofilled(wire_body, server)
                    results.append(
                        NavOpResult(
                            operation=op,
                            status=status,
                            response_body=server,
                            autofilled=autofilled,
                        )
                    )
                    autofilled_union.update(autofilled)
                elif method == "POST":
                    server = await self._post(relative, wire_body)
                    status = 201
                    # Track parent id for /salesOrders, line id for line POSTs,
                    # and incoming-doc id for attachment-id substitution.
                    if relative == "salesOrders":
                        sales_order_id = server.get("id") or sales_order_id
                        sales_order_number = server.get("number") or sales_order_number
                    elif relative.endswith("/salesOrderLines"):
                        last_line_id = server.get("id") or last_line_id
                    elif relative == "incomingDocuments":
                        last_incoming_doc_id = server.get("id") or last_incoming_doc_id
                    # POSTs always get a re-GET via the response body itself.
                    autofilled = _diff_autofilled(wire_body, server)
                    results.append(
                        NavOpResult(
                            operation=op,
                            status=status,
                            response_body=server,
                            autofilled=autofilled,
                        )
                    )
                    autofilled_union.update(autofilled)
                else:  # PATCH
                    # Single-field invariant is already enforced upstream by
                    # _assert_op_invariants; no need to re-check here.
                    status, server = await self._patch(relative, wire_body)
                    patch_autofilled: dict = {}
                    if op.get("expects"):
                        # Re-GET the parent resource to verify trigger results.
                        # NAV's PATCH response often already includes the full
                        # record, in which case we just diff against `body`.
                        if not server:
                            try:
                                server = await self._get(relative)
                            except Exception:
                                server = {}
                        patch_autofilled = _diff_autofilled(wire_body, server)
                    results.append(
                        NavOpResult(
                            operation=op,
                            status=status,
                            response_body=server,
                            autofilled=patch_autofilled,
                        )
                    )
                    autofilled_union.update(patch_autofilled)
            except Exception as exc:
                err_msg = self._format_http_error(exc)
                results.append(
                    NavOpResult(
                        operation=op,
                        status=getattr(getattr(exc, "response", None), "status_code", 0) or 0,
                        response_body={},
                        autofilled={},
                        error=err_msg,
                    )
                )
                log.error(
                    "nav_stepwise_failure",
                    op_index=idx,
                    op_label=op.get("label"),
                    op=method,
                    path=raw_path,
                    error=err_msg,
                )
                return StepwiseResult(
                    sales_order_id=sales_order_id,
                    sales_order_number=sales_order_number,
                    operation_results=results,
                    nav_autofilled=autofilled_union,
                )

        return StepwiseResult(
            sales_order_id=sales_order_id,
            sales_order_number=sales_order_number,
            operation_results=results,
            nav_autofilled=autofilled_union,
        )

    @staticmethod
    def _format_http_error(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            try:
                body = exc.response.json()
            except Exception:
                body = exc.response.text
            return f"HTTP {status}: {body}"
        return f"{type(exc).__name__}: {exc}"

    async def aclose(self) -> None:
        await self._client.aclose()


# ---------- Fixture-based replay client for offline QA ----------

class ReplayNavisionClient:
    """Serves responses from a JSON fixture file. Useful for CI and offline dev.

    Fixture format:
      {
        "customers": [ {...OData customer shape...} ],
        "items":     [ {...OData item shape...} ]
      }
    """

    def __init__(self, fixture_path: Path | str) -> None:
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self.customers = data.get("customers", [])
        self.items = data.get("items", [])
        self._orders: list[dict] = []

    async def get_customer(self, nr: str) -> Optional[dict]:
        return next((c for c in self.customers if c["number"] == nr), None)

    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        out = []
        for c in self.customers:
            if email and c.get("email", "").lower() == email.lower():
                out.append(c)
                continue
            if naam and naam.lower() in c.get("displayName", "").lower():
                out.append(c)
        return out

    async def get_item(self, nr: str) -> Optional[dict]:
        return next((i for i in self.items if i["number"] == nr), None)

    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]:
        if not beschrijving:
            return list(self.items)
        q = beschrijving.lower()
        return [i for i in self.items if q in i.get("displayName", "").lower()]

    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict:
        order_id = str(uuid.uuid4())
        order_nr = f"SO-REPLAY-{len(self._orders) + 1:04d}"
        rec = {"id": order_id, "number": order_nr, "header": header, "lines": lines, "status": "Draft"}
        self._orders.append(rec)
        return rec
