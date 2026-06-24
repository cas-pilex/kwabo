"""C2 — match_articles stap 2/3/4 moeten MIRROR-FIRST zijn (zoals stap 1).

Root cause (gemeten 24-06 op echte prod-data, order #941): een klant-mapping
(kruisverwijzing / klantenkaart / history) wees naar een Kwabo-artikel dat WEL in
de gesyncde artikelkaart-mirror staat maar (in de meet-stub / bij NAV-traagheid)
niet via `nav.get_item` bevestigd kon worden → de regel viel stil terug op
`manual`. Stap 1 was al mirror-first; stap 2/3/4 niet. Gevolg in prod: NAV-storing
of een niet-in-NAV-zichtbaar artikel zet een geldige mapping stil op review.

Deze tests pinnen vast dat een mapping naar een artikel dat ALLEEN in de mirror
bestaat (niet in de MockNAV-items) tóch matcht.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import (
    Artikelkaart,
    ArtikelKruisverwijzing,
    ArtikelMatchingHistory,
    KlantenkaartArtikel,
)
from kwabo.graph.nodes.match_articles import match_articles_node


@pytest.fixture
def app_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_articles as ma_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


# Een Kwabo-nummer dat NIET in de MockNAV-items zit, maar wél in de mirror.
MIRROR_ONLY = "9990001"


def _mirror_artikel(session) -> None:
    session.add(
        Artikelkaart(
            kwabo_artikelnr=MIRROR_ONLY,
            naam="ProGold Mirror-only artikel",
            basis_eenheid="STUK",
        )
    )
    session.commit()


def _state(klant_nr: str, regel: dict) -> dict:
    return {
        "email_id": "c2-test",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": {"navision_klantnr": klant_nr},
        "orderregels": [regel],
    }


@pytest.mark.asyncio
async def test_kruisverwijzing_matcht_mirror_only_artikel(session, app_engine):
    _mirror_artikel(session)
    session.add(ArtikelKruisverwijzing(
        klant_nr="10001", klant_artikelnr="ALT-1", kwabo_artikelnr=MIRROR_ONLY, bron="customer"))
    session.commit()
    out = await match_articles_node(_state("10001", {
        "positie": 1, "artikelnummer_klant": "ALT-1", "artikelnummer_kwabo": None,
        "omschrijving": "", "hoeveelheid": 1}))
    r = out["orderregels"][0]
    assert r["match_methode"] == "kruisverwijzing"
    assert r["artikelnummer_kwabo_matched"] == MIRROR_ONLY


@pytest.mark.asyncio
async def test_klantenkaart_matcht_mirror_only_artikel(session, app_engine):
    """De échte #941-vorm: het klant-artikelnr is zelf een geldig Kwabo-nummer,
    maar er is een klantenkaart-mapping (→ stap 1b geblokkeerd, stap 3 pakt het)."""
    _mirror_artikel(session)
    session.add(KlantenkaartArtikel(
        klant_nr="10001", klant_artikelnr=MIRROR_ONLY, kwabo_artikelnr=MIRROR_ONLY,
        omschrijving="941-vorm"))
    session.commit()
    out = await match_articles_node(_state("10001", {
        "positie": 1, "artikelnummer_klant": MIRROR_ONLY, "artikelnummer_kwabo": None,
        "omschrijving": "", "hoeveelheid": 1}))
    r = out["orderregels"][0]
    assert r["artikelnummer_kwabo_matched"] == MIRROR_ONLY
    assert r["match_methode"] in ("klantenkaart", "exact_klantnr")


@pytest.mark.asyncio
async def test_history_matcht_mirror_only_artikel(session, app_engine):
    _mirror_artikel(session)
    session.add(ArtikelMatchingHistory(
        klant_nr="10001", klant_artikelnr="ALT-3", kwabo_artikelnr=MIRROR_ONLY,
        match_methode="history"))
    session.commit()
    out = await match_articles_node(_state("10001", {
        "positie": 1, "artikelnummer_klant": "ALT-3", "artikelnummer_kwabo": None,
        "omschrijving": "", "hoeveelheid": 1}))
    r = out["orderregels"][0]
    assert r["artikelnummer_kwabo_matched"] == MIRROR_ONLY
    assert r["match_methode"] in ("history", "klantenkaart", "kruisverwijzing")
