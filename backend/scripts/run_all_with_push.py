"""Run ingest+finalize on all test emails and validate NAV stepwise ops."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.seed import seed  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.runner import finalize, run_on_eml  # noqa: E402


async def _run_one(path: Path) -> dict:
    try:
        st = await run_on_eml(path)
        regels = st.get("orderregels") or []
        matched = sum(1 for r in regels if r.get("artikelnummer_kwabo_matched"))
        klant = (st.get("klant_match") or {}).get("navision_klantnr")
        out = {
            "file": path.name,
            "is_order": st.get("is_order"),
            "klant": klant,
            "regels": len(regels),
            "matched": matched,
            "warnings": len(st.get("validatie_warnings") or []),
        }
        # Push to mock NAV if it's an order with matched articles
        if st.get("is_order") and matched > 0:
            final_state = await finalize(st)
            ops = final_state.get("nav_operation_results") or []
            out["pushed"] = final_state.get("navision_status")
            out["nav_order_nr"] = final_state.get("navision_order_nr")
            out["op_count"] = len(ops)
            out["op_methods"] = [o.get("operation", {}).get("op") for o in ops]
            out["op_paths"] = [o.get("operation", {}).get("path") for o in ops]
            out["op_errors"] = [o.get("error") for o in ops if o.get("error")]
            out["autofilled_keys"] = sorted((final_state.get("nav_autofilled") or {}).keys())
        out["ok"] = True
        return out
    except Exception as e:  # noqa: BLE001
        return {"file": path.name, "ok": False, "error": str(e)[:300]}


async def main() -> None:
    init_db()
    with Session(engine) as s:
        seed(s)

    files = sorted(Path("tests/test_data/emails").glob("*.eml"))
    sem = asyncio.Semaphore(4)

    async def bounded(p):
        async with sem:
            return await _run_one(p)

    results = await asyncio.gather(*(bounded(p) for p in files))

    # Summary
    total = len(results)
    ok = [r for r in results if r.get("ok")]
    orders = [r for r in ok if r.get("is_order")]
    pushed = [r for r in orders if r.get("pushed") == "Draft"]
    failed_push = [r for r in orders if r.get("pushed") == "failed"]
    no_push_unmatched = [r for r in orders if r.get("matched") == 0]

    print(f"\n{'='*70}")
    print(f"RAN: {total}")
    print(f"Parsed ok: {len(ok)}")
    print(f"Classified order: {len(orders)}")
    print(f"Klant gematcht: {sum(1 for r in orders if r.get('klant'))}/{len(orders)}")
    print(f"Pushed -> NAV mock as Draft: {len(pushed)}")
    print(f"Push failed: {len(failed_push)}")
    print(f"Skipped push (0 matched articles): {len(no_push_unmatched)}")
    if failed_push:
        for r in failed_push:
            print(f"  ! {r['file']}: errors={r.get('op_errors')}")
    # Stepwise integrity: every pushed order should have at least 1 POST + N PATCHes
    print(f"\nStepwise integrity per pushed order:")
    for r in pushed:
        methods = r.get("op_methods") or []
        n_post = sum(1 for m in methods if m == "POST")
        n_patch = sum(1 for m in methods if m == "PATCH")
        print(
            f"  {r['file'][:60]:60s}  POST={n_post:2d}  PATCH={n_patch:2d}  "
            f"autofilled={','.join(r.get('autofilled_keys') or [])[:60]}"
        )


if __name__ == "__main__":
    asyncio.run(main())
