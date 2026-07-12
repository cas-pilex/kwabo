"""FASE 1 PRE-FLIGHT — definitieve her-diagnose, stap 0 (STRICT READ-ONLY).

Doel: meetbasis vastpinnen VOORDAT er iets gemeten wordt:
  * git-anker (verwacht cd190a6 + schone tree, anders NO-GO);
  * prod-masterdata-drift sinds de 2-7-meting: count + kolommenset per
    mirror-tabel, gediffed tegen de referentie uit _upgrade/baseline.json;
  * bestaat/vult prod inmiddels pallet_plaatsen_basis?
  * preconditions: ANTHROPIC_API_KEY aanwezig (niet geprint), sqlite-override
    actief na kwabo-import.

STRICT READ-ONLY t.o.v. prod: identiek mechaniek aan verify_reality.py /
upgrade_baseline.py — sqlite-env staat VOOR elke kwabo-import; prod wordt
alleen via losse create_engine(PROD).connect()-SELECT's gelezen, nooit
.commit().

VERBODEN alternatieven (geen guard): run_all.py, run_all_with_push.py,
run_e2e_10x.py, verify_t12.py, seed_pallet_history.py,
sync_navision_masters.py, backfill_incoming_docs_to_supabase.py.

Usage (vanuit backend/):
  PYTHONPATH=.venv/Lib/site-packages python scripts/fase1_preflight.py
Output:
  backend/_upgrade/fase1/preflight.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND = Path(__file__).resolve().parents[1]

# --- 1) prod-URL lezen VOOR enige kwabo-import (verify_reality-patroon) ---
PROD_URL = None
ANTHROPIC_KEY_AANWEZIG = False
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    s = _l.strip()
    if s.startswith("DATABASE_URL="):
        PROD_URL = s.split("=", 1)[1].strip().strip('"').strip("'")
    if s.startswith("ANTHROPIC_API_KEY=") and len(s.split("=", 1)[1].strip()) > 10:
        ANTHROPIC_KEY_AANWEZIG = True
assert PROD_URL and not PROD_URL.startswith("sqlite"), "verwacht prod Postgres in .env"

# --- 2) env overschrijven -> wegwerp-sqlite (geen enkele prod-write mogelijk) ---
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'preflight.db').as_posix()}"
os.environ["NAVISION_MODE"] = "mirror"
os.environ["ADMIN_PASSWORD"] = ""
os.environ.setdefault("MAIL_MODE", "log")
os.environ.setdefault("EMAIL_MODE", "file_drop")

sys.path.insert(0, str(BACKEND / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

MIRROR = [
    "klantenkaarten", "klant_email_aliases", "klantenkaart_ship_to",
    "artikelkaarten", "artikel_eenheden", "klantenkaart_artikelen",
    "artikel_kruisverwijzing", "artikel_matching_history", "artikel_pallet_kennis",
    "prijsafspraken", "pallet_plaatsen_basis",
]

# Referentie-tellingen uit de 2-7-meting (backend/_upgrade/baseline.json,
# masterdata_counts). -2 = prod-read faalde (tabel bestond niet in prod).
REF_2_7 = {
    "klantenkaarten": 1787,
    "klant_email_aliases": 1,
    "klantenkaart_ship_to": 2506,
    "artikelkaarten": 3757,
    "artikel_eenheden": 12963,
    "klantenkaart_artikelen": 24,
    "artikel_kruisverwijzing": 3000,
    "artikel_matching_history": 24,
    "artikel_pallet_kennis": 19,
    "prijsafspraken": 0,
    "pallet_plaatsen_basis": -2,
}


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=BACKEND.parent, capture_output=True, text=True, check=False,
    ).stdout.strip()


def main() -> None:
    out_dir = BACKEND / "_upgrade" / "fase1"
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- git-anker --
    head = _git(["rev-parse", "HEAD"])
    dirty = _git(["status", "--porcelain"])
    # eigen meetgereedschap (scripts/fase1_*.py, nog uncommitted) telt niet als drift
    dirty_relevant = [
        l for l in dirty.splitlines()
        if l.strip() and "scripts/fase1_" not in l and ".claude/" not in l
    ]
    git_ok = head.startswith("cd190a6") and not dirty_relevant
    print(f"== git-anker: {head[:12]}  schoon={not dirty_relevant} ==", file=sys.stderr)
    if dirty_relevant:
        for l in dirty_relevant[:20]:
            print(f"   !! niet-schoon: {l}", file=sys.stderr)

    # -- prod read-only: counts + kolommen --
    print("== prod-masterdata (STRICT READ-ONLY, alleen SELECT) ==", file=sys.stderr)
    counts: dict[str, int] = {}
    kolommen: dict[str, list[str]] = {}
    prod = create_engine(PROD_URL)
    with prod.connect() as pc:
        for tbl in MIRROR:
            try:
                counts[tbl] = pc.execute(text(f"SELECT count(*) FROM {tbl}")).scalar_one()
                cols = pc.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t ORDER BY column_name"), {"t": tbl}).scalars().all()
                kolommen[tbl] = list(cols)
            except Exception as exc:  # noqa: BLE001
                counts[tbl] = -2
                kolommen[tbl] = []
                print(f"   !! {tbl}: prod-read faalde ({type(exc).__name__})", file=sys.stderr)
    prod.dispose()

    drift = {}
    for tbl in MIRROR:
        ref, nu = REF_2_7.get(tbl), counts.get(tbl)
        status = "GELIJK" if ref == nu else "DRIFT"
        drift[tbl] = {"2_7": ref, "nu": nu, "status": status}
        print(f"   {tbl:<28} 2-7={ref:>6}  nu={nu:>6}  {status}", file=sys.stderr)

    payload = {
        "doel": "FASE 1 pre-flight (stap 0) — meetbasis + prod-drift, read-only",
        "git_head": head,
        "git_schoon": not dirty_relevant,
        "git_dirty_regels": dirty_relevant,
        "git_ok": git_ok,
        "anthropic_key_aanwezig": ANTHROPIC_KEY_AANWEZIG,
        "sqlite_override": settings.database_url,
        "navision_mode": os.environ.get("NAVISION_MODE"),
        "counts_nu": counts,
        "counts_2_7": REF_2_7,
        "drift": drift,
        "kolommen": kolommen,
        "pallet_plaatsen_basis_in_prod": counts.get("pallet_plaatsen_basis", -2) >= 0,
    }
    out = out_dir / "preflight.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    n_drift = sum(1 for d in drift.values() if d["status"] == "DRIFT")
    print(f"\n# RESULTAAT -> {out}", file=sys.stderr)
    print(f"#   git_ok={git_ok} | anthropic_key={ANTHROPIC_KEY_AANWEZIG} | "
          f"drift-tabellen={n_drift} | pallet_plaatsen_basis_in_prod="
          f"{payload['pallet_plaatsen_basis_in_prod']}", file=sys.stderr)


if __name__ == "__main__":
    main()
