"""Fase 3 Branch A (E1/E2): standaard verkoopeenheid + aantal-omrekening.

Faalgeval Würth #716 (echte NAV-responses in tests/test_data/states/order_716*):
de tool POSTte regel 238601 zonder UoM-PATCH en PATCHte daarna quantity=66.
NAV default een nieuwe regel echter naar de STANDAARD VERKOOPEENHEID van de
artikelkaart (PALLET33, 33/pallet) — niet naar de base-eenheid. Resultaat:
66 PALLETS (Line_Amount €45.738) i.p.v. 66 rollen (= 2 pallets, €1.386).

De regels (besluit met Cas, 10-06):
  * Branch A (regel zonder mix-keuze) stuurt ALTIJD een expliciete eenheid mee
    — nooit meer op NAV's default vertrouwen.
  * Bestel-eenheid leeg/base/ongeldig: kies de verkoopeenheid van de kaart en
    reken het aantal om (66 STUK -> 2 × PALLET33), mits dat geheel uitkomt;
    anders expliciet de base-eenheid + het base-aantal (bedrag blijft correct).
  * Een GELDIGE niet-base bestel-eenheid blijft staan (2-6-fix: "60 stuks
    blijft 60 stuks") — de composer PATCHt die al expliciet.
  * Geen verkoopeenheid bekend: afleiding uit ArtikelEenheid alleen bij precies
    één gehele niet-mix kandidaat; anders expliciete base (geen gok).
  * De tool rekent nooit een prijs — alleen code + omgerekend aantal (M5).

Testdata: de échte 45 UoM-rijen van artikel 238601 uit de prod-export
(artikel_eenheden.json) — incl. de valkuilen EXW PAL33 (ook 33/pallet) en
M1STUK.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kwabo.db.models import Artikelkaart, ArtikelEenheid
from kwabo.db.repository import KlantRepo
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node

STATES = Path(__file__).resolve().parents[0] / "test_data" / "states"


def _seed_echte_eenheden(session, artikelnr: str) -> int:
    """Seed de échte ArtikelEenheid-rijen van een artikel uit de prod-export."""
    p = STATES / "artikel_eenheden.json"
    if not p.is_file():
        pytest.skip("artikel_eenheden.json ontbreekt — draai export_order_states.py")
    rows = [r for r in json.loads(p.read_text(encoding="utf-8"))
            if r["kwabo_artikelnr"] == artikelnr]
    assert rows, f"geen UoM-rijen voor {artikelnr} in export"
    for r in rows:
        session.add(ArtikelEenheid(**r))
    session.commit()
    return len(rows)


def _seed_kaart(session, artikelnr: str, *, basis: str, verkoop: str | None) -> None:
    session.add(Artikelkaart(
        kwabo_artikelnr=artikelnr, naam=f"art {artikelnr}",
        basis_eenheid=basis, verkoop_eenheid=verkoop,
    ))
    session.commit()


def _set_klant_mix(session, nav_klantnr: str, mix: bool) -> None:
    klant = KlantRepo(session).by_nav_nr(nav_klantnr)
    assert klant is not None
    klant.mixprijzen = mix
    session.add(klant)
    session.commit()


def _regel_716() -> dict:
    """De echte #716-regel zoals match_articles hem aflevert."""
    return {
        "positie": 1,
        "omschrijving": "ZELFKLEVEND-AFDEKVLIES-170GR-B0,67ML25M",
        "artikelnummer_kwabo_matched": "238601",
        "hoeveelheid": 66.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
    }


def _state(regels: list[dict], klant_nr: str = "10001") -> dict:
    return {
        "email_id": "fase3-test",
        "klant_match": {"navision_klantnr": klant_nr},
        "orderregels": regels,
        "needs_review_fields": [],
    }


def test_artikelkaart_heeft_verkoop_eenheid_veld(session):
    """E1: de standaard verkoopeenheid (NAV Sales_Unit_of_Measure) leeft op de
    artikelkaart-mirror."""
    _seed_kaart(session, "238601", basis="STUK", verkoop="PALLET33")
    kaart = session.get(Artikelkaart, "238601")
    assert kaart.verkoop_eenheid == "PALLET33"


@pytest.mark.asyncio
async def test_716_base_eenheid_wordt_verkoopeenheid_met_omrekening(session):
    """Faalgeval #716 rood->groen: 66 STUK (base) -> 2 × PALLET33."""
    _set_klant_mix(session, "10001", False)  # Würth is geen mix-klant (prod-export)
    _seed_kaart(session, "238601", basis="STUK", verkoop="PALLET33")
    _seed_echte_eenheden(session, "238601")

    out = await apply_mixprijzen_node(_state([_regel_716()]), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "PALLET33"
    assert r["verkoop_aantal"] == 2
    # Bestelde hoeveelheid blijft onaangetast voor UI/audit.
    assert r["hoeveelheid"] == 66.0
    assert r.get("mix_uom_gekozen") is None


@pytest.mark.asyncio
async def test_niet_gehele_omrekening_dwingt_expliciete_base_af(session):
    """50 STUK past op geen enkel geheel aantal pallets -> expliciete base-
    eenheid + base-aantal (NOOIT NAV's pallet-default laten gelden, en nooit
    stil afronden)."""
    _set_klant_mix(session, "10001", False)
    _seed_kaart(session, "238601", basis="STUK", verkoop="PALLET33")
    _seed_echte_eenheden(session, "238601")

    regel = _regel_716() | {"hoeveelheid": 50.0}
    out = await apply_mixprijzen_node(_state([regel]), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "STUK"
    assert r["verkoop_aantal"] == 50.0


@pytest.mark.asyncio
async def test_geldige_niet_base_besteleenheid_blijft_staan(session):
    """2-6-fix blijft gelden: klant bestelt expliciet 2 PALLET35 (geldig) ->
    niet aankomen; de composer PATCHt die eenheid al."""
    _set_klant_mix(session, "10001", False)
    _seed_kaart(session, "238601", basis="STUK", verkoop="PALLET33")
    _seed_echte_eenheden(session, "238601")

    regel = _regel_716() | {"hoeveelheid": 2.0, "eenheid": "PALLET35",
                            "eenheid_origineel": "PALLET35"}
    out = await apply_mixprijzen_node(_state([regel]), session=session)
    r = out["orderregels"][0]
    assert "verkoop_uom_gekozen" not in r
    assert r["eenheid"] == "PALLET35"
    assert r["hoeveelheid"] == 2.0


@pytest.mark.asyncio
async def test_geen_verkoopeenheid_meerdere_kandidaten_geen_gok(session):
    """Zonder verkoop_eenheid-veld: 66 deelt geheel door 33 — maar artikel
    238601 heeft PALLET33 én 'EXW PAL33' (beide 33/pallet). Twee kandidaten =
    geen gok (grondwet 5) -> expliciete base."""
    _set_klant_mix(session, "10001", False)
    _seed_kaart(session, "238601", basis="STUK", verkoop=None)
    _seed_echte_eenheden(session, "238601")

    out = await apply_mixprijzen_node(_state([_regel_716()]), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "STUK"
    assert r["verkoop_aantal"] == 66.0


@pytest.mark.asyncio
async def test_afleiding_bij_precies_een_gehele_kandidaat(session):
    """Zonder verkoop_eenheid-veld maar mét precies één gehele niet-mix
    kandidaat: die afleiden. (Synthetisch: alleen ROL-base + PALLET24.)"""
    _set_klant_mix(session, "10001", False)
    session.add(Artikelkaart(kwabo_artikelnr="909090", naam="t",
                             basis_eenheid="ROL", verkoop_eenheid=None))
    session.add(ArtikelEenheid(kwabo_artikelnr="909090", eenheid_code="ROL",
                               qty_per_base=1.0, is_mix_uom=False))
    session.add(ArtikelEenheid(kwabo_artikelnr="909090", eenheid_code="PALLET24",
                               qty_per_base=24.0, is_mix_uom=False))
    session.commit()

    regel = {"positie": 1, "artikelnummer_kwabo_matched": "909090",
             "hoeveelheid": 48.0, "eenheid": "ROL", "eenheid_origineel": "ROL",
             "eenheid_default": "ROL"}
    out = await apply_mixprijzen_node(_state([regel]), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "PALLET24"
    assert r["verkoop_aantal"] == 2


def test_upsert_neemt_verkoop_eenheid_mee(session):
    """De NAV-mirror-upsert (unconditional overwrite) moet het nieuwe veld
    meenemen — anders wist elke sync de verkoopeenheid weer."""
    from kwabo.db.repository import ArtikelkaartRepo

    repo = ArtikelkaartRepo(session)
    repo.upsert(Artikelkaart(kwabo_artikelnr="238601", naam="oud",
                             basis_eenheid="STUK"))
    repo.upsert(Artikelkaart(kwabo_artikelnr="238601", naam="nieuw",
                             basis_eenheid="STUK", verkoop_eenheid="PALLET33"))
    assert repo.get("238601").verkoop_eenheid == "PALLET33"


def test_admin_ingest_leest_sales_unit_of_measure():
    """Excel/JSON-ingest (NAV-native veldnamen) vult verkoop_eenheid."""
    from kwabo.api.admin import _item_to_artikelkaart

    kaart = _item_to_artikelkaart({
        "No": "238601", "Description": "Afdekvlies",
        "Base_Unit_of_Measure": "STUK", "Sales_Unit_of_Measure": "PALLET33",
    }, None)
    assert kaart.verkoop_eenheid == "PALLET33"
    bijgewerkt = _item_to_artikelkaart(
        {"No": "238601", "Description": "Afdekvlies",
         "Base_Unit_of_Measure": "STUK", "Sales_Unit_of_Measure": "PALLET35"},
        kaart,
    )
    assert bijgewerkt.verkoop_eenheid == "PALLET35"


def test_composer_emit_verkoopeenheid_en_omgerekend_aantal():
    """#716 op compose-niveau: regel met Branch-A-keuze -> expliciete
    unitOfMeasureCode-PATCH (PALLET33) + quantity-PATCH met het OMGEREKENDE
    aantal (2, niet 66). Beide single-field (PATCH-invariant)."""
    from kwabo.integrations.navision_steps import _emit_line_ops

    regel = _regel_716() | {"verkoop_uom_gekozen": "PALLET33", "verkoop_aantal": 2}
    ops = _emit_line_ops(regel, "238601", "regel 1")
    bodies = [op["body"] for op in ops]
    assert {"unitOfMeasureCode": "PALLET33"} in bodies
    assert {"quantity": 2} in bodies
    assert {"quantity": 66.0} not in bodies
    assert all(len(b) == 1 or op["op"] == "POST" for op, b in zip(ops, bodies))


def test_composer_mix_wint_van_verkoopkeuze():
    """Prioriteit: mix_uom_gekozen > verkoop_uom_gekozen (M2)."""
    from kwabo.integrations.navision_steps import _emit_line_ops

    regel = _regel_716() | {
        "verkoop_uom_gekozen": "PALLET33", "verkoop_aantal": 2,
        "mix_uom_gekozen": "M2PAL33", "mix_aantal": 2,
    }
    ops = _emit_line_ops(regel, "238601", "regel 1")
    bodies = [op["body"] for op in ops]
    assert {"unitOfMeasureCode": "M2PAL33"} in bodies
    assert {"unitOfMeasureCode": "PALLET33"} not in bodies


@pytest.mark.asyncio
async def test_ongeldige_besteleenheid_rol_gaat_nooit_naar_nav(session):
    """E3 keten-bewijs: klant bestelt 66 'ROL' — geen geldige eenheid voor
    238601 (gaf in echt NAV een 400). match_articles viel al terug op base;
    Branch A kiest de verkoopeenheid; de compose-output bevat dus nergens
    meer 'ROL'."""
    from kwabo.integrations.navision_steps import _emit_line_ops

    _set_klant_mix(session, "10001", False)
    _seed_kaart(session, "238601", basis="STUK", verkoop="PALLET33")
    _seed_echte_eenheden(session, "238601")

    # Zoals match_articles een ongeldige bestel-eenheid aflevert: eenheid op
    # base teruggevallen, het origineel bewaard (+ review-vlag elders).
    regel = _regel_716() | {"eenheid": "STUK", "eenheid_origineel": "ROL"}
    out = await apply_mixprijzen_node(_state([regel]), session=session)
    r = out["orderregels"][0]
    assert r["verkoop_uom_gekozen"] == "PALLET33"
    assert r["verkoop_aantal"] == 2

    ops = _emit_line_ops(r, "238601", "regel 1")
    bodies = [op["body"] for op in ops]
    assert {"unitOfMeasureCode": "PALLET33"} in bodies
    assert not any(b.get("unitOfMeasureCode") == "ROL" for b in bodies)
    assert {"quantity": 2} in bodies


def test_europallet_telt_branch_a_pallets_716():
    """E4 (#716): de regel staat na Branch A op 2 × PALLET33 -> europallet-
    regel 19820 met hoeveelheid 2. Vóór deze fix telde pallet_logic niets:
    238601 heeft VIER pallet-varianten (PALLET30/33/35/42) -> ambigu -> 0,
    precies waarom #716 destijds geen europallet kreeg."""
    from kwabo.utils.pallet_logic import compute_europallet

    class _GeenKennis:
        def lookup(self, *_):
            return None

    class _EchteUoms:
        def list_eenheden(self, artikelnr):
            p = STATES / "artikel_eenheden.json"
            if not p.is_file():
                pytest.skip("artikel_eenheden.json ontbreekt")
            return [ArtikelEenheid(**r)
                    for r in json.loads(p.read_text(encoding="utf-8"))
                    if r["kwabo_artikelnr"] == artikelnr]

    regel = _regel_716() | {"verkoop_uom_gekozen": "PALLET33", "verkoop_aantal": 2}
    uit = compute_europallet({"orderregels": [regel]},
                             repo=_GeenKennis(), uom_repo=_EchteUoms())
    assert uit is not None, "europallet-regel ontbreekt (faalgeval #716)"
    assert uit["artikelnummer_kwabo_matched"] == "19820"
    assert uit["hoeveelheid"] == 2


@pytest.mark.asyncio
async def test_mix_regel_blijft_van_mixlogica(session):
    """Een mix-regel (klant mix + artikel met mix-codes) krijgt mix_uom_gekozen
    en GEEN Branch-A-velden — mix wint (M2)."""
    _set_klant_mix(session, "10001", True)
    _seed_kaart(session, "238601", basis="STUK", verkoop="PALLET33")
    _seed_echte_eenheden(session, "238601")

    out = await apply_mixprijzen_node(_state([_regel_716()]), session=session)
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] is not None
    assert "verkoop_uom_gekozen" not in r


@pytest.mark.asyncio
async def test_herverwerking_wist_stale_verkoop_afgeleiden(session):
    """B3-herverwerking (#819-rerun): een opgeslagen regel draagt nog de oude
    afgeleiden (verkoop STUK/4.0) terwijl de eenheid inmiddels naar de
    pallet-UoM is gebrugd. Branch A laat een geldige niet-base eenheid staan,
    maar moet de STALE verkoop_*-afgeleiden dan wissen — anders pusht de
    composer alsnog de oude STUK-keuze naar NAV."""
    _set_klant_mix(session, "10001", False)
    _seed_kaart(session, "23691", basis="STUK", verkoop=None)
    session.add(ArtikelEenheid(kwabo_artikelnr="23691", eenheid_code="STUK",
                               qty_per_base=1, is_mix_uom=False))
    session.add(ArtikelEenheid(kwabo_artikelnr="23691", eenheid_code="PALLET",
                               qty_per_base=20, is_mix_uom=False))
    session.commit()

    regel = {
        "positie": 1,
        "artikelnummer_kwabo_matched": "23691",
        "hoeveelheid": 4.0,
        "eenheid": "PALLET",            # al gebrugd door match_articles
        "eenheid_origineel": "PAL",
        "eenheid_default": "STUK",
        "verkoop_uom_gekozen": "STUK",  # stale, uit de opgeslagen state
        "verkoop_aantal": 4.0,
    }
    out = await apply_mixprijzen_node(_state([regel]), session=session)
    r = out["orderregels"][0]
    assert r.get("verkoop_uom_gekozen") in (None, "PALLET"), r
    assert r.get("verkoop_aantal") in (None, 4), r
