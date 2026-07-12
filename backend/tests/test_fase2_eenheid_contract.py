"""FASE 2 (F2.3) — het eenheid+aantal-contract in ÉÉN module, mét herkomst.

Opdracht 2c: (artikel, bestelde eenheid, aantal, mixstatus) -> (geldige
NAV-UoM, omgerekend aantal, vlag?) in vaste volgorde, op één plek. De
her-diagnose telde ≥10 plekken; de beslislogica (resolve/pallet-brug/
Branch-A/verkoop-keuze/plain-pallet-equivalent/base-omrekening/mix-tier-
parsing) consolideert naar `kwabo.utils.eenheid_resolve` (het B3-contract-
bestand). apply_mixprijzen houdt alleen de ORDER-context (staffelbasis).

Nieuw gedrag dat hier eerst ROOD wordt aangetoond:
  * `bepaal_eenheid(...)` levert naast (code, vlag) ook een BRON in gewone
    taal — de UI-eis "eenheid-herkomst per regel" (opdracht Fase 2-UX) en
    de uitlegbaarheid van elke eenheid-beslissing;
  * `branch_a(...)` (voorheen apply_mixprijzen._branch_a) schrijft
    `regel["eenheid_bron"]` bij élke uitkomst;
  * de mix-staffel schrijft `eenheid_bron` met tier + staffelbasis;
  * F2.A-besluit-A-mechanismebewijs: met verkoop_eenheid=PALLET33 (de
    NAV-data-actie die Nico moet doen) wordt 66 STUK -> PALLET33 x 2.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import ArtikelEenheid, Artikelkaart
from kwabo.db.repository import ArtikelkaartRepo, KlantRepo
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node
from kwabo.utils.eenheid_resolve import bepaal_eenheid, branch_a


class _E:
    def __init__(self, code: str, qty: float, is_mix: bool = False):
        self.eenheid_code = code
        self.qty_per_base = qty
        self.is_mix_uom = is_mix


class _Kaart:
    def __init__(self, basis="STUK", verkoop=None):
        self.basis_eenheid = basis
        self.verkoop_eenheid = verkoop


# ---------- bepaal_eenheid: (code, vlag, bron) ----------

def test_geldige_bestelde_eenheid_met_bron():
    eenheden = [_E("STUK", 1), _E("DOOS", 30)]
    keuze = bepaal_eenheid({"eenheid": "DOOS"}, "STUK", eenheden)
    assert (keuze.code, keuze.vlag) == ("DOOS", False)
    assert "bestelde eenheid" in keuze.bron.lower()


def test_pallet_brug_met_bron():
    eenheden = [_E("STUK", 1), _E("PALLET", 20)]
    keuze = bepaal_eenheid({"eenheid": "PAL"}, "STUK", eenheden)
    assert (keuze.code, keuze.vlag) == ("PALLET", False)
    assert "pallet-brug" in keuze.bron.lower()


def test_ongeldige_eenheid_terugval_met_vlag_en_bron():
    eenheden = [_E("STUK", 1)]
    keuze = bepaal_eenheid({"eenheid": "ROL"}, "STUK", eenheden)
    assert (keuze.code, keuze.vlag) == ("STUK", True)
    assert "terugval" in keuze.bron.lower()


def test_lege_eenheid_is_base_met_bron():
    keuze = bepaal_eenheid({"eenheid": ""}, "STUK", [_E("STUK", 1)])
    assert (keuze.code, keuze.vlag) == ("STUK", False)
    assert "base" in keuze.bron.lower() or "standaard" in keuze.bron.lower()


# ---------- branch_a: pure functie + eenheid_bron op de regel ----------

def test_branch_a_verkoopeenheid_omrekening_schrijft_bron():
    """#954-mechanisme: verkoop_eenheid=PALLET (60/base) + 60 STUK -> 1 PALLET."""
    regel = {"positie": 1, "artikelnummer_kwabo_matched": "228321",
             "hoeveelheid": 60, "eenheid": "STUK"}
    eenheden = [_E("STUK", 1), _E("PALLET", 60)]
    w = branch_a(regel, _Kaart(verkoop="PALLET"), eenheden)
    assert w is None
    assert regel["verkoop_uom_gekozen"] == "PALLET"
    assert regel["verkoop_aantal"] == 1
    assert "verkoopeenheid" in regel["eenheid_bron"].lower()
    assert "60" in regel["eenheid_bron"]  # de maat is uitlegbaar


def test_branch_a_besluit_A_66_stuk_wordt_2_pallet33():
    """F2.A-mechanismebewijs (fixture-data = de NAV-actie van Nico):
    238601 met verkoop_eenheid=PALLET33 -> 66 STUK wordt PALLET33 x 2."""
    regel = {"positie": 1, "artikelnummer_kwabo_matched": "238601",
             "hoeveelheid": 66, "eenheid": "STUK"}
    eenheden = [_E("STUK", 1), _E("PALLET33", 33), _E("PALLET35", 35),
                _E("PALLET42", 42)]
    w = branch_a(regel, _Kaart(verkoop="PALLET33"), eenheden)
    assert w is None
    assert regel["verkoop_uom_gekozen"] == "PALLET33"
    assert regel["verkoop_aantal"] == 2
    assert "pallet33" in regel["eenheid_bron"].lower()


def test_branch_a_expliciete_base_schrijft_bron():
    """Geen gehele omrekening mogelijk (50 past in geen enkele pallet-maat):
    expliciete base x aantal — en ook dát is uitlegbaar. NB: bij precies één
    heel-passende kandidaat converteert verkoop_keuze WEL (uniek-heel-regel;
    zo blijft #716 op echte data alleen STUK doordat 'EXW PAL33' een tweede
    kandidaat vormt — zie test hieronder)."""
    regel = {"positie": 1, "artikelnummer_kwabo_matched": "238601",
             "hoeveelheid": 50, "eenheid": "STUK"}
    eenheden = [_E("STUK", 1), _E("PALLET33", 33), _E("PALLET35", 35)]
    w = branch_a(regel, _Kaart(verkoop="STUK"), eenheden)
    assert w is None
    assert regel["verkoop_uom_gekozen"] == "STUK"
    assert regel["verkoop_aantal"] == 50
    assert regel.get("eenheid_bron")


def test_branch_a_716_blijft_stuk_op_echte_prod_uoms():
    """Karakterisering van run 1 (#716, huidige NAV-data): verkoop=STUK én
    twee heel-passende kandidaten (PALLET33 + 'EXW PAL33') -> geen unieke
    keuze -> expliciete STUK x 66. Dit pint het gedrag dat de baseline mat."""
    regel = {"positie": 1, "artikelnummer_kwabo_matched": "238601",
             "hoeveelheid": 66, "eenheid": "STUK"}
    eenheden = [_E("STUK", 1), _E("PALLET33", 33), _E("EXW PAL33", 33),
                _E("PALLET35", 35), _E("PALLET42", 42)]
    w = branch_a(regel, _Kaart(verkoop="STUK"), eenheden)
    assert w is None
    assert regel["verkoop_uom_gekozen"] == "STUK"
    assert regel["verkoop_aantal"] == 66


def test_branch_a_geldige_alternatieve_besteleenheid_blijft_met_bron():
    regel = {"positie": 1, "artikelnummer_kwabo_matched": "23691",
             "hoeveelheid": 4, "eenheid": "PALLET"}
    eenheden = [_E("STUK", 1), _E("PALLET", 20)]
    w = branch_a(regel, _Kaart(verkoop="STUK"), eenheden)
    assert w is None
    assert "verkoop_uom_gekozen" not in regel
    assert "bestelde eenheid" in regel["eenheid_bron"].lower()


# ---------- mix-staffel schrijft eenheid_bron (order-context blijft in de node) ----------

def _set_klant_mix(session, nav_klantnr: str, mix: bool) -> None:
    klant = KlantRepo(session).by_nav_nr(nav_klantnr)
    assert klant is not None
    klant.mixprijzen = mix
    session.add(klant)
    session.commit()


@pytest.mark.asyncio
async def test_mix_regel_krijgt_eenheid_bron(session):
    _set_klant_mix(session, "10001", True)
    session.add(ArtikelEenheid(kwabo_artikelnr="23544", eenheid_code="ROL",
                               qty_per_base=1.0, is_mix_uom=False))
    session.add(ArtikelEenheid(kwabo_artikelnr="23544", eenheid_code="M7PAL30",
                               qty_per_base=30.0, is_mix_uom=False))
    session.commit()
    out = await apply_mixprijzen_node({
        "email_id": "f23-mix-bron",
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "23544",
                         "hoeveelheid": 210, "eenheid": "ROL",
                         "eenheid_origineel": "ROL"}],
        "needs_review_fields": [],
    }, session=session)
    r = out["orderregels"][0]
    assert r["mix_uom_gekozen"] == "M7PAL30"
    assert "staffel" in (r.get("eenheid_bron") or "").lower()
    assert "M7" in r["eenheid_bron"]


# ---------- consolidatie-bewijs: de oude paden bestaan niet meer ----------

def test_apply_mixprijzen_heeft_geen_eigen_beslislogica_meer():
    """Diff-borging: de verspreide beslisfuncties zijn uit de node verdwenen
    en leven uitsluitend nog in het contract-bestand."""
    import kwabo.graph.nodes.apply_mixprijzen as node
    import kwabo.utils.eenheid_resolve as contract
    for naam in ("_branch_a", "_verkoop_keuze", "_plain_pallet_equiv",
                 "_to_rolls", "_mix_codes_for"):
        assert not hasattr(node, naam) or getattr(node, naam).__module__ == contract.__name__, naam
    for naam in ("branch_a", "verkoop_keuze", "plain_pallet_equiv",
                 "to_base_qty", "mix_tiers_for", "bepaal_eenheid",
                 "resolve_line_uom", "pallet_uom_code"):
        assert hasattr(contract, naam), naam


def test_preview_importeert_contract_niet_de_node():
    """api-laag hangt niet meer aan een graph-node-interne functie."""
    import inspect
    import kwabo.api.preview as preview
    src = inspect.getsource(preview)
    assert "from kwabo.graph.nodes.apply_mixprijzen import" not in src
