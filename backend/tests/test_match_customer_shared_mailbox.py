"""FASE 1 — TABS #954 (4506877460): een agent-/groepsmailbox waarvan het
e-maildomein veel klanten dekt mag NIET confident (conf 1.0) één willekeurige
kaart kiezen. Disambigueer op het LEVERADRES via de ship-to-adressen van de
groep; uniek → match (conf 0.9 + CONTROLEER), anders kandidaten (geen gok).

Echte casus: supplychain@tabsholland.nl staat op precies één kaart (61793
PontMeyer Heerenveen) maar het domein tabsholland.nl dekt ~98 klanten over
meerdere merken. Het leveradres (Jongeneel Woerden 3449 JE) wijst de juiste
klant aan: 50094. De klantenkaarten hebben plaats/postcode NULL (zoals prod);
disambiguatie loopt dus via de ship-to-master.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import Klantenkaart, KlantenkaartShipTo
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


# (nav_klantnr, naam, email, [(ship_to_code, naam, straat, postcode, plaats)])
_GROEP = [
    ("61793", "PontMeyer Heerenveen", "supplychain@tabsholland.nl;heerenveen@pontmeyer.nl",
     [("8447 GH", "PontMeyer Heerenveen", "Skrynmakker 17", "8447 GH", "HEERENVEEN")]),
    ("50094", "Jongeneel Woerden BA659", "confirmation@tabsholland.nl;woerden@jongeneel.nl",
     [("3449 JE", "Jongeneel Woerden BA659", "Pijpenmakersweg 2", "3449 JE", "WOERDEN")]),
    ("60981", "PontMeyer", "confirmation@tabsholland.nl",
     [("1500 GA", "PontMeyer Zaandam", "Pinksterbloem 1", "1500 GA", "ZAANDAM")]),
    ("50047", "Jongeneel Alkmaar BA640", "confirmation@tabsholland.nl;alkmaar@jongeneel.nl",
     [("1812 PX", "Jongeneel Alkmaar BA640", "Marconistraat 5", "1812 PX", "ALKMAAR")]),
]


def _seed_groep(session):
    for nr, naam, email, shiptos in _GROEP:
        # plaats/postcode bewust NULL — exact zoals prod (customers-sync vult ze niet).
        session.add(Klantenkaart(nav_klantnr=nr, naam=naam, email=email))
        for code, snaam, straat, pc, plaats in shiptos:
            session.add(KlantenkaartShipTo(
                klant_nr=nr, ship_to_code=code, naam=snaam, straat=straat,
                postcode=pc, plaats=plaats, land="NL", is_default=False))
    session.commit()


def _state(**over):
    base = {
        "email_id": "o954",
        "email_from": "TABS Supply Chain <supplychain@tabsholland.nl>",
        "email_subject": "Bestelling 4506877460 633",
        "email_body": "", "bijlagen": [], "stappen_log": [], "orderregels": [],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_gedeelde_mailbox_kiest_op_leveradres(bind):
    _seed_groep(bind)
    state = _state(afleveradres={"naam": "Jongeneel Woerden BA659",
                                 "straat": "Pijpenmakersweg 2",
                                 "postcode": "3449 JE", "plaats": "WOERDEN", "land": "NL"})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "50094"  # niet 61793
    assert out["klant_match"]["match_confidence"] == 0.9
    assert out["klant_match"]["match_bron"] == "leveradres_shipto"
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_gedeelde_mailbox_leveradres_heerenveen_kiest_61793(bind):
    """Controle: hetzelfde gedeelde-mailbox-pad kiest 61793 als het leveradres
    Heerenveen is — disambiguatie volgt het leveradres, niet de kaart."""
    _seed_groep(bind)
    state = _state(afleveradres={"naam": "PontMeyer Heerenveen", "straat": "Skrynmakker 17",
                                 "postcode": "8447 GH", "plaats": "HEERENVEEN"})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61793"
    assert out["klant_match"]["match_bron"] == "leveradres_shipto"


@pytest.mark.asyncio
async def test_gedeelde_mailbox_geen_leveradres_match_geeft_kandidaten(bind):
    """Geen leveradres dat een ship-to aanwijst → géén confidente pick;
    kandidatenlijst + CONTROLEER (geen gok)."""
    _seed_groep(bind)
    state = _state(afleveradres={"postcode": "9999 ZZ", "plaats": "Onbekend"})
    out = await match_customer_node(state)
    assert out["klant_match"] is None
    assert out["klant_kandidaten"]
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_unieke_klant_op_eigen_email_blijft_conf_1(bind):
    """Backward-compat: een klant met een UNIEK e-maildomein (niet gedeeld)
    matcht gewoon confident op conf 1.0."""
    bind.add(Klantenkaart(nav_klantnr="60892", naam="Witzand Bouwmaterialen",
                          email="inkoop@witzand.nl"))
    bind.commit()
    state = _state(email_from="inkoop@witzand.nl",
                   afleveradres={"postcode": "3433 PA", "plaats": "Nieuwegein"})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert "klant_match" not in out["needs_review_fields"]
