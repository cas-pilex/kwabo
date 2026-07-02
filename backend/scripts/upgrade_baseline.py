"""RODE BASELINE — STRUCTURELE UPGRADE Fase A2.

Draait het golden corpus (tests/corpus/manifest.json) door de ECHTE pijplijn:
  * verse LLM-extractie (LLM_CACHE_MODE=off), volledige ingest-graph;
  * echte prod-masterdata, read-only gespiegeld met behoud van schaarste;
  * NAVISION_MODE=mirror (mirror-backed NAV-stub, geen live-creds/writes);
  * oordeel tegen tests/corpus/ground_truth.json:
        JUIST | FOUT-met-vlag (review) | STILLE-FOUT (fout zonder vlag)
    incl. corpus-uitbreidingen europallet_aantal en verzendwijze.

STRICT READ-ONLY t.o.v. prod: identiek mechaniek aan verify_reality.py —
sqlite-env staat VOOR elke kwabo-import; prod wordt alleen via losse
create_engine(PROD).connect()-SELECT's gelezen, nooit .commit().

Fase A: dit script FIXT niets; het legt vast wat de huidige code doet.

Usage (vanuit backend/):
  python scripts/upgrade_baseline.py               # heel corpus
  python scripts/upgrade_baseline.py --orders 944 954
Output:
  backend/_upgrade/baseline.json  (ruwe, ongesamenvatte per-order output)
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

# --- 1) prod-URL lezen VOOR enige kwabo-import (verify_reality-patroon) ---
PROD_URL = None
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _l.strip().startswith("DATABASE_URL="):
        PROD_URL = _l.split("=", 1)[1].strip().strip('"').strip("'")
        break
assert PROD_URL and not PROD_URL.startswith("sqlite"), "verwacht prod Postgres in .env"

# --- 2) env overschrijven -> wegwerp-sqlite + verse extractie ---
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'baseline.db').as_posix()}"
os.environ["NAVISION_MODE"] = "mirror"
os.environ["ADMIN_PASSWORD"] = ""
os.environ.setdefault("MAIL_MODE", "log")
os.environ.setdefault("EMAIL_MODE", "file_drop")
os.environ["LLM_CACHE_MODE"] = "off"  # het hele punt: extractie draait ECHT

sys.path.insert(0, str(BACKEND / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

import kwabo.db.models  # noqa: E402,F401
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.state import new_state  # noqa: E402
from kwabo.graph.graph import get_ingest_app  # noqa: E402
from kwabo.integrations.navision_api import nav_client_scope  # noqa: E402

CORPUS = BACKEND / "tests" / "corpus"
OUT_DIR = BACKEND / "_upgrade"

MIRROR = [
    "klantenkaarten", "klant_email_aliases", "klantenkaart_ship_to",
    "artikelkaarten", "artikel_eenheden", "klantenkaart_artikelen",
    "artikel_kruisverwijzing", "artikel_matching_history", "artikel_pallet_kennis",
    "prijsafspraken",
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
    """Reconstrueer PDF-bytes uit een tekstveld als dat lossless kan.

    De opgeslagen state bewaart bijlage-inhoud als tekst; alleen als die tekst
    strikt latin-1-encodebaar is, geen U+FFFD-replacement bevat en er een
    %%EOF-marker in zit, is de kans reëel dat het de originele bytes zijn.
    Anders: None (tekst-only pad, geen halfslachtige Vision-input)."""
    if not tekst or not tekst.startswith("%PDF") or "�" in tekst:
        return None
    try:
        raw = tekst.encode("latin-1")
    except UnicodeEncodeError:
        return None
    if b"%%EOF" not in raw[-2048:]:
        return None
    return raw


def load_source(path: Path) -> tuple[dict, str]:
    """Envelope-JSON -> vers graph-state. Retourneert (state, extractie_mode)."""
    env = json.loads(path.read_text(encoding="utf-8"))
    st = env.get("order_state") or {}
    mode = "tekst"
    bijlagen = []
    for b in st.get("bijlagen") or []:
        if not isinstance(b, dict):
            continue
        raw = _try_pdf_bytes(b.get("inhoud_tekst")) if (b.get("type") == "pdf") else None
        if raw:
            mode = "vision_reconstructie"
        bijlagen.append({"naam": b.get("naam"), "type": b.get("type"),
                         "inhoud_tekst": b.get("inhoud_tekst"), "raw": raw})
    state = new_state(
        email_id=str(env.get("order_id") or st.get("email_id") or path.stem),
        email_from=env.get("email_from") or "",
        email_subject=env.get("email_subject") or "",
        email_body=st.get("email_body") or "",
        email_date=str(env.get("email_date") or ""),
        bijlagen=bijlagen,
        source_path=st.get("source_path"),
    )
    return state, mode


# ---------- vastlegging (ongesamenvat) + oordeel ----------
def _norm(v) -> str:
    return "".join(str(v or "").split()).lower()


def regels_view(out: dict) -> list[dict]:
    return [{
        "pos": r.get("positie"),
        "art_klant": r.get("artikelnummer_klant"),
        "art_matched": r.get("artikelnummer_kwabo_matched") or r.get("artikelnummer_kwabo"),
        "oms": (r.get("omschrijving") or "")[:48],
        "hoeveelheid": r.get("hoeveelheid"),
        "eenheid": r.get("eenheid"),
        "eenheid_origineel": r.get("eenheid_origineel"),
        "eenheid_default": r.get("eenheid_default"),
        "verkoop_uom": r.get("verkoop_uom_gekozen"),
        "verkoop_aantal": r.get("verkoop_aantal"),
        "mix_uom": r.get("mix_uom_gekozen"),
        "mix_aantal": r.get("mix_aantal"),
        "methode": r.get("match_methode"),
        "conf": r.get("match_confidence"),
    } for r in (out.get("orderregels") or [])]


def summarize(out: dict) -> dict:
    km = out.get("klant_match") or {}
    nrf = out.get("needs_review_fields") or []
    afl = out.get("afleveradres") or {}
    ep = out.get("europallet_regel") or None
    ep_meta = ((out.get("_meta") or {}).get("europallet") or {})
    return {
        "extract": {
            "klantnaam_besteller": out.get("klantnaam_besteller"),
            "bestelnummer_klant": out.get("bestelnummer_klant"),
            "taal": out.get("taal"),
            "afleveradres": {k: afl.get(k) for k in ("naam", "straat", "postcode", "plaats", "land")}
            if isinstance(afl, dict) else afl,
            "verzendwijze": out.get("verzendwijze"),
            "n_regels": len(out.get("orderregels") or []),
        },
        "klant": {"nr": km.get("navision_klantnr"), "naam": km.get("klantnaam"),
                  "bron": km.get("match_bron"), "conf": km.get("match_confidence"),
                  "vlag": "klant_match" in nrf,
                  "kandidaten": [{"nr": k.get("navision_klantnr"), "naam": k.get("klantnaam")}
                                 for k in (out.get("klant_kandidaten") or [])]},
        "ship_to_gekozen": out.get("ship_to_gekozen"),
        "ship_to_kandidaten": [{"code": k.get("ship_to_code"), "pc": k.get("postcode"),
                                "plaats": k.get("plaats")}
                               for k in (out.get("ship_to_kandidaten") or [])],
        "regels": regels_view(out),
        "europallet": {"regel": {k: ep.get(k) for k in ("hoeveelheid", "eenheid", "confidence")}
                       if isinstance(ep, dict) else None,
                       "uitleg": ep_meta.get("uitleg"),
                       "onderbouwing_regels": ep_meta.get("regels")},
        "needs_review_fields": nrf,
        "validatie_warnings": out.get("validatie_warnings") or [],
        "is_order": out.get("is_order"),
    }


def judge(out: dict, gt: dict | None) -> dict:
    """verify_reality.judge + corpus-uitbreidingen europallet_aantal/verzendwijze."""
    if not gt:
        return {"status": "geen_grondwaarheid", "velden": []}
    km = out.get("klant_match") or {}
    nrf = out.get("needs_review_fields") or []
    klant_flagged = "klant_match" in nrf
    afl = out.get("afleveradres") or {}
    velden: list[dict] = []

    def add(naam, juist, gevlagd, verwacht, kreeg):
        if juist:
            velden.append({"veld": naam, "oordeel": "JUIST"})
        elif gevlagd:
            velden.append({"veld": naam, "oordeel": "FOUT-met-vlag", "verwacht": verwacht, "kreeg": kreeg})
        else:
            velden.append({"veld": naam, "oordeel": "STILLE-FOUT", "verwacht": verwacht, "kreeg": kreeg})

    def _has(v):
        return v not in (None, "")

    if _has(gt.get("klant_nr")):
        got = km.get("navision_klantnr")
        add("klant_nr", _norm(got) == _norm(gt["klant_nr"]), klant_flagged, gt["klant_nr"], got)
    if _has(gt.get("afleveradres_postcode")):
        got = (afl.get("postcode") if isinstance(afl, dict) else None)
        st_flag = "ship_to_gekozen" in nrf
        add("afleveradres_postcode", _norm(got) == _norm(gt["afleveradres_postcode"]),
            st_flag, gt["afleveradres_postcode"], got)
    if _has(gt.get("ship_to_code")):
        got = out.get("ship_to_gekozen")
        st_flag = "ship_to_gekozen" in nrf
        add("ship_to_code", _norm(got) == _norm(gt["ship_to_code"]), st_flag, gt["ship_to_code"], got)
    if _has(gt.get("verzendwijze")):
        got = out.get("verzendwijze")
        add("verzendwijze", _norm(got) == _norm(gt["verzendwijze"]), False, gt["verzendwijze"], got)
    if _has(gt.get("europallet_aantal")):
        ep = out.get("europallet_regel") or {}
        got = ep.get("hoeveelheid") if isinstance(ep, dict) else None
        ep_flag = any("europallet" in f for f in nrf)
        try:
            ok = abs(float(got) - float(gt["europallet_aantal"])) < 1e-6
        except (TypeError, ValueError):
            ok = False
        add("europallet_aantal", ok, ep_flag, gt["europallet_aantal"], got)
    gt_regels = {int(r["pos"]): r for r in (gt.get("regels") or []) if r.get("pos") is not None}
    for r in (out.get("orderregels") or []):
        pos = r.get("positie")
        g = gt_regels.get(int(pos)) if pos is not None else None
        if not g:
            continue
        if _has(g.get("eenheid")):
            got = r.get("verkoop_uom_gekozen") or r.get("mix_uom_gekozen") or r.get("eenheid")
            flag = (f"verkoop_eenheid:{pos}" in nrf or f"orderregels[{int(pos)-1}].eenheid" in nrf)
            add(f"regel{pos}.eenheid", _norm(got) == _norm(g["eenheid"]), flag, g["eenheid"], got)
        if _has(g.get("aantal")):
            got = r.get("verkoop_aantal") if r.get("verkoop_aantal") is not None else (
                r.get("mix_aantal") if r.get("mix_aantal") is not None else r.get("hoeveelheid"))
            try:
                ok = abs(float(got) - float(g["aantal"])) < 1e-6
            except (TypeError, ValueError):
                ok = False
            add(f"regel{pos}.aantal", ok, False, g["aantal"], got)
        if _has(g.get("artikel")):
            got = r.get("artikelnummer_kwabo_matched")
            flag = (got is None) or (r.get("match_confidence") or 0) < 0.85 or \
                f"orderregels[{int(pos)-1}].artikelnummer_kwabo_matched" in nrf
            add(f"regel{pos}.artikel", _norm(got) == _norm(g["artikel"]), flag, g["artikel"], got)

    stille = [v for v in velden if v["oordeel"] == "STILLE-FOUT"]
    review = [v for v in velden if v["oordeel"] == "FOUT-met-vlag"]
    status = "STILLE-FOUT" if stille else ("review" if review else "JUIST")
    return {"status": status, "velden": velden,
            "n_stille_fouten": len(stille), "n_review": len(review)}


async def run_order(state: dict) -> dict:
    app = get_ingest_app()
    async with nav_client_scope():
        return await app.ainvoke(state)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", nargs="*", help="subset van corpus-order-ids")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))["orders"]
    gt_all = json.loads((CORPUS / "ground_truth.json").read_text(encoding="utf-8"))
    oids = [o for o in manifest if not o.startswith("_")]
    if args.orders:
        oids = [o for o in oids if o in set(args.orders)]

    print("== Spiegel prod-masterdata -> wegwerp-sqlite (read-only) ==", file=sys.stderr)
    counts = mirror_masterdata()
    for t, n in counts.items():
        print(f"     {t:<28} {n}", file=sys.stderr)
    print(f"   sqlite: {settings.database_url}", file=sys.stderr)

    results = []
    print(f"\n== {len(oids)} corpus-orders door de ECHTE pijplijn (verse extractie) ==", file=sys.stderr)
    for oid in oids:
        m = manifest[oid]
        src = BACKEND / m["bron"].replace("tests/", "tests/", 1)
        print(f"  -> #{oid} {m['label']}", file=sys.stderr)
        try:
            state, mode = load_source(src)
            out = await run_order(state)
        except Exception as exc:  # noqa: BLE001
            print(f"     !! crash: {type(exc).__name__}: {exc}", file=sys.stderr)
            results.append({"order": oid, "label": m["label"], "bron_type": m["bron_type"],
                            "crash": f"{type(exc).__name__}: {exc}"})
            continue
        s = summarize(out)
        oordeel = judge(out, gt_all.get(oid))
        results.append({"order": oid, "label": m["label"], "bron_type": m["bron_type"],
                        "extractie_mode": mode, "categorieen": m.get("categorieen", []),
                        "samenvatting": s, "oordeel": oordeel})
        niet_juist = [v for v in oordeel.get("velden", []) if v.get("oordeel") != "JUIST"]
        print(f"     {oordeel.get('status')}"
              + (f" -> {niet_juist}" if niet_juist else ""), file=sys.stderr)

    n_stille = sum((r.get("oordeel") or {}).get("n_stille_fouten", 0) for r in results)
    n_review = sum((r.get("oordeel") or {}).get("n_review", 0) for r in results)
    n_ok = sum(1 for r in results if (r.get("oordeel") or {}).get("status") == "JUIST")
    n_crash = sum(1 for r in results if r.get("crash"))
    payload = {
        "doel": "RODE BASELINE (Fase A2) — huidige code, echte pijplijn, geen fixes",
        "n": len(results), "masterdata_counts": counts,
        "stille_fouten_totaal": n_stille, "fout_met_vlag_totaal": n_review,
        "orders_juist": n_ok, "crashes": n_crash,
        "orders": results,
    }
    out_file = OUT_DIR / "baseline.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n# RESULTAAT -> {out_file}", file=sys.stderr)
    print(f"#   stille fouten: {n_stille} | fout-met-vlag: {n_review} | juist: {n_ok}/{len(results)} | crashes: {n_crash}",
          file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
