"""D1 — differentieel: rode baseline (pre-upgrade, uit UPGRADE_BASELINE.md)
naast de verse run op de nieuwe code (_upgrade/d1_nieuw_vers.json).

Puur lezen/vergelijken — geen DB, geen LLM. Output: markdown-tabel op stdout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def parse_baseline_md() -> dict[str, dict]:
    md = (ROOT / "UPGRADE_BASELINE.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", md, flags=re.DOTALL)
    out = {}
    for b in blocks:
        d = json.loads(b)
        out[d["order"]] = d
    return out


def kern(o: dict) -> str:
    if o.get("crash"):
        return f"CRASH: {o['crash'][:60]}"
    oo = o.get("oordeel") or {}
    niet = [f"{v['veld']}={v.get('kreeg')}≠{v.get('verwacht')}({v['oordeel']})"
            for v in oo.get("velden", []) if v.get("oordeel") != "JUIST"]
    return oo.get("status", "?") + (": " + "; ".join(niet) if niet else "")


def main() -> None:
    oud = parse_baseline_md()
    nieuw = {o["order"]: o for o in json.loads(
        (ROOT / "backend/_upgrade/d1_nieuw_vers.json").read_text(encoding="utf-8"))["orders"]}

    print("| order | OUD (pre-upgrade, vers 2-7 ochtend) | NIEUW (na B1-B4, vers) |")
    print("|---|---|---|")
    stil_oud = stil_nieuw = 0
    for oid in oud:
        o, n = oud[oid], nieuw.get(oid, {})
        stil_oud += (o.get("oordeel") or {}).get("n_stille_fouten", 0)
        stil_nieuw += (n.get("oordeel") or {}).get("n_stille_fouten", 0)
        print(f"| #{oid} | {kern(o)} | {kern(n)} |")
    print(f"\nStille fouten totaal: OUD {stil_oud} -> NIEUW {stil_nieuw}")


if __name__ == "__main__":
    main()
