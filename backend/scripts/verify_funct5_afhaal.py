"""Verificatie Functie 5 — afhaal detecteren → verzendwijze (Shipment Method Code = EXW).

Verse output + MockNAV (trigger-emulatie). Geen echte #819-fixture beschikbaar, dus
een #819-achtige afhaalorder ("AFHAALORDER — klant haalt zelf op") + een gewone
verzendorder. Toont:
  - afhaalorder -> detect_verzendwijze=EXW -> compose-op shipmentMethodCode=EXW
    (single-field) -> na mock-push staat order['shipmentMethodCode'] == 'EXW';
  - verzendorder -> geen detectie, geen op, geen shipmentMethodCode op de order.

Read-only t.o.v. prod: temp-sqlite + NAVISION_MODE=mock + lege ADMIN_PASSWORD.

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct5_afhaal.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'verify_funct5.db'}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from kwabo.integrations.nav_operations import _assert_op_invariants  # noqa: E402
from kwabo.integrations.navision_api import MockNavisionClient  # noqa: E402
from kwabo.integrations.navision_steps import compose_navision_operations  # noqa: E402
from kwabo.utils.verzendwijze import detect_verzendwijze  # noqa: E402


def _mock() -> MockNavisionClient:
    m = MockNavisionClient(out_dir=Path(tempfile.mkdtemp()))
    m.items.append({"number": "9001", "displayName": "Testartikel",
                    "baseUnitOfMeasureCode": "STUK", "salesUnitOfMeasure": "STUK",
                    "mixprijzen": False})
    m.item_uoms["9001"] = [{"code": "STUK"}]
    return m


def _state(afleverinstructies: str) -> dict:
    return {
        "email_id": "verify-f5",
        "email_subject": "Bestelling 12345",
        "klant_match": {"navision_klantnr": "10001", "klantnaam": "Testklant"},
        "afleverinstructies": afleverinstructies,
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "9001",
                         "hoeveelheid": 2, "eenheid": "STUK"}],
    }


async def _push(mock: MockNavisionClient, ops: list) -> dict:
    await mock.create_sales_order_stepwise(ops)
    return next(iter(mock._orders.values()))


async def _scenario(naam: str, afleverinstructies: str, verwacht_exw: bool) -> bool:
    st = _state(afleverinstructies)
    vw = detect_verzendwijze(st)
    if vw:
        st["verzendwijze"] = vw
    ops = compose_navision_operations(st)
    for i, op in enumerate(ops):
        _assert_op_invariants(i, op)
    method_ops = [o for o in ops if o.get("body", {}).get("shipmentMethodCode")]
    order = await _push(_mock(), ops)
    gezet = order.get("shipmentMethodCode")
    print(f"{naam}:")
    print(f"   afleverinstructies = {afleverinstructies!r}")
    print(f"   detect_verzendwijze = {vw!r}")
    print(f"   compose shipmentMethodCode-PATCHes = {[o['body'] for o in method_ops]}")
    print(f"   mock-order shipmentMethodCode = {gezet!r}")
    ok = (gezet == "EXW") if verwacht_exw else (gezet is None and not method_ops)
    print(f"   -> {'[OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def main() -> int:
    a = await _scenario("A. Afhaalorder (#819-achtig)",
                        "AFHAALORDER — klant haalt zelf op", True)
    b = await _scenario("B. Gewone verzendorder",
                        "Graag bezorgen op het afleveradres", False)
    print("RESULTAAT:", "ALLES GROEN [OK]" if (a and b) else "ONVERWACHT")
    return 0 if (a and b) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
