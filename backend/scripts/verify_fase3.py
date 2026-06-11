"""Eindverificatie Fase 3 (grondwet 4): eenheidscode & aantal op het echte #716.

Laadt de geëxporteerde prod-state van order 716 (Würth, 66 × artikel 238601)
plus de échte ArtikelEenheid-rijen, en toont:
  1. WAS: wat er destijds echt naar NAV ging (quantity 66 zonder UoM-PATCH) en
     wat NAV ervan maakte (66 × PALLET33 = €45.738 — de factor-33-fout).
  2. NU (Branch A): apply_mixprijzen kiest PALLET33 + aantal 2; compose emit
     beide expliciet; compute_europallet voegt de europallet-regel toe.
  3. Mock-push: de regel staat op 2 × PALLET33; een geforceerde ongeldige
     code (ROL) krijgt een 400, zoals echt NAV.
  4. Mix-tak: zelfde regel bij een mix-klant -> M2PAL33; staffel 23685
     (1/8/12 pallets -> M1/M7/M10PAL30).

Usage (vanuit backend/): python scripts/verify_fase3.py
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
_tmpdb = Path(tempfile.mkdtemp()) / "verify_fase3.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"
os.environ["NAVISION_MODE"] = "mock"

from sqlmodel import Session, SQLModel  # noqa: E402

from kwabo.db.models import Artikelkaart, ArtikelEenheid, Klantenkaart  # noqa: E402
from kwabo.db.session import engine  # noqa: E402
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node  # noqa: E402
from kwabo.graph.nodes.compute_europallet import compute_europallet_node  # noqa: E402
from kwabo.integrations.navision_api import MockNavisionClient  # noqa: E402
from kwabo.integrations.navision_steps import _emit_line_ops  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"


def seed(mix_klant: bool) -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    ae = json.loads((STATES / "artikel_eenheden.json").read_text(encoding="utf-8"))
    with Session(engine) as s:
        # verkoop_eenheid PALLET33: bron = NAV's eigen line-POST-response in de
        # echte order #716 (unitOfMeasureCode=PALLET33, Qty_per_UoM=33).
        s.add(Artikelkaart(kwabo_artikelnr="238601",
                           naam="Quality Covers Top coat Heavy-duty 25m2 67cm",
                           basis_eenheid="STUK", verkoop_eenheid="PALLET33"))
        s.add(Artikelkaart(kwabo_artikelnr="23685", naam="Stucloper 30/pallet",
                           basis_eenheid="STUK", verkoop_eenheid="PALLET"))
        s.add(Klantenkaart(nav_klantnr="61030", naam="Würth Nederland B.V.",
                           email="Richard.verhagen@wurth.nl", mixprijzen=mix_klant))
        for r in ae:
            if r["kwabo_artikelnr"] in ("238601", "23685"):
                s.add(ArtikelEenheid(**r))
        s.commit()


def _line_ops_str(regel: dict) -> str:
    ops = _emit_line_ops(regel, regel["artikelnummer_kwabo_matched"], "regel")
    return "  +  ".join(f"{o['op']} {o['body']}" for o in ops)


async def main() -> None:
    env = json.loads(next(iter(STATES.glob("order_716*"))).read_text(encoding="utf-8"))
    st_oud = env["order_state"]
    regel_oud = st_oud["orderregels"][0]

    print("=== #716 Würth — WAS (echte prod-push) ===")
    for op in st_oud.get("nav_operations") or []:
        b = op.get("body") or {}
        if any(k in b for k in ("itemNumber", "unitOfMeasureCode", "quantity")):
            print(f"  {op['op']} {b}")
    for res in st_oud.get("nav_operation_results") or []:
        rb = res.get("response_body") or {}
        if (res.get("operation") or {}).get("body", {}).get("quantity") is not None:
            print(f"  -> NAV-regel werd: {rb.get('quantity')} x "
                  f"{rb.get('unitOfMeasureCode')} à €{rb.get('Unit_Price')} = "
                  f"€{rb.get('Line_Amount')}  (gewenst: 2 x PALLET33 = €1386)")
    print(f"  europallet_regel was: {st_oud.get('europallet_regel')!r}\n")

    # --- NU: Branch A (Würth is géén mix-klant; prod-export mixprijzen=False)
    seed(mix_klant=False)
    state = {
        "email_id": "verify-716",
        "klant_match": {"navision_klantnr": "61030"},
        "orderregels": [{**regel_oud,
                         "mix_uom_gekozen": None, "mix_aantal": None}],
        "needs_review_fields": [],
    }
    uit = await apply_mixprijzen_node(state)
    uit = await compute_europallet_node(uit)
    r = uit["orderregels"][0]
    print("=== NU — Branch A (E1/E2) ===")
    print(f"  verkoop_uom_gekozen={r.get('verkoop_uom_gekozen')!r}  "
          f"verkoop_aantal={r.get('verkoop_aantal')!r}  (besteld: "
          f"{regel_oud['hoeveelheid']} {regel_oud.get('eenheid')})")
    print(f"  compose:  {_line_ops_str(r)}")
    ep = uit.get("europallet_regel")
    print(f"  europallet (E4): {ep and f'{ep['hoeveelheid']} x {ep['artikelnummer_kwabo_matched']}'}\n")

    # --- Mock-push: eerlijke NAV-emulatie (default = sales UoM; 400 op fout)
    mock = MockNavisionClient(out_dir=Path(tempfile.mkdtemp()))
    kop = [{"op": "POST", "path": "/salesOrders",
            "body": {"customerNumber": "10001"}, "label": "header"}]
    ops = kop + _emit_line_ops(r, "238601", "regel")
    res = await mock.create_sales_order_stepwise(ops)
    line = next(iter(mock._orders.values()))["lines"][0]
    print("=== Mock-push (trigger-emulatie) ===")
    print(f"  regelstand na push: {line['quantity']} x {line['unitOfMeasureCode']}")
    fout = await mock.create_sales_order_stepwise(
        kop + [{"op": "POST", "path": "/salesOrders({id})/salesOrderLines",
                "body": {"lineType": "Item", "itemNumber": "238601"}, "label": "l"},
               {"op": "PATCH", "path": "/salesOrderLines({id})",
                "body": {"unitOfMeasureCode": "ROL"}, "label": "uom"}])
    laatste = fout["operation_results"][-1]
    print(f"  geforceerde ROL-PATCH (E3): status={laatste['status']}  "
          f"error={laatste.get('error')!r}\n")

    # --- Mix-tak (M2/M4): zelfde regel bij een mix-klant + staffel 23685
    seed(mix_klant=True)
    uit2 = await apply_mixprijzen_node(json.loads(json.dumps(state)))
    r2 = uit2["orderregels"][0]
    print("=== Mix-tak (M1-M4) — zelfde regel, klant mét mixvlag ===")
    print(f"  238601 (families PAL33/35/42, verkoopeenheid kiest 33): "
          f"mix_uom_gekozen={r2.get('mix_uom_gekozen')!r} mix_aantal={r2.get('mix_aantal')!r}")
    for pallets in (1, 8, 12):
        st = {"email_id": "verify-23685",
              "klant_match": {"navision_klantnr": "61030"},
              "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "23685",
                               "hoeveelheid": pallets * 30.0, "eenheid": "STUK",
                               "eenheid_origineel": "STUK"}],
              "needs_review_fields": []}
        u = await apply_mixprijzen_node(st)
        print(f"  23685 {pallets:>2} pallets ({pallets*30} stuks) -> "
              f"{u['orderregels'][0].get('mix_uom_gekozen')}")


if __name__ == "__main__":
    asyncio.run(main())
