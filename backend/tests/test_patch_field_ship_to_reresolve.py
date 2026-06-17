"""Functie 2 — ship-to volgt de juiste klant na een handmatige klant-wijziging.

De echte bug (#847, Streckenbestelling): de tool matchte eerst de afzender
(Werkzeuge Dietrich 60103); de reviewer corrigeerde de klant naar se Huber
(61532), maar `ship_to_gekozen` bleef hangen op de ship-to-code van de óúde
klant (31303 Burgdorf). De compose pakt `ship_to_gekozen` als eerste, dus NAV
kreeg het verkeerde verzendadres.

Fix: bij een handmatige klant-wijziging in patch_field moet ship-to OPNIEUW
bepaald worden voor de nieuwe klant (kandidaten herladen + scoren op het
leveradres). Bij een her-bevestiging van dezelfde klant blijft een al gekozen
ship-to staan.
"""
from __future__ import annotations

import json

from sqlmodel import Session

from kwabo.db.models import KlantenkaartShipTo
from kwabo.db.repository import OrderLogRepo


def _add_ship_to(session, **kwargs) -> None:
    session.add(KlantenkaartShipTo(**kwargs))
    session.commit()


def _maak_order(session, state: dict) -> int:
    row = OrderLogRepo(session).create(
        email_id=state.get("email_id") or "t-f2", order_state=json.dumps(state)
    )
    return row.id


def _state(session, oid: int) -> dict:
    with Session(session.get_bind()) as s2:
        row = OrderLogRepo(s2).get(oid)
        return json.loads(row.order_state or "{}")


def _se_huber_straubing(session) -> None:
    """Nieuwe-klant (61532) ship-to-mirror: het Straubing-adres + 1 ruis-rij."""
    _add_ship_to(
        session, klant_nr="61532", ship_to_code="94315",
        naam="se Huber GmbH & Co KG", straat="Borsigstr. 15",
        postcode="94315", plaats="Straubing", land="DE", is_default=True,
    )
    _add_ship_to(
        session, klant_nr="61532", ship_to_code="80331",
        naam="se Huber Filiale", straat="Sendlinger Str. 1",
        postcode="80331", plaats="Muenchen", land="DE", is_default=False,
    )


def test_klant_change_reresolves_ship_to(client, session):
    """De echte bug: klant 60103→61532 → ship-to herberekend op het leveradres
    (Straubing 94315), niet de stale 31303 van de oude klant."""
    _se_huber_straubing(session)
    oid = _maak_order(session, {
        "email_id": "t-f2-847",
        "klant_match": {"navision_klantnr": "60103", "klantnaam": "Werkzeuge Dietrich"},
        "afleveradres": {"naam": "se Huber GmbH & Co KG", "straat": "Borsigstr. 15",
                         "postcode": "94315", "plaats": "Straubing", "land": "DE"},
        # Stale ship-to van de OUDE klant 60103:
        "ship_to_gekozen": "31303",
        "ship_to_kandidaten": [
            {"klant_nr": "60103", "ship_to_code": "31303", "naam": "Werkzeuge Dietrich",
             "postcode": "D 31303", "plaats": "Burgdorf", "land": "DE", "is_default": False},
        ],
        "needs_review_fields": [],
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match", "value": "61532"})
    assert r.status_code == 200

    st = _state(session, oid)
    assert st["klant_match"]["navision_klantnr"] == "61532"
    # Ship-to is opnieuw bepaald voor de NIEUWE klant op het leveradres.
    assert st["ship_to_gekozen"] == "94315"
    klantnrs = {c["klant_nr"] for c in st["ship_to_kandidaten"]}
    assert klantnrs == {"61532"}
    # De stale code van de oude klant is verdwenen.
    assert "31303" not in [c["ship_to_code"] for c in st["ship_to_kandidaten"]]


def test_klant_change_ambiguous_flags_review(client, session):
    """Nieuwe klant met ≥2 even-zwak-scorende ship-to's en geen leveradres-
    signaal → geen autopick; ship_to_gekozen None + review-vlag."""
    _add_ship_to(session, klant_nr="61532", ship_to_code="AAA", naam="Loc A",
                 straat="Astraat 1", postcode="1000 AA", plaats="Alkmaar", land="NL")
    _add_ship_to(session, klant_nr="61532", ship_to_code="BBB", naam="Loc B",
                 straat="Bstraat 2", postcode="2000 BB", plaats="Breda", land="NL")
    oid = _maak_order(session, {
        "email_id": "t-f2-ambi",
        "klant_match": {"navision_klantnr": "60103", "klantnaam": "Oud"},
        # Geen leveradres-signaal dat een van beide aanwijst.
        "afleveradres": {},
        "ship_to_gekozen": "OLD",
        "ship_to_kandidaten": [],
        "needs_review_fields": [],
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match", "value": "61532"})
    assert r.status_code == 200
    assert "ship_to_gekozen" in r.json()["needs_review_fields"]

    st = _state(session, oid)
    assert st["ship_to_gekozen"] is None
    assert {c["klant_nr"] for c in st["ship_to_kandidaten"]} == {"61532"}


def test_same_klant_reconfirm_keeps_ship_to(client, session):
    """Her-bevestiging van dezelfde klant mag een al gekozen ship-to niet
    wissen of herberekenen (de 'Bevestig deze klant'-knop patcht hetzelfde nr)."""
    _se_huber_straubing(session)
    oid = _maak_order(session, {
        "email_id": "t-f2-reconfirm",
        "klant_match": {"navision_klantnr": "61532", "klantnaam": "se Huber"},
        "afleveradres": {"postcode": "94315", "plaats": "Straubing"},
        # Reviewer koos eerder handmatig de Muenchen-vestiging.
        "ship_to_gekozen": "80331",
        "ship_to_kandidaten": [
            {"klant_nr": "61532", "ship_to_code": "80331", "naam": "se Huber Filiale",
             "postcode": "80331", "plaats": "Muenchen", "land": "DE", "is_default": False},
        ],
        "needs_review_fields": [],
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match", "value": "61532"})
    assert r.status_code == 200

    st = _state(session, oid)
    # Onaangeroerd: geen re-resolve bij gelijk klantnr.
    assert st["ship_to_gekozen"] == "80331"
    assert [c["ship_to_code"] for c in st["ship_to_kandidaten"]] == ["80331"]


def test_klant_change_zero_ship_to_uses_nav_default(client, session):
    """Nieuwe klant zonder ship-to-rijen → ship_to_gekozen None, géén review
    (NAV gebruikt de klant-default)."""
    oid = _maak_order(session, {
        "email_id": "t-f2-zero",
        "klant_match": {"navision_klantnr": "60103", "klantnaam": "Oud"},
        "afleveradres": {"postcode": "94315", "plaats": "Straubing"},
        "ship_to_gekozen": "31303",
        "ship_to_kandidaten": [
            {"klant_nr": "60103", "ship_to_code": "31303", "naam": "Oud",
             "postcode": "D 31303", "plaats": "Burgdorf", "land": "DE", "is_default": False},
        ],
        "needs_review_fields": [],
    })

    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": "klant_match", "value": "61532"})
    assert r.status_code == 200
    assert "ship_to_gekozen" not in r.json()["needs_review_fields"]

    st = _state(session, oid)
    assert st["ship_to_gekozen"] is None
    assert st["ship_to_kandidaten"] == []
