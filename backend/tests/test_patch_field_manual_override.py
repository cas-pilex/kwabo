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
    session.add(Klantenkaart(nav_klantnr="60892", naam="Witzand Bouwmaterialen B.V."))
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
