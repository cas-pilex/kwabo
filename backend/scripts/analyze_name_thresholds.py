"""Empirische onderbouwing van de klant-naam-autopick-lat (Fase 2 K3). Read-only.

Zelfde opzet als analyze_fuzzy_thresholds.py, maar voor de KLANT-naam-fallback:
alle scores op ÉÉN schaal — token_set_ratio 0-100, na rechtsvorm-strip, exact
zoals _match_by_name beslist. De getoonde drempels en normalisatie worden uit
match_customer geïmporteerd, dus dit script kan nooit uit de pas lopen met
productie.

Per naam-signaal (letterlijk wat in het orderdocument van de faalorders staat,
zelfde lijst als verify_fase2.py) printen we de top-kandidaten met score + gap
en het besluit volgens de productie-regel:
    AUTOPICK    top >= NAAM_ACCEPT (90) én gap >= NAAM_GAP (10)
    KANDIDATEN  top >= NAAM_SHOW (75), geen unieke winnaar
    GEEN        anders

De confidence 0.8 die een naam-match in de provenance krijgt is GEEN tweede
beslis-schaal: het is het bron-vertrouwensniveau (0-1) ná acceptatie, net als
email=1.0 en navision_email=0.9/0.95. Beslist wordt uitsluitend op 0-100.

Usage (vanuit backend/): python scripts/analyze_name_thresholds.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

# Vóór elke kwabo-import: nooit de echte DB raken (backend/.env wijst naar prod).
_tmpdb = Path(tempfile.mkdtemp()) / "analyze_name.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"
os.environ["NAVISION_MODE"] = "mock"

from rapidfuzz import fuzz, process  # noqa: E402

from kwabo.graph.nodes.match_customer import (  # noqa: E402
    NAAM_ACCEPT,
    NAAM_GAP,
    NAAM_SHOW,
    _normaliseer_klantnaam,
)

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

# (label, naam-signaal zoals letterlijk in document/onderwerp van de faalorder)
SIGNALEN = [
    ("#718 Witzand", "Witzand Bouwmaterialen B.V."),
    ("#721 Van Dongen", "Van Dongen Verf BV"),
    ("#707 GBI Borne (zevij-portaal)", "GBI Borne"),
    ("#635 TABS (pontmeyer-agent)", "TABS Holland"),
    ("#550 Jongeneel (franchise)", "Jongeneel"),
]


def main() -> None:
    kaarten = json.loads((STATES / "klantenkaarten.json").read_text(encoding="utf-8"))
    namen = {
        k["nav_klantnr"]: _normaliseer_klantnaam(k["naam"])
        for k in kaarten if k.get("naam")
    }
    per_nr = {k["nav_klantnr"]: k["naam"] for k in kaarten}
    print(f"kandidaten-set: {len(namen)} echte klantenkaart-namen "
          f"(token_set_ratio na rechtsvorm-strip)\n")
    print(f"productie-regel (match_customer.py): AUTOPICK bij top >= {NAAM_ACCEPT} "
          f"én gap >= {NAAM_GAP}; kandidaten tonen vanaf {NAAM_SHOW}\n")

    for label, signaal in SIGNALEN:
        norm = _normaliseer_klantnaam(signaal)
        top = process.extract(norm, namen, scorer=fuzz.token_set_ratio, limit=3)
        top1 = top[0][1]
        gap = top1 - top[1][1] if len(top) > 1 else 100.0
        if top1 >= NAAM_ACCEPT and gap >= NAAM_GAP:
            besluit = f"AUTOPICK {top[0][2]} (conf 0.8, zachte controleer-vlag)"
        elif top1 >= NAAM_SHOW:
            besluit = "GEEN AUTOPICK — kandidaten naar operator"
        else:
            besluit = "GEEN match, geen kandidaten"
        print(f"== {label}  signaal: {signaal!r}")
        for _, score, nr in top:
            print(f"     {score:5.1f}/100  {nr}  {per_nr[nr]!r}")
        print(f"     top={top1:.0f}  gap={gap:.0f}  ->  {besluit}\n")

    print("== SAMENVATTING (één schaal: token_set_ratio 0-100)")
    print(f"  artikel-fuzzy-lat (A5): 90 (WRatio, 0-100)  |  "
          f"klant-naam-lat (K3): {NAAM_ACCEPT} + gap {NAAM_GAP} (token_set_ratio, 0-100)")
    print("  TABS Holland haalt max ~87 op het VERKEERDE bedrijf -> onder de lat,")
    print("  afgewezen. Witzand/Van Dongen/GBI halen 100 met ruime gap -> erboven.")
    print("  Jongeneel haalt 100 maar gap 0 (franchise: 1 kaart per vestiging) ->")
    print("  kandidaten, nooit autopick (grondwet 5).")


if __name__ == "__main__":
    main()
