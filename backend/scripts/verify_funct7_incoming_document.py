"""Verificatie Functie 7 — bron-document als inkomend document koppelen.

Verse output (deterministisch, geen netwerk, geen prod). Bewijst de drie
eigenschappen waar de go/no-go op leunt:

  A. Flag UIT (default): de drie incoming-doc-ops (POST /incomingDocuments,
     PATCH salesOrder.incomingDocumentNumber, POST .../attachments) worden
     GEDETECTEERD en overgeslagen met een `_skipped`-marker, terwijl de
     header- en regel-ops gewoon uitgevoerd worden en GEEN `error` dragen ->
     een ontbrekende PLX_IncomingDocument-page verspilt nooit een echte order.

  B. Flag AAN: dezelfde incoming-doc-op valt door naar _translate_path en
     faalt LUID (het op-resultaat draagt `error`) -> nooit een stille skip.
     Tot de partner de page publiceert EN er een translate-regel gewired is,
     stopt de push hier met een zichtbare fout i.p.v. ongemerkt door te gaan.

  C. Banner-keten: de `_skipped`-marker levert via _skipped_attachment_warning
     exact de tekst op met prefix "Bron-document is NIET", waar
     SourceDocLinkBanner.tsx in de UI op rendert -> zichtbaar voor de reviewer.

De live 404-diagnose (PLX_IncomingDocument niet gepubliceerd = partner-actie)
staat hier los van en draait via GET /api/diagnostics/nav/services tegen prod.

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct7_incoming_document.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'verify_funct7.db'}"
os.environ["NAVISION_MODE"] = "nav2018"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

import httpx  # noqa: E402

from kwabo.graph.nodes.push_navision import _skipped_attachment_warning  # noqa: E402
from kwabo.integrations.navision_nav2018 import Nav2018ODataClient  # noqa: E402

# De drie ops die samen het inkomend-document vormen (de PATCH draagt de
# {incoming_document_id}-placeholder; zonder skip raist de substitutie en
# faalt de hele push — daarom horen ze als bundel bij elkaar).
INCOMING_DOC_OPS = [
    {"op": "POST", "path": "/incomingDocuments",
     "body": {"description": "order-bestelling.eml", "vendorName": "Testklant"},
     "label": "Bron-document aanmaken"},
    {"op": "PATCH", "path": "/salesOrders({id})",
     "body": {"incomingDocumentNumber": "{incoming_document_id}"},
     "label": "Bron-document koppelen aan order"},
    {"op": "POST", "path": "/incomingDocuments({incoming_document_id})/attachments",
     "body": {"fileName": "order-bestelling.eml", "_attachment_path": "/tmp/x.eml"},
     "label": "Bestand uploaden"},
]

ORDER_OPS = [
    {"op": "POST", "path": "/salesOrders", "body": {"customerNumber": "50000"}},
    {"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
     "body": {"lineType": "Item", "itemNumber": "238531"}},
]


def _client(*, enabled: bool) -> Nav2018ODataClient:
    """nav2018-client met gestubde transport: header/regel-POSTs lukken (201),
    GETs zijn leeg. Géén echte NAV nodig — we testen de skip/fail-loud-logica."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                201, json={"No": "VO-TEST-1", "Document_No": "VO-TEST-1", "Line_No": 10000}
            )
        return httpx.Response(200, json={"value": []})

    return Nav2018ODataClient(
        base_url="https://mock.invalid/ODataV4",
        company="Testbedrijf",
        username="u",
        password="p",
        verify_ssl=False,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        incoming_document_enabled=enabled,
    )


def _is_skip(r: dict) -> bool:
    return any("incomingDocuments" in str(v) for v in (r.get("autofilled") or {}).values())


async def _deel_a() -> bool:
    client = _client(enabled=False)
    try:
        res = await client.create_sales_order_stepwise(ORDER_OPS + INCOMING_DOC_OPS)
    finally:
        await client.aclose()
    ops = res["operation_results"]
    skipped = [r for r in ops if _is_skip(r)]
    order_ok = [r for r in ops if not _is_skip(r)]
    no_error = all(not r.get("error") for r in order_ok)
    print("A. Flag UIT — incoming-doc-ops detecteren + overslaan, order blijft staan")
    print(f"   overgeslagen incoming-doc-ops = {len(skipped)} (verwacht 3)")
    print(f"   uitgevoerde header/regel-ops  = {len(order_ok)} zonder error = {no_error}")
    ok = len(skipped) == 3 and len(order_ok) == 2 and no_error
    print(f"   -> {'[OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def _deel_b() -> bool:
    client = _client(enabled=True)
    try:
        res = await client.create_sales_order_stepwise([INCOMING_DOC_OPS[0]])
    finally:
        await client.aclose()
    r = res["operation_results"][0]
    err = r.get("error")
    print("B. Flag AAN — incoming-doc-op faalt LUID (geen stille skip)")
    print(f"   op overgeslagen? = {_is_skip(r)} (verwacht False)")
    print(f"   error            = {err}")
    ok = not _is_skip(r) and bool(err)
    print(f"   -> {'[OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def _deel_c() -> bool:
    client = _client(enabled=False)
    try:
        res = await client.create_sales_order_stepwise(INCOMING_DOC_OPS)
    finally:
        await client.aclose()
    warning = _skipped_attachment_warning(res["operation_results"])
    prefix = "Bron-document is NIET"
    print("C. Banner-keten — skip-marker levert de reviewer-waarschuwing op")
    print(f"   warning = {warning!r}")
    ok = bool(warning) and warning.startswith(prefix) and "handmatig" in warning.lower()
    print(f"   -> {'banner-prefix matcht SourceDocLinkBanner.tsx [OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def main() -> int:
    a = await _deel_a()
    b = await _deel_b()
    c = await _deel_c()
    print("RESULTAAT:", "ALLES GROEN [OK]" if (a and b and c) else "ONVERWACHT")
    return 0 if (a and b and c) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
