"""Verificatie Functie 3 — eenheid + aantal correct (pallet-bestelling).

Verse output met ECHTE UoM-rijen (artikel_eenheden.json) + MockNAV-trigger-
emulatie (een nieuwe regel default naar de verkoopeenheid; een ongeldige UoM ->
HTTP 400). Toont:

  A. #819 — 4 Paletten van 23691 (PALLET, qty_per_base 20): de hele pijplijn
     (match_articles -> apply_mixprijzen -> compose -> mock-push) levert
     PALLET + quantity 4, NIET 4 STUK.
  B. Lasaulec — handmatig 15620 (verkoop_eenheid PALLET, qty_per_base 30) via het
     patch-field-endpoint: 60 STUK -> 2 PALLET (Branch A herberekend).
  C. Ongeldige eenheid (ROL) op 23691 -> terugval op base + review-vlag, en een
     geforceerde ROL-PATCH naar NAV wordt geweigerd (400).

Read-only t.o.v. prod: temp-sqlite + NAVISION_MODE=mock + lege ADMIN_PASSWORD,
vóór de imports.

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct3_eenheid.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "verify_funct3.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from kwabo.db import session as db_session  # noqa: E402
from kwabo.db.models import Artikelkaart, ArtikelEenheid  # noqa: E402
from kwabo.db.repository import OrderLogRepo  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node  # noqa: E402
from kwabo.graph.nodes.match_articles import match_articles_node  # noqa: E402
from kwabo.integrations.navision_api import MockNavisionClient  # noqa: E402
from kwabo.integrations.navision_steps import _emit_line_ops  # noqa: E402
from kwabo.main import create_app  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

ARTIKELEN = [
    # (kwabo_artikelnr, naam, basis_eenheid, verkoop_eenheid)
    ("23691", "Stucloper 20/pallet", "STUK", "PALLET"),
    ("15620", "Afdekvlies 30/pallet", "STUK", "PALLET"),
]


def _seed() -> None:
    init_db()
    ae = json.loads((STATES / "artikel_eenheden.json").read_text("utf-8"))
    with Session(engine) as s:
        for nr, naam, base, verkoop in ARTIKELEN:
            s.add(Artikelkaart(kwabo_artikelnr=nr, naam=naam,
                               basis_eenheid=base, verkoop_eenheid=verkoop))
        for r in ae:
            if r["kwabo_artikelnr"] in {nr for nr, *_ in ARTIKELEN}:
                s.add(ArtikelEenheid(**r))
        s.commit()


def _mock() -> MockNavisionClient:
    """MockNAV met de artikelen + hun echte item-UoM-codes geregistreerd, zodat
    de trigger-emulatie (default sales-UoM; 400 op ongeldige UoM) klopt."""
    from kwabo.db.repository import ArtikelkaartRepo

    mock = MockNavisionClient(out_dir=Path(tempfile.mkdtemp()))
    with Session(engine) as s:
        repo = ArtikelkaartRepo(s)
        for nr, naam, base, verkoop in ARTIKELEN:
            mock.items.append({"number": nr, "displayName": naam,
                               "baseUnitOfMeasureCode": base,
                               "salesUnitOfMeasure": verkoop, "mixprijzen": False})
            mock.item_uoms[nr] = [{"code": e.eenheid_code}
                                  for e in repo.list_eenheden(nr)]
    return mock


async def _line_after_push(mock: MockNavisionClient, regel: dict, artnr: str) -> dict:
    kop = [{"op": "POST", "path": "/salesOrders",
            "body": {"customerNumber": "10001"}, "label": "header"}]
    await mock.create_sales_order_stepwise(kop + _emit_line_ops(regel, artnr, "regel"))
    return next(iter(mock._orders.values()))["lines"][-1]


async def deel_a(mock: MockNavisionClient) -> bool:
    state = {
        "email_id": "verify-819",
        "klant_match": {"navision_klantnr": "10001"},
        "stappen_log": [],
        "orderregels": [{"positie": 1, "artikelnummer_kwabo": "23691",
                         "eenheid": "PAL", "hoeveelheid": 4}],
    }
    uit = await match_articles_node(state)
    uit = await apply_mixprijzen_node(uit)
    r = uit["orderregels"][0]
    vlag = "orderregels[0].eenheid" in (uit.get("needs_review_fields") or [])
    ops = _emit_line_ops(r, r["artikelnummer_kwabo_matched"], "regel")
    bodies = [o["body"] for o in ops]
    line = await _line_after_push(mock, r, "23691")
    print("A. #819 — 4 Paletten van 23691 (PALLET, qty_per_base 20)")
    print(f"   eenheid (na match)   = {r['eenheid']!r}  (origineel {r.get('eenheid_origineel')!r}); review-vlag={vlag}")
    print(f"   compose-bodies       = {bodies}")
    print(f"   mock-push regelstand = {line['quantity']} x {line['unitOfMeasureCode']}")
    ok = (r["eenheid"] == "PALLET" and not vlag
          and {"unitOfMeasureCode": "PALLET"} in bodies and {"quantity": 4} in bodies
          and line["unitOfMeasureCode"] == "PALLET" and line["quantity"] == 4)
    print(f"   -> {'PALLET x4 [OK]' if ok else 'ONVERWACHT'}\n")
    return ok


def deel_b() -> bool:
    state = {
        "email_id": "verify-lasaulec",
        "klant_match": {"navision_klantnr": "61745", "klantnaam": "Lasaulec B.V."},
        "orderregels": [{"positie": 1, "artikelnummer_klant": "LAS-99",
                         "artikelnummer_kwabo": None, "artikelnummer_kwabo_matched": None,
                         "omschrijving": "Afdekvlies pallet", "hoeveelheid": 60,
                         "eenheid": "STUK", "match_methode": "manual",
                         "match_confidence": 0.0}],
        "needs_review_fields": ["orderregels[0].artikelnummer_kwabo_matched"],
        "stappen_log": [],
    }
    with Session(engine) as s:
        oid = OrderLogRepo(s).create(email_id=state["email_id"],
                                     order_state=json.dumps(state)).id

    db_session.engine = engine
    app = create_app()
    with TestClient(app) as client:
        r = client.patch(f"/api/orders/{oid}/patch-field",
                         json={"path": "orderregels[0].artikelnummer_kwabo_matched",
                               "value": "15620"})
        assert r.status_code == 200, r.text
    with Session(engine) as s:
        regel = json.loads(OrderLogRepo(s).get(oid).order_state)["orderregels"][0]
    ops = _emit_line_ops(regel, "15620", "regel")
    bodies = [o["body"] for o in ops]
    print("B. Lasaulec — handmatig 15620 (verkoop_eenheid PALLET, qty_per_base 30)")
    print(f"   was: 60 STUK, leeg aantal -> verkoop_uom_gekozen={regel.get('verkoop_uom_gekozen')!r}, verkoop_aantal={regel.get('verkoop_aantal')!r}")
    print(f"   compose-bodies = {bodies}")
    ok = (regel.get("verkoop_uom_gekozen") == "PALLET" and regel.get("verkoop_aantal") == 2
          and {"unitOfMeasureCode": "PALLET"} in bodies and {"quantity": 2} in bodies)
    print(f"   -> {'PALLET x2 [OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def deel_c(mock: MockNavisionClient) -> bool:
    state = {
        "email_id": "verify-rol",
        "klant_match": {"navision_klantnr": "10001"},
        "stappen_log": [],
        "orderregels": [{"positie": 1, "artikelnummer_kwabo": "23691",
                         "eenheid": "ROL", "hoeveelheid": 4}],
    }
    uit = await match_articles_node(state)
    r = uit["orderregels"][0]
    vlag = "orderregels[0].eenheid" in (uit.get("needs_review_fields") or [])
    kop = [{"op": "POST", "path": "/salesOrders", "body": {"customerNumber": "10001"}, "label": "h"}]
    fout = await mock.create_sales_order_stepwise(
        kop + [{"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
                "body": {"lineType": "Item", "itemNumber": "23691"}, "label": "l"},
               {"op": "PATCH", "path": "/salesOrderLines({id})",
                "body": {"unitOfMeasureCode": "ROL"}, "label": "uom"}])
    status = fout["operation_results"][-1]["status"]
    print("C. Ongeldige eenheid ROL op 23691")
    print(f"   match_articles eenheid = {r['eenheid']!r} (terugval base), review-vlag={vlag}")
    print(f"   geforceerde ROL-PATCH naar NAV: status={status}")
    ok = r["eenheid"] == "STUK" and vlag and status == 400
    print(f"   -> {'terugval + vlag + 400 [OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def main() -> int:
    _seed()
    mock = _mock()
    a = await deel_a(mock)
    b = deel_b()
    c = await deel_c(_mock())
    print("RESULTAAT:", "ALLES GROEN [OK]" if (a and b and c) else "ZIE ONVERWACHT HIERBOVEN")
    return 0 if (a and b and c) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
