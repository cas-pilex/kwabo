"""Verificatie Functie 2 — #847: ship-to volgt de juiste klant.

Toont met VERSE output dat een handmatige klant-wijziging (afzender Werkzeuge
Dietrich 60103 → leveradres-partij se Huber 61532) het verzendadres herberekent
op het leveradres (Straubing, 94315) i.p.v. de stale 31303 (Burgdorf) van de
oude klant te laten staan.

Read-only t.o.v. prod: wegwerp-sqlite + mock-NAV + lege ADMIN_PASSWORD, vóór elke
import (verify_funct1_847-patroon). Draait de ECHTE geexporteerde state van #847
door het patch-field-endpoint via TestClient.

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct2_shipto.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "verify_funct2_shipto.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Windows-console (cp1252) verslikt zich anders in de → / ≥ glyphs hieronder.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover - oudere/rare stdout
    pass

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from kwabo.db import session as db_session  # noqa: E402
from kwabo.db.models import KlantenkaartShipTo  # noqa: E402
from kwabo.db.repository import OrderLogRepo  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.main import create_app  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

# De nieuwe-klant (se Huber 61532) ship-to-mirror: het Straubing-adres + 1 ruis-
# rij. In prod komt dit uit de master-sync (klantenkaart_ship_to); hier geseed
# omdat de geexporteerde #847-state alleen de ship-to's van de OUDE klant bevat.
SHIP_TO_61532 = [
    ("61532", "94315", "se Huber GmbH & Co KG", "Borsigstr. 15", "94315", "Straubing", "DE", True),
    ("61532", "80331", "se Huber Filiale", "Sendlinger Str. 1", "80331", "Muenchen", "DE", False),
]


def _seed_ship_to() -> None:
    init_db()
    with Session(engine) as s:
        for nr, code, naam, straat, pc, plaats, land, dflt in SHIP_TO_61532:
            s.add(KlantenkaartShipTo(klant_nr=nr, ship_to_code=code, naam=naam,
                                     straat=straat, postcode=pc, plaats=plaats,
                                     land=land, is_default=dflt))
        s.commit()


def _load_847() -> dict:
    f = next(STATES.glob("order_847*.json"))
    env = json.loads(f.read_text(encoding="utf-8"))
    return dict(env["order_state"])


def _maak_order(st: dict) -> int:
    with Session(engine) as s:
        row = OrderLogRepo(s).create(email_id="verify-f2-847",
                                     order_state=json.dumps(st, default=str))
        return row.id


def _read(client: TestClient, oid: int) -> dict:
    with Session(engine) as s:
        row = OrderLogRepo(s).get(oid)
        return json.loads(row.order_state or "{}")


def main() -> int:
    _seed_ship_to()

    # Begin met de ECHTE state, maar zet de klant terug op de OUDE (foute)
    # automatische match zodat we de handmatige correctie naar 61532 simuleren.
    st = _load_847()
    st["klant_match"] = {"navision_klantnr": "60103", "klantnaam": "Werkzeuge Dietrich GmbH & Co KG",
                         "match_bron": "naam_extract", "match_confidence": 0.8}
    oid = _maak_order(st)

    print("VOOR (automatische match = afzender, ship-to van de oude klant):")
    print(f"  klant_match      = {st['klant_match']['navision_klantnr']} {st['klant_match']['klantnaam']}")
    print(f"  ship_to_gekozen  = {st.get('ship_to_gekozen')}")
    kl_voor = {c.get('klant_nr') for c in (st.get('ship_to_kandidaten') or [])}
    print(f"  kandidaten klant = {kl_voor}")
    afl = st.get("afleveradres") or {}
    print(f"  leveradres       = {afl.get('naam')} {afl.get('plaats')} {afl.get('postcode')}")
    print()

    db_session.engine = engine
    app = create_app()
    with TestClient(app) as client:
        r = client.patch(f"/api/orders/{oid}/patch-field",
                         json={"path": "klant_match", "value": "61532"})
        assert r.status_code == 200, r.text
        needs = r.json().get("needs_review_fields") or []
        na = _read(client, oid)

    km = na.get("klant_match") or {}
    gekozen = na.get("ship_to_gekozen")
    kand = na.get("ship_to_kandidaten") or []
    kl_na = {c.get("klant_nr") for c in kand}
    chosen_rec = next((c for c in kand if c.get("ship_to_code") == gekozen), {})

    print("NA handmatige klant-wijziging → se Huber 61532 (verse patch-field-run):")
    print(f"  klant_match      = {km.get('navision_klantnr')} {km.get('klantnaam')}")
    print(f"  ship_to_gekozen  = {gekozen}  ({chosen_rec.get('naam')} {chosen_rec.get('plaats')} {chosen_rec.get('postcode')})")
    print(f"  kandidaten klant = {kl_na}")
    print(f"  needs_review     = {needs}")
    print()

    ok = (km.get("navision_klantnr") == "61532"
          and gekozen == "94315"
          and kl_na == {"61532"}
          and gekozen != "31303")
    print("DUIDING: ship-to volgt nu de gecorrigeerde klant en het leveradres "
          "(se Huber Straubing 94315), niet de stale 31303 (Burgdorf) van de oude klant.")
    print("RESULTAAT:", "GECORRIGEERD [OK]" if ok else f"ONVERWACHT (gekozen={gekozen}, klanten={kl_na})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
