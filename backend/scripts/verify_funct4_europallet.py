"""DIAGNOSE Functie 4 — europallet op de ECHTE prod-data (artikel 19820).

LET OP: dit is een DIAGNOSE, geen 'groen'-bewijs. De eerdere versie seedde
fictief verkoop_eenheid=PALLET33 en gaf #832->1 / #833->1. De prod-export bevat
verkoop_eenheid=STUK voor 238601/238531/229231, en de europallet-telling gebruikt
artikel_pallet_kennis (per_pallet) als PRIMAIRE bron — die overschaduwt
verkoop_eenheid. Op de echte data, met de kennis-tabel:

  #832 = 33 STUK 238601  -> per_pallet=24 (kennis) -> 33/24=1,375 -> 2 europallet.
  #833 = 5 STUK 229231 + 15 STUK 238531 -> 229231 5/24=0,208 (<drempel);
         238531 geen kennis + verkoop_eenheid=STUK -> 0 bijdrage -> 0 europallet.

Kernprobleem: artikel_pallet_kennis.per_pallet=24 matcht GEEN echte pallet-familie
(238601: 30/33/35/42; 23691: echte PALLET=20). De juiste pallet-maat per artikel
is een OPEN EXPERTVRAAG (Cas/Nico) — deze diagnose stelt 'm vast, lost 'm niet op.

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

from kwabo.db.models import (  # noqa: E402
    Artikelkaart, ArtikelEenheid, ArtikelPalletKennis,
)
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node  # noqa: E402
from kwabo.graph.nodes.compute_europallet import compute_europallet_node  # noqa: E402
from kwabo.graph.nodes.match_articles import match_articles_node  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"
_AE = json.loads((STATES / "artikel_eenheden.json").read_text("utf-8"))
# verkoop_eenheid + pallet-kennis komen UIT de prod-export (geen hardcode meer),
# zodat de telling de ECHTE prod-data weerspiegelt (incl. de foute kennis-waarden).
_AK = {r["kwabo_artikelnr"]: r
       for r in json.loads((STATES / "artikelkaarten.json").read_text("utf-8"))}
_PK = json.loads((STATES / "artikel_pallet_kennis.json").read_text("utf-8"))
ARTIKELEN = ["238601", "238531", "229231"]  # de regels uit #832/#833


def _seed() -> None:
    init_db()
    with Session(engine) as s:
        for nr in ARTIKELEN:
            kaart = _AK.get(nr) or {}
            s.add(Artikelkaart(kwabo_artikelnr=nr, naam=kaart.get("naam") or f"art {nr}",
                               basis_eenheid=kaart.get("basis_eenheid") or "STUK",
                               verkoop_eenheid=kaart.get("verkoop_eenheid")))
        for r in _AE:
            if r["kwabo_artikelnr"] in ARTIKELEN:
                s.add(ArtikelEenheid(**r))
        # artikel_pallet_kennis is de PRIMAIRE pallet-bron — meeseeden zodat de
        # diagnose de echte prod-uitkomst toont (per_pallet=24).
        for r in _PK:
            if r["kwabo_artikelnr"] in ARTIKELEN:
                s.add(ArtikelPalletKennis(
                    kwabo_artikelnr=r["kwabo_artikelnr"], eenheid=r["eenheid"],
                    pallet_required=bool(r["pallet_required"]),
                    per_pallet=int(r["per_pallet"]), confidence=float(r["confidence"])))
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


def _kennis_mismatch() -> None:
    """Toon waarom de kennis-waarde verdacht is: per_pallet vs echte pallet-families."""
    pk = {r["kwabo_artikelnr"]: r for r in _PK}
    print("=== Root cause: artikel_pallet_kennis.per_pallet vs echte pallet-UoM ===")
    for nr in ARTIKELEN:
        per = (pk.get(nr) or {}).get("per_pallet")
        fams = sorted({r["qty_per_base"] for r in _AE
                       if r["kwabo_artikelnr"] == nr and "PAL" in r["eenheid_code"].upper()
                       and r["qty_per_base"] > 1})
        match = "OK" if per in fams else "MISMATCH — geen enkele pallet-familie = %s" % per
        print(f"   {nr}: kennis per_pallet={per}  echte pallet-maten={fams}  -> {match}")


async def main() -> int:
    _seed()
    print("=== DIAGNOSE: #832 / #833 op de ECHTE prod-data (kennis + verkoop_eenheid) ===")
    a832 = _print("order_832", 2, await _run_pipeline("order_832"))
    a833 = _print("order_833", None, await _run_pipeline("order_833"))
    print()
    _kennis_mismatch()
    print()
    print("BEVINDING: de europallet-telling leunt op artikel_pallet_kennis (per_pallet=24),")
    print("niet op verkoop_eenheid. per_pallet=24 matcht geen echte pallet-familie -> de")
    print("uitkomst (#832=%s, #833=%s) is data-gedreven FOUT. De juiste pallet-maat per" % (a832, a833))
    print("artikel is een OPEN EXPERTVRAAG (Cas/Nico); deze diagnose lost niets op.")
    return 0  # diagnose: altijd 0 — documenteert de stand, gate't niet op 'groen'


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
