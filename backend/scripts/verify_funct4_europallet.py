"""Verificatie Functie 4 — europallet deterministisch + verklaarbaar (artikel 19820).

Verse output op de ECHTE orders + UoM-rijen:

  #832 = 33 STUK 238601 (verkoop PALLET33=33) -> 1 europallet (opgeslagen stale: 2).
  #833 = 5 STUK 229231 (80) + 15 STUK 238531 (33) -> 0,06+0,45 = 0,51 -> 1 (was: niets).
  Regressie #707/#716: ongewijzigd (mijn wijziging vuurt alleen als verkoop_eenheid
  is gevuld; met de fixture-masterdata (verkoop_eenheid leeg) blijven ze None).

Read-only t.o.v. prod: temp-sqlite + NAVISION_MODE=mock + lege ADMIN_PASSWORD.

Usage (vanuit backend/):
    PYTHONPATH=".venv/Lib/site-packages" python scripts/verify_funct4_europallet.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "verify_funct4.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
os.environ["NAVISION_MODE"] = "mock"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

from sqlmodel import Session  # noqa: E402

from kwabo.db.models import Artikelkaart, ArtikelEenheid  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node  # noqa: E402
from kwabo.graph.nodes.compute_europallet import compute_europallet_node  # noqa: E402
from kwabo.graph.nodes.match_articles import match_articles_node  # noqa: E402
from kwabo.utils.pallet_logic import europallet_breakdown  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"
_AE = json.loads((STATES / "artikel_eenheden.json").read_text("utf-8"))

# Prod-complete verkoop_eenheid (Sales_Unit_of_Measure) per artikel.
VERKOOP = {"238601": "PALLET33", "238531": "PALLET33", "229231": "PALLET"}


def _seed() -> None:
    init_db()
    with Session(engine) as s:
        for nr, verkoop in VERKOOP.items():
            s.add(Artikelkaart(kwabo_artikelnr=nr, naam=f"art {nr}",
                               basis_eenheid="STUK", verkoop_eenheid=verkoop))
        for r in _AE:
            if r["kwabo_artikelnr"] in VERKOOP:
                s.add(ArtikelEenheid(**r))
        s.commit()


def _load(prefix: str) -> dict:
    f = next(STATES.glob(f"{prefix}*.json"))
    env = json.loads(f.read_text("utf-8"))
    return dict(env["order_state"])


async def _run_pipeline(order: str) -> dict:
    st = _load(order)
    # Reset de afgeleiden zodat de pijplijn vers telt.
    for r in st.get("orderregels") or []:
        for k in ("verkoop_uom_gekozen", "verkoop_aantal", "mix_uom_gekozen", "mix_aantal"):
            r.pop(k, None)
    st["europallet_regel"] = None
    out = await match_articles_node(st)
    out = await apply_mixprijzen_node(out)
    out = await compute_europallet_node(out)
    return out


def _print(order: str, stored, out: dict) -> int:
    meta = (out.get("_meta") or {}).get("europallet") or {}
    regel = out.get("europallet_regel")
    aantal = regel["hoeveelheid"] if regel else 0
    print(f"#{order}: opgeslagen={stored}  ->  NU={aantal}")
    print(f"   onderbouwing: {meta.get('uitleg')}")
    for r in meta.get("regels") or []:
        print(f"     - {r['artikelnr']}: {r['qty']} {r['eenheid']}"
              f"{(' ÷ %s/pallet' % r['pallet_maat']) if r['pallet_maat'] else ''}"
              f" = {r['pallets']} pallet ({r['bron']})")
    return aantal


class _Kaart:
    def __init__(self, v): self.verkoop_eenheid = v


class _NoKennis:
    def lookup(self, a, e): return None


class _FixtureRepo:
    """uom_repo met de echte UoM-rijen maar verkoop_eenheid LEEG (fixture-stand)."""
    def list_eenheden(self, nr):
        rows = [r for r in _AE if r["kwabo_artikelnr"] == nr]
        return [type("E", (), {"eenheid_code": r["eenheid_code"],
                               "qty_per_base": r["qty_per_base"],
                               "is_mix_uom": r.get("is_mix_uom", False)})() for r in rows]
    def get(self, nr): return _Kaart(None)


def _regressie(order: str) -> tuple[int, int]:
    st = _load(order)
    stored = (st.get("europallet_regel") or {}).get("hoeveelheid", 0) if st.get("europallet_regel") else 0
    bd = europallet_breakdown(st, repo=_NoKennis(), uom_repo=_FixtureRepo())
    print(f"#{order} (regressie, fixture-masterdata): opgeslagen={stored} -> NU={bd['europallet_aantal']}")
    return stored, bd["europallet_aantal"]


async def main() -> int:
    _seed()
    print("=== Headline: #832 / #833 (verkoop_eenheid gevuld) ===")
    a832 = _print("order_832", 2, await _run_pipeline("order_832"))
    a833 = _print("order_833", None, await _run_pipeline("order_833"))
    print()
    print("=== Regressie: #707 / #716 (mijn wijziging is additief) ===")
    s707, n707 = _regressie("order_707")
    s716, n716 = _regressie("order_716")
    print()
    ok = a832 == 1 and a833 == 1 and n707 == s707 and n716 == s716
    print("RESULTAAT:", "ALLES GROEN [OK]" if ok else "ONVERWACHT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
