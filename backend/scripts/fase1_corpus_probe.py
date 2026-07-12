"""FASE 1 stap 1 — corpus-probe (STRICT READ-ONLY).

Voor de 7 corpus-orders met eml_nalevering=true: check in prod-order_log of
er een incoming_document_storage_key in de order_state staat (= .eml bestaat
in Supabase Storage en kan door Cas/OPS worden nageleverd) en of de opgeslagen
bijlagen alsnog %PDF-bytes bevatten.

Zelfde guard-mechaniek als fase1_preflight.py: prod-URL apart gelezen,
DATABASE_URL naar wegwerp-sqlite VOOR kwabo-import, prod alleen SELECT.

Usage (vanuit backend/):
  PYTHONPATH=.venv/Lib/site-packages python scripts/fase1_corpus_probe.py
Output:
  backend/_upgrade/fase1/corpus_probe.json
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND = Path(__file__).resolve().parents[1]

PROD_URL = None
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _l.strip().startswith("DATABASE_URL="):
        PROD_URL = _l.split("=", 1)[1].strip().strip('"').strip("'")
        break
assert PROD_URL and not PROD_URL.startswith("sqlite"), "verwacht prod Postgres in .env"

os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'probe.db').as_posix()}"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(BACKEND / "src"))
from sqlalchemy import create_engine, text  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

# corpus-orders met eml_nalevering=true + de 2 observatie-orders
IDS = [944, 954, 941, 819, 845, 203, 816, 619, 712]


def main() -> None:
    out_dir = BACKEND / "_upgrade" / "fase1"
    out_dir.mkdir(parents=True, exist_ok=True)
    prod = create_engine(PROD_URL)
    rows = []
    with prod.connect() as pc:
        res = pc.execute(text(
            "SELECT id, email_id, email_from, email_subject, order_state "
            "FROM order_log WHERE id = ANY(:ids)"), {"ids": IDS}).fetchall()
    prod.dispose()

    for oid, email_id, efrom, subj, state_json in res:
        st = json.loads(state_json) if state_json else {}
        bijlagen = st.get("bijlagen") or []
        pdf_bytes = any(
            isinstance(b, dict) and str(b.get("inhoud_tekst") or "").startswith("%PDF")
            for b in bijlagen
        )
        rows.append({
            "order": oid,
            "email_id": email_id,
            "email_from": efrom,
            "email_subject": subj,
            "storage_key": st.get("incoming_document_storage_key"),
            "incoming_document_path": st.get("incoming_document_path"),
            "n_bijlagen": len(bijlagen),
            "bijlage_pdf_bytes": pdf_bytes,
        })
        print(f"  #{oid}: storage_key={st.get('incoming_document_storage_key')!r} "
              f"pdf_bytes_in_state={pdf_bytes} bijlagen={len(bijlagen)}", file=sys.stderr)

    gevonden = {r["order"] for r in rows}
    for oid in IDS:
        if oid not in gevonden:
            rows.append({"order": oid, "ontbreekt_in_order_log": True})
            print(f"  #{oid}: NIET GEVONDEN in order_log", file=sys.stderr)

    out = out_dir / "corpus_probe.json"
    out.write_text(json.dumps({"doel": "eml-naleveringsprobe (read-only)", "orders": rows},
                              ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"# RESULTAAT -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
