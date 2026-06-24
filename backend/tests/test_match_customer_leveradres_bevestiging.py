"""Review-kalibratie (24-06): een NAAM-afgeleide klant-match die ONAFHANKELIJK
en UNIEK door het leveradres wordt bevestigd mag vlagvrij door — zo daalt de
review-last zonder stille-fout-risico.

"Uniek bevestigd" = de exacte leverpostcode komt in de HELE ship-to-master bij
precies één klant voor, en dat is dezelfde klant als de naam-match. Twee
onafhankelijke unieke signalen (naam + postcode) → veilig conf 1.0 (geen vlag).
Bij een gedeelde postcode, of een postcode die een ANDERE klant aanwijst, blijft
de CONTROLEER-vlag staan (grondwet: niet gokken). Beschermt zichzelf bij
franchises (naam→overkoepelend vs postcode→vestiging wijken af → vuurt niet).
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


def _kaart(session, nr, naam, email, shiptos):
    session.add(Klantenkaart(nav_klantnr=nr, naam=naam, email=email))
    for code, pc in shiptos:
        session.add(KlantenkaartShipTo(
            klant_nr=nr, ship_to_code=code, naam=naam, straat="Straat 1",
            postcode=pc, plaats="Plaats", land="NL", is_default=False))
    session.commit()


def _state(naam_besteller, postcode):
    return {
        "email_id": "kal-1",
        # afzender staat op GÉÉN kaart → match loopt via de naam-fallback (K3).
        "email_from": "orders@agent-portal.example",
        "email_subject": "Bestelling",
        "email_body": "", "bijlagen": [], "stappen_log": [], "orderregels": [],
        "klantnaam_besteller": naam_besteller,
        "afleveradres": {"postcode": postcode, "plaats": "Plaats", "straat": "Straat 1"},
    }


@pytest.mark.asyncio
async def test_naam_match_uniek_bevestigd_door_postcode_is_vlagvrij(bind):
    _kaart(bind, "60892", "Witzand Bouwmaterialen", "inkoop@witzand.nl", [("3433 PA", "3433 PA")])
    _kaart(bind, "60001", "Andere Klant", "x@andere.nl", [("1111 AA", "1111 AA")])
    out = await match_customer_node(_state("Witzand Bouwmaterialen", "3433 PA"))
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert out["klant_match"].get("leveradres_bevestigd") is True
    assert "klant_match" not in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_gedeelde_postcode_blijft_gevlagd(bind):
    # Twee klanten op DEZELFDE leverpostcode → postcode is geen uniek signaal.
    _kaart(bind, "60892", "Witzand Bouwmaterialen", "inkoop@witzand.nl", [("3433 PA", "3433 PA")])
    _kaart(bind, "60002", "Tweede Klant", "x@tweede.nl", [("3433 PA", "3433 PA")])
    out = await match_customer_node(_state("Witzand Bouwmaterialen", "3433 PA"))
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_confidence"] < 1.0
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_postcode_wijst_andere_klant_aan_blijft_gevlagd(bind):
    # Naam zegt Witzand, maar de leverpostcode hoort UNIEK bij een ANDERE klant
    # → signalen wijken af → niet auto-bevestigen (zelfbescherming).
    _kaart(bind, "60892", "Witzand Bouwmaterialen", "inkoop@witzand.nl", [("3433 PA", "3433 PA")])
    _kaart(bind, "60003", "Derde Klant", "x@derde.nl", [("9999 ZZ", "9999 ZZ")])
    out = await match_customer_node(_state("Witzand Bouwmaterialen", "9999 ZZ"))
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_confidence"] < 1.0
    assert "klant_match" in out["needs_review_fields"]
