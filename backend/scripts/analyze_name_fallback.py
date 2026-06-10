"""Empirische validatie van de klantnaam-fallback-drempels (Fase 2 K3).

Scoort de échte geëxtraheerde klantnamen uit de faalorders tegen alle 1787
echte klantenkaart-namen (token_sort_ratio na normalisatie), en print de
top-5 per naam. Onderbouwt: accepteer alleen top >= ACCEPT én gap >= GAP;
kandidaten tonen vanaf SHOW.

Usage (vanuit backend/): python scripts/analyze_name_fallback.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from rapidfuzz import fuzz, process  # noqa: E402

STATES = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"

RECHTSVORM_RE = re.compile(
    r"\b(b\.?v\.?|n\.?v\.?|v\.?o\.?f\.?|gmbh|& ?co\.? ?kg|bv|nv)\b\.?", re.IGNORECASE
)


def normaliseer(naam: str) -> str:
    n = (naam or "").lower()
    n = RECHTSVORM_RE.sub(" ", n)
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# Echte naam-signalen uit de faalorders (wat de extractie/het document zegt):
TESTNAMEN = [
    ("Witzand Bouwmaterialen B.V.", "#718 — moet 60892 worden"),
    ("Van Dongen Verf B.V.", "#721 — moet 61472 worden"),
    ("GBI Borne", "#707 — moet 61948 worden"),
    ("TABS Holland", "#635/#619 — meerdere DC TABS → kandidaten"),
    ("Jongeneel", "#550 — franchise, ~40 vestigingen → kandidaten"),
    ("PontMeyer", "agent-mails — meerdere vestigingen → kandidaten"),
    ("Kuipers BMH", "#717 regressieguard — moet 61844 worden"),
    ("Witzand", "verkorte schrijfwijze"),
]


def main() -> None:
    rows = json.loads((STATES / "klantenkaarten.json").read_text(encoding="utf-8"))
    namen = {r["nav_klantnr"]: normaliseer(r["naam"]) for r in rows if r["naam"]}
    origineel = {r["nav_klantnr"]: r["naam"] for r in rows}

    for naam, verwacht in TESTNAMEN:
        top = process.extract(normaliseer(naam), namen,
                              scorer=fuzz.token_sort_ratio, limit=5)
        print(f"== {naam!r}  ({verwacht})")
        for _, score, nr in top:
            print(f"   {score:5.1f}  {nr}  {origineel[nr]}")
        if len(top) >= 2:
            print(f"   gap top-2: {top[0][1] - top[1][1]:.1f}")
        print()


if __name__ == "__main__":
    main()
