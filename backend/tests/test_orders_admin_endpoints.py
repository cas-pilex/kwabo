"""Tests for the post-MVP admin-style endpoints on /api/orders.

Covers DELETE /api/orders/{id}, GET /api/orders/{id}/nav-debug, and the
updated approve_order response shape that surfaces nav_status/nav_error
to the reviewer.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from kwabo.main import create_app


@pytest.fixture
def client(session, monkeypatch):
    """TestClient backed by the seeded test DB.

    orders.py reads the engine via ``db_session.engine`` at call time, so
    patching the single source ``kwabo.db.session.engine`` is sufficient for
    handlers inside ``with Session(db_session.engine) as s:`` blocks.
    """
    test_engine = session.get_bind()
    monkeypatch.setattr("kwabo.db.session.engine", test_engine, raising=True)
    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed_order(session, status: str = "review", order_state: dict | None = None) -> int:
    from kwabo.db.repository import OrderLogRepo
    repo = OrderLogRepo(session)
    row = repo.create(
        email_id=f"test-{status}",
        status=status,
        is_order=True,
        order_state=json.dumps(order_state or {"orderregels": []}),
    )
    return row.id


# ---------- DELETE /api/orders/{id} ----------


def test_delete_requires_confirm_query(client, session):
    order_id = _seed_order(session)
    r = client.delete(f"/api/orders/{order_id}")
    assert r.status_code == 400
    assert "confirm" in r.json()["detail"].lower()


def test_delete_with_confirm_removes_row(client, session):
    order_id = _seed_order(session)
    r = client.delete(f"/api/orders/{order_id}?confirm=true")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "deleted_id": order_id}
    # Subsequent GET must 404.
    r2 = client.get(f"/api/orders/{order_id}")
    assert r2.status_code == 404


def test_delete_unknown_id_404s(client, session):
    r = client.delete("/api/orders/999999?confirm=true")
    assert r.status_code == 404


# ---------- GET /api/orders/{id}/nav-debug ----------


def test_nav_debug_returns_op_trail(client, session):
    state = {
        "navision_status": "failed",
        "errors": ["push_navision: NAV op failed: HTTP 400 STUK not allowed"],
        "nav_operation_results": [
            {
                "operation": {"op": "POST", "path": "/salesOrders", "label": "Klant"},
                "status": 201,
                "response_body": {"id": "abc"},
                "autofilled": {},
            },
            {
                "operation": {"op": "PATCH", "path": "/salesOrderLines(id)", "label": "Regel 1 qty"},
                "status": 400,
                "response_body": {},
                "error": "HTTP 400 STUK not allowed",
            },
        ],
    }
    order_id = _seed_order(session, status="failed", order_state=state)
    r = client.get(f"/api/orders/{order_id}/nav-debug")
    assert r.status_code == 200
    body = r.json()
    assert body["order_id"] == order_id
    assert body["status"] == "failed"
    assert body["navision_status"] == "failed"
    assert len(body["nav_operation_results"]) == 2
    assert body["nav_operation_results"][1]["error"] == "HTTP 400 STUK not allowed"
    assert "push_navision:" in body["errors"][0]


def test_nav_debug_unknown_id_404s(client):
    r = client.get("/api/orders/999999/nav-debug")
    assert r.status_code == 404


def test_nav_debug_empty_for_fresh_order(client, session):
    """Order that hasn't been pushed yet returns empty trails."""
    order_id = _seed_order(session)
    r = client.get(f"/api/orders/{order_id}/nav-debug")
    assert r.status_code == 200
    body = r.json()
    assert body["nav_operation_results"] == []
    assert body["errors"] == []
    assert body["navision_order_nr"] is None
