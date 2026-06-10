"""Fase 4 (B1+C2, audit §12.D.1): match_articles parallel met begrensde
concurrency — zonder de uitkomst te veranderen.

Bewijst: (1) de semaphore-limiet wordt gerespecteerd én er ís parallellisme;
(2) de output blijft in inputvolgorde, ook als de eerste regel het traagst is;
(3) crash-semantiek (manual-fallback + >=50%-outage-warning) is ongewijzigd;
(4) conc=1 en conc=5 geven een json-identieke node-uitkomst.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from kwabo.config import settings
from kwabo.db.models import Artikelkaart
from kwabo.graph.nodes import match_articles as ma


class InstrumentedNav:
    """Fake NAV-client: telt in-flight-calls, configureerbare latency per
    artikelnr, optionele crash-nummers."""

    def __init__(self, delay: float = 0.01, delays: dict[str, float] | None = None,
                 crash_nrs: set[str] | None = None) -> None:
        self.delay = delay
        self.delays = delays or {}
        self.crash_nrs = crash_nrs or set()
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = 0

    async def _track(self, nr: str | None):
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delays.get(nr, self.delay))
            if nr in self.crash_nrs:
                raise RuntimeError(f"NAV down voor {nr}")
        finally:
            self.in_flight -= 1

    async def get_item(self, nr):
        await self._track(nr)
        return {"number": nr, "displayName": f"Artikel {nr}"}

    async def search_items(self, beschrijving=None):
        await self._track(None)
        return []

    async def search_customers(self, **kw):
        return []


def _regel(positie: int, kwabo_nr: str | None = None, oms: str = "") -> dict:
    return {"positie": positie, "artikelnummer_kwabo": kwabo_nr,
            "artikelnummer_klant": None,
            "omschrijving": oms or f"Artikel {kwabo_nr}",
            "hoeveelheid": 1.0, "eenheid": "STUK"}


def _state(regels: list[dict]) -> dict:
    return {"email_id": "conc-test", "klant_match": {"navision_klantnr": "10001"},
            "orderregels": regels, "needs_review_fields": []}


@pytest.mark.asyncio
async def test_semaphore_limiet_gerespecteerd_en_echt_parallel(monkeypatch, session):
    """12 mirror-miss-regels bij limiet 3: nooit >3 NAV-calls tegelijk,
    maar wel >1 (anders is er geen parallellisme en dus geen winst)."""
    monkeypatch.setattr(ma, "engine", session.get_bind())
    monkeypatch.setattr(settings, "match_concurrency", 3)
    nav = InstrumentedNav(delay=0.02)
    monkeypatch.setattr(ma, "get_navision_client", lambda: nav)

    regels = [_regel(i + 1, kwabo_nr=f"99900{i:02d}") for i in range(12)]
    out = await ma.match_articles_node(_state(regels))

    assert len(out["orderregels"]) == 12
    assert nav.max_in_flight <= 3, f"semaphore geschonden: {nav.max_in_flight}"
    assert nav.max_in_flight > 1, "geen parallellisme gemeten — nog serieel?"


@pytest.mark.asyncio
async def test_output_blijft_in_inputvolgorde(monkeypatch, session):
    """Eerste regel het traagst: bij naïef 'wie het eerst klaar is' zou die
    achteraan eindigen. Output moet positie 1..6 in inputvolgorde houden."""
    monkeypatch.setattr(ma, "engine", session.get_bind())
    monkeypatch.setattr(settings, "match_concurrency", 6)
    nrs = [f"88800{i}" for i in range(6)]
    delays = {nr: 0.05 * (len(nrs) - i) for i, nr in enumerate(nrs)}
    nav = InstrumentedNav(delays=delays)
    monkeypatch.setattr(ma, "get_navision_client", lambda: nav)

    regels = [_regel(i + 1, kwabo_nr=nr) for i, nr in enumerate(nrs)]
    out = await ma.match_articles_node(_state(regels))

    assert [r["positie"] for r in out["orderregels"]] == [1, 2, 3, 4, 5, 6]
    assert [r["artikelnummer_kwabo_matched"] for r in out["orderregels"]] == nrs


@pytest.mark.asyncio
async def test_crash_semantiek_ongewijzigd(monkeypatch, session):
    """2 van 3 regels crashen: manual-fallback per regel + de identieke
    NAV-outage-warning (>=50%-drempel) — karakter-voor-karakter."""
    monkeypatch.setattr(ma, "engine", session.get_bind())
    monkeypatch.setattr(settings, "match_concurrency", 5)
    nav = InstrumentedNav(crash_nrs={"777001", "777002"})
    monkeypatch.setattr(ma, "get_navision_client", lambda: nav)

    regels = [_regel(1, "777001"), _regel(2, "777002"), _regel(3, "777003")]
    out = await ma.match_articles_node(_state(regels))

    r1, r2, r3 = out["orderregels"]
    assert r1["match_methode"] == "manual" and r1["match_confidence"] == 0.0
    assert r2["match_methode"] == "manual" and r2["match_confidence"] == 0.0
    assert r3["match_methode"] == "exact"
    verwacht = ("NAV tijdelijk niet bereikbaar — 2/3 artikel-matches crashten. "
                "Re-run de pipeline of vul handmatig in.")
    assert verwacht in out["validatie_warnings"]


@pytest.mark.asyncio
async def test_conc1_en_conc5_geven_identieke_uitkomst(monkeypatch, session):
    """Determinisme-borg: parallellisme mag de uitkomst NIET wijzigen.
    Mix van mirror-hit, mirror-miss en fuzzy-naar-manual regels."""
    session.add(Artikelkaart(kwabo_artikelnr="555001", naam="Mirror artikel A",
                             basis_eenheid="STUK"))
    session.add(Artikelkaart(kwabo_artikelnr="555002", naam="Mirror artikel B",
                             basis_eenheid="STUK"))
    session.commit()
    monkeypatch.setattr(ma, "engine", session.get_bind())

    regels = [
        _regel(1, "555001"), _regel(2, "555002"),          # mirror-hit
        _regel(3, "666001"), _regel(4, "666002"),          # mirror-miss → NAV
        _regel(5, None, oms="Volstrekt onbekend qqxyz 1"),  # fuzzy → manual
        _regel(6, None, oms="Volstrekt onbekend qqxyz 2"),
    ]

    def _strip(out: dict) -> str:
        d = json.loads(json.dumps(out))
        for stap in d.get("stappen_log") or []:
            stap.pop("timestamp", None)
        return json.dumps(d, sort_keys=True)

    uitkomsten = []
    for conc in (1, 5):
        monkeypatch.setattr(settings, "match_concurrency", conc)
        nav = InstrumentedNav()
        monkeypatch.setattr(ma, "get_navision_client", lambda: nav)
        out = await ma.match_articles_node(_state(json.loads(json.dumps(regels))))
        uitkomsten.append(_strip(out))

    assert uitkomsten[0] == uitkomsten[1]
