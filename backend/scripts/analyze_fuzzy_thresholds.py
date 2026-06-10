"""Empirische onderbouwing van de fuzzy-matchdrempel (Fase 2 A5). Read-only.

Draait volledig op de geëxporteerde fixtures (tests/test_data/states/):
  * artikelkaarten.json     — alle 3757 echte artikelnamen (kandidaten-set)
  * order_*.json            — echte orders; fuzzy-gematchte regels = junk-set,
                              exact-gematchte regels = bekende-correcte paren
  * matching_history.json   — goedgekeurde (omschrijving → artikel)-paren

Per regel herberekenen we wat process.extractOne(omschrijving, namen) doet
met drie scorers (WRatio / token_sort_ratio / token_set_ratio), en printen:
  - JUNK:  wat de foute auto-fill scoorde (moet ONDER de nieuwe drempel)
  - GOED:  zou fuzzy het juiste artikel gekozen hebben, en met welke score
           (bepaalt hoeveel terecht-fuzzy we boven de drempel verliezen)

Usage (vanuit backend/):
    python scripts/analyze_fuzzy_thresholds.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from rapidfuzz import fuzz, process  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

SCORERS = {
    "WRatio": fuzz.WRatio,
    "token_sort": fuzz.token_sort_ratio,
    "token_set": fuzz.token_set_ratio,
}


def laad_namen() -> dict[str, str]:
    rows = json.loads((STATES / "artikelkaarten.json").read_text(encoding="utf-8"))
    return {r["kwabo_artikelnr"]: r["naam"] for r in rows}


def scores_tegen_alle(oms: str, namen: dict[str, str]) -> dict[str, tuple[str, float]]:
    """Per scorer: (gekozen artikelnr, score) van extractOne over alle namen."""
    uit = {}
    for label, scorer in SCORERS.items():
        best = process.extractOne(oms, namen, scorer=scorer)
        uit[label] = (best[2], best[1]) if best else ("-", 0.0)
    return uit


def main() -> None:
    namen = laad_namen()
    junk: list[dict] = []    # fuzzy auto-fills uit de faalorders
    goed: list[dict] = []    # regels met bekend-correct artikel (exact/history)

    for p in sorted(STATES.glob("order_*.json")):
        env = json.loads(p.read_text(encoding="utf-8"))
        st = env["order_state"]
        for r in st.get("orderregels") or []:
            oms = (r.get("omschrijving") or "").strip()
            if not oms:
                continue
            methode = r.get("match_methode")
            matched = r.get("artikelnummer_kwabo_matched")
            if methode == "fuzzy" and matched:
                junk.append({"order": env["order_id"], "oms": oms, "fout_naar": matched})
            elif methode == "exact" and matched:
                goed.append({"order": env["order_id"], "oms": oms, "correct": matched})

    hist = json.loads((STATES / "matching_history.json").read_text(encoding="utf-8"))
    for h in hist:
        oms = (h.get("klant_omschrijving") or "").strip()
        if oms and h.get("kwabo_artikelnr"):
            goed.append({"order": f"hist:{h['match_methode']}", "oms": oms,
                         "correct": h["kwabo_artikelnr"]})

    kop = f"{'set':5} {'order':12} {'WRatio':>22} {'token_sort':>22} {'token_set':>22}"

    print("== JUNK-SET: fuzzy auto-fills uit de echte faalorders")
    print("   (score = wat extractOne koos over alle 3757 echte namen)")
    print(kop)
    junk_max: dict[str, float] = {k: 0.0 for k in SCORERS}
    for j in junk:
        sc = scores_tegen_alle(j["oms"], namen)
        cells = []
        for label in SCORERS:
            nr, s = sc[label]
            junk_max[label] = max(junk_max[label], s)
            cells.append(f"{nr}@{s:.0f}")
        print(f"{'JUNK':5} {j['order']!s:12} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22}")
        print(f"      oms: {j['oms'][:70]!r}  (was auto-ingevuld: "
              f"{j['fout_naar']} {namen.get(j['fout_naar'], '?')[:40]!r})")

    print()
    print("== BEKEND-CORRECTE PAREN: zou fuzzy het juiste artikel kiezen, en hoe hoog?")
    print(kop)
    for g in goed:
        sc = scores_tegen_alle(g["oms"], namen)
        cells = []
        for label in SCORERS:
            nr, s = sc[label]
            ok = "✓" if nr == g["correct"] else "✗"
            cells.append(f"{ok}{nr}@{s:.0f}")
        print(f"{'GOED':5} {g['order']!s:12} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22}")
        print(f"      oms: {g['oms'][:70]!r}  (correct: {g['correct']} "
              f"{namen.get(g['correct'], '?')[:40]!r})")

    print()
    print("== SAMENVATTING")
    for label in SCORERS:
        print(f"  hoogste JUNK-score onder {label}: {junk_max[label]:.0f}")
    print()
    print("Beslisregel: drempel = ronde waarde strikt boven de hoogste junk-score")
    print("met marge; ✓-regels in de GOED-set tonen wat een drempel aan terechte")
    print("fuzzy-hits zou kosten (✗ = fuzzy zou sowieso het verkeerde kiezen).")


if __name__ == "__main__":
    main()
