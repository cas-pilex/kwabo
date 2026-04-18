"""Run the ingest graph on all emls in test_data and report match rates."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.seed import seed  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.runner import run_on_eml  # noqa: E402


async def _run_one(path: Path) -> dict:
    try:
        st = await run_on_eml(path)
        regels = st.get("orderregels") or []
        matched = sum(1 for r in regels if r.get("artikelnummer_kwabo_matched"))
        klant = (st.get("klant_match") or {}).get("navision_klantnr")
        return {
            "file": path.name,
            "is_order": st.get("is_order"),
            "taal": st.get("taal"),
            "klant": klant,
            "regels": len(regels),
            "matched": matched,
            "warnings": len(st.get("validatie_warnings") or []),
            "bestelnr": st.get("bestelnummer_klant"),
            "ok": True,
        }
    except Exception as e:  # noqa: BLE001
        return {"file": path.name, "ok": False, "error": str(e)[:200]}


async def main() -> None:
    init_db()
    with Session(engine) as s:
        seed(s)

    files = sorted(Path("tests/test_data/emails").glob("*.eml"))
    # Run in limited concurrency to avoid rate limits
    sem = asyncio.Semaphore(4)

    async def bounded(p):
        async with sem:
            return await _run_one(p)

    results = await asyncio.gather(*(bounded(p) for p in files))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    ok = [r for r in results if r.get("ok")]
    orders = [r for r in ok if r.get("is_order")]
    print(f"\nRAN: {len(results)} | Parsed ok: {len(ok)} | Classified order: {len(orders)}")
    tot_regels = sum(r.get("regels", 0) for r in orders)
    tot_matched = sum(r.get("matched", 0) for r in orders)
    print(f"Regels totaal: {tot_regels} | Auto-matched: {tot_matched} ({(tot_matched/tot_regels*100) if tot_regels else 0:.1f}%)")
    klant_hits = sum(1 for r in orders if r.get("klant"))
    print(f"Klant gematcht: {klant_hits}/{len(orders)}")


if __name__ == "__main__":
    asyncio.run(main())
