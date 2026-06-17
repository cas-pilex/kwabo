"""FUNCTIE 7 — inkomend document in NAV: config-gated activatie.

Vandaag heeft NAV 2018 geen gepubliceerde PLX_IncomingDocument-page, dus de
nav2018-client slaat de 3 incoming-doc-ops bewust over (header+regels blijven
geldig; de reviewer krijgt een waarschuwing). Zodra de page er is moet dat
aangezet kunnen worden zonder code-deploy: een env-flag heft de skip op.

Deze tests borgen:
  1. De flag staat default UIT (nul gedragswijziging in prod).
  2. Flag UIT  -> de nav2018-client skipt de incoming-doc-ops (huidig gedrag).
  3. Flag AAN  -> de nav2018-client skipt NIET meer; hij probeert de ops uit te
     voeren (de daadwerkelijke transport-vertaling naar de PLX-page is
     partner-werk zodra de echte page-vorm bekend is — tot dan faalt het
     luid, nooit stil).
  4. De composer->execute-keten is testbaar klaar: tegen de MockNavisionClient
     (die de gepubliceerde page emuleert) worden de 3 ops volledig uitgevoerd —
     document aangemaakt, gekoppeld en bijlage geupload, geen skip.

[[nav-spec-conformiteit-mix-incomingdoc]]
"""
from __future__ import annotations

import base64

import httpx
import pytest

from kwabo.integrations.nav_operations import NavOperation
from kwabo.integrations.navision_nav2018 import Nav2018ODataClient


# The 3 incoming-doc ops exactly as compose_navision_operations emits them.
def _incoming_doc_ops(attachment_path: str) -> list[NavOperation]:
    return [
        {"op": "POST", "path": "/incomingDocuments",
         "body": {"description": "Bestelling PO-9", "vendorName": "Ferney Diabolo B.V."}},
        {"op": "PATCH", "path": "/salesOrders({id})",
         "body": {"incomingDocumentNumber": "{incoming_document_id}"}},
        {"op": "POST", "path": "/incomingDocuments({incoming_document_id})/attachments",
         "body": {"fileName": "PO-9.eml", "_attachment_path": attachment_path}},
    ]


def _exploding_transport() -> httpx.AsyncClient:
    """Any HTTP call fails the test — proves the ops never hit the wire."""
    def _boom(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError(f"unexpected HTTP call: {_request.method} {_request.url}")

    return httpx.AsyncClient(transport=httpx.MockTransport(_boom))


def _nav2018(http_client: httpx.AsyncClient, **kw) -> Nav2018ODataClient:
    return Nav2018ODataClient(
        base_url="https://nav.example.com:1153/ST-1/ODataV4",
        company="Kopie 2026 Kwabo Techniek B.V.",
        username="user",
        password="key",
        verify_ssl=False,
        http_client=http_client,
        **kw,
    )


def test_config_flag_defaults_off():
    from kwabo.config import settings

    assert settings.nav2018_incoming_document_enabled is False


@pytest.mark.asyncio
async def test_nav2018_skips_incoming_doc_when_flag_off():
    client = _nav2018(_exploding_transport())  # default flag = off
    result = await client.create_sales_order_stepwise(_incoming_doc_ops("/tmp/PO-9.eml"))

    results = result["operation_results"]
    assert len(results) == 3
    assert all(
        (r.get("autofilled") or {}).get("_skipped") for r in results
    ), results
    assert all(not r.get("error") for r in results)


@pytest.mark.asyncio
async def test_nav2018_attempts_incoming_doc_when_flag_on():
    client = _nav2018(_exploding_transport(), incoming_document_enabled=True)
    result = await client.create_sales_order_stepwise(_incoming_doc_ops("/tmp/PO-9.eml"))

    results = result["operation_results"]
    # Gating works: the skip branch is bypassed entirely.
    assert not any((r.get("autofilled") or {}).get("_skipped") for r in results), results
    # The transport translation isn't wired yet (needs the real published
    # page) -> it must fail LOUDLY, never silently skip.
    assert any(r.get("error") for r in results), results


@pytest.mark.asyncio
async def test_composer_path_ready_end_to_end_against_mock(tmp_path):
    """The published page is emulated by MockNavisionClient: the composed
    3-op bundle executes fully (doc created, linked, attachment uploaded)."""
    from kwabo.integrations.navision_api import MockNavisionClient
    from kwabo.integrations.navision_steps import compose_navision_operations

    incoming_doc = tmp_path / "PO-9.eml"
    payload = b"raw email bytes"
    incoming_doc.write_bytes(payload)

    state = {
        "klant_match": {"navision_klantnr": "10001", "klantnaam": "Ferney Diabolo B.V."},
        "orderregels": [{
            "artikelnummer_kwabo_matched": "1515155",
            "hoeveelheid": 5, "eenheid": "STUK", "eenheid_default": "STUK",
        }],
        "email_subject": "Bestelling PO-9",
        "incoming_document_path": str(incoming_doc),
    }
    ops = compose_navision_operations(state)

    client = MockNavisionClient()
    result = await client.create_sales_order_stepwise(ops)

    results = result["operation_results"]
    assert not any((r.get("autofilled") or {}).get("_skipped") for r in results), results
    assert all(not r.get("error") for r in results), results

    # Document created + attachment uploaded with the real bytes.
    docs = list(client._incoming_documents.values())
    assert len(docs) == 1
    assert docs[0]["attachments"], "attachment must be uploaded"
    decoded = base64.b64decode(docs[0]["attachments"][0]["content"])
    assert decoded == payload
