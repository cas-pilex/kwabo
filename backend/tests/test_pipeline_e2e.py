"""End-to-end pipeline tests for T9.

These tests prove the wired-up pipeline:
    compose_order -> (review pause) -> push_navision

emits a NavOperation list, executes it stepwise via MockNavisionClient,
and propagates per-op results + autofilled trigger output back into
state. They also cover the failure path (stop-on-error semantics).

We don't run the full ingest graph here — that's the regression suite's
job. Instead we hand-build a synthetic state that already has matched
articles, matched customer, and validated prices, then drive the two
nodes directly. This isolates T9's wiring from upstream LLM noise.
"""
from __future__ import annotations

import json
from typing import Optional

import pytest

from kwabo.graph.nodes.compose_order import compose_order_node
from kwabo.graph.nodes.push_navision import push_navision_node
from kwabo.graph.state import OrderState


def _synthetic_state(email_id: str = "e2e-pipeline-1") -> OrderState:
    """A minimal OrderState with everything T9 needs to execute end-to-end.

    Customer 10001 + item 1515155 are present in MOCK_CUSTOMERS / MOCK_ITEMS.
    """
    return {  # type: ignore[typeddict-item]
        "email_id": email_id,
        "email_from": "purchaseorders@ferney.nl",
        "email_subject": "PO-T9-001",
        "email_body": "Synthetic e2e order",
        "email_date": "2026-04-25",
        "bijlagen": [],
        "is_order": True,
        "classificatie_reden": "synthetic",
        "classificatie_confidence": 1.0,
        "klant_match": {
            "navision_klantnr": "10001",
            "klantnaam": "Ferney Diabolo B.V.",
            "match_confidence": 1.0,
            "match_bron": "manual",
        },
        "bestelnummer_klant": "PO-T9-001",
        "gewenste_leverdatum": "2026-05-01",
        "orderregels": [
            {
                "positie": 1,
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                "eenheid": "ROL",
                "prijs_per_eenheid": 100.0,
                "prijs_validated": True,
            },
        ],
        "alle_artikelen_gematcht": True,
        "alle_prijzen_valide": True,
        "validatie_warnings": [],
        "review_status": "approved",
        "stappen_log": [],
        "errors": [],
    }


@pytest.mark.asyncio
async def test_compose_order_populates_nav_operations(session, monkeypatch):
    """compose_order must populate state["nav_operations"] with the trigger-
    aware NavOperation list. Customer + matched line should both be present."""
    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.compose_order as compose_mod
    monkeypatch.setattr(compose_mod, "engine", session.get_bind())

    state = _synthetic_state()
    out = await compose_order_node(state)

    ops = out["nav_operations"]
    assert ops, "compose_order must populate nav_operations"

    # The first op is always the single-field customer POST.
    assert ops[0]["op"] == "POST"
    assert ops[0]["path"] == "/salesOrders"
    assert ops[0]["body"] == {"customerNumber": "10001"}

    # The matched line gets POSTed + (optional UoM PATCH) + qty PATCH.
    line_posts = [o for o in ops if o["path"].endswith("/salesOrderLines") and o["op"] == "POST"]
    assert len(line_posts) == 1
    assert line_posts[0]["body"] == {"lineType": "Item", "itemNumber": "1515155"}

    # order_log row was persisted with status=review.
    assert out["order_log_id"]
    assert out["review_status"] == "pending"


@pytest.mark.asyncio
async def test_e2e_push_navision_executes_operations(session, monkeypatch, tmp_path):
    """End-to-end: compose_order -> push_navision against a MockNavisionClient.

    Asserts:
      * push_navision result has a sales_order_number,
      * nav_operation_results recorded on state,
      * autofilled trigger fields visible.
    """
    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.compose_order as compose_mod
    import kwabo.graph.nodes.push_navision as push_mod
    monkeypatch.setattr(compose_mod, "engine", session.get_bind())
    monkeypatch.setattr(push_mod, "engine", session.get_bind())

    # Pin a deterministic out_dir for the mock client; the default uses
    # settings.navision_mock_path/orders which writes outside tmp_path.
    from kwabo.integrations.navision_api import MockNavisionClient
    pinned_client = MockNavisionClient(out_dir=tmp_path)
    monkeypatch.setattr(
        "kwabo.graph.nodes.push_navision.get_navision_client",
        lambda: pinned_client,
    )

    state = _synthetic_state(email_id="e2e-pipeline-happy")

    composed = await compose_order_node(state)
    assert composed["nav_operations"], "compose_order should have populated ops"

    pushed = await push_navision_node(composed)

    assert pushed["navision_status"] == "Draft", (
        f"push_navision should mark Draft, got status={pushed.get('navision_status')!r}, "
        f"results={pushed.get('nav_operation_results')!r}"
    )
    assert pushed["navision_order_nr"], "expected a sales_order_number"
    assert pushed["navision_order_nr"].startswith("SO-")

    op_results = pushed["nav_operation_results"]
    assert len(op_results) == len(composed["nav_operations"])
    for r in op_results:
        assert "error" not in r, f"unexpected op error: {r}"

    # Trigger autofill captured (e.g. paymentTermsCode from POST /salesOrders).
    autofilled = pushed["nav_autofilled"]
    assert "paymentTermsCode" in autofilled or "currencyCode" in autofilled

    # The order_log row was updated with status=pushed + the order number.
    # Use a fresh session — the fixture session has the row cached at its
    # pre-update state.
    from sqlmodel import Session as _Session
    from kwabo.db.repository import OrderLogRepo
    with _Session(session.get_bind()) as fresh:
        row = OrderLogRepo(fresh).get(pushed["order_log_id"])
        assert row.status == "pushed"
        assert row.navision_order_nr == pushed["navision_order_nr"]


@pytest.mark.asyncio
async def test_e2e_push_navision_stop_on_error(session, monkeypatch, tmp_path):
    """Inject a failure on the second PATCH; verify push_navision marks the
    order failed but compose_order still saved the prepared ops in state."""
    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.compose_order as compose_mod
    import kwabo.graph.nodes.push_navision as push_mod
    monkeypatch.setattr(compose_mod, "engine", session.get_bind())
    monkeypatch.setattr(push_mod, "engine", session.get_bind())

    from kwabo.integrations.navision_api import MockNavisionClient
    pinned_client = MockNavisionClient(out_dir=tmp_path)

    # Force the THIRD op (index 2) to fail. With our synthetic state the
    # composed sequence is:
    #   0: POST /salesOrders
    #   1: PATCH externalDocumentNumber
    #   2: PATCH requestedDeliveryDate     <-- forced failure
    def predicate(idx: int, op: dict) -> Optional[str]:
        if idx == 2:
            return "simulated NAV failure on PATCH #2"
        return None
    pinned_client._fail_predicate = predicate

    monkeypatch.setattr(
        "kwabo.graph.nodes.push_navision.get_navision_client",
        lambda: pinned_client,
    )

    state = _synthetic_state(email_id="e2e-pipeline-fail")

    composed = await compose_order_node(state)
    composed_ops = composed["nav_operations"]
    # compose_order must NOT have been short-circuited by the failure
    # injection (which only fires at push time).
    assert composed_ops, "prepared ops must still be saved even when push fails"

    pushed = await push_navision_node(composed)

    assert pushed["navision_status"] == "failed"
    assert not pushed.get("navision_order_nr")
    op_results = pushed["nav_operation_results"]
    assert len(op_results) == 3, "stepwise client stops after the failed op"
    assert op_results[2].get("error") == "simulated NAV failure on PATCH #2"

    # The DB row reflects the failure (read through a fresh session so the
    # fixture session's cached row doesn't shadow the update).
    from sqlmodel import Session as _Session
    from kwabo.db.repository import OrderLogRepo
    with _Session(session.get_bind()) as fresh:
        row = OrderLogRepo(fresh).get(composed["order_log_id"])
        assert row.status == "failed"

    # Audit trail records the reason.
    push_step = [s for s in pushed["stappen_log"] if s["stap"] == "push_navision"][0]
    assert "afgebroken" in push_step["beslissing"].lower()

    # And errors[] is populated for downstream consumers.
    assert any("push_navision" in e for e in pushed["errors"])


@pytest.mark.asyncio
async def test_push_navision_without_operations_marks_failed(session, monkeypatch):
    """If compose_order didn't populate nav_operations (e.g. no klant match),
    push_navision must refuse and mark the row failed."""
    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.push_navision as push_mod
    monkeypatch.setattr(push_mod, "engine", session.get_bind())

    # Persist a stub row first so we can verify the status update.
    from kwabo.db.repository import OrderLogRepo
    repo = OrderLogRepo(session)
    row = repo.create(
        email_id="t9-no-ops",
        status="approved",
        is_order=True,
    )

    state: OrderState = {  # type: ignore[typeddict-item]
        "email_id": "t9-no-ops",
        "order_log_id": row.id,
        "is_order": True,
        "stappen_log": [],
        "errors": [],
        "nav_operations": [],
    }
    pushed = await push_navision_node(state)
    assert pushed["navision_status"] == "failed"

    # Re-query in a fresh session — the test fixture session has the row
    # cached at its pre-update state.
    from sqlmodel import Session
    with Session(session.get_bind()) as fresh:
        refreshed = OrderLogRepo(fresh).get(row.id)
        assert refreshed.status == "failed"


@pytest.mark.asyncio
async def test_navision_preview_endpoint_returns_operations_shape(session, monkeypatch):
    """The /api/orders/{id}/navision-preview endpoint returns the new
    {operations, expected_post_count, expected_patch_count, status,
    missing_count} shape — no more {header, lines}."""
    from fastapi.testclient import TestClient

    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.compose_order as compose_mod
    monkeypatch.setattr(compose_mod, "engine", session.get_bind())
    import kwabo.api.preview as preview_mod
    monkeypatch.setattr(preview_mod, "engine", session.get_bind())

    # Drive compose_order so a row exists with nav_operations on state.
    state = _synthetic_state(email_id="preview-e2e-1")
    composed = await compose_order_node(state)
    order_id = composed["order_log_id"]

    from kwabo.main import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.get(f"/api/orders/{order_id}/navision-preview")
        assert r.status_code == 200, r.text
        body = r.json()

    assert "header" not in body and "lines" not in body, (
        "T9 dropped the legacy {header, lines} preview shape"
    )
    assert "operations" in body
    assert isinstance(body["operations"], list) and body["operations"]
    assert body["expected_post_count"] >= 1
    assert body["expected_patch_count"] >= 1
    # First op invariant: customer POST.
    assert body["operations"][0]["op"] == "POST"
    assert body["operations"][0]["path"] == "/salesOrders"
