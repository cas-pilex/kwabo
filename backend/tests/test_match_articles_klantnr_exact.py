"""A1 (Fase 2): een geëxtraheerd klant-artnr dat zélf een geldig Kwabo-nummer
is, moet direct exact matchen — niet als klant-SKU de fuzzy-cascade in.

Echte faalgevallen:
  * #718 Witzand: klant_art="238601" (geldig Kwabo-nr, geen kruisverwijzing)
    werd fuzzy gematcht naar 11190 "Vloerschraper met steel 30 cm".
  * #550/#635 pontmeyer/jongeneel: de LLM wisselt de kolommen om —
    klant_art="238531" en kwabo="K700100093" (de échte PontMeyer-SKU).

Voorrang (besloten met Cas): een expliciete mapping voor (klant, nummer)
— kruisverwijzing (NAV 5717) of klantenkaart-mapping — wint altijd van de
nummer-collisie-interpretatie. A1 vuurt alleen als die er niet zijn.

A1 checkt alléén de lokale artikelkaarten-mirror (geen live-NAV-fallback):
elke ongematchte regel zou anders een extra NAV-round-trip kosten, en een
nummer dat niet in de gesyncde mirror staat is vrijwel zeker geen Kwabo-nr.
"""
from __future__ import annotations

import json

import pytest

from kwabo.db.models import Artikelkaart, ArtikelKruisverwijzing, KlantenkaartArtikel
from kwabo.graph.nodes.match_articles import match_articles_node

from conftest import load_state


@pytest.fixture
def app_engine(session, monkeypatch):
    """Swap the module-level engine so the node sees our test DB."""
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_articles as ma_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


def _insert_artikelkaart(session, nr: str, naam: str) -> None:
    session.add(Artikelkaart(kwabo_artikelnr=nr, naam=naam, basis_eenheid="STUK"))
    session.commit()


def _state(klant_nr: str | None, regels: list[dict]) -> dict:
    return {
        "email_id": "a1-test",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": {"navision_klantnr": klant_nr} if klant_nr else None,
        "orderregels": regels,
    }


@pytest.mark.asyncio
async def test_klant_artnr_dat_kwabo_nr_is_matcht_exact(session, app_engine):
    """Geval 238601 (Witzand #718): geldig Kwabo-nr in klant_art → exact."""
    _insert_artikelkaart(session, "238601", "Quality Covers|Top coat Heavy-duty/25m²/67cm")

    state = _state("60892", [{
        "positie": 1,
        "artikelnummer_klant": "238601",
        "artikelnummer_kwabo": "5021180003",  # Witzand-EAN, géén Kwabo-nr
        "omschrijving": "Afdekvlies 0,67x37 mt wit met zelfklevende onderzijde",
        "hoeveelheid": 5,
    }])

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "238601"
    assert regel["match_methode"] == "exact_klantnr"
    assert regel["match_confidence"] == 1.0
    # Confident match → regel niet in review.
    assert "orderregels[0].artikelnummer_kwabo_matched" not in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_kruisverwijzing_wint_van_exact_klantnr(session, app_engine):
    """Een klant-SKU die toevallig een Kwabo-nr is maar een kruisverwijzing
    naar een ánder artikel heeft → de klant-mapping is gezaghebbend."""
    _insert_artikelkaart(session, "238601", "Quality Covers|Top coat Heavy-duty/25m²/67cm")
    session.add(ArtikelKruisverwijzing(
        klant_nr="60892", klant_artikelnr="238601",
        kwabo_artikelnr="1515155", bron="customer",
    ))
    session.commit()

    state = _state("60892", [{
        "positie": 1,
        "artikelnummer_klant": "238601",
        "artikelnummer_kwabo": None,
        "omschrijving": "",
        "hoeveelheid": 1,
    }])

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "kruisverwijzing"
    assert regel["artikelnummer_kwabo_matched"] == "1515155"


@pytest.mark.asyncio
async def test_klantenkaart_mapping_wint_van_exact_klantnr(session, app_engine):
    """Idem voor een handmatige klantenkaart-mapping op hetzelfde nummer."""
    _insert_artikelkaart(session, "238601", "Quality Covers|Top coat Heavy-duty/25m²/67cm")
    session.add(KlantenkaartArtikel(
        klant_nr="60892", klant_artikelnr="238601",
        kwabo_artikelnr="228321", omschrijving="bewuste mapping",
    ))
    session.commit()

    state = _state("60892", [{
        "positie": 1,
        "artikelnummer_klant": "238601",
        "artikelnummer_kwabo": None,
        "omschrijving": "",
        "hoeveelheid": 1,
    }])

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "klantenkaart"
    assert regel["artikelnummer_kwabo_matched"] == "228321"


@pytest.mark.asyncio
async def test_zonder_klant_nr_krijgt_review_vlag(session, app_engine):
    """Klant onbekend → kruisverwijzing-afwezigheid niet verifieerbaar →
    wel invullen (beste gok) maar onder de review-drempel (0.85), zodat de
    reviewer de collisie-interpretatie bevestigt. Fase 6 V3: vlagvrij 0.95
    was zelfversterkend — na approve leerde _learn_from_approved de foute
    mapping permanent aan."""
    _insert_artikelkaart(session, "238601", "Quality Covers|Top coat Heavy-duty/25m²/67cm")

    state = _state(None, [{
        "positie": 1,
        "artikelnummer_klant": "238601",
        "artikelnummer_kwabo": None,
        "omschrijving": "",
        "hoeveelheid": 1,
    }])

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "238601"
    assert regel["match_methode"] == "exact_klantnr"
    assert regel["match_confidence"] == 0.84
    assert "orderregels[0].artikelnummer_kwabo_matched" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_geen_kwabo_nr_valt_door_naar_cascade(session, app_engine):
    """Een klant-artnr dat géén Kwabo-nr is (Kuipers '0007738178') raakt A1
    niet en valt door zoals voorheen."""
    state = _state("61844", [{
        "positie": 1,
        "artikelnummer_klant": "0007738178",
        "artikelnummer_kwabo": None,
        "omschrijving": "",  # geen omschrijving → manual
        "hoeveelheid": 1,
    }])

    out = await match_articles_node(state)
    regel = out["orderregels"][0]
    assert regel["match_methode"] == "manual"
    assert regel["artikelnummer_kwabo_matched"] is None


@pytest.mark.asyncio
async def test_echte_witzand_regel_718(session, app_engine):
    """Grondwet 4: de échte #718-regel, verbatim uit prod. Vóór de fix werd
    dit fuzzy 11190 'Vloerschraper met steel 30 cm'."""
    env = load_state("order_718")
    regel_in = json.loads(json.dumps(env["order_state"]["orderregels"][0]))  # kopie
    # Reset de oude (foute) matchvelden zoals ze vóór match_articles staan.
    regel_in["artikelnummer_kwabo_matched"] = None
    regel_in["match_methode"] = None
    regel_in["match_confidence"] = None
    _insert_artikelkaart(session, "238601", "Quality Covers|Top coat Heavy-duty/25m²/67cm")
    # Het junk-doelwit bestaat óók echt — de fix moet 'm links laten liggen.
    _insert_artikelkaart(session, "11190", "Vloerschraper met steel 30 cm")

    out = await match_articles_node(_state("60892", [regel_in]))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "238601"
    assert regel["match_methode"] == "exact_klantnr"


@pytest.mark.asyncio
async def test_echte_kolomswap_regel_550(session, app_engine):
    """Grondwet 4: #550 r0 — de LLM wisselde de kolommen om (klant_art=238531,
    kwabo=K700100093). Vóór de fix werd dit fuzzy 11530."""
    env = load_state("order_550")
    regel_in = json.loads(json.dumps(env["order_state"]["orderregels"][0]))
    regel_in["artikelnummer_kwabo_matched"] = None
    regel_in["match_methode"] = None
    regel_in["match_confidence"] = None
    _insert_artikelkaart(session, "238531", "Quality Cover|Top coat Heavy-Duty/25m²/100cm")

    out = await match_articles_node(_state(None, [regel_in]))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "238531"
    assert regel["match_methode"] == "exact_klantnr"
