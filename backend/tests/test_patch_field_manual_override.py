"""M1: handmatige override moet plakken (Fase 2, op echte faalorders).

Faalgeval Van Dongen (#721): reviewer vulde klantnr 61472 en Kwabo-artnr
228321 handmatig in; de NAV-operaties kregen de juiste waarden, maar de
rode review-status bleef staan. Backend-aandeel daarvan:

  1. een regel-patch op artikelnummer_kwabo_matched laat match_methode op
     "manual"/confidence 0.0 staan i.p.v. "handmatig"/1.0;
  2. de raw-extract-flag (orderregels[i].artikelnummer_kwabo) wordt bij een
     handmatige match niet gewist, terwijl match_articles dat bij een
     confident automatische match wél doet — de order blijft dus eeuwig
     "ONTBREEKT" tonen;
  3. het leegmaken van een match zet needs_review NIET terug (generieke
     meta-patch zet needs_review altijd False) — grondwet 5 eist herflaggen;
  4. een patch op het sub-pad klant_match.navision_klantnr mist de
     special-case-branch en wist de klant-review-flag niet.

Fixtures: echte order-states #718 (Witzand, klant ongematcht) en
#721 (Van Dongen) via scripts/export_order_states.py.
"""
from __future__ import annotations

import json

from sqlmodel import Session

from kwabo.db.models import Klantenkaart
from kwabo.db.repository import OrderLogRepo

from conftest import load_state


def _maak_order(session, name: str) -> tuple[int, dict]:
    env = load_state(name)
    row = OrderLogRepo(session).create(
        email_id=f"t-m1-{env['order_id']}", order_state=json.dumps(env["order_state"])
    )
    return row.id, env["order_state"]


def _state(session, oid: int) -> dict:
    with Session(session.get_bind()) as s2:
        row = OrderLogRepo(s2).get(oid)
        return json.loads(row.order_state or "{}")


def _seed_witzand(session) -> None:
    session.add(Klantenkaart(
        nav_klantnr="60892", naam="Witzand Bouwmaterialen B.V.",
        is_4plus=True, kredietlimiet=5000.0, betalingsconditie="30 dagen",
    ))
    session.commit()


# --- Klant-override -----------------------------------------------------


def test_patch_klant_match_wist_review_status(client, session):
    """Pin: het hoofdpad 'klant_match' wist de review-flag (werkte al)."""
    _seed_witzand(session)
    oid, st0 = _maak_order(session, "order_718")
    assert "klant_match" in (st0.get("needs_review_fields") or [])

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match", "value": "60892"})
    assert r.status_code == 200
    assert "klant_match" not in r.json()["needs_review_fields"]

    st = _state(session, oid)
    assert st["klant_match"]["navision_klantnr"] == "60892"
    assert st["klant_match"]["klantnaam"] == "Witzand Bouwmaterialen B.V."
    assert st["klant_match"]["match_bron"] == "manual"
    assert st["_meta"]["klant_match"]["needs_review"] is False
    # Compose-cache geleegd zodat de volgende preview 60892 meeneemt.
    assert st["nav_operations"] == []


def test_patch_klant_match_subpad_wist_ook(client, session):
    """Bug 4: sub-pad klant_match.navision_klantnr moet de badge óók wissen."""
    _seed_witzand(session)
    oid, _ = _maak_order(session, "order_718")

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match.navision_klantnr", "value": "60892"})
    assert r.status_code == 200
    assert "klant_match" not in r.json()["needs_review_fields"]

    st = _state(session, oid)
    assert st["klant_match"]["navision_klantnr"] == "60892"
    assert st["klant_match"]["klantnaam"] == "Witzand Bouwmaterialen B.V."
    assert st["_meta"]["klant_match"]["needs_review"] is False


def test_patch_klant_match_verrijkt_4plus_en_krediet(client, session):
    """Fase 6 V2/V8: een handmatige klant-keuze (of bevestiging van een
    CONTROLEER-vlag) mag de 4+/krediet-context niet wegvagen — de UI-badges
    en de kredietcheck lezen die uit klant_match."""
    _seed_witzand(session)
    oid, _ = _maak_order(session, "order_718")

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match", "value": "60892"})
    assert r.status_code == 200

    km = _state(session, oid)["klant_match"]
    assert km["is_4plus"] is True
    assert km["kredietlimiet"] == 5000.0
    assert km["betalingsconditie"] == "30 dagen"


# --- Artikel-override ---------------------------------------------------


def test_patch_regel_matched_zet_handmatig_en_wist_ontbreekt(client, session):
    """Bug 1+2: handmatig Kwabo-artnr → methode 'handmatig' + ONTBREEKT weg.

    #721 is de échte na-patch-state uit prod: matched al gevuld door de
    reviewer, maar methode bleef 'manual'/0.0 en de raw-extract-flag
    (orderregels[0].artikelnummer_kwabo) bleef in needs_review staan.
    """
    oid, st0 = _maak_order(session, "order_721")
    assert "orderregels[0].artikelnummer_kwabo" in (st0.get("needs_review_fields") or [])

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].artikelnummer_kwabo_matched",
                           "value": "228321"})
    assert r.status_code == 200
    needs = r.json()["needs_review_fields"]
    assert "orderregels[0].artikelnummer_kwabo_matched" not in needs
    assert "orderregels[0].artikelnummer_kwabo" not in needs

    st = _state(session, oid)
    regel = st["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "228321"
    assert regel["match_methode"] == "handmatig"
    assert regel["match_confidence"] == 1.0
    rm = st["_meta"]["orderregels"][0]["artikelnummer_kwabo_matched"]
    assert rm["needs_review"] is False
    assert rm["source"] == "manual"
    assert st["alle_artikelen_gematcht"] is True
    assert st["nav_operations"] == []


def test_patch_regel_matched_leegmaken_herflagt(client, session):
    """Bug 3: een match leegmaken moet de regel terug in review zetten."""
    oid, _ = _maak_order(session, "order_721")

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].artikelnummer_kwabo_matched",
                           "value": ""})
    assert r.status_code == 200
    assert "orderregels[0].artikelnummer_kwabo_matched" in r.json()["needs_review_fields"]

    st = _state(session, oid)
    regel = st["orderregels"][0]
    assert not regel["artikelnummer_kwabo_matched"]
    assert regel["match_methode"] == "manual"
    assert regel["match_confidence"] == 0.0
    assert st["_meta"]["orderregels"][0]["artikelnummer_kwabo_matched"]["needs_review"] is True
    assert st["alle_artikelen_gematcht"] is False


# --- Fase 6 V1: afgeleide Branch-A/mix-velden stale na regel-patch -------
#
# De pipeline leidt verkoop_uom_gekozen/verkoop_aantal (Branch A) en
# mix_uom_gekozen/mix_aantal (mixprijzen) af uit hoeveelheid + artikel.
# De composer geeft die velden voorrang boven hoeveelheid/eenheid — een
# handmatige correctie die ze laat staan wordt bij push dus genegeerd
# (UI toont de fix, NAV krijgt de oude waarde; zelfde foutklasse als #716).


def _maak_order_met_regel(session, regel_extra: dict) -> int:
    regel = {
        "positie": 1,
        "artikelnummer_klant": None,
        "artikelnummer_kwabo": "238601",
        "artikelnummer_kwabo_matched": "238601",
        "omschrijving": "Afdekvlies",
        "hoeveelheid": 66,
        "eenheid": "STUK",
        "match_methode": "exact",
        "match_confidence": 1.0,
    }
    regel.update(regel_extra)
    state = {
        "email_id": f"t-v1-{abs(hash(json.dumps(regel_extra, sort_keys=True)))}",
        "email_from": "x@y.nl",
        "email_subject": "V1",
        "klant_match": {"navision_klantnr": "60892", "klantnaam": "Witzand"},
        "orderregels": [regel],
        "needs_review_fields": [],
        "stappen_log": [],
    }
    row = OrderLogRepo(session).create(
        email_id=state["email_id"], order_state=json.dumps(state)
    )
    return row.id


def test_patch_hoeveelheid_wist_afgeleide_verkoopvelden(client, session):
    """66→6 stuks corrigeren: de oude omrekening (2 PALLET33) mag niet
    blijven staan, anders pusht NAV alsnog 2 PALLET33."""
    oid = _maak_order_met_regel(session, {
        "verkoop_uom_gekozen": "PALLET33", "verkoop_aantal": 2,
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].hoeveelheid", "value": 6})
    assert r.status_code == 200

    regel = _state(session, oid)["orderregels"][0]
    assert regel["hoeveelheid"] == 6
    assert not regel.get("verkoop_uom_gekozen")
    assert regel.get("verkoop_aantal") is None


def test_patch_artikel_wist_afgeleide_mix_en_eenheidvelden(client, session):
    """Ander artikel kiezen: mix-keuze, kandidaten én eenheid_default horen
    bij het óúde artikel en moeten weg."""
    oid = _maak_order_met_regel(session, {
        "mix_uom_gekozen": "M7PAL30", "mix_aantal": 7,
        "mix_uom_kandidaat": ["M7PAL30", "M33PAL35"],
        "eenheid_default": "ROL",
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].artikelnummer_kwabo_matched",
                           "value": "228321"})
    assert r.status_code == 200

    regel = _state(session, oid)["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "228321"
    assert not regel.get("mix_uom_gekozen")
    assert regel.get("mix_aantal") is None
    assert not regel.get("mix_uom_kandidaat")
    assert not regel.get("eenheid_default")


def test_patch_eenheid_wist_afgeleide_uom_keuzes(client, session):
    """Reviewer kiest expliciet een eenheid: die moet winnen — de composer
    geeft verkoop/mix-keuzes anders voorrang en negeert de patch."""
    oid = _maak_order_met_regel(session, {
        "verkoop_uom_gekozen": "PALLET33", "verkoop_aantal": 2,
        "mix_uom_gekozen": "M7PAL30", "mix_aantal": 7,
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].eenheid", "value": "DOOS"})
    assert r.status_code == 200

    regel = _state(session, oid)["orderregels"][0]
    assert regel["eenheid"] == "DOOS"
    assert not regel.get("verkoop_uom_gekozen")
    assert regel.get("verkoop_aantal") is None
    assert not regel.get("mix_uom_gekozen")
    assert regel.get("mix_aantal") is None
