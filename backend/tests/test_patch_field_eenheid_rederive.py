"""Functie 3 DEEL B — een handmatige kwabo-artnr-invoer moet de eenheid + het
aantal correct (her)berekenen (Branch A), niet als STUK met leeg aantal landen.

patch_field WIST de afgeleide velden (verkoop_uom_gekozen/verkoop_aantal) bij een
bronveld-patch (Fase 6 V1), maar herberekende ze nooit — Branch A draait alleen
tijdens ingest. Gevolg bij een handmatige artikel-match: de compose viel terug op
de letterlijke base-eenheid/leeg aantal. Nu draait Branch A opnieuw op het
artikel-pad.

Lasaulec: 60 STUK + handmatig 15620 (verkoop_eenheid PALLET, qty_per_base 30)
-> 2 PALLET.
"""
from __future__ import annotations

import json

from sqlmodel import Session

from kwabo.db.models import Artikelkaart, ArtikelEenheid
from kwabo.db.repository import OrderLogRepo
from kwabo.integrations.navision_steps import _emit_line_ops


def _seed_15620(session) -> None:
    session.add(Artikelkaart(kwabo_artikelnr="15620", naam="Afdekvlies 30/pallet",
                             basis_eenheid="STUK", verkoop_eenheid="PALLET"))
    session.add(ArtikelEenheid(kwabo_artikelnr="15620", eenheid_code="STUK", qty_per_base=1))
    session.add(ArtikelEenheid(kwabo_artikelnr="15620", eenheid_code="PALLET", qty_per_base=30))
    session.commit()


def _maak_order(session, regel_extra: dict | None = None) -> int:
    regel = {
        "positie": 1,
        "artikelnummer_klant": "LAS-99",
        "artikelnummer_kwabo": None,
        "artikelnummer_kwabo_matched": None,
        "omschrijving": "Afdekvlies pallet",
        "hoeveelheid": 60,
        "eenheid": "STUK",
        "match_methode": "manual",
        "match_confidence": 0.0,
    }
    regel.update(regel_extra or {})
    state = {
        "email_id": "t-f3b",
        "klant_match": {"navision_klantnr": "61745", "klantnaam": "Lasaulec B.V."},
        "orderregels": [regel],
        "needs_review_fields": ["orderregels[0].artikelnummer_kwabo_matched"],
        "stappen_log": [],
    }
    row = OrderLogRepo(session).create(email_id=state["email_id"],
                                       order_state=json.dumps(state))
    return row.id


def _state(session, oid: int) -> dict:
    with Session(session.get_bind()) as s2:
        row = OrderLogRepo(s2).get(oid)
        return json.loads(row.order_state or "{}")


def test_manual_article_rederives_branch_a(client, session):
    """60 STUK + handmatig 15620 -> verkoop PALLET, aantal 2; ops = PALLET + 2."""
    _seed_15620(session)
    oid = _maak_order(session)

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].artikelnummer_kwabo_matched",
                           "value": "15620"})
    assert r.status_code == 200

    regel = _state(session, oid)["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "15620"
    assert regel["verkoop_uom_gekozen"] == "PALLET"
    assert regel["verkoop_aantal"] == 2

    ops = _emit_line_ops(regel, "15620", "regel")
    bodies = [op["body"] for op in ops]
    assert {"unitOfMeasureCode": "PALLET"} in bodies
    assert {"quantity": 2} in bodies


def test_manual_article_without_masterdata_is_noop(client, session):
    """Geen masterdata voor het gekozen artikel -> her-berekening slaat over
    (de V1-wipe blijft gelden, geen verzonnen verkoopvelden)."""
    oid = _maak_order(session)

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "orderregels[0].artikelnummer_kwabo_matched",
                           "value": "999999"})
    assert r.status_code == 200

    regel = _state(session, oid)["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "999999"
    assert not regel.get("verkoop_uom_gekozen")
    assert regel.get("verkoop_aantal") is None
