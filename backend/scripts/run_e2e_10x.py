"""Run the full ingest graph N times across all sample emails, then write a
markdown report assessing stability + bugs that surface across iterations.

Use this before any go-live to flush out:
  - Uncaught exceptions on the happy path
  - LLM-induced flakiness (different ops between iterations for the same email)
  - Regressions on auto-match rates, klant matching, or composed-ops counts

Output: `backend/reports/e2e_10x_<timestamp>.md`. Per email we capture which
iterations succeeded, how stable the composed nav_operations were (hashed),
and any errors. The summary block at the top is the eyes-on signal.

Usage:
    python backend/scripts/run_e2e_10x.py            # 10 iterations
    python backend/scripts/run_e2e_10x.py --runs 3   # quick smoke
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.seed import seed  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.runner import run_on_eml  # noqa: E402


EMAILS_DIR = ROOT / "tests" / "test_data" / "emails"
REPORT_DIR = ROOT / "reports"


def _ops_hash(ops: list[dict[str, Any]]) -> str:
    """Stable hash of the composed ops, ignoring volatile fields like
    `shipmentDate` (which is computed as today + 1 weekday) so the hash
    is comparable across iterations on the same calendar day."""
    canonical = []
    for op in ops:
        body = dict(op.get("body") or {})
        # shipmentDate moves with the wallclock; exclude.
        body.pop("shipmentDate", None)
        canonical.append({
            "op": op.get("op"),
            "path": op.get("path"),
            "body_keys": sorted(body.keys()),
            # Hash only stringified values to ignore numeric type drift.
            "body_values": [str(body[k]) for k in sorted(body.keys())],
        })
    raw = json.dumps(canonical, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


async def _run_one(path: Path) -> dict[str, Any]:
    try:
        st = await run_on_eml(path)
        regels = st.get("orderregels") or []
        matched = sum(1 for r in regels if r.get("artikelnummer_kwabo_matched"))
        ops = st.get("nav_operations") or []
        return {
            "file": path.name,
            "ok": True,
            "is_order": bool(st.get("is_order")),
            "klant": (st.get("klant_match") or {}).get("navision_klantnr"),
            "regels": len(regels),
            "matched": matched,
            "nav_ops": len(ops),
            "ops_hash": _ops_hash(ops),
            "compose_error": st.get("compose_error"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "file": path.name,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


async def _run_iteration(files: list[Path], concurrency: int) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)

    async def bounded(p: Path) -> dict[str, Any]:
        async with sem:
            return await _run_one(p)

    return await asyncio.gather(*(bounded(p) for p in files))


def _summarise_iterations(runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Roll up N iteration outputs into per-email stability metrics."""
    per_file: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "ok_count": 0,
        "fail_count": 0,
        "ops_hashes": Counter(),
        "klants": Counter(),
        "matched_per_iter": [],
        "nav_ops_per_iter": [],
        "errors": [],
    })
    for it_idx, it in enumerate(runs, start=1):
        for r in it:
            agg = per_file[r["file"]]
            if r.get("ok"):
                agg["ok_count"] += 1
                agg["ops_hashes"][r.get("ops_hash") or "-"] += 1
                if r.get("klant"):
                    agg["klants"][r["klant"]] += 1
                agg["matched_per_iter"].append((it_idx, r.get("matched", 0), r.get("regels", 0)))
                agg["nav_ops_per_iter"].append((it_idx, r.get("nav_ops", 0)))
            else:
                agg["fail_count"] += 1
                agg["errors"].append((it_idx, r.get("error", "")))
    return per_file


def _write_report(
    runs: list[list[dict[str, Any]]],
    files: list[Path],
    elapsed: float,
    out_path: Path,
) -> None:
    n_iter = len(runs)
    summary = _summarise_iterations(runs)
    out: list[str] = []
    out.append(f"# E2E 10× rapport — {datetime.now().isoformat(timespec='seconds')}")
    out.append("")
    out.append(f"- Iterations run: **{n_iter}**")
    out.append(f"- Emails per iteration: **{len(files)}**")
    out.append(f"- Total runs: **{n_iter * len(files)}**")
    out.append(f"- Elapsed: **{elapsed:.1f}s**")
    out.append("")

    # Aggregate health gauges
    flaky_files: list[str] = []
    failing_files: list[str] = []
    stable_files: list[str] = []
    for f, agg in summary.items():
        if agg["fail_count"] == n_iter:
            failing_files.append(f)
        elif agg["fail_count"] > 0 or len(agg["ops_hashes"]) > 1:
            flaky_files.append(f)
        else:
            stable_files.append(f)

    out.append("## Aggregate verdict")
    out.append("")
    out.append(f"- ✅ Fully stable (same ops every iteration, no errors): **{len(stable_files)}/{len(files)}**")
    out.append(f"- ⚠️ Flaky (varies between iterations OR partial errors): **{len(flaky_files)}/{len(files)}**")
    out.append(f"- ❌ Always failing: **{len(failing_files)}/{len(files)}**")
    out.append("")

    out.append("## Per-email")
    out.append("")
    out.append("| File | OK / N | Distinct op-hashes | Avg matched | Klant | Notes |")
    out.append("|---|---|---|---|---|---|")
    for f in sorted(summary.keys()):
        agg = summary[f]
        ok_n = f"{agg['ok_count']}/{n_iter}"
        n_hashes = len(agg["ops_hashes"]) if agg["ops_hashes"] else 0
        if agg["matched_per_iter"]:
            avg_match = statistics.mean(m for _, m, _ in agg["matched_per_iter"])
            avg_total = statistics.mean(t for _, _, t in agg["matched_per_iter"])
            match_str = f"{avg_match:.1f}/{avg_total:.1f}"
        else:
            match_str = "-"
        klant = agg["klants"].most_common(1)[0][0] if agg["klants"] else "-"
        notes: list[str] = []
        if n_hashes > 1:
            notes.append(f"⚠ {n_hashes} variants")
        if agg["fail_count"]:
            notes.append(f"❌ {agg['fail_count']} fail")
        if not notes:
            notes.append("✅")
        out.append(f"| {f} | {ok_n} | {n_hashes} | {match_str} | {klant} | {' '.join(notes)} |")

    if flaky_files or failing_files:
        out.append("")
        out.append("## Drill-down: flaky / failing emails")
        out.append("")
        for f in flaky_files + failing_files:
            agg = summary[f]
            out.append(f"### {f}")
            out.append("")
            if agg["ops_hashes"] and len(agg["ops_hashes"]) > 1:
                out.append("op-hash distribution: " +
                          ", ".join(f"{h} (×{c})" for h, c in agg["ops_hashes"].most_common()))
                out.append("")
            for it_idx, err in agg["errors"]:
                out.append(f"- iter {it_idx}: {err}")
            out.append("")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")


async def main(runs: int, concurrency: int) -> int:
    init_db()
    with Session(engine) as s:
        seed(s)

    files = sorted(EMAILS_DIR.glob("*.eml"))
    if not files:
        print(f"No .eml files in {EMAILS_DIR!s} — nothing to run.")
        return 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    runs_out: list[list[dict[str, Any]]] = []
    for i in range(1, runs + 1):
        print(f"[iter {i}/{runs}] running {len(files)} emails…", flush=True)
        iter_started = time.time()
        results = await _run_iteration(files, concurrency=concurrency)
        runs_out.append(results)
        ok = sum(1 for r in results if r.get("ok"))
        ord_count = sum(1 for r in results if r.get("ok") and r.get("is_order"))
        with_ops = sum(1 for r in results if r.get("ok") and r.get("nav_ops", 0) > 0)
        print(
            f"  ok={ok}/{len(results)} orders={ord_count} with_ops={with_ops} "
            f"({time.time() - iter_started:.1f}s)",
            flush=True,
        )

    elapsed = time.time() - started
    out_path = REPORT_DIR / f"e2e_{runs}x_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    _write_report(runs_out, files, elapsed, out_path)
    print(f"\nReport written: {out_path}")

    # Exit code: non-zero if anything failed in every iteration.
    summary = _summarise_iterations(runs_out)
    always_failing = sum(1 for agg in summary.values() if agg["fail_count"] == runs)
    if always_failing:
        print(f"FAIL: {always_failing} email(s) failed in every iteration.")
        return 2
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10, help="Number of iterations (default 10)")
    parser.add_argument("--concurrency", type=int, default=4, help="Parallel emails per iteration")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.runs, args.concurrency)))
