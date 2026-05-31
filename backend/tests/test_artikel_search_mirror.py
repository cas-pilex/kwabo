"""Regressie: /api/artikelen/search wordt uit de lokale Artikelkaart-mirror
bediend i.p.v. live NAV OData. Voorheen haalde elke order-detailpagina de
volledige NAV-itemcatalogus op (geen $top) -> ~15s SSR per pagina = "app sloom".
Ontdekt 31-05-2026 tijdens de live E2E-verificatie (responseEnd ~15s).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kwabo.db.models import Artikelkaart


@pytest.fixture
def client(session):
    """TestClient backed by de geseede test-DB (zelfde patroon als test_api.py)."""
    from kwabo.db import session as db_session_mod

    original_engine = db_session_mod.engine
    db_session_mod.engine = session.get_bind()
    from kwabo.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
    db_session_mod.engine = original_engine


def _seed_items(session) -> None:
    session.add(Artikelkaart(kwabo_artikelnr="900001", naam="Afdekvlies 160gr 1x50m", basis_eenheid="ROL"))
    session.add(Artikelkaart(kwabo_artikelnr="900002", naam="Beschermfolie transparant", basis_eenheid="ROL"))
    session.add(Artikelkaart(kwabo_artikelnr="900003", naam="Schuurpapier korrel 120", basis_eenheid="STUK"))
    session.commit()


def test_search_serves_from_mirror(client, session):
    _seed_items(session)
    r = client.get("/api/artikelen/search")
    assert r.status_code == 200
    body = r.json()
    nrs = {i["number"] for i in body}
    assert {"900001", "900002", "900003"} <= nrs


def test_search_filters_by_query(client, session):
    _seed_items(session)
    r = client.get("/api/artikelen/search", params={"q": "vlies"})
    assert r.status_code == 200
    body = r.json()
    nrs = {i["number"] for i in body}
    assert "900001" in nrs  # naam bevat "vlies"
    assert "900003" not in nrs


def test_search_filters_by_artikelnr(client, session):
    _seed_items(session)
    r = client.get("/api/artikelen/search", params={"q": "900002"})
    assert r.status_code == 200
    nrs = {i["number"] for i in r.json()}
    assert nrs == {"900002"}


def test_search_no_match_returns_empty_without_nav_fallback(client, session):
    """Met een gevulde mirror mag een niet-bestaande query GEEN dure NAV-call doen
    en gewoon een lege lijst geven."""
    _seed_items(session)
    r = client.get("/api/artikelen/search", params={"q": "ditbestaatzeker-niet-xyz"})
    assert r.status_code == 200
    assert r.json() == []
