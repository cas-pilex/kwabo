"""Verificatie Functie 1 (klant-matching) op de ECHTE faalorders.

Draait de geëxporteerde order_states van #832/#833/#834 (TABS/PontMeyer) door de
NIEUWE match_customer_node en toont dat de vestiging-correctie op het leveradres
de confidente-foute e-mailmatch (altijd Heerenveen 61793) corrigeert naar de
juiste vestiging — i.p.v. zelfverzekerd fout.

Read-only t.o.v. prod: gebruikt een wegwerp-sqlite (verify_fase2-patroon). De
PontMeyer-vestigingskaarten worden geseed met hun ECHTE klantnr + plaats +
postcode (de stand ná de customers-sync die City/Post_Code vult). 61793 draagt
de agent-mail supplychain@tabsholland.nl, precies zoals in prod.

Usage (vanuit backend/):
    python scripts/verify_funct1_klant.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Wegwerp-sqlite vóór élke kwabo-import (nooit bij prod kunnen).
_tmp = Path(tempfile.mkdtemp()) / "verify_funct1.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.models import Klantenkaart  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.nodes.match_customer import match_customer_node  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

# Echte PontMeyer-vestigingen (klantnr + adres = stand ná customers-sync).
VESTIGINGEN = [
    ("61793", "PontMeyer Heerenveen", "supplychain@tabsholland.nl;heerenveen@pontmeyer.nl", "Heerenveen", "8441 PW"),
    ("61088", "PontMeyer Zwaag", "zwaag@pontmeyer.nl", "Zwaag", "1689 AK"),
    ("61468", "Pontmeyer Zoetermeer", "zoetermeer@pontmeyer.nl", "Zoetermeer", "2718 TB"),
    ("61019", "PontMeyer Heemstede", "heemstede@pontmeyer.nl", "Heemstede", "2102 LL"),
]

ORDERS = [
    ("order_832", "61468", "Zoetermeer"),
    ("order_833", "61019", "Heemstede"),
    ("order_834", "61088", "Zwaag"),
]


def _seed() -> None:
    init_db()
    with Session(engine) as s:
        for nr, naam, email, plaats, postcode in VESTIGINGEN:
            s.add(Klantenkaart(nav_klantnr=nr, naam=naam, email=email,
                               plaats=plaats, postcode=postcode))
        s.commit()


def _load(prefix: str) -> dict:
    f = next(STATES.glob(f"{prefix}*.json"))
    return json.loads(f.read_text(encoding="utf-8"))


async def main() -> int:
    _seed()
    print(f"{'order':<10} {'oud (prod)':<26} {'nieuw':<26} {'verwacht':<12} ok?")
    print("-" * 90)
    ok = True
    for prefix, verwacht_nr, verwacht_plaats in ORDERS:
        env = _load(prefix)
        st = dict(env["order_state"])
        oud = (st.get("klant_match") or {}).get("navision_klantnr")
        oud_naam = (st.get("klant_match") or {}).get("klantnaam")
        # Reset de klant-velden zodat de node vers matcht (de export bevat de
        # oude uitkomst).
        st["klant_match"] = None
        st["klant_kandidaten"] = []
        st.setdefault("email_from", env.get("email_from"))
        st.setdefault("email_subject", env.get("email_subject"))
        out = await match_customer_node(st)
        km = out.get("klant_match") or {}
        nieuw = km.get("navision_klantnr")
        regel_ok = nieuw == verwacht_nr
        ok = ok and regel_ok
        oud_txt = f"{oud} {oud_naam}"[:25]
        nieuw_txt = f"{nieuw} {km.get('klantnaam')}"[:25]
        verwacht_txt = f"{verwacht_nr} {verwacht_plaats}"
        controleer = "klant_match" in (out.get("needs_review_fields") or [])
        print(f"{prefix:<10} {oud_txt:<26} {nieuw_txt:<26} {verwacht_txt:<12} {'JA' if regel_ok else 'NEE'}")
        print(f"           reden: {km.get('match_uitleg') or km.get('match_bron')} "
              f"(conf {km.get('match_confidence')}, CONTROLEER={controleer})")
    print("-" * 90)
    print("RESULTAAT:", "ALLE 3 GECORRIGEERD [OK]" if ok else "FOUT - niet alle orders gecorrigeerd")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
