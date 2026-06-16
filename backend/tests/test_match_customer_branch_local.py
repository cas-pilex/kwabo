"""DEEL A — de LOKALE naam-fallback (K3, _match_by_name) moet bij een franchise
met één klantenkaart per vestiging (PontMeyer Heerenveen vs Zwaag) de juiste
vestiging op het LEVERADRES kiezen, niet blind de hoogste naam-score.

Onderscheid met test_match_customer_disambig.py: die test de NAV-zoekpaden
(K2a/K4). Hier vindt NAV niets, dus de lokale klantenkaart-mirror-fuzzy is aan
de beurt.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import Klantenkaart
from kwabo.db.seed import purge_demo_seed
from kwabo.graph.nodes import match_customer as mc_mod
from kwabo.graph.nodes.match_customer import match_customer_node


class _NoNav:
    async def search_customers(self, naam=None, email=None):
        return []


@pytest.fixture
def app_engine(session, monkeypatch):
    """Bind the matcher + repos to the test DB and load PontMeyer branch cards."""
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _NoNav())

    # Demo-seed (incl. "TABS / PontMeyer" 10002) vervuilt de pontmeyer-fuzzy.
    purge_demo_seed(session)
    session.add(Klantenkaart(nav_klantnr="61088", naam="PontMeyer Zwaag",
                             plaats="Zwaag", postcode="1689 AK"))
    session.add(Klantenkaart(nav_klantnr="61793", naam="PontMeyer Heerenveen",
                             plaats="Heerenveen", postcode="8444 AB"))
    session.commit()
    yield


def _state(**over):
    base = {
        "email_id": "p",
        "email_from": "inkoop@example-noklant.invalid",
        "email_subject": "Bestelling",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_bare_brand_picks_branch_on_leveradres_postcode(app_engine):
    """Besteller noemt alleen 'PontMeyer'; het leveradres (postcode Zwaag) kiest
    de juiste vestiging."""
    state = _state(
        klantnaam_besteller="PontMeyer",
        afleveradres={"postcode": "1689 AK", "plaats": "Zwaag"},
    )
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61088"
    assert out["klant_match"]["plaats"] == "Zwaag"
    assert out["klant_match"]["match_confidence"] == 0.85
    assert "Zwaag" in (out["klant_match"].get("match_uitleg") or "")
    # Naam-afgeleide match (< 1.0) → CONTROLEER-vlag.
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_leveradres_overrules_name_autopick_wrong_branch(app_engine):
    """#834: de besteller-naam noemt 'Heerenveen' (zou autopicken), maar het
    leveradres is Zwaag → het leveradres wint, niet de naam-score."""
    state = _state(
        klantnaam_besteller="PontMeyer Heerenveen",
        afleveradres={"postcode": "1689 AK", "plaats": "Zwaag"},
    )
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61088"  # Zwaag, niet 61793


@pytest.mark.asyncio
async def test_branches_without_leveradres_flags_review(app_engine):
    """Twee vestigingen, geen leveradres-signaal → niet gokken: kandidaten +
    CONTROLEER."""
    state = _state(klantnaam_besteller="PontMeyer")
    out = await match_customer_node(state)
    assert out["klant_match"] is None
    assert "klant_match" in out["needs_review_fields"]
    kandidaten = out.get("klant_kandidaten") or []
    nrs = {k["navision_klantnr"] for k in kandidaten}
    assert {"61088", "61793"} <= nrs
    assert all("plaats" in k for k in kandidaten)
    assert any("MEERDERE KLANTEN" in w for w in out.get("validatie_warnings") or [])


@pytest.mark.asyncio
async def test_single_entity_still_autopicks(session, monkeypatch):
    """Een klant zónder zuster-vestiging behoudt het bestaande autopick-gedrag
    (conf 0.8), ongewijzigd."""
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _NoNav())
    purge_demo_seed(session)
    session.add(Klantenkaart(nav_klantnr="60892", naam="Witzand Bouwmaterialen",
                             plaats="Nieuwegein", postcode="3433 PA"))
    session.commit()

    state = _state(klantnaam_besteller="Witzand Bouwmaterialen")
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_confidence"] == 0.8
