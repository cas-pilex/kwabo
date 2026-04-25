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
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

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
