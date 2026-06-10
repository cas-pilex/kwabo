"""Eindverificatie Fase 2 (grondwet 4): echte faalorders door de nieuwe matching.

Laadt de geëxporteerde prod-states + echte masterdata (klantenkaarten,
artikelkaarten) in een wegwerp-sqlite, draait match_customer_node en
match_articles_node opnieuw, en print per order een before/after-tabel.

Het naam-signaal (klantnaam_besteller) bestaat nog niet in de oude states;
we geven mee wat letterlijk in het orderdocument/onderwerp staat — de
LLM-extractieverificatie daarvan is een aparte stap (vereist API-key).

Usage (vanuit backend/): python scripts/verify_fase2.py
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
_tmpdb = Path(tempfile.mkdtemp()) / "verify_fase2.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"
os.environ["NAVISION_MODE"] = "mock"

from sqlmodel import SQLModel, Session  # noqa: E402

from kwabo.db.models import Artikelkaart, Klantenkaart  # noqa: E402
from kwabo.db.session import engine  # noqa: E402
from kwabo.graph.nodes.match_articles import match_articles_node  # noqa: E402
from kwabo.graph.nodes.match_customer import match_customer_node  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

# (fixture-prefix, naam-signaal zoals letterlijk in document/onderwerp staat)
ORDERS = [
    ("order_706", None),                            # PPG — klant matchte al via e-mail
    ("order_707", "GBI Borne"),                     # zevij-portaal
    ("order_717", None),                            # Kuipers — klant matchte al via e-mail
    ("order_718", "Witzand Bouwmaterialen B.V."),
    ("order_721", "Van Dongen Verf BV"),
    ("order_635", "TABS Holland"),                  # pontmeyer-agent
    ("order_550", "Jongeneel"),                     # franchise → kandidaten verwacht
]


def seed_echte_masterdata() -> None:
    SQLModel.metadata.create_all(engine)
    kk = json.loads((STATES / "klantenkaarten.json").read_text(encoding="utf-8"))
    ak = json.loads((STATES / "artikelkaarten.json").read_text(encoding="utf-8"))
    with Session(engine) as s:
        for r in kk:
            s.add(Klantenkaart(nav_klantnr=r["nav_klantnr"], naam=r["naam"] or "",
                               email=r.get("email"), email_bestelling=r.get("email_bestelling")))
        for r in ak:
            s.add(Artikelkaart(kwabo_artikelnr=r["kwabo_artikelnr"], naam=r["naam"] or "",
                               basis_eenheid=r["basis_eenheid"] or "STUK"))
        s.commit()
    print(f"masterdata geladen: {len(kk)} klantenkaarten, {len(ak)} artikelkaarten\n")


def _laad(prefix: str) -> dict:
    f = next(iter(sorted(STATES.glob(f"{prefix}*"))), None)
    if not f:
        raise SystemExit(f"fixture {prefix}* ontbreekt")
    return json.loads(f.read_text(encoding="utf-8"))


async def main() -> None:
    seed_echte_masterdata()
    for prefix, naam_signaal in ORDERS:
        env = _laad(prefix)
        st_oud = env["order_state"]
        km_oud = st_oud.get("klant_match") or {}

        # Verse input-state: matching-velden gereset, naam-signaal toegevoegd.
        st = {
            "email_id": f"verify-{env['order_id']}",
            "email_from": env["email_from"],
            "email_subject": env["email_subject"],
            "email_body": st_oud.get("email_body") or "",
            "bijlagen": st_oud.get("bijlagen") or [],
            "stappen_log": [],
            "klantnaam_besteller": naam_signaal,
            "afleveradres": st_oud.get("afleveradres"),
            "orderregels": [],
        }
        for r in st_oud.get("orderregels") or []:
            r2 = dict(r)
            r2["artikelnummer_kwabo_matched"] = None
            r2["match_methode"] = None
            r2["match_confidence"] = None
            st["orderregels"].append(r2)

        uit = await match_customer_node(st)
        uit = await match_articles_node(uit)

        km = uit.get("klant_match") or {}
        kand = uit.get("klant_kandidaten") or []
        kmeta = (uit.get("_meta") or {}).get("klant_match") or {}
        print(f"=== #{env['order_id']}  {env['email_subject'][:58]!r}")
        print(f"    van: {env['email_from'][:60]!r}  naam-signaal: {naam_signaal!r}")
        print(f"    KLANT  was: {km_oud.get('navision_klantnr')!r} "
              f"({km_oud.get('match_bron')}, conf {km_oud.get('match_confidence')})")
        print(f"           nu:  {km.get('navision_klantnr')!r} "
              f"({km.get('match_bron')}, conf {km.get('match_confidence')})"
              + (f"  kandidaten: {[(k['navision_klantnr'], k['klantnaam']) for k in kand]}"
                 if kand else ""))
        if km:
            vlag = ("CONTROLEER — operator bevestigt vóór approve"
                    if kmeta.get("needs_review") else "geen (vertrouwd)")
            print(f"           vlag: {vlag}  detail: {kmeta.get('source_detail')!r}")
        for i, (r_oud, r_nieuw) in enumerate(
            zip(st_oud.get("orderregels") or [], uit.get("orderregels") or [])
        ):
            print(f"    REGEL {i}  {(r_oud.get('omschrijving') or '')[:48]!r}")
            print(f"           was: {r_oud.get('artikelnummer_kwabo_matched')!r} "
                  f"({r_oud.get('match_methode')}, conf {r_oud.get('match_confidence')})")
            print(f"           nu:  {r_nieuw.get('artikelnummer_kwabo_matched')!r} "
                  f"({r_nieuw.get('match_methode')}, conf {r_nieuw.get('match_confidence')})")
        print()


if __name__ == "__main__":
    asyncio.run(main())
