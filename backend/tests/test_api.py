"""FastAPI endpoint tests via TestClient (no LLM calls)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(session):
    """Create a TestClient backed by the seeded test DB."""
    # Override engine to use the test session's engine
    from kwabo.db import session as db_session_mod
    original_engine = db_session_mod.engine
    db_session_mod.engine = session.get_bind()

    from kwabo.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c

    db_session_mod.engine = original_engine


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "kwabo-order-intake"


def test_list_klanten(client):
    r = client.get("/api/klanten")
    assert r.status_code == 200
    klanten = r.json()
    assert len(klanten) >= 16
    assert any(k["nav_klantnr"] == "10001" for k in klanten)


def test_get_klant(client):
    r = client.get("/api/klanten/10001")
    assert r.status_code == 200
    assert r.json()["naam"] == "Ferney Diabolo B.V."


def test_get_klant_not_found(client):
    r = client.get("/api/klanten/99999")
    assert r.status_code == 404


def test_list_artikelen_search(client):
    r = client.get("/api/artikelen/search")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_audit_stats(client):
    r = client.get("/api/audit/stats")
    assert r.status_code == 200
    d = r.json()
    assert "total_orders" in d
    assert "by_status" in d


def test_prijsafspraken_crud(client):
    # List
    r = client.get("/api/klanten/10001/prijsafspraken")
    assert r.status_code == 200
    initial = len(r.json())

    # Add
    r = client.post("/api/klanten/10001/prijsafspraken", json={
        "kwabo_artikelnr": "TEST-API", "prijs": 42.00, "korting_pct": 10, "type": "standaard"
    })
    assert r.status_code == 200
    prijs_id = r.json()["id"]

    # Verify added
    r = client.get("/api/klanten/10001/prijsafspraken")
    assert len(r.json()) == initial + 1

    # Delete
    r = client.delete(f"/api/klanten/10001/prijsafspraken/{prijs_id}")
    assert r.status_code == 200

    # Verify deleted
    r = client.get("/api/klanten/10001/prijsafspraken")
    assert len(r.json()) == initial


def test_artikelmapping_add(client):
    r = client.post("/api/klanten/10001/artikelen", json={
        "klant_artikelnr": "API-TEST-K", "kwabo_artikelnr": "API-TEST-Q", "omschrijving": "test"
    })
    assert r.status_code == 200
    assert r.json()["kwabo_artikelnr"] == "API-TEST-Q"


def test_logs_tail(client):
    r = client.get("/api/logs/tail?lines=5")
    assert r.status_code == 200
    assert "lines" in r.json()


def test_orders_empty(client):
    r = client.get("/api/orders")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
