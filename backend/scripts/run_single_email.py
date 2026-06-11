"""Run ingest graph on a single .eml file and print the resulting state."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# De state bevat ⚠/zero-width tekens die de Windows-console (cp1252) niet aankan.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# GUARD — backend/.env bevat de prod-Postgres-URL met schrijfrechten; dit
# script doet init_db()+seed() en heeft prod al twee keer vervuild (31-05,
# 11-06). Daarom: zonder --allow-real-db draait het ALTIJD op sqlite. Moet
# vóór elke kwabo-import staan: pydantic-settings leest .env bij import en
# alleen os.environ wint daarvan.
if "--allow-real-db" in sys.argv:
    sys.argv.remove("--allow-real-db")
    print("!! --allow-real-db: DATABASE_URL uit env/.env wordt gebruikt — init_db()+seed() raken die database.", file=sys.stderr)
else:
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url and not env_url.startswith("sqlite"):
        print(
            "GEWEIGERD: DATABASE_URL wijst niet naar sqlite "
            f"({env_url.split('@')[-1] if '@' in env_url else env_url}).\n"
            "Dit script seedt demo-data; gebruik --allow-real-db als je dit echt wilt.",
            file=sys.stderr,
        )
        sys.exit(2)
    os.environ["DATABASE_URL"] = "sqlite:///./kwabo.db"
    os.environ.setdefault("NAVISION_MODE", "mock")

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
