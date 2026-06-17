"""Verificatie Functie 6 — artikel-keuze valideren tegen de prijslijst.

Verse output (temp-sqlite, geen prod). Toont:
  A. #816-achtig: klant geeft 23853 (geen prijs), 238531 heeft wél een prijs via
     kruisverwijzing -> regel GEVLAGD + alternatief 238531 + reden; matched NIET
     blind gewisseld.
  B. Artikel mét prijsafspraak -> ongewijzigd (geen valse correctie).
  C. Bewijs dat de tool nergens zelf een prijs naar NAV stuurt: de composer
     (navision_steps.py) emit géén prijsveld; de enige unitPrice-schrijfacties
     staan in navision_api.py (MockNavisionClient, die NAV emuleert). Het script
     leest beide bestanden en bevestigt dit.

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct6_prijs.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'verify_funct6.db'}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from sqlmodel import Session  # noqa: E402

from kwabo.db.models import ArtikelKruisverwijzing, Prijsafspraak  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.nodes import validate_prices as vp  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "kwabo"


def _seed() -> None:
    init_db()
    with Session(engine) as s:
        s.add(Prijsafspraak(klant_nr="K9", kwabo_artikelnr="238531", prijs=24.8))
        s.add(Prijsafspraak(klant_nr="K9", kwabo_artikelnr="999999", prijs=10.0))
        s.add(ArtikelKruisverwijzing(klant_nr="K9", klant_artikelnr="SKU-816",
                                     kwabo_artikelnr="238531"))
        s.commit()


def _state(matched: str, sku: str, prijs=None) -> dict:
    return {
        "email_id": "verify-f6",
        "klant_match": {"navision_klantnr": "K9"},
        "orderregels": [{"positie": 1, "artikelnummer_klant": sku,
                         "artikelnummer_kwabo_matched": matched, "hoeveelheid": 10.0,
                         "eenheid": "STUK", "prijs_per_eenheid": prijs}],
        "needs_review_fields": [],
    }


async def _deel_a() -> bool:
    out = await vp.validate_prices_node(_state("23853", "SKU-816"))
    r = out["orderregels"][0]
    alt = (r.get("artikel_prijs_alternatief") or {}).get("kwabo")
    gevlagd = "orderregels[0].artikelnummer_kwabo_matched" in out["needs_review_fields"]
    reden = next((w for w in out["validatie_warnings"] if "ARTIKEL ONZEKER" in w), None)
    print("A. #816 — 23853 (geen prijs), alternatief 238531 (wel prijs)")
    print(f"   matched (ongewijzigd) = {r['artikelnummer_kwabo_matched']}")
    print(f"   alternatief           = {alt}")
    print(f"   gevlagd (review)      = {gevlagd}")
    print(f"   reden                 = {reden}")
    ok = r["artikelnummer_kwabo_matched"] == "23853" and alt == "238531" and gevlagd
    print(f"   -> {'[OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def _deel_b() -> bool:
    out = await vp.validate_prices_node(_state("999999", "SKU-816"))
    r = out["orderregels"][0]
    onzeker = any("ARTIKEL ONZEKER" in w for w in out["validatie_warnings"])
    print("B. Artikel mét prijsafspraak (999999)")
    print(f"   alternatief = {r.get('artikel_prijs_alternatief')}  onzeker-vlag = {onzeker}")
    ok = r.get("artikel_prijs_alternatief") is None and not onzeker
    print(f"   -> {'[OK]' if ok else 'ONVERWACHT'}\n")
    return ok


def _deel_c() -> bool:
    steps = (SRC / "integrations" / "navision_steps.py").read_text("utf-8")
    api = (SRC / "integrations" / "navision_api.py").read_text("utf-8")
    steps_price = [ln for ln in steps.splitlines()
                   if re.search(r"unitPrice|Unit_Price", ln) and "body" in ln.lower()]
    api_price = len(re.findall(r"unitPrice", api))
    print("C. Bewijs: stuurt de tool ooit zelf een prijs naar NAV?")
    print(f"   composer (navision_steps) body-prijsvelden = {steps_price}")
    print(f"   MockNAV (navision_api) unitPrice-treffers   = {api_price} (NAV-emulatie)")
    ok = not steps_price and api_price > 0
    print(f"   -> {'composer prijst nooit; alleen MockNAV emuleert NAV [OK]' if ok else 'ONVERWACHT'}\n")
    return ok


async def main() -> int:
    _seed()
    a = await _deel_a()
    b = await _deel_b()
    c = _deel_c()
    print("RESULTAAT:", "ALLES GROEN [OK]" if (a and b and c) else "ONVERWACHT")
    return 0 if (a and b and c) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
