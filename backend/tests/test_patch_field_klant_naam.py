"""Regressie: bij een handmatig gezette klant verrijkt de backend klant_match
met de NAAM uit de klantenkaart (i.p.v. een leeg/stale naamveld te bewaren).

Voorheen toonde de review-UI bij een handmatige klant alleen het nummer +
confidence, niet de naam — verwarrend voor de order-invoerder die in namen
denkt, niet in codes. Ontdekt 01-06-2026. [[artikel-automatch-data-sparsity]]
"""
from __future__ import annotations

import json

from sqlmodel import Session

from kwabo.db.repository import OrderLogRepo


def _state(session, oid: int) -> dict:
    with Session(session.get_bind()) as s2:
        row = OrderLogRepo(s2).get(oid)
        return json.loads(row.order_state or "{}")


def test_patch_field_klant_match_enriches_name(client, session):
    row = OrderLogRepo(session).create(
        email_id="t-naam-1", order_state=json.dumps({"klant_match": {}})
    )
    oid = row.id

    r = client.patch(f"/api/orders/{oid}/patch-field", json={"path": "klant_match", "value": "10001"})
    assert r.status_code == 200

    st = _state(session, oid)
    assert st["klant_match"]["navision_klantnr"] == "10001"
    assert st["klant_match"]["klantnaam"] == "Ferney Diabolo B.V."


def test_patch_field_unknown_klant_keeps_empty_name(client, session):
    row = OrderLogRepo(session).create(
        email_id="t-naam-2", order_state=json.dumps({"klant_match": {}})
    )
    oid = row.id

    r = client.patch(f"/api/orders/{oid}/patch-field", json={"path": "klant_match", "value": "99999"})
    assert r.status_code == 200

    st = _state(session, oid)
    assert st["klant_match"]["navision_klantnr"] == "99999"
    # Niet gevonden in de mirror -> nummer blijft, naam leeg (UI toont nummer).
    assert st["klant_match"]["klantnaam"] == ""


def test_patch_order_klant_nr_enriches_name(client, session):
    row = OrderLogRepo(session).create(
        email_id="t-naam-3", order_state=json.dumps({"klant_match": {}})
    )
    oid = row.id

    r = client.patch(f"/api/orders/{oid}", json={"klant_nr": "10001"})
    assert r.status_code == 200

    st = _state(session, oid)
    assert st["klant_match"]["klantnaam"] == "Ferney Diabolo B.V."
