"""FASE 2 (F2.7) — gelabelde fixtures voor de ontbrekende FASE1_MATRIX-cellen.

Characterization-tests + grondwet-borging: elke test is een REALISTISCHE,
ALS RECONSTRUCTIE GELABELDE casus (geen echte .eml, geen prod-data-dump) die
het VERWACHTE gedrag van de BESTAANDE code vastlegt. De matrix-cel staat in
elke docstring. Gedekte cellen (status FIXTURE in FASE1_MATRIX.md):

  K1  e-mailalias-tabel (klant_email_aliases)         -> match via alias
  K3  domein-alias (K2b)                              -> bron domein_alias, conf 0.9
  K5  naam-fuzzy ambigu (gap < NAAM_GAP=10)           -> geen autopick, kandidaten
  K10 onbekende afzender                              -> geen match, wel CONTROLEER
  K11 demo-/seed-klant (VERPLICHT, opdracht)          -> safety-net: vlag + waarschuwing
  A7  >=2 ship-to's even goed op afleveradres         -> geen stille keuze
  E7  DOOS-tussen-eenheid + onbekende COLLI           -> geldige keuze / terugval+vlag

DI-patroon volgt tests/test_match_customer_shared_mailbox.py (engine-monkeypatch
+ NAV-mock) en tests/test_select_ship_to.py (repo=…); geen netwerk, geen prod.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from kwabo.db.models import Klantenkaart, KlantEmailAlias, KlantenkaartShipTo
from kwabo.db.repository import ShipToRepo
from kwabo.db.seed import purge_demo_seed
from kwabo.graph.nodes import match_customer as mc_mod
from kwabo.graph.nodes.match_customer import match_customer_node
from kwabo.graph.nodes.select_ship_to import select_ship_to_node
from kwabo.utils.eenheid_resolve import resolve_line_uom


class _NoNav:
    """NAV-stub: geen enkele NAV-kandidaat — alle paden lopen op de mirror."""

    async def search_customers(self, naam=None, email=None):
        return []


def _bind_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod

    eng = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", eng)
    monkeypatch.setattr(mc_mod, "engine", eng)
    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _NoNav())
    return session


@pytest.fixture
def bind(session, monkeypatch):
    """Session-DI voor match_customer ZONDER demo-seed: K1/K3/K5/K10 draaien op
    eigen (gelabelde) klantenkaarten; de seed-klanten 10001-10016 zouden anders
    via hun echte order-mailadressen kunnen meematchen."""
    _bind_engine(session, monkeypatch)
    purge_demo_seed(session)
    yield session


@pytest.fixture
def bind_met_demo_seed(session, monkeypatch):
    """Zoals ``bind`` maar MET de demo-seed (10001-10016) — K11 test juist het
    safety-net dat op die klanten moet vuren."""
    _bind_engine(session, monkeypatch)
    yield session


def _state(**over) -> dict:
    base = {
        "email_id": "f2-matrix",
        "email_from": "",
        "email_subject": "Bestelling",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [],
        "needs_review_fields": [],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# K11 (VERPLICHT, opdracht) — demo-klant-poging MOET vlaggen, nooit stil
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k11_demo_klant_match_krijgt_controleer_vlag_en_waarschuwing(
    bind_met_demo_seed,
):
    """[K11 — FIXTURE, verplicht] Reconstructie: een order-mail van
    purchaseorders@ferney.nl. Dat adres staat op seed-kaart 10001 (Ferney
    Diabolo B.V.) — een nummer dat NIET in de live NAV-company bestaat, dus een
    push zou stil falen (Internal_InvalidTableRelation). K1 (`by_email`) matcht
    hier op conf 1.0 — het énige vlagvrije pad — maar het safety-net
    (match_customer.py regels 752-762) moet CONTROLEER forceren én expliciet
    waarschuwen dat de klant niet in live NAV bestaat."""
    state = _state(
        email_from="Ferney Inkoop <purchaseorders@ferney.nl>",
        email_subject="Inkooporder 4200056148",
    )
    out = await match_customer_node(state)

    # De match zelf loopt gewoon via K1 (e-mail, conf 1.0)…
    assert out["klant_match"] is not None
    assert out["klant_match"]["navision_klantnr"] == "10001"
    assert out["klant_match"]["match_bron"] == "email"
    assert out["klant_match"]["match_confidence"] == 1.0

    # …maar het safety-net dwingt CONTROLEER af ondanks conf 1.0.
    assert "klant_match" in out["needs_review_fields"]
    assert out["_meta"]["klant_match"]["needs_review"] is True

    demo_warns = [
        w for w in out["validatie_warnings"]
        if "DEMO" in w and "10001" in w
    ]
    assert demo_warns, f"geen demo-waarschuwing in {out['validatie_warnings']}"
    assert "bestaat niet in de live NAV-company" in demo_warns[0]


# ---------------------------------------------------------------------------
# K5 — naam-fuzzy ambigu (gap < NAAM_GAP=10) -> vlag, geen gok
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k5_naam_fuzzy_ambigu_kleine_gap_geen_autopick(bind):
    """[K5 — FIXTURE] Reconstructie: twee sterk gelijkende kaartnamen zonder
    e-mail ("Bouwcenter Janssen B.V." vs "Bouwcentrum Janssen B.V.") en een
    besteller-naam ertussenin ("Bouwcentre Janssen"). token_set_ratio na
    rechtsvorm-strip: 94.4 vs 91.9 — top >= NAAM_ACCEPT(90) maar gap 2.5 <
    NAAM_GAP(10). Verwacht (grondwet 5): GEEN autopick op hoge confidence;
    kandidatenlijst met beide kaarten + CONTROLEER-vlag."""
    bind.add(Klantenkaart(nav_klantnr="61201", naam="Bouwcenter Janssen B.V."))
    bind.add(Klantenkaart(nav_klantnr="61202", naam="Bouwcentrum Janssen B.V."))
    bind.commit()

    state = _state(
        email_from="Inkoop <inkoop@janssen-afbouw.example>",
        klantnaam_besteller="Bouwcentre Janssen",
    )
    out = await match_customer_node(state)

    assert out["klant_match"] is None, (
        f"autopick op ambigu naam-signaal: {out['klant_match']}"
    )
    nrs = {k["navision_klantnr"] for k in out["klant_kandidaten"]}
    assert {"61201", "61202"} <= nrs, out["klant_kandidaten"]
    assert "klant_match" in out["needs_review_fields"]
    assert any("MEERDERE KLANTEN" in w for w in out["validatie_warnings"])


# ---------------------------------------------------------------------------
# K1 — e-mailalias-tabel (klant_email_aliases)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k1_email_alias_matcht_juiste_klant(bind):
    """[K1 — FIXTURE] Reconstructie: kaart 60892 (Witzand Bouwmaterialen,
    kaart-e-mail inkoop@witzand.example) heeft een beheerder-alias in
    klant_email_aliases voor een besteladres op een ÁNDER domein
    (bestellingen@bouwportaal-drenthe.example — prod heeft exact 1 zo'n rij).
    Een mail van dat alias moet op 60892 uitkomen.

    Gedocumenteerd pad: `KlantRepo.by_email` lost het alias intern op, dus het
    alias-pad geeft DEZELFDE bron 'email' + conf 1.0 (vlagvrij) als een directe
    kaartmatch — het alias is in de provenance niet te onderscheiden van het
    kaartveld."""
    bind.add(Klantenkaart(
        nav_klantnr="60892", naam="Witzand Bouwmaterialen B.V.",
        email="inkoop@witzand.example",
    ))
    bind.add(KlantEmailAlias(
        klant_nr="60892", email="bestellingen@bouwportaal-drenthe.example",
        label="besteller-alias (F2-reconstructie)",
    ))
    bind.commit()

    state = _state(
        email_from="Bestellingen <bestellingen@bouwportaal-drenthe.example>",
    )
    out = await match_customer_node(state)

    assert out["klant_match"] is not None
    assert out["klant_match"]["navision_klantnr"] == "60892"
    assert out["klant_match"]["match_bron"] == "email"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert "klant_match" not in out["needs_review_fields"]
    assert out["_meta"]["klant_match"]["source"] == "klantenkaart"


# ---------------------------------------------------------------------------
# K3 — domein-alias (K2b) -> bron 'domein_alias', conf 0.9 + CONTROLEER
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k3_domein_alias_geeft_bron_domein_alias_conf_09(bind):
    """[K3 — FIXTURE] Reconstructie (#635-patroon): een beheerder koppelt een
    heel e-maildomein aan één klant via een klant_email_aliases-rij van de vorm
    "@pontmeyer.example" (kaart 61793, TABS Holland). Een afzender van dat
    domein (jan.devries@pontmeyer.example, staat op geen enkele kaart) moet op
    61793 uitkomen via `repo.by_domain_alias` — bewust conf 0.9 en dus mét
    CONTROLEER-vlag: een domein kan bij een franchise meerdere vestigingen
    dekken, dus nooit het vlagvrije 1.0-regime van een exacte e-mailmatch."""
    bind.add(Klantenkaart(
        nav_klantnr="61793", naam="TABS Holland B.V.",
        email="supplychain@tabsholland.example",
    ))
    bind.add(KlantEmailAlias(
        klant_nr="61793", email="@pontmeyer.example",
        label="domein-alias (F2-reconstructie)",
    ))
    bind.commit()

    state = _state(
        email_from="Jan de Vries <jan.devries@pontmeyer.example>",
    )
    out = await match_customer_node(state)

    assert out["klant_match"] is not None
    assert out["klant_match"]["navision_klantnr"] == "61793"
    assert out["klant_match"]["match_bron"] == "domein_alias"
    assert out["klant_match"]["match_confidence"] == 0.9
    # conf < 1.0 -> automatische CONTROLEER-vlag (3b in match_customer).
    assert "klant_match" in out["needs_review_fields"]


# ---------------------------------------------------------------------------
# K10 — onbekende afzender: geen kaart, geen naam-match -> nooit autopick
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k10_onbekende_afzender_geen_match_wel_controleer(bind):
    """[K10 — FIXTURE] Reconstructie: afzender info@pietersen-afbouw.example
    staat op geen enkele kaart, het domein heeft geen alias en de bestellernaam
    ("Aannemersbedrijf Pietersen") lijkt op geen enkele kaartnaam (< NAAM_SHOW
    75 tegen de enige kaart Witzand). Verwacht: klant_match None, kandidaten
    mogen leeg zijn, maar needs_review bevat ALTIJD 'klant_match' plus de
    'KLANT NIET GEVONDEN'-waarschuwing — nooit een stille autopick."""
    # Eén niet-gerelateerde kaart zodat "geen match" betekenisvol is.
    bind.add(Klantenkaart(
        nav_klantnr="60892", naam="Witzand Bouwmaterialen B.V.",
        email="inkoop@witzand.example",
    ))
    bind.commit()

    state = _state(
        email_from="Aannemersbedrijf Pietersen <info@pietersen-afbouw.example>",
        klantnaam_besteller="Aannemersbedrijf Pietersen",
    )
    out = await match_customer_node(state)

    assert out["klant_match"] is None
    assert out["klant_kandidaten"] == []  # leeg mag — als er maar gevlagd wordt
    assert "klant_match" in out["needs_review_fields"]
    assert out["_meta"]["klant_match"]["needs_review"] is True
    assert out["_meta"]["klant_match"]["value"] is None
    assert any("KLANT NIET GEVONDEN" in w for w in out["validatie_warnings"])


# ---------------------------------------------------------------------------
# A7 — >=2 ship-to's die even goed scoren -> geen stille keuze
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a7_twee_shiptos_zelfde_postcode_kiest_niet_stil(session):
    """[A7 — FIXTURE] Reconstructie: klant 61999 heeft twee ship-to's op
    hetzelfde adres-complex (Hal 1 / Hal 2, IDENTIEKE postcode 7005 AS en
    plaats). Het afleveradres noemt alleen het complex — beide kandidaten
    scoren exact gelijk (postcode 5 + plaats 3 + naam 2 + straat 1). Verwacht
    (select_ship_to._decide stap 4): GEEN stille keuze en GEEN terugval op de
    default-vestiging; ship_to_gekozen None + vlag 'ship_to_gekozen'."""
    for code, naam, straat, is_default in [
        ("HAL1", "Magazijn Hal 1", "Industrieweg 12", True),
        ("HAL2", "Magazijn Hal 2", "Industrieweg 14", False),
    ]:
        session.add(KlantenkaartShipTo(
            klant_nr="61999", ship_to_code=code, naam=naam, straat=straat,
            postcode="7005 AS", plaats="DOETINCHEM", land="NL",
            is_default=is_default,
        ))
    session.commit()

    state = {
        "email_id": "f2-a7",
        "klant_match": {"navision_klantnr": "61999"},
        "afleveradres": {
            "naam": "Magazijn", "straat": "Industrieweg",
            "postcode": "7005 AS", "plaats": "DOETINCHEM",
        },
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=ShipToRepo(session))

    assert out["ship_to_gekozen"] is None  # óók niet de is_default-rij
    assert "ship_to_gekozen" in out["needs_review_fields"]
    assert len(out["ship_to_kandidaten"]) == 2


# ---------------------------------------------------------------------------
# E7 — DOOS-tussen-eenheid; onbekende COLLI -> terugval + vlag
# ---------------------------------------------------------------------------

@dataclass
class _E:
    """ArtikelEenheid-vorm zoals resolve_line_uom hem leest (zie
    tests/test_eenheid_resolve_pallet_brug.py)."""

    eenheid_code: str
    qty_per_base: float = 1.0
    is_mix_uom: bool = False


# Reconstructie van het matrix-genoemde artikel 23559: DOOS(30) bestaat echt
# in artikel_eenheden; STUK/PALLET-maten gelabeld aangevuld.
_E7_EENHEDEN = [_E("STUK", 1), _E("DOOS", 30), _E("PALLET", 600)]


def test_e7_doos_eenheid_is_geldige_keuze_zonder_vlag():
    """[E7 — FIXTURE] Bestelde eenheid 'DOOS' (aantal 4) op een artikel met
    UoM's STUK(1)/DOOS(30)/PALLET(600) — matrix: 23559 heeft DOOS(30) in
    artikel_eenheden. Regel b/2 van het eenheid-contract: de bestelde code zit
    exact in de Item-UoM -> die canonieke code, GEEN vlag."""
    eenheid, vlag = resolve_line_uom(
        {"eenheid": "DOOS", "hoeveelheid": 4}, "STUK", _E7_EENHEDEN,
    )
    assert eenheid == "DOOS"
    assert vlag is False

    # Casus-variant: extractor levert lowercase — zelfde canonieke keuze.
    eenheid, vlag = resolve_line_uom(
        {"eenheid": "doos", "hoeveelheid": 4}, "STUK", _E7_EENHEDEN,
    )
    assert eenheid == "DOOS"
    assert vlag is False


def test_e7_onbekende_colli_valt_terug_op_base_met_vlag():
    """[E7 — FIXTURE] Bestelde eenheid 'COLLI' bestaat NIET in de Item-UoM van
    het artikel en is geen pallet-familie. Regel e/4 van het eenheid-contract:
    nooit een ongeldige code naar NAV — terugval op de base-eenheid (STUK) mét
    review-vlag, geen stille terugval."""
    eenheid, vlag = resolve_line_uom(
        {"eenheid": "COLLI", "hoeveelheid": 4}, "STUK", _E7_EENHEDEN,
    )
    assert eenheid == "STUK"
    assert vlag is True
