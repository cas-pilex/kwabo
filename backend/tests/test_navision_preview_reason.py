"""Fase 5 (A): leesbare reden bij 0 NAV-operaties in de navision-preview.

Nico's casus: een order toont "0 operaties" zonder uitleg. De backend weet
de reden (geen klant / geen gematchte regels / compose-fout) — het
preview-endpoint moet die als NL-reviewer-tekst (`reason`) meegeven, en
een compose-fout die níét over artikelen gaat mag niet als
"no_matched_articles" vermomd worden.
"""
from __future__ import annotations

import json

# Module-level import zodat SQLModel.metadata gevuld is vóór de session-fixture
# create_all draait (anders: "no such table" bij een file-alleen-run).
from kwabo.db.repository import OrderLogRepo


def _order(session, state: dict) -> int:
    row = OrderLogRepo(session).create(
        email_id=f"preview-reason-{id(state)}", email_from="x@y.nl",
        email_subject="test", status="review",
    )
    row.order_state = json.dumps(state)
    session.add(row)
    session.commit()
    return row.id


def test_geen_gematchte_regels_geeft_leesbare_reden(client, session):
    """Klant wél gematcht, 0 gematchte regels → status no_matched_articles
    + reviewer-tekst die zegt wat te doen."""
    oid = _order(session, {
        "email_id": "preview-reason-1",
        "is_order": True,
        "klant_match": {"navision_klantnr": "10001", "klantnaam": "Test"},
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo_matched": None, "hoeveelheid": 10},
            {"positie": 2, "artikelnummer_kwabo_matched": "", "hoeveelheid": 5},
        ],
        "nav_operations": [],
    })
    r = client.get(f"/api/orders/{oid}/navision-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "no_matched_articles"
    assert body["operations"] == []
    assert "Geen artikelregel gematcht" in (body.get("reason") or ""), body


def test_geen_klant_geeft_leesbare_reden(client, session):
    oid = _order(session, {
        "email_id": "preview-reason-2",
        "is_order": True,
        "klant_match": {},
        "orderregels": [],
        "nav_operations": [],
    })
    r = client.get(f"/api/orders/{oid}/navision-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "no_customer"
    assert "Geen klant gematcht" in (body.get("reason") or ""), body


def test_andere_compose_fout_heet_geen_no_matched_articles(client, session, monkeypatch):
    """Een compose-fout die niets met artikelen te maken heeft (b.v. een
    ongeldige eenheid) moet als status compose_error + detail-tekst komen."""
    from kwabo.api import preview as preview_mod

    def boom(state):
        raise ValueError("eenheid 'XYZ' is ongeldig voor artikel 123")

    monkeypatch.setattr(preview_mod, "compose_navision_operations", boom)
    oid = _order(session, {
        "email_id": "preview-reason-3",
        "is_order": True,
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "111", "hoeveelheid": 1}],
        "nav_operations": [],
    })
    r = client.get(f"/api/orders/{oid}/navision-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "compose_error", body
    assert "Order samenstellen mislukt" in (body.get("reason") or ""), body
    assert "eenheid 'XYZ'" in body["reason"]


def test_ready_heeft_geen_reden_en_missing_telt(client, session, monkeypatch):
    """ready → reason None; missing → telling in de reden."""
    from kwabo.api import preview as preview_mod

    monkeypatch.setattr(
        preview_mod, "compose_navision_operations",
        lambda state: [{"op": "POST", "path": "x", "body": {}}],
    )
    # ready: klant + geen needs_review
    oid = _order(session, {
        "email_id": "preview-reason-4a",
        "is_order": True,
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "111"}],
        "nav_operations": [],
    })
    body = client.get(f"/api/orders/{oid}/navision-preview").json()
    assert body["status"] == "ready"
    assert body.get("reason") is None

    # missing: één needs_review-veld in _meta
    oid2 = _order(session, {
        "email_id": "preview-reason-4b",
        "is_order": True,
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "111"}],
        "nav_operations": [],
        "_meta": {"klant_match": {"value": "10001", "needs_review": True}},
    })
    body2 = client.get(f"/api/orders/{oid2}/navision-preview").json()
    assert body2["status"] == "missing"
    assert "1 veld" in (body2.get("reason") or ""), body2
