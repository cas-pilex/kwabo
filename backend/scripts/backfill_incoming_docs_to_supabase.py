"""One-off: lift bestaande order_log.incoming_document_path naar Supabase Storage.

Voor orders die vóór de Supabase-storage migratie (Fase 2) zijn verwerkt:
- als de .eml nog op disk staat → upload naar Supabase, zet storage_key in state.
- als de .eml weg is (ephemere Railway-FS al gewist) → log warning, skip.

Idempotent: orders die al een `incoming_document_storage_key` hebben worden
overgeslagen. Dry-run optie zodat Cas eerst kan zien wat er gaat gebeuren.

Gebruik:
    PYTHONPATH=src python scripts/backfill_incoming_docs_to_supabase.py --dry-run
    PYTHONPATH=src python scripts/backfill_incoming_docs_to_supabase.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlmodel import Session, select

from kwabo.db.models import OrderLog
from kwabo.db.session import engine
from kwabo.integrations.supabase_storage import get_supabase_storage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Niets opslaan, alleen rapporteren")
    parser.add_argument("--limit", type=int, default=0, help="Max aantal orders (0=alles)")
    args = parser.parse_args()

    client = get_supabase_storage()
    if client is None:
        print(
            "ERR: Supabase niet geconfigureerd. Zet SUPABASE_URL + "
            "SUPABASE_SERVICE_ROLE_KEY env-vars eerst.",
            file=sys.stderr,
        )
        return 2

    counters = {
        "scanned": 0,
        "already_migrated": 0,
        "no_path_field": 0,
        "file_missing": 0,
        "uploaded": 0,
        "upload_failed": 0,
    }

    with Session(engine) as s:
        rows = s.exec(select(OrderLog)).all()
        for row in rows:
            counters["scanned"] += 1
            if args.limit and counters["uploaded"] >= args.limit:
                break

            state = json.loads(row.order_state or "{}") if row.order_state else {}
            if state.get("incoming_document_storage_key"):
                counters["already_migrated"] += 1
                continue

            path_str = state.get("incoming_document_path")
            if not path_str:
                counters["no_path_field"] += 1
                continue

            p = Path(path_str)
            if not p.exists():
                counters["file_missing"] += 1
                print(f"  SKIP order {row.id} email={row.email_id}: file missing at {path_str}")
                continue

            # Reconstruct the same canonical key the new intake path uses.
            from kwabo.api.intake_trigger import _safe_eml_id
            safe_id = _safe_eml_id(row.email_id)
            key = f"by_email_id/{safe_id}.eml"

            if args.dry_run:
                print(f"  WOULD UPLOAD order {row.id} email={row.email_id}: {p} → {key}")
                counters["uploaded"] += 1
                continue

            try:
                raw = p.read_bytes()
                client.put_object(key, raw, "message/rfc822")
                state["incoming_document_storage_key"] = key
                row.order_state = json.dumps(state, default=str)
                s.add(row)
                s.commit()
                counters["uploaded"] += 1
                print(f"  OK   order {row.id} email={row.email_id}: → {key}")
            except Exception as exc:  # noqa: BLE001
                counters["upload_failed"] += 1
                print(f"  FAIL order {row.id} email={row.email_id}: {exc!r}", file=sys.stderr)

    print("\n--- Backfill report ---")
    for k, v in counters.items():
        print(f"  {k:18s} {v}")
    if args.dry_run:
        print("\n(dry-run — geen wijzigingen geschreven)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
