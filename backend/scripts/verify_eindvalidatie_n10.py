"""Eindvalidatie N10 — brede steekproef: echte orders vers door de volledige sub-graph.

Laadt ALLE geëxporteerde prod-masterdata (klantenkaarten incl. mixvlag,
artikelkaarten, artikel_eenheden, kruisverwijzingen, klantenkaart_artikelen,
ship-to's, matching_history, pallet_kennis) in een wegwerp-sqlite, reset per
order de match-/compose-velden (extractie blijft staan) en draait de volledige
sub-graph (match_customer → select_ship_to → match_articles → apply_mixprijzen
→ compute_europallet → validate_prices → compose) tegen MockNavisionClient.

Het naam-signaal (klantnaam_besteller) bestaat niet in de oude prod-states
(oude code); we geven mee wat LETTERLIJK in de mail/het document staat — de
verse LLM-extractie van dat veld is apart bewezen (test_extract_klantnaam_
besteller + regressieset).

Usage (vanuit backend/): python scripts/verify_eindvalidatie_n10.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

# Vóór elke kwabo-import: nooit de echte DB raken (backend/.env wijst naar prod).
_tmpdb = Path(tempfile.mkdtemp()) / "verify_n10.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"
os.environ["NAVISION_MODE"] = "mock"

from sqlmodel import SQLModel, Session  # noqa: E402

from kwabo.db.models import (  # noqa: E402
    Artikelkaart,
    ArtikelEenheid,
    ArtikelKruisverwijzing,
    ArtikelMatchingHistory,
    ArtikelPalletKennis,
    Klantenkaart,
    KlantenkaartArtikel,
    KlantenkaartShipTo,
)
from kwabo.db.session import engine  # noqa: E402
from kwabo.graph.graph import get_sub_order_app  # noqa: E402
from kwabo.integrations.navision_api import nav_client_scope  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

# (order_id, naam-signaal zoals LETTERLIJK in mail/document staat — None als de
#  klant via e-mailadres hoort te matchen, verwachte klant of 'kandidaten')
ORDERS = [
    # — de 7+1 faalorders uit Nico's praktijktest —
    (706, None, "60282"),                              # PPG — email
    (707, "GBI Borne", "61948"),                       # zevij-portaal
    (717, None, "61844"),                              # Kuipers — email
    (718, "Witzand Bouwmaterialen B.V.", "60892"),
    (721, "Van Dongen Verf BV", "61472"),
    (635, "TABS Holland", "kandidaten"),               # pontmeyer-agent
    (550, "Jongeneel", "kandidaten"),                  # franchise
    (716, None, "61030"),                              # Würth — email
    # — 10 extra recente orders (deterministische selectie, zie rapport) —
    (765, "Ter Hoeven Verfgroep Ede", None),           # body: letterlijk
    (742, None, "60597"),                              # farbenklein — email
    (712, None, "60228"),                              # stucshowroom — email
    (700, "BAUHAUS Nederland C.V.", None),             # body: letterlijk
    (678, "Carel Lurvink Logistics B.V.", None),       # afleveradres/body
    (660, "Kopadi", None),                             # forwarded, body
    (628, "Omtzigt Bouwmaterialen B.V.", None),        # body: letterlijk
    (619, None, "61793"),                              # TABS — email
    (595, "Bouwmarkt Baarn", None),                    # body: letterlijk
    (685, None, "60203"),                              # Veris — email, mixklant
]

VERBODEN_BODY_KEYS = {"unitPrice", "unit_price", "Unit_Price", "description", "Description"}


def _load_json(name: str) -> list[dict]:
    return json.loads((STATES / name).read_text(encoding="utf-8"))


def seed_masterdata() -> None:
    SQLModel.metadata.create_all(engine)
    kk = _load_json("klantenkaarten.json")
    ak = _load_json("artikelkaarten.json")
    ae = _load_json("artikel_eenheden.json")
    kv = _load_json("kruisverwijzingen.json")
    ka = _load_json("klantenkaart_artikelen.json")
    st = _load_json("shipto.json")
    mh = _load_json("matching_history.json")
    pk = _load_json("artikel_pallet_kennis.json")
    with Session(engine) as s:
        for r in kk:
            s.add(Klantenkaart(nav_klantnr=r["nav_klantnr"], naam=r["naam"] or "",
                               email=r.get("email"), email_bestelling=r.get("email_bestelling"),
                               mixprijzen=bool(r.get("mixprijzen"))))
        for r in ak:
            s.add(Artikelkaart(kwabo_artikelnr=r["kwabo_artikelnr"], naam=r["naam"] or "",
                               basis_eenheid=r["basis_eenheid"] or "STUK"))
        for r in ae:
            s.add(ArtikelEenheid(kwabo_artikelnr=r["kwabo_artikelnr"],
                                 eenheid_code=r["eenheid_code"],
                                 qty_per_base=r["qty_per_base"],
                                 is_mix_uom=bool(r["is_mix_uom"])))
        for r in kv:
            s.add(ArtikelKruisverwijzing(klant_nr=r["klant_nr"],
                                         klant_artikelnr=r["klant_artikelnr"],
                                         kwabo_artikelnr=r["kwabo_artikelnr"],
                                         eenheid_klant=r.get("eenheid_klant")))
        for r in ka:
            s.add(KlantenkaartArtikel(klant_nr=r["klant_nr"], klant_artikelnr=r["klant_artikelnr"],
                                      kwabo_artikelnr=r["kwabo_artikelnr"],
                                      omschrijving=r.get("omschrijving")))
        for r in st:
            s.add(KlantenkaartShipTo(klant_nr=r["klant_nr"], ship_to_code=r["ship_to_code"],
                                     naam=r["naam"] or "", straat=r["straat"] or "",
                                     postcode=r["postcode"] or "", plaats=r["plaats"] or "",
                                     land=r["land"] or "", is_default=bool(r["is_default"])))
        for r in mh:
            s.add(ArtikelMatchingHistory(klant_nr=r["klant_nr"], klant_artikelnr=r.get("klant_artikelnr"),
                                         klant_omschrijving=r.get("klant_omschrijving"),
                                         kwabo_artikelnr=r["kwabo_artikelnr"],
                                         match_methode=r["match_methode"],
                                         was_correctie=bool(r.get("was_correctie"))))
        for r in pk:
            s.add(ArtikelPalletKennis(kwabo_artikelnr=r["kwabo_artikelnr"], eenheid=r["eenheid"],
                                      pallet_required=bool(r["pallet_required"]),
                                      per_pallet=int(r["per_pallet"]),
                                      confidence=float(r["confidence"])))
        s.commit()
    print(f"masterdata: {len(kk)} klanten, {len(ak)} artikelen, {len(ae)} eenheden, "
          f"{len(kv)} kruisverw., {len(st)} ship-to's, {len(ka)} kaart-mappings, "
          f"{len(mh)} history, {len(pk)} pallet-kennis\n")


def _laad_order(oid: int) -> dict:
    f = next(iter(sorted(STATES.glob(f"order_{oid}_*.json"))), None)
    if not f:
        raise SystemExit(f"fixture order_{oid}_* ontbreekt")
    return json.loads(f.read_text(encoding="utf-8"))


REGEL_RESET = ("artikelnummer_kwabo_matched", "match_methode", "match_confidence",
               "verkoop_uom_gekozen", "verkoop_aantal", "mix_uom_gekozen", "mix_aantal")


def verse_input(env: dict, naam_signaal: str | None) -> dict:
    st_oud = env["order_state"]
    st = {
        "email_id": f"n10-{env['order_id']}",
        "email_from": env["email_from"],
        "email_subject": env["email_subject"],
        "email_body": st_oud.get("email_body") or "",
        "bijlagen": st_oud.get("bijlagen") or [],
        "stappen_log": [],
        "is_order": True,
        "klantnaam_besteller": naam_signaal,
        "afleveradres": st_oud.get("afleveradres"),
        "bestelnummer_klant": st_oud.get("bestelnummer_klant"),
        "gewenste_leverdatum": st_oud.get("gewenste_leverdatum"),
        "opmerkingen": st_oud.get("opmerkingen"),
        "orderregels": [],
        "_meta": {},
    }
    for r in st_oud.get("orderregels") or []:
        r2 = dict(r)
        for k in REGEL_RESET:
            r2[k] = None
        st["orderregels"].append(r2)
    return st


def _check_verboden_keys(ops: list[dict]) -> list[str]:
    hits = []
    for i, op in enumerate(ops):
        body = op.get("body") or {}
        for k in body:
            if k in VERBODEN_BODY_KEYS:
                hits.append(f"op[{i}] {op.get('op')} {op.get('path')}: verboden key {k!r}")
    return hits


async def main() -> None:
    seed_masterdata()
    app = get_sub_order_app()
    totaal_verboden: list[str] = []
    for oid, naam_signaal, ref in ORDERS:
        env = _laad_order(oid)
        st_oud = env["order_state"]
        st = verse_input(env, naam_signaal)
        async with nav_client_scope():
            uit = await app.ainvoke(st)

        km = uit.get("klant_match") or {}
        kand = uit.get("klant_kandidaten") or []
        kmeta = (uit.get("_meta") or {}).get("klant_match") or {}
        ship = uit.get("ship_to_gekozen")
        ship_k = uit.get("ship_to_kandidaten") or []
        ops = uit.get("nav_operations") or []
        ep = uit.get("europallet_regel")

        print(f"=== #{oid}  {env['email_subject'][:55]!r}")
        print(f"    van: {env['email_from'][:55]!r}  signaal: {naam_signaal!r}  referentie: {ref!r}")
        vlag = "CONTROLEER" if kmeta.get("needs_review") else "vertrouwd"
        print(f"    KLANT  {km.get('navision_klantnr')!r} ({km.get('match_bron')}, "
              f"conf {km.get('match_confidence')}) vlag={vlag}"
              + (f"  kandidaten: {[(k.get('navision_klantnr'), k.get('klantnaam')) for k in kand[:6]]}"
                 if kand else ""))
        if ship:
            detail = next((k for k in ship_k if k.get("ship_to_code") == ship), {})
            print(f"    SHIP-TO  {ship!r} {detail.get('plaats')!r} {detail.get('postcode')!r} "
                  f"(van {len(ship_k)} kandidaten)")
        else:
            nrf = uit.get("needs_review_fields") or []
            extra = " — AMBIGU, review-vlag" if "ship_to_gekozen" in nrf else " -> NAV-default"
            print(f"    SHIP-TO  geen gekozen (kandidaten: {len(ship_k)}){extra}")
        for i, r in enumerate(uit.get("orderregels") or []):
            oud = (st_oud.get("orderregels") or [{}] * 99)[i] if i < len(st_oud.get("orderregels") or []) else {}
            extra = ""
            if r.get("mix_uom_gekozen"):
                extra = f"  mix: {r['mix_aantal']} x {r['mix_uom_gekozen']}"
            elif r.get("verkoop_uom_gekozen"):
                extra = f"  verkoop: {r['verkoop_aantal']} x {r['verkoop_uom_gekozen']}"
            print(f"    REGEL{i}  {(r.get('omschrijving') or '')[:42]!r} qty={r.get('hoeveelheid')} {r.get('eenheid')!r}")
            print(f"        was: {oud.get('artikelnummer_kwabo_matched')!r} ({oud.get('match_methode')})"
                  f"  ->  nu: {r.get('artikelnummer_kwabo_matched')!r} "
                  f"({r.get('match_methode')}, conf {r.get('match_confidence')}){extra}")
        print(f"    EUROPALLET  {('%s x %s' % (ep.get('hoeveelheid'), ep.get('artikelnummer_kwabo'))) if ep else 'geen'}")
        nrf = uit.get("needs_review_fields") or []
        meta = uit.get("_meta") or {}
        regel_flags = sorted(k for k, v in meta.items()
                             if isinstance(v, dict) and v.get("needs_review"))
        print(f"    REVIEW-VELDEN  needs_review_fields={nrf}  _meta-flags={regel_flags}")
        if ops:
            print(f"    OPERATIONS ({len(ops)}):")
            for op in ops:
                print(f"        {op.get('op'):5s} {op.get('path')}  {json.dumps(op.get('body'), ensure_ascii=False, default=str)}")
        else:
            reden = uit.get("compose_error") or "(geen compose_error gezet)"
            print(f"    OPERATIONS: 0 — reden: {reden}")
        verboden = _check_verboden_keys(ops)
        totaal_verboden.extend(f"#{oid}: {v}" for v in verboden)
        print()

    print("=== E6-check: verboden keys (prijs/omschrijving) in operations ===")
    if totaal_verboden:
        for v in totaal_verboden:
            print("  FAIL:", v)
    else:
        print("  geen enkele operation bevat unitPrice/description — OK")


if __name__ == "__main__":
    asyncio.run(main())
