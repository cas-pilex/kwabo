"""DEEL A (uitbreiding) — vestiging-correctie op leveradres geldt voor ELKE
match, ook een confidente e-mailmatch (conf 1.0).

Echte casus #834: de agent-mail supplychain@tabsholland.nl staat op precies één
kaart (PontMeyer Heerenveen 61793), dus K1 by_email matcht confident Heerenveen,
terwijl het leveradres PontMeyer Zwaag (61088) is. Het leveradres is leidend:
een agent-/groepsmail kan op de verkeerde vestiging staan.
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
def bind(session, monkeypatch):
    from kwabo.db import session as db_session_mod

    eng = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", eng)
    monkeypatch.setattr(mc_mod, "engine", eng)
    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _NoNav())
    purge_demo_seed(session)
    yield session


def _pontmeyer(session):
    session.add(Klantenkaart(
        nav_klantnr="61793", naam="PontMeyer Heerenveen",
        email="supplychain@tabsholland.nl;heerenveen@pontmeyer.nl",
        plaats="Heerenveen", postcode="8444 AB"))
    session.add(Klantenkaart(
        nav_klantnr="61088", naam="PontMeyer Zwaag",
        email="zwaag@pontmeyer.nl", plaats="Zwaag", postcode="1689 AK"))
    session.commit()


def _state(**over):
    base = {
        "email_id": "o834",
        "email_from": "TABS Supply Chain <supplychain@tabsholland.nl>",
        "email_subject": "Bestelling 4506870444 157",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_email_match_corrected_to_leveradres_vestiging(bind):
    _pontmeyer(bind)
    state = _state(afleveradres={"naam": "PontMeyer Zwaag", "straat": "De Factorij 23",
                                 "postcode": "1689 AK", "plaats": "ZWAAG", "land": "NL"})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61088"  # Zwaag, niet 61793
    assert out["klant_match"]["match_confidence"] == 0.85
    assert "leveradres" in (out["klant_match"].get("match_uitleg") or "").lower()
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_email_match_confirmed_by_leveradres_stays_vlagvrij(bind):
    _pontmeyer(bind)
    # Leveradres = Heerenveen → de e-mailmatch klopt → onaangeroerd, conf 1.0.
    state = _state(afleveradres={"naam": "PontMeyer Heerenveen",
                                 "postcode": "8444 AB", "plaats": "Heerenveen"})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61793"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert "klant_match" not in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_coincidental_city_in_body_does_not_override_correct_email_match(bind):
    """Een zuster-vestiging-stad die alleen TOEVALLIG in de mailtekst/bijlage
    voorkomt (footer, vorige thread) mag een correcte confidente e-mailmatch
    NIET overschrijven. De correctie kijkt uitsluitend naar het leveradres."""
    _pontmeyer(bind)
    state = _state(
        email_body="PS: wij leveren ook vanuit onze vestiging in Zwaag.",
        # Leveradres wijst GEEN zuster-vestiging aan (postcode matcht niets).
        afleveradres={"postcode": "9999 ZZ", "plaats": ""},
    )
    out = await match_customer_node(state)
    # supplychain@ matcht Heerenveen op e-mail; geen leveradres-signaal naar een
    # andere vestiging → blijft Heerenveen, vlagvrij.
    assert out["klant_match"]["navision_klantnr"] == "61793"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert "klant_match" not in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_non_franchise_email_match_untouched(bind):
    bind.add(Klantenkaart(nav_klantnr="60892", naam="Witzand Bouwmaterialen",
                          email="inkoop@witzand.nl", plaats="Nieuwegein", postcode="3433 PA"))
    bind.commit()
    state = _state(email_from="inkoop@witzand.nl",
                   afleveradres={"postcode": "9999 ZZ", "plaats": "Ergens"})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert "klant_match" not in out["needs_review_fields"]
