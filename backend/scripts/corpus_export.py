"""GOLDEN-CORPUS-EXPORT — haal corpus-orders read-only uit prod (STRUCTURELE UPGRADE, Fase A).

Strict read-only t.o.v. prod: geen enkele kwabo-import (dus geen init_db()/seed()
die per ongeluk zouden kunnen schrijven), alleen losse SELECT's via sqlalchemy.
Schrijft uitsluitend naar backend/tests/corpus/sources/.

Usage (vanuit backend/, met prod DATABASE_URL in backend/.env):
    python scripts/corpus_export.py --ids 816 819 941 944 954
    python scripts/corpus_export.py --search lasaulec          # alleen kandidaten tonen
    python scripts/corpus_export.py --search lasaulec --export-hits

Output: tests/corpus/sources/order_<id>.json (envelope + order_state, binaire
sleutels gestript — raw PDF-bytes zitten toch niet in de opgeslagen state).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND / "tests" / "corpus" / "sources"

# Prod-URL rechtstreeks uit .env — bewust GEEN kwabo.config-import (zie docstring).
PROD_URL = None
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _l.strip().startswith("DATABASE_URL="):
        PROD_URL = _l.split("=", 1)[1].strip().strip('"').strip("'")
        break
assert PROD_URL and not PROD_URL.startswith("sqlite"), "verwacht prod Postgres in backend/.env"

from sqlalchemy import create_engine, text  # noqa: E402

# Binaire/zware sleutels zonder matching-signaal (zelfde lijst als export_order_states.py).
STRIP_KEYS = {"raw", "inhoud_b64", "content_b64", "data"}

SELECT_COLS = "id, email_from, email_subject, email_date, status, order_state"


def _strip_binary(state: dict) -> dict:
    for b in state.get("bijlagen") or []:
        if isinstance(b, dict):
            for k in list(b):
                if k in STRIP_KEYS:
                    b.pop(k)
    return state


def _export(row) -> None:
    oid, email_from, subject, email_date, status, raw_state = row
    if not raw_state:
        print(f"  !! order {oid}: geen order_state — overgeslagen")
        return
    state = _strip_binary(json.loads(raw_state) if isinstance(raw_state, str) else raw_state)
    heeft_pdf = any("%PDF" in (b.get("inhoud_tekst") or "")[:16] for b in (state.get("bijlagen") or [])
                    if isinstance(b, dict)) or "%PDF" in (state.get("email_body") or "")[:200000]
    envelope = {
        "order_id": oid,
        "email_from": email_from,
        "email_subject": subject,
        "email_date": str(email_date or ""),
        "status": status,
        "order_state": state,
    }
    out = OUT_DIR / f"order_{oid}.json"
    out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  -> {out.name}  (van: {email_from!r}, onderwerp: {(subject or '')[:60]!r}, "
          f"pdf_in_state={heeft_pdf})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", nargs="*", type=int, default=[])
    ap.add_argument("--search", nargs="*", default=[])
    ap.add_argument("--export-hits", action="store_true",
                    help="zoekterm-hits ook exporteren (default: alleen tonen)")
    ap.add_argument("--per-term", type=int, default=10)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(PROD_URL)
    with engine.connect() as conn:
        if args.ids:
            print(f"== Orders op id: {args.ids}")
            rows = conn.execute(text(
                f"SELECT {SELECT_COLS} FROM order_log WHERE id = ANY(:ids) ORDER BY id"
            ), {"ids": args.ids}).fetchall()
            found = {r[0] for r in rows}
            for missing in sorted(set(args.ids) - found):
                print(f"  !! order {missing}: niet gevonden in prod")
            for row in rows:
                _export(row)
        for term in args.search:
            print(f"== Zoekterm {term!r} (max {args.per_term} recentste)")
            rows = conn.execute(text(
                f"SELECT {SELECT_COLS} FROM order_log "
                "WHERE lower(email_from) LIKE :t OR lower(email_subject) LIKE :t "
                "   OR lower(order_state::text) LIKE :t "
                "ORDER BY id DESC LIMIT :n"
            ), {"t": f"%{term.lower()}%", "n": args.per_term}).fetchall()
            if not rows:
                print("  (geen hits)")
            for row in rows:
                print(f"  #{row[0]}  {str(row[3])[:16]}  van={row[1]!r}  ond={(row[2] or '')[:60]!r}")
                if args.export_hits:
                    _export(row)
    engine.dispose()
    print("\nKlaar (alleen SELECT's uitgevoerd; geschreven naar tests/corpus/sources/).")


if __name__ == "__main__":
    main()
