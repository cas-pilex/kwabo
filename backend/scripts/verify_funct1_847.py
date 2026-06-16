"""Verificatie Functie 1 — #847 (Streckenbestellung Werkzeuge Dietrich / se Huber).

Toont met VERSE output wat de AUTOMATISCHE match_customer_node doet met de echte
geexporteerde state van #847: de afzender/Rechnungsempfanger Werkzeuge Dietrich
(60103) wordt via naam_extract gematcht met CONTROLEER-vlag; se Huber (61532, het
LEVERADRES) is in prod alleen via een handmatige dashboard-override gezet. De
Strecken-regel "leveradres-partij = klant" (DEEL B) is bewust uitgesteld.

Read-only t.o.v. prod: wegwerp-sqlite + mock-NAV (verify_fase2-patroon).

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct1_847.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "verify_funct1_847.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.models import Klantenkaart  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.nodes.match_customer import match_customer_node  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

# Beide partijen als klantenkaart: de besteller/Rechnungsempfanger Dietrich (60103)
# en de leveradres-partij se Huber (61532). Geen van beide draagt de afzendermail,
# zodat de matcher op de naam terugvalt (zoals in prod).
VESTIGINGEN = [
    ("60103", "Werkzeuge Dietrich GmbH & Co KG", "", "Burgdorf", "31303"),
    ("61532", "se Huber Straubing GmbH & Co KG", "", "Straubing", "94315"),
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
    env = _load("order_847")
    st = dict(env["order_state"])
    opgeslagen = st.get("klant_match") or {}
    print("OPGESLAGEN state (na handmatige correctie in prod):")
    print(f"  klant_match = {opgeslagen.get('navision_klantnr')} "
          f"{opgeslagen.get('klantnaam')} "
          f"(bron={opgeslagen.get('match_bron')}, conf={opgeslagen.get('match_confidence')})")
    print()
    # Reset zodat de node vers matcht.
    st["klant_match"] = None
    st["klant_kandidaten"] = []
    st.setdefault("email_from", env.get("email_from"))
    st.setdefault("email_subject", env.get("email_subject"))
    out = await match_customer_node(st)
    km = out.get("klant_match") or {}
    kand = out.get("klant_kandidaten") or []
    controleer = "klant_match" in (out.get("needs_review_fields") or [])
    print("AUTOMATISCHE match (verse run van match_customer_node):")
    print(f"  navision_klantnr = {km.get('navision_klantnr')}")
    print(f"  klantnaam        = {km.get('klantnaam')}")
    print(f"  match_bron       = {km.get('match_bron')}")
    print(f"  match_confidence = {km.get('match_confidence')}")
    print(f"  CONTROLEER       = {controleer}")
    print(f"  reden            = {km.get('match_uitleg') or km.get('match_bron')}")
    print(f"  kandidaten       = {[(k.get('navision_klantnr'), k.get('klantnaam')) for k in kand]}")
    print(f"  afleveradres     = {(st.get('afleveradres') or {}).get('naam')} "
          f"{(st.get('afleveradres') or {}).get('plaats')}")
    print()
    auto_nr = km.get("navision_klantnr")
    ok = auto_nr == "60103" and controleer
    print("DUIDING: automatisch = afzender/Rechnungsempfanger Dietrich (60103) + CONTROLEER.")
    print("         se Huber 61532 was handmatige override; Strecken-regel DEEL B uitgesteld.")
    print("RESULTAAT:", "EERLIJK-ONZEKER [OK]" if ok else f"ONVERWACHT ({auto_nr}, CONTROLEER={controleer})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
