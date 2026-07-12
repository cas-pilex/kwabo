"""FASE 2 (F2.1) — vlaggen mogen niet verdampen door een veldbewerking.

Her-diagnose 10-7 (FASE1_DIAGNOSE.md, meta-diagnose 2): PATCH /patch-field
herschrijft needs_review_fields volledig uit state['_meta']
(preview.py:_all_needs_review_paths). De node-vlaggen `ship_to_gekozen`,
`europallet`, `verkoop_eenheid:{pos}` en `mix_uom:{pos}` bestaan NIET in
_meta met een needs_review-provenance en verdwenen dus uit banner én
approve-gate zodra de reviewer één willekeurig ander veld bewerkte —
het vlag-vernietigingsmechanisme dat gevlagde waarheid als stille fout
bij de klant liet aankomen.

Contract dat hier vastligt:
  * meta-loze node-vlaggen overleven elke ONGERELATEERDE patch;
  * ze worden WEL gewist door de bewerking die ze adresseert:
      - ship_to_gekozen        -> patch van ship_to_gekozen (meta-provenance wint)
      - europallet             -> patch van europallet_regel*
      - mix_uom:{pos}          -> patch van orderregels[pos-1].mix_uom_gekozen
                                  of een artikel-wissel op die regel
      - verkoop_eenheid:{pos}  -> patch van orderregels[pos-1].eenheid /
                                  .verkoop_uom_gekozen of een artikel-wissel
  * meta-gedekte vlaggen blijven meta-gedreven (stale nrf-entries winnen
    nooit van een needs_review=False-provenance).
"""
from __future__ import annotations

import json

from sqlmodel import Session

from kwabo.db.repository import OrderLogRepo


def _maak_order(session, *, nrf: list[str], meta: dict | None = None,
                regel_extra: dict | None = None) -> int:
    regel = {
        "positie": 1,
        "artikelnummer_klant": "804600",
        "artikelnummer_kwabo_matched": "238601",
        "omschrijving": "Afdekvlies",
        "hoeveelheid": 66,
        "eenheid": "STUK",
        "match_methode": "exact",
        "match_confidence": 1.0,
    }
    regel.update(regel_extra or {})
    state = {
        "email_id": f"t-f21-{abs(hash(json.dumps(sorted(nrf)) + json.dumps(meta or {}, sort_keys=True) + json.dumps(regel_extra or {}, sort_keys=True)))}",
        "email_from": "x@y.nl",
        "email_subject": "F2.1",
        "klant_match": {"navision_klantnr": "60892", "klantnaam": "Witzand"},
        "orderregels": [regel],
        "needs_review_fields": list(nrf),
        "needs_review_count": len(nrf),
        "_meta": meta or {},
        "stappen_log": [],
    }
    row = OrderLogRepo(session).create(
        email_id=state["email_id"], order_state=json.dumps(state)
    )
    return row.id


def _patch(client, oid: int, path: str, value):
    r = client.patch(f"/api/orders/{oid}/patch-field",
                     json={"path": path, "value": value})
    assert r.status_code == 200
    return r.json()["needs_review_fields"]


def _state(session, oid: int) -> dict:
    with Session(session.get_bind()) as s2:
        row = OrderLogRepo(s2).get(oid)
        return json.loads(row.order_state or "{}")


# ---------- overleven van ongerelateerde patches ----------

def test_europallet_vlag_overleeft_onafhankelijke_patch(client, session):
    """compute_europallet zet 'europallet' zonder meta-provenance; een patch
    op opmerkingen mag die vlag niet wegvagen (het europallet-probleem is
    er nog steeds)."""
    oid = _maak_order(session, nrf=["europallet"],
                      meta={"europallet": {"regels": [], "onbekend": [
                          {"artikelnr": "238601", "qty": 66.0, "eenheid": "STUK"}]}})
    nrf = _patch(client, oid, "opmerkingen", "spoed graag")
    assert "europallet" in nrf
    assert "europallet" in _state(session, oid)["needs_review_fields"]


def test_mix_uom_vlag_overleeft_onafhankelijke_patch(client, session):
    oid = _maak_order(session, nrf=["mix_uom:1"])
    nrf = _patch(client, oid, "opmerkingen", "x")
    assert "mix_uom:1" in nrf


def test_verkoop_eenheid_vlag_overleeft_onafhankelijke_patch(client, session):
    oid = _maak_order(session, nrf=["verkoop_eenheid:1"])
    nrf = _patch(client, oid, "gewenste_leverdatum", "2026-08-01")
    assert "verkoop_eenheid:1" in nrf


def test_ship_to_vlag_overleeft_onafhankelijke_patch(client, session):
    """select_ship_to zet de vlag zonder meta; alleen een echte
    ship-to-beslissing (of klant-wissel-reresolve) mag hem oplossen."""
    oid = _maak_order(session, nrf=["ship_to_gekozen"])
    nrf = _patch(client, oid, "opmerkingen", "x")
    assert "ship_to_gekozen" in nrf


def test_needs_review_endpoint_toont_bewaarde_vlaggen(client, session):
    oid = _maak_order(session, nrf=["europallet", "mix_uom:1"])
    r = client.get(f"/api/orders/{oid}/needs-review")
    assert r.status_code == 200
    fields = r.json()["fields"]
    assert "europallet" in fields
    assert "mix_uom:1" in fields


# ---------- gericht oplossen wist de vlag wél ----------

def test_ship_to_keuze_wist_de_vlag(client, session):
    oid = _maak_order(session, nrf=["ship_to_gekozen"])
    nrf = _patch(client, oid, "ship_to_gekozen", "7671 JE")
    assert "ship_to_gekozen" not in nrf


def test_europallet_bewerking_wist_de_vlag(client, session):
    oid = _maak_order(session, nrf=["europallet"])
    nrf = _patch(client, oid, "europallet_regel.hoeveelheid", 1)
    assert "europallet" not in nrf


def test_mix_uom_keuze_wist_alleen_die_positie(client, session):
    oid = _maak_order(session, nrf=["mix_uom:1", "mix_uom:2"])
    nrf = _patch(client, oid, "orderregels[0].mix_uom_gekozen", "M1PAL33")
    assert "mix_uom:1" not in nrf
    assert "mix_uom:2" in nrf


def test_eenheid_keuze_wist_verkoop_eenheid_vlag(client, session):
    oid = _maak_order(session, nrf=["verkoop_eenheid:1"])
    nrf = _patch(client, oid, "orderregels[0].eenheid", "PALLET33")
    assert "verkoop_eenheid:1" not in nrf


def test_artikel_wissel_wist_eenheid_en_mix_vlag_van_die_regel(client, session):
    """Artikel-wissel wipet de afgeleiden (V1) en herberekent Branch A
    (F3 DEEL B) — de oude keuze-vlaggen horen bij het oude artikel."""
    oid = _maak_order(session, nrf=["verkoop_eenheid:1", "mix_uom:1"])
    nrf = _patch(client, oid, "orderregels[0].artikelnummer_kwabo_matched", "228321")
    assert "verkoop_eenheid:1" not in nrf
    assert "mix_uom:1" not in nrf


# ---------- meta blijft de baas waar meta bestaat ----------

def test_meta_gedekte_vlag_wint_van_stale_nrf(client, session):
    """Een stale nrf-entry ('klant_match') met needs_review=False in _meta
    mag NIET bewaard worden — anders herflaggen we opgeloste velden."""
    oid = _maak_order(
        session, nrf=["klant_match"],
        meta={"klant_match": {"value": "60892", "source": "manual",
                              "confidence": 1.0, "needs_review": False}})
    nrf = _patch(client, oid, "opmerkingen", "x")
    assert "klant_match" not in nrf


def test_klant_wissel_reresolve_meta_wint_voor_ship_to(client, session):
    """Na een ECHTE klant-wissel schrijft _reresolve_ship_to verse
    meta-provenance voor ship_to_gekozen; de oude node-vlag (van de oude
    klant) mag die niet overstemmen."""
    oid = _maak_order(session, nrf=["ship_to_gekozen"])
    # wissel 60892 -> 61472 (andere klant; triggert _reresolve_ship_to)
    nrf = _patch(client, oid, "klant_match", "61472")
    # 61472 heeft in deze kale test-DB geen ship-to's -> reresolve besluit
    # vlagloos (0 kandidaten, NAV-default) en zet needs_review=False.
    assert "ship_to_gekozen" not in nrf


def test_zelfde_klant_bevestigen_laat_ship_to_vlag_staan(client, session):
    """De 'Bevestig deze klant'-knop patcht hetzelfde nummer: dat lost de
    ship-to-ambiguïteit NIET op, dus de vlag blijft."""
    oid = _maak_order(session, nrf=["ship_to_gekozen"])
    nrf = _patch(client, oid, "klant_match", "60892")
    assert "ship_to_gekozen" in nrf
