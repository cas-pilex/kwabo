"""FASE 1 — zelftest van de baseline-judge ("test van de test").

De her-diagnose wantrouwt ook het meetinstrument: deze tests bewijzen eerst
ROOD dat de Fase A-judge (letterlijk gekopieerd naar scripts/fase1_judge.py)
vlaggen mist die de pipeline wél zet, en pas daarna wordt de judge gefixt.

Gedocumenteerde judge-beslissingen die hier vastliggen:
  1. mix_uom:{pos} (gezet door apply_mixprijzen.py:366) telt als eenheid-vlag
     — een gevlagde mix-eenheidfout is FOUT-met-vlag, geen STILLE-FOUT.
  2. regel.aantal deelt de eenheid-vlag van dezelfde positie: eenheid en
     omgerekend aantal zijn één beslissing (resolve_line_uom); een reviewer
     die de eenheid-vlag ziet, ziet het aantal ernaast.
  3. verzendwijze blijft BEWUST vlagloos-streng: de pipeline kent geen
     verzendwijze-vlag, dus elke fout is per definitie stil.
  4. summarize() legt adres-per-rol en compose-status/regelverlies vast
     (opdracht 1b: klant/adres-per-rol/regels/europallet/compose-status).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fase1_judge as fj  # noqa: E402


def _out(**over) -> dict:
    """Minimale pipeline-output; velden overschrijfbaar per test."""
    base = {
        "is_order": True,
        "klant_match": {"navision_klantnr": "61532", "klantnaam": "se Huber",
                        "match_bron": "email", "match_confidence": 1.0},
        "needs_review_fields": [],
        "afleveradres": {"naam": "se Huber", "straat": "x", "postcode": "94315",
                         "plaats": "Straubing", "land": "DE"},
        "ship_to_gekozen": "94315",
        "orderregels": [],
        "validatie_warnings": [],
    }
    base.update(over)
    return base


# ---------- basisgedrag (moet in oude én nieuwe judge gelijk zijn) ----------

def test_juist():
    oordeel = fj.judge(_out(), {"klant_nr": "61532", "ship_to_code": "94315"})
    assert oordeel["status"] == "JUIST"
    assert oordeel["n_stille_fouten"] == 0


def test_fout_met_klantvlag_is_review():
    out = _out(needs_review_fields=["klant_match"])
    oordeel = fj.judge(out, {"klant_nr": "99999"})
    assert oordeel["status"] == "review"
    assert oordeel["n_review"] == 1


def test_confident_foute_klant_zonder_vlag_is_stille_fout():
    """De strenge definitie: confident-fout op 100% zonder vlag = STILLE FOUT."""
    oordeel = fj.judge(_out(), {"klant_nr": "50094"})
    assert oordeel["status"] == "STILLE-FOUT"


def test_geen_grondwaarheid():
    assert fj.judge(_out(), None)["status"] == "geen_grondwaarheid"


def test_none_waarden_crashen_niet():
    out = _out(europallet_regel=None, verzendwijze=None)
    oordeel = fj.judge(out, {"europallet_aantal": 1, "verzendwijze": "EXW"})
    statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
    assert statussen["europallet_aantal"] == "STILLE-FOUT"
    assert statussen["verzendwijze"] == "STILLE-FOUT"


def test_verzendwijze_fout_blijft_altijd_stil():
    """Beslissing 3: er bestaat geen verzendwijze-vlag -> fout is stil, ook
    als er toevallig andere vlaggen staan."""
    out = _out(verzendwijze="AF FABRIEK", needs_review_fields=["klant_match"])
    oordeel = fj.judge(out, {"verzendwijze": "EXW"})
    statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
    assert statussen["verzendwijze"] == "STILLE-FOUT"


# ---------- de bewezen Fase A-gaten (eerst ROOD, dan judge-fix) ----------

def test_mix_uom_vlag_telt_als_eenheid_vlag():
    """apply_mixprijzen.py:366 zet f"mix_uom:{pos}" bij een onzekere
    mix-eenheid; de Fase A-judge (upgrade_baseline.py:274) kent die key niet
    en telt een gevlagde mix-fout dan onterecht als STILLE-FOUT."""
    out = _out(
        needs_review_fields=["mix_uom:2"],
        orderregels=[{"positie": 2, "eenheid": "PAL", "hoeveelheid": 2,
                      "mix_uom_gekozen": "M1PAL30", "mix_aantal": 1,
                      "artikelnummer_kwabo_matched": "23522",
                      "match_confidence": 1.0}],
    )
    oordeel = fj.judge(out, {"regels": [{"pos": 2, "eenheid": "PALLET", "aantal": 2}]})
    statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
    assert statussen["regel2.eenheid"] == "FOUT-met-vlag"


def test_aantal_fout_onder_eenheidsvlag_is_review():
    """Beslissing 2: eenheid+aantal zijn één beslissing; bij een
    eenheid-vlag op de positie is een fout omgerekend aantal FOUT-met-vlag."""
    out = _out(
        needs_review_fields=["verkoop_eenheid:1"],
        orderregels=[{"positie": 1, "eenheid": "PAL", "hoeveelheid": 60,
                      "verkoop_uom_gekozen": "STUK", "verkoop_aantal": 60,
                      "artikelnummer_kwabo_matched": "15620",
                      "match_confidence": 1.0}],
    )
    oordeel = fj.judge(out, {"regels": [{"pos": 1, "eenheid": "PALLET", "aantal": 2}]})
    statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
    assert statussen["regel1.eenheid"] == "FOUT-met-vlag"
    assert statussen["regel1.aantal"] == "FOUT-met-vlag"


def test_aantal_fout_zonder_enige_vlag_blijft_stille_fout():
    out = _out(
        orderregels=[{"positie": 1, "eenheid": "STUK", "hoeveelheid": 60,
                      "verkoop_uom_gekozen": "STUK", "verkoop_aantal": 60,
                      "artikelnummer_kwabo_matched": "15620",
                      "match_confidence": 1.0}],
    )
    oordeel = fj.judge(out, {"regels": [{"pos": 1, "eenheid": "STUK", "aantal": 2}]})
    statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
    assert statussen["regel1.aantal"] == "STILLE-FOUT"


def test_afleveradres_vlag_uit_extract_telt_voor_postcode():
    """Vocabulaire-audit: extract zet 'afleveradres' (extract.py:148/160/162)
    of 'adressen' (meta-herleiding) bij rol-twijfel; de Fase A-judge keek voor
    afleveradres_postcode alleen naar 'ship_to_gekozen' -> een gevlagd fout
    afleveradres telde onterecht als STILLE-FOUT."""
    for vlag in ("afleveradres", "adressen"):
        out = _out(
            needs_review_fields=[vlag],
            afleveradres={"naam": "BAUHAUS", "straat": "x", "postcode": "3981 LB",
                          "plaats": "Bunnik", "land": "NL"},
        )
        oordeel = fj.judge(out, {"afleveradres_postcode": "7559 SR"})
        statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
        assert statussen["afleveradres_postcode"] == "FOUT-met-vlag", vlag


def test_foute_postcode_zonder_vlag_blijft_stille_fout():
    out = _out(afleveradres={"naam": "BAUHAUS", "straat": "x", "postcode": "3981 LB",
                             "plaats": "Bunnik", "land": "NL"})
    oordeel = fj.judge(out, {"afleveradres_postcode": "7559 SR"})
    statussen = {v["veld"]: v["oordeel"] for v in oordeel["velden"]}
    assert statussen["afleveradres_postcode"] == "STILLE-FOUT"


# ---------- vastlegging (opdracht 1b: letterlijk, incl. rollen + compose) ----------

def test_summarize_bevat_adres_rollen():
    out = _out(adres_rollen={"besteller": {"plaats": "Bunnik", "postcode": "3981 LB"},
                             "aflever": {"plaats": "Hengelo", "postcode": "7559 SR"},
                             "factuur": None, "eindontvanger": None})
    s = fj.summarize(out)
    assert s["extract"]["adres_rollen"]["aflever"]["postcode"] == "7559 SR"
    assert s["extract"]["adres_rollen"]["besteller"]["plaats"] == "Bunnik"


def test_summarize_adres_rollen_uit_meta_fallback():
    """adres_rollen is geen OrderState-channel (state.py) en wordt door
    LangGraph na extract gedropt; de rollen overleven alleen in
    _meta['adressen'].value (extract.py:133). De vastlegging moet ze daar
    terugvinden — anders is 'adres per rol' (opdracht 1b) structureel leeg."""
    out = _out(_meta={"adressen": {
        "value": {"besteller": {"plaats": "Bunnik", "postcode": "3981 LB"},
                  "aflever": {"plaats": "Hengelo", "postcode": "7559 SR"},
                  "factuur": None, "eindontvanger": None},
        "source": "llm", "needs_review": False}})
    s = fj.summarize(out)
    assert s["extract"]["adres_rollen"]["aflever"]["plaats"] == "Hengelo"


def test_summarize_bevat_compose_status_en_regelverlies():
    out = _out(
        orderregels=[
            {"positie": 1, "artikelnummer_kwabo_matched": "23520", "match_confidence": 1.0},
            {"positie": 2, "artikelnummer_kwabo_matched": None, "omschrijving": "toeslag"},
        ],
        nav_operations=[
            {"op": "POST", "path": "/salesOrders", "body": {"customerNumber": "60245"},
             "label": "order aanmaken"},
            {"op": "PATCH", "path": "/salesOrders({id})", "body": {"shipToCode": "X"},
             "optional": True},
        ],
        validatie_warnings=["⚠ Regel 2 (toeslag) heeft geen artikel-match en is "
                            "NIET in de NAV-operaties opgenomen."],
    )
    s = fj.summarize(out)
    assert s["compose"]["status"] == "ok"
    assert s["compose"]["nav_ops_count"] == 2
    assert s["compose"]["regels_zonder_match"] == [2]
    assert s["compose"]["regelverlies_gevlagd"] is True
    assert s["compose"]["ops"][0] == {"op": "POST", "path": "/salesOrders",
                                      "body_keys": ["customerNumber"], "optional": False}


def test_summarize_compose_error():
    out = _out(compose_error="ValueError: kapot", nav_operations=[])
    s = fj.summarize(out)
    assert s["compose"]["status"] == "error"
    assert s["compose"]["error"] == "ValueError: kapot"


def test_summarize_compose_leeg_zonder_error():
    out = _out(nav_operations=[])
    s = fj.summarize(out)
    assert s["compose"]["status"] == "leeg"
