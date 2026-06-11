"""A5 (Fase 2): fuzzy-drempel empirisch verhoogd 80 → 90; eronder NIET invullen.

Onderbouwing — scripts/analyze_fuzzy_thresholds.py op de échte faalorders en
alle 3757 echte artikelnamen (10-06-2026):

    JUNK (fuzzy auto-fills uit prod, WRatio van extractOne over alle namen):
      #550 'tfc top coat premium afdekvlies 1000mm rol a 25m2' → 11530@86
      #550 'stucloper/protectiekarton onbedrukt 950-1050mm…'   → 11530@86
      #635 'stucloper/protectiekarton 600mm rol a 30m2'        → 18390@86
      #707 'TFC STUCLOPER BLOK 4, 50M2 / C2S / 130 CM'         → 23374@86
      #717 'Stucloper grijs rol a 36 m2 breedte 60-65cm'       → 18390@86
      #718 'Afdekvlies 0,67x37 mt wit met zelfklevende onder…' → 11190@86
      → hoogste junk-score: 86 (WRatio's partial-ratio plafond ~0.9×95.6)

    BEKEND-CORRECT (16 paren uit groene orders + history): extractOne koos
    vrijwel NOOIT het juiste artikel (15×✗) — klant-omschrijvingen lijken
    tekstueel niet op de Kwabo-catalogusnamen ('Quality Covers|…'). Fuzzy in
    [80,99) had op deze data dus géén terecht-positieve waarde, alleen schade.

    Beslissing: drempel 90 (ronde waarde strikt boven 86 met marge); geen
    scorer-switch (token_sort scheidt junk ook, maar er valt niets legitiems
    te behouden — minimal change wint). description_exact (≥99) ongewijzigd.
"""
from __future__ import annotations

import pytest

from kwabo.graph.nodes.match_articles import match_articles_node

# De échte junk-doelwitten uit prod (artikelkaarten.json) als NAV-kandidaten.
ECHTE_ITEMS = [
    {"number": "18390", "displayName": "Tork rol Katrien"},
    {"number": "11190", "displayName": "Vloerschraper met steel 30 cm"},
    {"number": "11530", "displayName": "Tegelzetterselastiek op rol 20 m"},
    {"number": "23374", "displayName": "TFC Statiegeld Displays"},
    {"number": "224681", "displayName": "Quality Covers|Board Premium/30m²/C2S/65cm"},
]


class _FakeNav:
    def __init__(self, items: list[dict]):
        self.items = items

    async def get_item(self, nr: str):
        return next((i for i in self.items if i["number"] == nr), None)

    async def search_items(self, beschrijving: str | None = None):
        # Altijd de volledige set teruggeven — worst case voor fuzzy, en
        # precies wat de echte fallback (search_items zonder filter) doet.
        return list(self.items)


@pytest.fixture
def fake_nav(monkeypatch):
    from kwabo.graph.nodes import match_articles as ma_mod

    nav = _FakeNav(list(ECHTE_ITEMS))
    monkeypatch.setattr(ma_mod, "get_navision_client", lambda: nav)
    yield nav


def _state(regels: list[dict]) -> dict:
    return {
        "email_id": "a5-test",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": {"navision_klantnr": "61844"},
        "orderregels": regels,
    }


def _regel(oms: str, klant_art: str | None = None) -> dict:
    return {
        "positie": 1,
        "artikelnummer_klant": klant_art,
        "artikelnummer_kwabo": None,
        "omschrijving": oms,
        "hoeveelheid": 1,
    }


# Echte faalregels: omschrijving → (junk-artikel dat vóór de fix werd ingevuld)
ECHTE_JUNK_GEVALLEN = [
    ("Stucloper grijs rol a 36 m2 breedte 60-65cm", "18390"),           # #717
    ("Afdekvlies 0,67x37 mt wit met zelfklevende onderlaag", "11190"),  # #718
    ("stucloper/protectiekarton onbedrukt 950-1050mm rol a 50m2", "11530"),  # #550
    ("TFC STUCLOPER BLOK 4, 50M2 / C2S / 130 CM", "23374"),             # #707
]


@pytest.mark.asyncio
@pytest.mark.parametrize("oms,oude_junk", ECHTE_JUNK_GEVALLEN)
async def test_junk_score_86_wordt_niet_meer_ingevuld(fake_nav, oms, oude_junk):
    """De prod-junk (WRatio 86) blijft onder drempel 90 → niet gematcht
    (grondwet 5), in plaats van een fout artikel."""
    out = await match_articles_node(_state([_regel(oms)]))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] is None, (
        f"junk-match {regel['artikelnummer_kwabo_matched']!r} werd toch ingevuld "
        f"(was in prod: {oude_junk})"
    )
    assert regel["match_methode"] == "manual"
    assert regel["match_confidence"] == 0.0
    assert "orderregels[0].artikelnummer_kwabo_matched" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_bijna_exacte_omschrijving_matcht_nog(fake_nav):
    """Typo-variant boven de nieuwe drempel (90-98) blijft fuzzy matchen —
    met conf ≤0.84, dus altijd ter review."""
    out = await match_articles_node(_state([_regel("Tork roll Katrien")]))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "18390"
    assert regel["match_methode"] == "fuzzy"
    assert regel["match_confidence"] <= 0.84
    assert "orderregels[0].artikelnummer_kwabo_matched" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_exacte_omschrijving_blijft_description_exact(fake_nav):
    """Score ≥99 (tekstueel identiek) blijft het description_exact-pad."""
    out = await match_articles_node(_state([_regel("Tork rol Katrien")]))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "18390"
    assert regel["match_methode"] == "description_exact"
    assert regel["match_confidence"] == 0.95
