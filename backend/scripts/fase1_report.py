"""FASE 1 — rapportgenerator: run-JSONs -> FASE1_BASELINE.md (stap 3).

Leest backend/_upgrade/fase1/fase1_run{1..4}*.json en schrijft het
baseline-rapport met per order de VOLLEDIGE run 1-record (niets samengevat,
opdracht 1b) plus de delta's run1<->run2/3 (pipeline-determinisme) en
run1<->run4 (LLM-variantie op de 5 ankers).

Puur lokaal bestandswerk — geen DB, geen netwerk, geen kwabo-imports.

Usage (vanuit backend/):
  python scripts/fase1_report.py
Output:
  C:\\Kwabo\\FASE1_BASELINE.md (repo-root, niet gitignored)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND = Path(__file__).resolve().parents[1]
FASE1 = BACKEND / "_upgrade" / "fase1"
OUT = BACKEND.parent / "FASE1_BASELINE.md"

RUNS = {
    "run1": "fase1_run1_vers.json",
    "run2": "fase1_run2_replay.json",
    "run3": "fase1_run3_replay.json",
    "run4": "fase1_run4_vers2.json",
}


def _key(rec: dict) -> str:
    return f"{rec.get('order')}|{rec.get('variant') or 'state'}"


def _diff(a, b, pad="") -> list[str]:
    """Recursieve JSON-diff; retourneert regels 'pad: a -> b'."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f"{pad}.{k}" if pad else k)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{pad}: lengte {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diff(x, y, f"{pad}[{i}]")
    elif a != b:
        out.append(f"{pad}: {json.dumps(a, ensure_ascii=False, default=str)} -> "
                   f"{json.dumps(b, ensure_ascii=False, default=str)}")
    return out


def main() -> None:
    runs: dict[str, dict] = {}
    for naam, bestand in RUNS.items():
        p = FASE1 / bestand
        if p.exists():
            runs[naam] = json.loads(p.read_text(encoding="utf-8"))
    if "run1" not in runs:
        sys.exit("fase1_run1_vers.json ontbreekt")

    by_run = {naam: {_key(r): r for r in d["orders"]} for naam, d in runs.items()}
    r1 = runs["run1"]

    lines: list[str] = []
    w = lines.append
    w("# FASE 1 — RODE BASELINE (her-diagnose, opdracht 1b)")
    w("")
    w("Volledige per-order-output van de HUIDIGE gecommitte pipeline met echte extractie")
    w("en echte prod-masterdata (read-only mirror). Niets samengevat: per order staat de")
    w("integrale meetrecord van run 1 (vers) hieronder geplakt. Judge = geauditeerd")
    w("(`FASE1_JUDGE_AUDIT.md`); corpus-getrouwheid = her-gelabeld (`tests/corpus/manifest.json`).")
    w("")
    w("## Run-metadata")
    w("")
    for naam, d in runs.items():
        rm = d.get("run_meta") or {}
        w(f"- **{naam}** ({RUNS[naam]}): git `{str(rm.get('git_head'))[:12]}`, model "
          f"`{rm.get('model')}`, cache `{rm.get('llm_cache_mode')}` "
          f"({rm.get('cache_entries_voor')}→{rm.get('cache_entries_na')} entries), "
          f"NAV `{rm.get('navision_mode')}`, {d.get('n')} records, {rm.get('tijdstip_utc')}")
    w("")
    w("## Totaal (run 1, geauditeerde judge)")
    w("")
    w(f"| stille fouten | fout-met-vlag | juist | geen-GT | crashes |")
    w(f"|---|---|---|---|---|")
    w(f"| **{r1.get('stille_fouten_totaal')}** | {r1.get('fout_met_vlag_totaal')} | "
      f"{r1.get('orders_juist')} | {r1.get('geen_grondwaarheid')} | {r1.get('crashes')} |")
    w("")
    w("Masterdata-tellingen (schaarste zichtbaar): "
      + ", ".join(f"{k}={v}" for k, v in (r1.get("masterdata_counts") or {}).items()))
    w("")
    w("## Overzicht per order (run 1)")
    w("")
    w("| order | bron | extractie | oordeel | niet-juiste velden | vlaggen |")
    w("|---|---|---|---|---|---|")
    for rec in r1["orders"]:
        o = rec.get("oordeel") or {}
        s = rec.get("samenvatting") or {}
        niet = [f"{v['veld']}={v['oordeel']}" for v in o.get("velden", [])
                if v.get("oordeel") != "JUIST"]
        nrf = s.get("needs_review_fields") or []
        naam = f"#{rec.get('order')}" + (f" ({rec['variant']})" if rec.get("variant") else "")
        if rec.get("crash"):
            w(f"| {naam} | {rec.get('bron_type','?')} | — | **CRASH** | {rec['crash']} | |")
            continue
        w(f"| {naam} | {rec.get('bron_type')} | {rec.get('extractie_mode')} | "
          f"{o.get('status')} | {'; '.join(niet) or '—'} | {len(nrf)} |")
    w("")

    # determinisme + variantie
    for naam, titel in (("run2", "Replay-delta run1↔run2 (pipeline-determinisme)"),
                        ("run3", "Replay-delta run1↔run3 (pipeline-determinisme)"),
                        ("run4", "Verse-trekking-delta run1↔run4 (LLM-variantie, 5 ankers)")):
        if naam not in by_run:
            continue
        w(f"## {titel}")
        w("")
        any_delta = False
        for k, rec in by_run["run1"].items():
            other = by_run[naam].get(k)
            if other is None:
                continue
            d = _diff(
                {kk: rec.get(kk) for kk in ("samenvatting", "oordeel", "crash")},
                {kk: other.get(kk) for kk in ("samenvatting", "oordeel", "crash")},
            )
            if d:
                any_delta = True
                w(f"### {k}")
                w("```")
                lines.extend(d)
                w("```")
        if not any_delta:
            w("*Geen enkele delta — byte-identiek op samenvatting+oordeel.*")
        w("")

    w("## Volledige per-order-records (run 1, ongesamenvat)")
    w("")
    for rec in r1["orders"]:
        naam = f"#{rec.get('order')}" + (f" — {rec['variant']}" if rec.get("variant") else "")
        w(f"### Order {naam} — {rec.get('label', '')}")
        w("")
        w("```json")
        w(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
        w("```")
        w("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"# RAPPORT -> {OUT} ({len(lines)} regels)")


if __name__ == "__main__":
    main()
