"""match_customer zet warning als ordertotaal > kredietlimiet."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest
from sqlmodel import select

from kwabo.db.models import Klantenkaart
from kwabo.graph.nodes.match_customer import match_customer_node


@pytest.fixture
def app_engine(session, monkeypatch):
    """Override the app's module-level engine to use the test session's engine."""
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_customer as mc_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    yield


@pytest.mark.asyncio
async def test_warning_bij_overschrijding(session, app_engine):
    k = session.exec(select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10001")).first()
    k.kredietlimiet = 100.0
    session.add(k)
    session.commit()

    state = {
        "email_id": "k1",
        "email_from": "purchaseorders@ferney.nl",
        "email_subject": "Order",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [
            {"positie": 1, "hoeveelheid": 10, "prijs_per_eenheid": 20.0},
        ],
    }
    out = await match_customer_node(state)
    assert any("kredietlimiet" in w.lower() for w in out.get("validatie_warnings") or [])


@pytest.mark.asyncio
async def test_geen_warning_onder_limiet(session, app_engine):
    k = session.exec(select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10001")).first()
    k.kredietlimiet = 1000.0
    session.add(k)
    session.commit()

    state = {
        "email_id": "k2",
        "email_from": "purchaseorders@ferney.nl",
        "email_subject": "Order",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [
            {"positie": 1, "hoeveelheid": 10, "prijs_per_eenheid": 20.0},
        ],
    }
    out = await match_customer_node(state)
    assert not any("kredietlimiet overschreden" in w.lower() for w in out.get("validatie_warnings") or [])
