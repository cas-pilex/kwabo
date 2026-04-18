"""Run ingest graph on a single .eml file and print the resulting state."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kwabo.db.session import init_db  # noqa: E402
from kwabo.db.seed import seed  # noqa: E402
from kwabo.graph.runner import finalize, run_on_eml  # noqa: E402
from sqlmodel import Session  # noqa: E402
from kwabo.db.session import engine  # noqa: E402


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: run_single_email.py <path> [--approve]")
        sys.exit(1)
    path = sys.argv[1]
    approve = "--approve" in sys.argv

    init_db()
    with Session(engine) as s:
        seed(s)

    state = await run_on_eml(path)
    # Strip bijlage-text for readability
    out = {k: v for k, v in state.items() if k != "bijlagen"}
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))

    if approve and state.get("is_order"):
        final_state = await finalize(state)
        print("\n=== FINALIZED ===")
        print("navision_order_nr:", final_state.get("navision_order_nr"))


if __name__ == "__main__":
    asyncio.run(main())
