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
