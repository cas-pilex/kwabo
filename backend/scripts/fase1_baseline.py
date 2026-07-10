"""FASE 1 — RODE BASELINE van de her-diagnose (stap 3 / opdracht 1b).

Draait het golden corpus (tests/corpus/manifest.json, 19 orders) door de
ECHTE pijplijn op de huidige main:
  * verse LLM-extractie met REPRODUCEERBAAR cache-protocol (zie hieronder);
  * echte prod-masterdata, read-only gespiegeld met behoud van schaarste;
  * NAVISION_MODE=mirror (mirror-backed NAV-stub, geen live-creds/writes);
  * geauditeerde judge uit scripts/fase1_judge.py (zelftest:
    tests/test_fase1_judge.py) — Fase A-judge-gaten (mix_uom-vlag,
    aantal-koppeling, compose-capture) zijn daar rood->groen gedicht;
  * voor orders met eml_ondersteunend (alleen #847) draait daarnaast het
    ECHTE Vision-pad via run_on_eml over de .eml-bestanden.

Cache-protocol (llm_cache.py: 'off' schrijft NIETS weg en is dus niet
reproduceerbaar — daarom niet gebruikt):
  run 1 (vers):    --cache-mode on  --cache-dir _upgrade/fase1/llm_cache (LEEG)
  run 2/3 (replay): --cache-mode read-only  (zelfde dir; delta = eigen
                    niet-determinisme van de pipeline)
  run 4 (2e trekking): --cache-mode on --cache-dir _upgrade/fase1/llm_cache2
                    --orders 944 954 941 845 832 (LLM-variantie-maat)

STRICT READ-ONLY t.o.v. prod: identiek mechaniek aan verify_reality.py —
sqlite-env staat VOOR elke kwabo-import; prod wordt alleen via losse
create_engine(PROD).connect()-SELECT's gelezen, nooit .commit().

Usage (vanuit backend/):
  PYTHONPATH=.venv/Lib/site-packages python scripts/fase1_baseline.py \
      --out fase1_run1_vers.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

# --- 1) prod-URL lezen VOOR enige kwabo-import (verify_reality-patroon) ---
PROD_URL = None
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _l.strip().startswith("DATABASE_URL="):
        PROD_URL = _l.split("=", 1)[1].strip().strip('"').strip("'")
        break
assert PROD_URL and not PROD_URL.startswith("sqlite"), "verwacht prod Postgres in .env"

# --- 2) env overschrijven -> wegwerp-sqlite (geen enkele prod-write mogelijk) ---
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'fase1.db').as_posix()}"
os.environ["NAVISION_MODE"] = "mirror"
os.environ["ADMIN_PASSWORD"] = ""
os.environ.setdefault("MAIL_MODE", "log")
os.environ.setdefault("EMAIL_MODE", "file_drop")

# cache-args al vóór de kwabo-import verwerken (llm_cache leest env per call,
# maar we willen ook --no-llm consistent met upgrade_baseline ondersteunen)
_NO_LLM = "--no-llm" in sys.argv

sys.path.insert(0, str(BACKEND / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

import kwabo.db.models  # noqa: E402,F401
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.state import new_state  # noqa: E402
from kwabo.graph.graph import get_ingest_app  # noqa: E402
from kwabo.graph.runner import run_on_eml  # noqa: E402
from kwabo.integrations.navision_api import nav_client_scope  # noqa: E402
from kwabo.config_store import effective_setting  # noqa: E402

from fase1_judge import judge, summarize  # noqa: E402  (geauditeerde judge)

CORPUS = BACKEND / "tests" / "corpus"
OUT_DIR = BACKEND / "_upgrade" / "fase1"

MIRROR = [
    "klantenkaarten", "klant_email_aliases", "klantenkaart_ship_to",
    "artikelkaarten", "artikel_eenheden", "klantenkaart_artikelen",
    "artikel_kruisverwijzing", "artikel_matching_history", "artikel_pallet_kennis",
    "prijsafspraken", "pallet_plaatsen_basis",
]


def mirror_masterdata() -> dict:
    """Spiegel prod-masterdata read-only -> wegwerp-sqlite (verify_reality-patroon)."""
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
                print(f"  !! {tbl}: prod-read faalde ({type(exc).__name__}: {exc})", file=sys.stderr)
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


def _try_pdf_bytes(tekst: str | None) -> bytes | None:
    """Lossless PDF-reconstructie (zelfde criteria als upgrade_baseline.py).

    Fase 1-feit (10-7): geen enkele corpus-bron op schijf haalt dit — de
    %PDF-bytes zitten lossy (U+FFFD) in email_body. De functie blijft staan
    zodat nageleverde bronnen automatisch het Vision-pad pakken."""
    if not tekst or not tekst.startswith("%PDF") or "�" in tekst:
        return None
    try:
        raw = tekst.encode("latin-1")
    except UnicodeEncodeError:
        return None
    if b"%%EOF" not in raw[-2048:]:
        return None
    return raw


def load_source(path: Path) -> tuple[dict, str, dict, dict]:
    """Envelope-JSON -> vers graph-state.

    Retourneert (state, extractie_mode, stored, getrouwheid): getrouwheid
    annoteert eerlijk wat deze bron wel/niet kan bewijzen."""
    env = json.loads(path.read_text(encoding="utf-8"))
    st = env.get("order_state") or {}
    mode = "opgeslagen-extractie" if _NO_LLM else "tekst"
    getrouwheid = {}
    bijlagen = []
    for b in st.get("bijlagen") or []:
        if not isinstance(b, dict):
            continue
        raw = _try_pdf_bytes(b.get("inhoud_tekst")) if (b.get("type") == "pdf") else None
        if raw:
            mode = "vision_reconstructie"
        bijlagen.append({"naam": b.get("naam"), "type": b.get("type"),
                         "inhoud_tekst": b.get("inhoud_tekst"), "raw": raw})
    body = st.get("email_body") or ""
    if body.startswith("%PDF"):
        # Fase 1-herlabeling: PDF-bytes lossy in email_body -> de extractor
        # ziet binaire ruis als bodytekst; Vision niet reproduceerbaar.
        getrouwheid["email_body_bevat_lossy_pdf"] = True
    state = new_state(
        email_id=str(env.get("order_id") or st.get("email_id") or path.stem),
        email_from=env.get("email_from") or "",
        email_subject=env.get("email_subject") or "",
        email_body=body,
        email_date=str(env.get("email_date") or ""),
        bijlagen=bijlagen,
        source_path=st.get("source_path"),
    )
    return state, mode, st, getrouwheid


async def run_order(state: dict, stored: dict | None = None) -> dict:
    if _NO_LLM and stored is not None:
        from kwabo.graph.graph import get_sub_order_app
        for k in ("klantnaam_besteller", "bestelnummer_klant", "taal", "afleveradres",
                  "adres_rollen", "afleverinstructies", "opmerkingen", "orderregels",
                  "gewenste_leverdatum", "verzendwijze", "_meta"):
            if k in stored:
                state[k] = stored[k]
        state["is_order"] = True
        app = get_sub_order_app()
    else:
        app = get_ingest_app()
    async with nav_client_scope():
        return await app.ainvoke(state)


async def run_eml(path: Path) -> dict:
    async with nav_client_scope():
        return await run_on_eml(str(path))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", nargs="*", help="subset van corpus-order-ids")
    ap.add_argument("--no-llm", action="store_true",
                    help="opgeslagen extractie; alleen deterministische lagen (debug)")
    ap.add_argument("--out", default="fase1_run.json", help="uitvoerbestand in _upgrade/fase1/")
    ap.add_argument("--cache-mode", default="on", choices=["on", "read-only", "off"],
                    help="LLM_CACHE_MODE: on=vers+vastleggen, read-only=replay")
    ap.add_argument("--cache-dir", default=str(OUT_DIR / "llm_cache"),
                    help="LLM_CACHE_DIR (run 1/2/3 zelfde dir; run 4 een tweede)")
    ap.add_argument("--skip-eml", action="store_true",
                    help="eml_ondersteunend-bronnen (Vision-pad) overslaan")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    Path(args.cache_dir).mkdir(parents=True, exist_ok=True)
    os.environ["LLM_CACHE_MODE"] = "on" if _NO_LLM else args.cache_mode
    os.environ["LLM_CACHE_DIR"] = args.cache_dir
    n_cache_voor = len(list(Path(args.cache_dir).glob("*.json")))

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))["orders"]
    gt_all = json.loads((CORPUS / "ground_truth.json").read_text(encoding="utf-8"))
    oids = [o for o in manifest if not o.startswith("_")]
    if args.orders:
        oids = [o for o in oids if o in set(args.orders)]

    git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BACKEND.parent,
                              capture_output=True, text=True, check=False).stdout.strip()

    print("== Spiegel prod-masterdata -> wegwerp-sqlite (read-only) ==", file=sys.stderr)
    counts = mirror_masterdata()
    for t, n in counts.items():
        print(f"     {t:<28} {n}", file=sys.stderr)
    print(f"   sqlite: {settings.database_url}", file=sys.stderr)
    print(f"   cache: mode={os.environ['LLM_CACHE_MODE']} dir={args.cache_dir} "
          f"(entries vooraf: {n_cache_voor})", file=sys.stderr)

    results = []
    print(f"\n== {len(oids)} corpus-orders door de ECHTE pijplijn ==", file=sys.stderr)
    for oid in oids:
        m = manifest[oid]
        src = BACKEND / m["bron"]
        print(f"  -> #{oid} {m['label']}", file=sys.stderr)
        try:
            state, mode, stored, getrouwheid = load_source(src)
            out = await run_order(state, stored)
        except Exception as exc:  # noqa: BLE001
            print(f"     !! crash: {type(exc).__name__}: {exc}", file=sys.stderr)
            results.append({"order": oid, "label": m["label"], "bron_type": m["bron_type"],
                            "crash": f"{type(exc).__name__}: {exc}"})
            continue
        s = summarize(out)
        oordeel = judge(out, gt_all.get(oid))
        results.append({"order": oid, "label": m["label"], "bron_type": m["bron_type"],
                        "extractie_mode": mode, "getrouwheid": getrouwheid,
                        "categorieen": m.get("categorieen", []),
                        "samenvatting": s, "oordeel": oordeel})
        niet_juist = [v for v in oordeel.get("velden", []) if v.get("oordeel") != "JUIST"]
        print(f"     {oordeel.get('status')}"
              + (f" -> {niet_juist}" if niet_juist else ""), file=sys.stderr)

        # Vision-pad: echte .eml's (alleen #847 heeft die op schijf).
        if not args.skip_eml and not _NO_LLM:
            for rel in m.get("eml_ondersteunend") or []:
                eml_path = BACKEND / rel
                if not eml_path.exists():
                    print(f"     !! eml ontbreekt: {rel}", file=sys.stderr)
                    continue
                print(f"  -> #{oid} VISION via {eml_path.name}", file=sys.stderr)
                try:
                    out_e = await run_eml(eml_path)
                except Exception as exc:  # noqa: BLE001
                    print(f"     !! crash: {type(exc).__name__}: {exc}", file=sys.stderr)
                    results.append({"order": oid, "variant": f"eml:{eml_path.name}",
                                    "crash": f"{type(exc).__name__}: {exc}"})
                    continue
                s_e = summarize(out_e)
                # eml_ondersteunend = zelfde FAMILIE (shared mailbox), niet
                # dezelfde order: de WD-.eml's zijn bestelnr 4401054959 resp.
                # een non-order (test_data/expected). Judgen tegen de GT van
                # #847 gaf 5 valse stille fouten (run 1a) -> observatie.
                oordeel_e = judge(out_e, None)
                results.append({"order": oid, "variant": f"eml:{eml_path.name}",
                                "label": m["label"], "bron_type": "echt_eml",
                                "extractie_mode": "vision_eml_echt",
                                "gt_status": "geen (familie-order, niet dezelfde order)",
                                "categorieen": m.get("categorieen", []),
                                "samenvatting": s_e, "oordeel": oordeel_e})
                niet_juist = [v for v in oordeel_e.get("velden", [])
                              if v.get("oordeel") != "JUIST"]
                print(f"     {oordeel_e.get('status')}"
                      + (f" -> {niet_juist}" if niet_juist else ""), file=sys.stderr)

    n_stille = sum((r.get("oordeel") or {}).get("n_stille_fouten", 0) for r in results)
    n_review = sum((r.get("oordeel") or {}).get("n_review", 0) for r in results)
    n_ok = sum(1 for r in results if (r.get("oordeel") or {}).get("status") == "JUIST")
    n_geen_gt = sum(1 for r in results
                    if (r.get("oordeel") or {}).get("status") == "geen_grondwaarheid")
    n_crash = sum(1 for r in results if r.get("crash"))
    n_cache_na = len(list(Path(args.cache_dir).glob("*.json")))
    payload = {
        "doel": "FASE 1 RODE BASELINE (her-diagnose) — huidige main, echte pijplijn, geen fixes",
        "run_meta": {
            "git_head": git_head,
            "tijdstip_utc": datetime.now(tz=timezone.utc).isoformat(),
            "model": effective_setting("anthropic_model", settings.anthropic_model),
            "llm_cache_mode": os.environ["LLM_CACHE_MODE"],
            "llm_cache_dir": args.cache_dir,
            "cache_entries_voor": n_cache_voor,
            "cache_entries_na": n_cache_na,
            "navision_mode": os.environ.get("NAVISION_MODE"),
            "judge": "fase1_judge.py (geauditeerd; zelftest tests/test_fase1_judge.py)",
        },
        "n": len(results), "masterdata_counts": counts,
        "stille_fouten_totaal": n_stille, "fout_met_vlag_totaal": n_review,
        "orders_juist": n_ok, "geen_grondwaarheid": n_geen_gt, "crashes": n_crash,
        "orders": results,
    }
    out_file = OUT_DIR / args.out
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n# RESULTAAT -> {out_file}", file=sys.stderr)
    print(f"#   stille fouten: {n_stille} | fout-met-vlag: {n_review} | juist: {n_ok} | "
          f"geen-GT: {n_geen_gt} | crashes: {n_crash} | cache {n_cache_voor}->{n_cache_na}",
          file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
