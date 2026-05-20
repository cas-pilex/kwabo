"""Connectivity diagnostics — dashboard helpers that probe external systems.

Today this exposes a single endpoint, GET /api/diagnostics/nav, which calls
`Nav2018ODataClient.probe()` against the configured NAV endpoint and returns
a structured status. The frontend renders this in a debug panel so the
operator can verify NAV credentials and entity names without needing to
run curl from a developer machine.
"""
from __future__ import annotations

from fastapi import APIRouter

from kwabo.config import settings

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("/nav")
async def nav_probe(page: str | None = None) -> dict:
    """Probe NAV connectivity using the currently configured client.

    Returns a status dict; never raises. The operator can read the URL,
    page name and HTTP status to diagnose 401 (creds wrong), 404 (page
    name wrong), or DNS/connect failures.

    Pass `?page=PLX_Item` (or any other PLX_*) to probe a specific page —
    needed for diagnosing the case where the sales-order page works but
    master-data pages return 404 / empty / 401 separately.
    """
    mode = settings.navision_mode
    if mode != "nav2018":
        return {
            "ok": False,
            "skipped": True,
            "reason": f"NAVISION_MODE={mode} (probe is only meaningful for nav2018)",
            "mode": mode,
        }

    from kwabo.integrations.navision_nav2018 import Nav2018ODataClient

    client = Nav2018ODataClient()
    try:
        result = await client.probe(page=page)
    finally:
        await client.aclose()
    result["mode"] = mode
    return result


@router.get("/nav/services")
async def nav_list_services() -> dict:
    """List all published OData web services for the configured company.

    Reads the OData service document at Company('...')/ which enumerates every
    EntitySet the server exposes. Useful when probe() reports 404 on an
    expected page — this shows the canonical names actually published, so
    the operator can fix the env-var page mappings instead of asking NAV-beheer
    to (re)publish pages that may already be there under a different name.
    """
    mode = settings.navision_mode
    if mode != "nav2018":
        return {"ok": False, "skipped": True, "mode": mode}

    from kwabo.integrations.navision_nav2018 import Nav2018ODataClient

    client = Nav2018ODataClient()
    try:
        services = await client.list_services()
    finally:
        await client.aclose()
    names = sorted({s.get("name") for s in services if s.get("name")})
    return {
        "ok": True,
        "count": len(names),
        "names": names,
        "company": client.company,
    }


@router.get("/nav/raw")
async def nav_raw_request(path: str = "/", under_company: bool = True) -> dict:
    """Send a raw GET to NAV and dump the response.

    Diagnostic only — when list_services returns 0 entries we want to see
    exactly what NAV 2018 puts at various URLs. With `under_company=true`
    (default) the path is appended after Company('...'); with `false` the
    path is appended directly after the OData root, which is where the
    NAV 2018 service document lives.
    """
    mode = settings.navision_mode
    if mode != "nav2018":
        return {"ok": False, "skipped": True, "mode": mode}

    from kwabo.integrations.navision_nav2018 import (
        Nav2018ODataClient,
        _quote_company,
    )

    client = Nav2018ODataClient()
    try:
        if under_company:
            url = (
                f"{client.base_url}/Company('{_quote_company(client.company)}')"
                f"{path}"
            )
        else:
            url = f"{client.base_url}{path}"
        try:
            resp = await client._client.get(
                url,
                headers=client._headers(),
                auth=client._auth(),
            )
            return {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "url": url,
                "content_type": resp.headers.get("content-type"),
                "body_preview": (resp.text or "")[:2000],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await client.aclose()
