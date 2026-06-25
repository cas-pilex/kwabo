"""WERKELIJKHEID-HARNESS — meet de ECHTE pijplijn zoals het team hem ervaart.

Bewust het tegenovergestelde van de oude verify_*-scripts:
  * LLM_CACHE_MODE=off  -> extractie draait ECHT (geen bevroren orderregels).
  * Raw .eml-modus      -> volledige Vision-extractie over de PDF-bytes.
  * Mirror = read-only prod-masterdata MET PROD-SCHAARSTE (NULL's niet aanvullen).
  * Oordeel = vergelijking met GRONDWAARHEID (_reality/ground_truth.json):
        JUIST | FOUT-met-vlag (review) | STILLE FOUT (fout zonder vlag).

STRICT READ-ONLY t.o.v. prod: sqlite-env staat VOOR elke kwabo-import; prod wordt
alleen via een losse create_engine(PROD).connect()-SELECT gelezen, nooit .commit().

Modi:
  python scripts/verify_reality.py --eml <pad-of-map>   # verse raw .eml's (Vision)
  python scripts/verify_reality.py --orders 954 944 941 # opgeslagen prod-orders
                                                        #   (TEKST-ONLY extractie:
                                                        #    raw PDF-bytes ontbreken
                                                        #    in de opgeslagen state)
  python scripts/verify_reality.py --orders-file ids.txt
Opties:
  --no-llm   : extractie NIET opnieuw draaien (gebruik opgeslagen extractie) —
               alleen matching/review meten; sneller/gratis. Default = vers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Console kan ⚠/zero-width niet aan op cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BACKEND = Path(__file__).resolve().parents[1]

# --- 1) prod-URL lezen VOOR enige kwabo-import ---
PROD_URL = None
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _l.strip().startswith("DATABASE_URL="):
        PROD_URL = _l.split("=", 1)[1].strip().strip('"').strip("'")
        break
assert PROD_URL and not PROD_URL.startswith("sqlite"), "verwacht prod Postgres in .env"

# --- 2) env overschrijven -> wegwerp-sqlite + verse extractie ---
_ARGV = sys.argv
_NO_LLM = "--no-llm" in _ARGV
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'reality.db').as_posix()}"
os.environ["NAVISION_MODE"] = "mirror"  # mirror-backed NAV-stub: get_item/search uit gesyncde mirror
                                        # (geen demo-vervuiling, geen live-creds nodig)
os.environ["ADMIN_PASSWORD"] = ""
os.environ.setdefault("MAIL_MODE", "log")
os.environ.setdefault("EMAIL_MODE", "file_drop")
# DIT is het hele punt: extractie mag NIET uit de cache komen (tenzij --no-llm).
os.environ["LLM_CACHE_MODE"] = "on" if _NO_LLM else "off"

sys.path.insert(0, str(BACKEND / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

import kwabo.db.models  # noqa: E402,F401  (registreert alle tabellen)
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.state import new_state  # noqa: E402
from kwabo.graph.graph import get_ingest_app  # noqa: E402
from kwabo.graph.runner import run_on_eml  # noqa: E402
from kwabo.integrations.navision_api import nav_client_scope  # noqa: E402

OUT = BACKEND / "_reality"
GT_PATH = OUT / "ground_truth.json"

# Alle matchings-tabellen — prod-schaarste blijft behouden (geen aanvulling).
MIRROR = [
    "klantenkaarten", "klant_email_aliases", "klantenkaart_ship_to",
    "artikelkaarten", "artikel_eenheden", "klantenkaart_artikelen",
    "artikel_kruisverwijzing", "artikel_matching_history", "artikel_pallet_kennis",
    "prijsafspraken",
]

# Bekende ploeg-gerapporteerde + eerder-gevalideerde orders (default-corpus).
DEFAULT_ORDERS = [954, 944, 941]


def mirror_masterdata() -> dict:
    """Spiegel prod-masterdata read-only -> wegwerp-sqlite. Retourneer rij-tellingen
    zodat schaarste (lege/NULL tabellen) zichtbaar is in het rapport."""
    init_db()
    counts: dict[str, int] = {}
    prod = create_engine(PROD_URL)
    with prod.connect() as pc:
        for tbl in MIRROR:
            if tbl not in SQLModel.metadata.tables:
                counts[tbl] = -1  # tabel onbekend in metadata
                continue
            try:
                rows = pc.execute(text(f"SELECT * FROM {tbl}")).mappings().all()
            except Exception as exc:  # noqa: BLE001
                counts[tbl] = -2  # prod-read faalde
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


def pull_orders(oids: list[int]) -> dict[int, dict]:
    prod = create_engine(PROD_URL)
    with prod.connect() as pc:
        rows = {r["id"]: dict(r) for r in pc.execute(text(
            "SELECT id,email_from,email_subject,email_date,klant_nr,order_state "
            "FROM order_log WHERE id = ANY(:i)"), {"i": list(oids)}).mappings()}
    prod.dispose()
    return rows


def build_state_from_stored(env: dict) -> tuple[dict, dict]:
    raw_os = env["order_state"]
    st = json.loads(raw_os) if isinstance(raw_os, str) else raw_os
    bij = [{"naam": b.get("naam"), "type": b.get("type"),
            "inhoud_tekst": b.get("inhoud_tekst"), "raw": None}
           for b in (st.get("bijlagen") or []) if isinstance(b, dict)]
    s = new_state(
        email_id=st.get("email_id") or str(env["id"]),
        email_from=env.get("email_from") or "",
        email_subject=env.get("email_subject") or "",
        email_body=st.get("email_body") or "",
        email_date=str(env.get("email_date") or ""),
        bijlagen=bij, source_path=st.get("source_path"),
    )
    return s, st


# ---------- normalisatie + oordeel ----------
def _norm(v) -> str:
    return "".join(str(v or "").split()).lower()


def _norm_pc(v) -> str:
    return "".join(str(v or "").split()).lower()


def regels_view(out: dict) -> list[dict]:
    return [{
        "pos": r.get("positie"),
        "art_klant": r.get("artikelnummer_klant"),
        "art": r.get("artikelnummer_kwabo_matched") or r.get("artikelnummer_kwabo"),
        "oms": (r.get("omschrijving") or "")[:40],
        "hoeveelheid": r.get("hoeveelheid"),
        "eenheid": r.get("eenheid"),
        "verkoop_uom": r.get("verkoop_uom_gekozen"),
        "verkoop_aantal": r.get("verkoop_aantal"),
        "mix_uom": r.get("mix_uom_gekozen"),
        "methode": r.get("match_methode"),
        "conf": r.get("match_confidence"),
    } for r in (out.get("orderregels") or [])]


def summarize(out: dict) -> dict:
    km = out.get("klant_match") or {}
    nrf = out.get("needs_review_fields") or []
    afl = out.get("afleveradres") or {}
    return {
        "extract": {
            "klantnaam_besteller": out.get("klantnaam_besteller"),
            "bestelnummer_klant": out.get("bestelnummer_klant"),
            "taal": out.get("taal"),
            "afleveradres": {k: afl.get(k) for k in ("naam", "straat", "postcode", "plaats")}
            if isinstance(afl, dict) else afl,
            "n_regels": len(out.get("orderregels") or []),
        },
        "klant": {"nr": km.get("navision_klantnr"), "naam": km.get("klantnaam"),
                  "bron": km.get("match_bron"), "conf": km.get("match_confidence"),
                  "vlag": "klant_match" in nrf,
                  "n_kandidaten": len(out.get("klant_kandidaten") or [])},
        "ship_to_gekozen": out.get("ship_to_gekozen"),
        "ship_to_kandidaten": [{"code": k.get("ship_to_code"), "pc": k.get("postcode"),
                                "plaats": k.get("plaats")}
                               for k in (out.get("ship_to_kandidaten") or [])],
        "regels": regels_view(out),
        "needs_review_fields": nrf,
        "validatie_warnings": out.get("validatie_warnings") or [],
        "is_order": out.get("is_order"),
    }


def judge(out: dict, gt: dict | None) -> dict:
    """Vergelijk uitkomst met grondwaarheid. Elk afwijkend veld:
       FOUT-met-vlag (review)  -> veld staat in needs_review_fields / heeft vlag
       STILLE FOUT             -> fout EN niet gevlagd (de gevaarlijke klasse)."""
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

    # Belangrijk: vergelijk ALLEEN velden waarvoor de grondwaarheid een ECHTE
    # waarde heeft. Een ontbrekende/None-GT-waarde betekent "geen grondwaarheid
    # voor dit veld" — die overslaan i.p.v. als 'verwacht leeg' te behandelen
    # (anders telt elke berekende waarde vals als fout).
    def _has(v):
        return v not in (None, "")

    if _has(gt.get("klant_nr")):
        got = km.get("navision_klantnr")
        add("klant_nr", _norm(got) == _norm(gt["klant_nr"]), klant_flagged, gt["klant_nr"], got)
    if _has(gt.get("afleveradres_postcode")):
        got = (afl.get("postcode") if isinstance(afl, dict) else None)
        st_flag = "ship_to_gekozen" in nrf
        add("afleveradres_postcode", _norm_pc(got) == _norm_pc(gt["afleveradres_postcode"]),
            st_flag, gt["afleveradres_postcode"], got)
    if _has(gt.get("ship_to_code")):
        got = out.get("ship_to_gekozen")
        st_flag = "ship_to_gekozen" in nrf
        add("ship_to_code", _norm(got) == _norm(gt["ship_to_code"]), st_flag, gt["ship_to_code"], got)
    # Regels: per positie eenheid + aantal (alleen waar GT een echte waarde heeft)
    gt_regels = {int(r["pos"]): r for r in (gt.get("regels") or []) if r.get("pos") is not None}
    for r in (out.get("orderregels") or []):
        pos = r.get("positie")
        g = gt_regels.get(int(pos)) if pos is not None else None
        if not g:
            continue
        if _has(g.get("eenheid")):
            got = r.get("verkoop_uom_gekozen") or r.get("eenheid")
            flag = (f"verkoop_eenheid:{pos}" in nrf or f"orderregels[{int(pos)-1}].eenheid" in nrf)
            add(f"regel{pos}.eenheid", _norm(got) == _norm(g["eenheid"]), flag, g["eenheid"], got)
        if _has(g.get("aantal")):
            got = r.get("verkoop_aantal")
            try:
                ok = abs(float(got) - float(g["aantal"])) < 1e-6
            except (TypeError, ValueError):
                ok = False
            add(f"regel{pos}.aantal", ok, False, g["aantal"], got)
        if _has(g.get("artikel")):
            got = r.get("artikelnummer_kwabo_matched")
            flag = (got is None) or (r.get("match_confidence") or 0) < 0.85
            add(f"regel{pos}.artikel", _norm(got) == _norm(g["artikel"]), flag, g["artikel"], got)

    stille = [v for v in velden if v["oordeel"] == "STILLE-FOUT"]
    review = [v for v in velden if v["oordeel"] == "FOUT-met-vlag"]
    status = "STILLE-FOUT" if stille else ("review" if review else "JUIST")
    return {"status": status, "velden": velden,
            "n_stille_fouten": len(stille), "n_review": len(review)}


def review_ratio(summary: dict) -> dict:
    """Telt of dit order/zijn regels een review-vlag droegen (voor de 'te veel
    review'-klacht)."""
    nrf = summary.get("needs_review_fields") or []
    n_regels = len(summary.get("regels") or [])
    regel_flags = sum(1 for f in nrf if f.startswith("orderregels[") or f.startswith("verkoop_eenheid:"))
    return {"order_gevlagd": bool(nrf), "n_vlaggen": len(nrf),
            "n_regels": n_regels, "n_regel_vlaggen": regel_flags}


async def run_eml(path: Path) -> dict:
    async with nav_client_scope():
        out = await run_on_eml(str(path))
    return out


async def run_stored(env: dict) -> dict:
    state, stored = build_state_from_stored(env)
    if _NO_LLM:
        # Gebruik de opgeslagen extractie (sla classify+extract over): injecteer
        # de opgeslagen orderregels/velden en draai vanaf match_customer.
        from kwabo.graph.graph import get_sub_order_app
        for k in ("klantnaam_besteller", "bestelnummer_klant", "taal", "afleveradres",
                  "afleverinstructies", "opmerkingen", "orderregels", "gewenste_leverdatum",
                  "verzendwijze", "_meta"):
            if k in stored:
                state[k] = stored[k]
        state["is_order"] = True
        app = get_sub_order_app()
    else:
        app = get_ingest_app()
    async with nav_client_scope():
        out = await app.ainvoke(state)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eml", help="pad naar .eml-bestand of map met .eml's")
    ap.add_argument("--orders", nargs="*", type=int, help="order_log-ids")
    ap.add_argument("--orders-file", help="tekstbestand met één order-id per regel")
    ap.add_argument("--no-llm", action="store_true", help="extractie NIET opnieuw draaien")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    print("== Spiegel prod-masterdata -> wegwerp-sqlite (read-only) ==", file=sys.stderr)
    counts = mirror_masterdata()
    print("   masterdata-tellingen (schaarste zichtbaar):", file=sys.stderr)
    for t, n in counts.items():
        print(f"     {t:<28} {n}", file=sys.stderr)

    gt_all = {}
    if GT_PATH.exists():
        gt_all = json.loads(GT_PATH.read_text(encoding="utf-8"))
        print(f"   grondwaarheid geladen: {len(gt_all)} orders", file=sys.stderr)
    else:
        print("   (geen ground_truth.json — alleen beschrijvend, geen JUIST/FOUT-oordeel)", file=sys.stderr)

    mode_label = "opgeslagen-extractie" if _NO_LLM else ("VISION (raw .eml)" if args.eml else "TEKST-ONLY vers")
    results = []

    if args.eml:
        p = Path(args.eml)
        emls = sorted(p.glob("*.eml")) if p.is_dir() else [p]
        print(f"\n== {len(emls)} .eml door de ECHTE pijplijn ({mode_label}) ==", file=sys.stderr)
        for e in emls:
            print(f"  -> {e.name}", file=sys.stderr)
            try:
                out = await run_eml(e)
            except Exception as exc:  # noqa: BLE001
                print(f"     !! crash: {type(exc).__name__}: {exc}", file=sys.stderr)
                results.append({"bron": e.name, "crash": f"{type(exc).__name__}: {exc}"})
                continue
            s = summarize(out)
            key = e.stem
            block = {"bron": e.name, "mode": mode_label, "samenvatting": s,
                     "review_ratio": review_ratio(s), "oordeel": judge(out, gt_all.get(key))}
            results.append(block)
    else:
        oids = list(args.orders or [])
        if args.orders_file:
            oids += [int(x) for x in Path(args.orders_file).read_text().split() if x.strip().isdigit()]
        if not oids:
            oids = DEFAULT_ORDERS
        print(f"\n== {len(oids)} opgeslagen orders door de pijplijn ({mode_label}) ==", file=sys.stderr)
        if not _NO_LLM:
            print("   LET OP: opgeslagen orders missen raw PDF-bytes -> TEKST-ONLY extractie "
                  "(Vision niet reproduceerbaar; gebruik --eml voor de volle test).", file=sys.stderr)
        envs = pull_orders(oids)
        for o in oids:
            if o not in envs:
                print(f"  !! order {o} niet gevonden in prod", file=sys.stderr)
                continue
            print(f"  -> #{o}", file=sys.stderr)
            try:
                out = await run_stored(envs[o])
            except Exception as exc:  # noqa: BLE001
                print(f"     !! crash: {type(exc).__name__}: {exc}", file=sys.stderr)
                results.append({"bron": f"order_{o}", "crash": f"{type(exc).__name__}: {exc}"})
                continue
            s = summarize(out)
            block = {"bron": f"order_{o}", "id": o, "mode": mode_label, "samenvatting": s,
                     "review_ratio": review_ratio(s), "oordeel": judge(out, gt_all.get(str(o)))}
            results.append(block)

    # Aggregatie
    n_stille = sum((r.get("oordeel") or {}).get("n_stille_fouten", 0) for r in results)
    n_review_orders = sum(1 for r in results if (r.get("review_ratio") or {}).get("order_gevlagd"))
    n_ok = sum(1 for r in results if (r.get("oordeel") or {}).get("status") == "JUIST")
    n_judged = sum(1 for r in results if (r.get("oordeel") or {}).get("status") not in (None, "geen_grondwaarheid"))
    payload = {
        "mode": mode_label, "n": len(results),
        "masterdata_counts": counts,
        "stille_fouten_totaal": n_stille,
        "orders_met_review_vlag": n_review_orders,
        "juist_van_beoordeeld": f"{n_ok}/{n_judged}",
        "orders": results,
    }
    out_file = OUT / ("eml.json" if args.eml else "orders.json")
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n# RESULTAAT -> {out_file}", file=sys.stderr)
    print(f"#   stille fouten:        {n_stille}", file=sys.stderr)
    print(f"#   orders met review:    {n_review_orders}/{len(results)}", file=sys.stderr)
    print(f"#   juist van beoordeeld: {n_ok}/{n_judged}", file=sys.stderr)
    for r in results:
        oo = r.get("oordeel") or {}
        if oo.get("status") in ("STILLE-FOUT", "review"):
            print(f"#   {r['bron']}: {oo['status']} -> "
                  f"{[v for v in oo.get('velden', []) if v['oordeel'] != 'JUIST']}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
