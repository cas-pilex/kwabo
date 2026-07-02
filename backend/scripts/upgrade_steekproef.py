"""D2 — BREDE STEEKPROEF (structurele upgrade, Fase D).

Draait niet-corpus prod-orders VERS door de echte pijplijn (LLM_CACHE_MODE=off,
mirror-NAV, prod read-only — identiek mechaniek aan upgrade_baseline.py) en
beoordeelt ze tegen de MENSELIJK GOEDGEKEURDE uitkomst: voor orders met status
'pushed' is de opgeslagen state door de reviewer bevestigd en naar NAV gegaan —
dat is de sterkst beschikbare grondwaarheid buiten het corpus.

Pseudo-GT per pushed order: klant_nr, ship_to_gekozen en per regel het
NAV-resultaat (mix_uom/mix_aantal > verkoop_uom/verkoop_aantal, artikel =
matched). Review-orders (nog niet goedgekeurd) draaien beschrijvend mee:
daar telt de strenge definitie (crash / unmatched-regel zonder vlag /
confident-klant zonder vlag buiten e-mail-bron) — handmatig toegelicht in
het rapport.

Usage: python scripts/upgrade_steekproef.py --pushed 814 567 537 522 516 121 120 --review 5
Output: backend/_upgrade/steekproef.json
"""
from __future__ import annotations

import argparse
import asyncio
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

os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'steekproef.db').as_posix()}"
os.environ["NAVISION_MODE"] = "mirror"
os.environ["ADMIN_PASSWORD"] = ""
os.environ.setdefault("MAIL_MODE", "log")
os.environ.setdefault("EMAIL_MODE", "file_drop")
os.environ["LLM_CACHE_MODE"] = "off"

sys.path.insert(0, str(BACKEND / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

from kwabo.graph.state import new_state  # noqa: E402
from kwabo.graph.graph import get_ingest_app  # noqa: E402
from kwabo.integrations.navision_api import nav_client_scope  # noqa: E402

# Herbruik de bewezen bouwstenen van de corpus-runner (zelfde judge-regels).
sys.path.insert(0, str(BACKEND / "scripts"))
_CORPUS_IDS = {"944", "954", "941", "847", "819", "845", "203", "816",
               "832", "833", "834", "716", "717", "718", "721", "707", "685"}

OUT_DIR = BACKEND / "_upgrade"

MIRROR = [
    "klantenkaarten", "klant_email_aliases", "klantenkaart_ship_to",
    "artikelkaarten", "artikel_eenheden", "klantenkaart_artikelen",
    "artikel_kruisverwijzing", "artikel_matching_history", "artikel_pallet_kennis",
    "prijsafspraken", "pallet_plaatsen_basis",
]


def mirror_masterdata() -> dict:
    from sqlmodel import SQLModel
    import kwabo.db.models  # noqa: F401
    from kwabo.db.session import engine, init_db
    init_db()
    counts: dict[str, int] = {}
    prod = create_engine(PROD_URL)
    with prod.connect() as pc:
        for tbl in MIRROR:
            if tbl not in SQLModel.metadata.tables:
                counts[tbl] = -1
                continue
            try:
                rows = pc.execute(text(f"SELECT * FROM {tbl}")).mappings().all()
            except Exception as exc:  # noqa: BLE001
                counts[tbl] = -2
                print(f"  !! {tbl}: prod-read faalde ({type(exc).__name__})", file=sys.stderr)
                continue
            table = SQLModel.metadata.tables[tbl]
            cols = {c.name for c in table.columns}
            data = [{k: v for k, v in r.items() if k in cols} for r in rows]
            if data:
                with engine.begin() as sc:
                    sc.execute(table.insert(), data)
            counts[tbl] = len(data)
    prod.dispose()
    return counts


def pull(oids: list[int], extra_review: int) -> list[dict]:
    prod = create_engine(PROD_URL)
    envs: list[dict] = []
    with prod.connect() as pc:
        if oids:
            for r in pc.execute(text(
                "SELECT id,email_from,email_subject,email_date,status,order_state "
                "FROM order_log WHERE id = ANY(:i) ORDER BY id DESC"), {"i": oids}).mappings():
                envs.append(dict(r))
        if extra_review:
            for r in pc.execute(text(
                "SELECT id,email_from,email_subject,email_date,status,order_state "
                "FROM order_log WHERE status='review' ORDER BY id DESC LIMIT :n"),
                    {"n": extra_review + len(_CORPUS_IDS)}).mappings():
                if str(r["id"]) in _CORPUS_IDS:
                    continue
                envs.append(dict(r))
                if sum(1 for e in envs if e["status"] == "review") >= extra_review:
                    break
    prod.dispose()
    return envs


def pseudo_gt(stored: dict, klant_nr: str | None) -> dict:
    """GT uit de menselijk goedgekeurde state. Alleen velden met echte waarde."""
    regels = []
    for r in stored.get("orderregels") or []:
        eenheid = r.get("mix_uom_gekozen") or r.get("verkoop_uom_gekozen")
        aantal = r.get("mix_aantal") if r.get("mix_uom_gekozen") else r.get("verkoop_aantal")
        regels.append({
            "pos": r.get("positie"),
            "artikel": r.get("artikelnummer_kwabo_matched"),
            "eenheid": eenheid,   # None -> niet gejudged (oude runs zonder Branch A)
            "aantal": aantal,
        })
    return {
        "klant_nr": klant_nr,
        "ship_to_code": stored.get("ship_to_gekozen"),
        "regels": regels,
    }


def build_state(env: dict) -> dict:
    st = json.loads(env["order_state"]) if isinstance(env["order_state"], str) else env["order_state"]
    bij = [{"naam": b.get("naam"), "type": b.get("type"),
            "inhoud_tekst": b.get("inhoud_tekst"), "raw": None}
           for b in (st.get("bijlagen") or []) if isinstance(b, dict)]
    s = new_state(
        email_id=str(env["id"]),
        email_from=env.get("email_from") or "",
        email_subject=env.get("email_subject") or "",
        email_body=st.get("email_body") or "",
        email_date=str(env.get("email_date") or ""),
        bijlagen=bij, source_path=st.get("source_path"),
    )
    return s, st


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pushed", nargs="*", type=int, default=[814, 567, 537, 522, 516, 121, 120])
    ap.add_argument("--review", type=int, default=5)
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    # judge/summarize van de corpus-runner hergebruiken (zelfde strenge regels).
    # upgrade_baseline heeft top-level env-setup; onze env staat al, en zijn
    # os.environ-overrides raken de al-geïmporteerde settings/engine niet.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ub", BACKEND / "scripts" / "upgrade_baseline.py")
    ub = importlib.util.module_from_spec(spec)
    sys.argv = [sys.argv[0]]  # laat zijn --no-llm-sniffing niets zien
    spec.loader.exec_module(ub)

    print("== Spiegel prod-masterdata (read-only) ==", file=sys.stderr)
    counts = mirror_masterdata()
    envs = pull(args.pushed, args.review)
    print(f"== {len(envs)} steekproef-orders vers door de pijplijn ==", file=sys.stderr)

    results = []
    app = get_ingest_app()
    for env in envs:
        oid = env["id"]
        print(f"  -> #{oid} [{env['status']}] {(env.get('email_subject') or '')[:50]}", file=sys.stderr)
        try:
            state, stored = build_state(env)
            async with nav_client_scope():
                out = await app.ainvoke(state)
        except Exception as exc:  # noqa: BLE001
            print(f"     !! crash: {type(exc).__name__}: {exc}", file=sys.stderr)
            results.append({"order": oid, "status_prod": env["status"],
                            "crash": f"{type(exc).__name__}: {exc}"})
            continue
        gt = pseudo_gt(stored, env.get("klant_nr") or (stored.get("klant_match") or {}).get("navision_klantnr")) \
            if env["status"] == "pushed" else None
        # klant_nr kolom zit niet in de SELECT — haal uit stored state.
        if gt is not None and not gt["klant_nr"]:
            gt["klant_nr"] = (stored.get("klant_match") or {}).get("navision_klantnr")
        oordeel = ub.judge(out, gt)
        s = ub.summarize(out)
        results.append({"order": oid, "status_prod": env["status"],
                        "gt_bron": "menselijk goedgekeurd (pushed)" if gt else "geen (beschrijvend)",
                        "samenvatting": s, "oordeel": oordeel})
        niet = [v for v in oordeel.get("velden", []) if v.get("oordeel") != "JUIST"]
        print(f"     {oordeel.get('status')}" + (f" -> {niet}" if niet else ""), file=sys.stderr)

    n_stil = sum((r.get("oordeel") or {}).get("n_stille_fouten", 0) for r in results)
    payload = {"doel": "D2 brede steekproef", "n": len(results),
               "masterdata_counts": counts, "stille_fouten_totaal": n_stil,
               "orders": results}
    (OUT_DIR / "steekproef.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n# RESULTAAT -> {OUT_DIR/'steekproef.json'} | stille fouten: {n_stil}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
