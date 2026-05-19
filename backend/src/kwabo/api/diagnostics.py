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
