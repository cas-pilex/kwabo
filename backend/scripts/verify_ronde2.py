"""VALIDATIE RONDE 2 — verse pijplijn + differentieel + stille-fout-kerngetal.

STRICT READ-ONLY t.o.v. prod (guard: sqlite-env vóór elke kwabo-import; prod alleen
via losse create_engine(PROD).connect()-SELECT, nooit commit). Draai dezelfde file
in een worktree op de pre-fix baseline voor het differentieel.

Modi:
  python scripts/verify_ronde2.py            # volledige steekproef (Blok A,B,E)
  python scripts/verify_ronde2.py --core     # kernset (determinisme/diff)
  python scripts/verify_ronde2.py --eenheid   # Blok C: apply_mixprijzen op echte regels

STILLE FOUT (nieuwe definitie) = confident (conf>=1.0 of géén review-vlag) ÉN fout:
  - klant: agent/portaal-order met conf>=1.0 ZONDER vlag (de oude TABS-bug).
  - ship-to: afleveradres-postcode == een kandidaat, maar een ANDERE ship-to gekozen, geen vlag.
  - eenheid: regel-verkoop_uom is een mix-staffelcode op niet-mix-order, geen vlag.
"""
from __future__ import annotations
import os, sys, json, argparse, tempfile, asyncio
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROD = None
for _l in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    if _l.strip().startswith("DATABASE_URL="):
        PROD = _l.split("=", 1)[1].strip().strip('"').strip("'"); break
assert PROD and not PROD.startswith("sqlite"), "verwacht prod Postgres in .env"
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'r2.db').as_posix()}"
os.environ["NAVISION_MODE"] = "mock"; os.environ["ADMIN_PASSWORD"] = ""
os.environ.setdefault("MAIL_MODE", "log"); os.environ.setdefault("EMAIL_MODE", "file_drop")
sys.path.insert(0, str(BACKEND / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlmodel import SQLModel, Session  # noqa: E402
from kwabo.config import settings  # noqa: E402
assert settings.database_url.startswith("sqlite"), settings.database_url
import kwabo.db.models  # noqa: E402,F401
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.db.repository import KlantRepo  # noqa: E402
from kwabo.graph.state import new_state  # noqa: E402
from kwabo.graph.graph import get_ingest_app  # noqa: E402
from kwabo.graph.nodes.select_ship_to import select_ship_to_node  # noqa: E402
from kwabo.graph.nodes.match_articles import match_articles_node  # noqa: E402
from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node  # noqa: E402
from kwabo.integrations.navision_api import nav_client_scope  # noqa: E402

# Self-contained helpers (versie-onafhankelijk: identiek op oud/nieuw zodat het
# differentieel PUUR het node-gedrag meet, niet helper-verschillen).
import re as _re  # noqa: E402


def _norm_pc(v):
    return "".join((v or "").split()).lower()


def is_mix_code(code):
    return bool(code) and _re.match(r"^M\d+PAL\d+$", code.strip(), _re.IGNORECASE) is not None

PORTAL_DOMAINS = {"orders.nl", "zevij-necomij.com", "bahag.com"}
MIRROR = ["klantenkaarten", "klant_email_aliases", "klantenkaart_ship_to", "artikelkaarten",
          "artikel_eenheden", "klantenkaart_artikelen", "artikel_kruisverwijzing",
          "artikel_matching_history", "artikel_pallet_kennis"]

# Graaf-orders (klant + ship-to). force_klant = reviewer-bevestigde klant voor de
# ship-to-re-resolve bij portaalorders (klant wordt daar niet auto-confident).
GRAAF = {
    954: {"blok": "B", "label": "TABS->Jongeneel Woerden"},
    955: {"blok": "B", "label": "TABS->PontMeyer Alkmaar"},
    834: {"blok": "B", "label": "TABS->PontMeyer Zwaag"},
    915: {"blok": "B", "label": "Zevij-portaal"},
    944: {"blok": "A", "label": "BAUHAUS->Hengelo", "force_klant": ("61854", "Bauhaus Nederland C.V.")},
    662: {"blok": "A", "label": "BAUHAUS->Groningen", "force_klant": ("61854", "Bauhaus Nederland C.V.")},
    716: {"blok": "A/E", "label": "Wurth (regressie 1-op-1)"},
    717: {"blok": "A/E", "label": "Kuipers (regressie 1-op-1)"},
}
STEEKPROEF_EXTRA = [945, 926, 897, 896, 887, 868, 856, 718, 707, 721, 832, 833, 847, 816, 635]
CORE = [954, 944, 716, 717, 955, 834]
# Blok C eenheid: echte prod-matched regels door apply_mixprijzen + echte kaarten.
EENHEID = [941, 922, 819, 854, 845, 847]


def mirror():
    init_db()
    pe = create_engine(PROD)
    with pe.connect() as pc:
        for tbl in MIRROR:
            t = SQLModel.metadata.tables[tbl]
            cols = {c.name for c in t.columns}
            rows = pc.execute(text(f"SELECT * FROM {tbl}")).mappings().all()
            if rows:
                with engine.begin() as sc:
                    sc.execute(t.insert(), [{k: v for k, v in r.items() if k in cols} for r in rows])
    pe.dispose()


def pull(oids):
    pe = create_engine(PROD)
    with pe.connect() as pc:
        rows = {r["id"]: dict(r) for r in pc.execute(text(
            "SELECT id,email_from,email_subject,email_date,klant_nr,order_state "
            "FROM order_log WHERE id = ANY(:i)"), {"i": list(oids)}).mappings()}
    pe.dispose()
    return rows


def build_state(env):
    st = json.loads(env["order_state"])
    bij = [{"naam": b.get("naam"), "type": b.get("type"),
            "inhoud_tekst": b.get("inhoud_tekst"), "raw": None}
           for b in (st.get("bijlagen") or []) if isinstance(b, dict)]
    s = new_state(email_id=st.get("email_id") or str(env["id"]),
                  email_from=env["email_from"] or "", email_subject=env["email_subject"] or "",
                  email_body=st.get("email_body") or "", email_date=str(env.get("email_date") or ""),
                  bijlagen=bij, source_path=st.get("source_path"))
    return s, st


def domain_card_count(email_from):
    """Aantal distincte klantnrs dat het afzenderdomein draagt — via een directe
    SQL-telling op de gespiegelde klantenkaarten (geen kwabo-matching-code, dus
    identiek op oud/nieuw)."""
    m = _re.search(r"[\w\.\-\+]+@[\w\.\-]+", email_from or "")
    if not m:
        return 0, ""
    dom = m.group(0).split("@")[1].lower()
    with engine.connect() as c:
        n = c.execute(text(
            "SELECT count(DISTINCT nav_klantnr) FROM klantenkaarten "
            "WHERE lower(email) LIKE :p OR lower(email_bestelling) LIKE :p"),
            {"p": f"%@{dom}%"}).scalar()
    return n or 0, dom


def is_agent_or_portal(email_from):
    cnt, dom = domain_card_count(email_from)
    return cnt >= 3 or dom in PORTAL_DOMAINS


def silent_faults(env, out, klant_flagged):
    faults = []
    km = out.get("klant_match") or {}
    conf = km.get("match_confidence")
    confident = (conf is not None and conf >= 1.0) or not klant_flagged
    # 1) klant: agent/portaal + confident + geen vlag
    if km.get("navision_klantnr") and confident and not klant_flagged and is_agent_or_portal(env["email_from"]):
        faults.append(("KLANT", f"agent/portaal-order confident {km.get('navision_klantnr')} "
                                f"(conf={conf}) ZONDER vlag"))
    # 2) ship-to: afleveradres-postcode == kandidaat maar andere gekozen, geen vlag
    afl_pc = _norm_pc((out.get("afleveradres") or {}).get("postcode"))
    chosen = out.get("ship_to_gekozen")
    kand = out.get("ship_to_kandidaten") or []
    if afl_pc and kand:
        exact = [k for k in kand if _norm_pc(k.get("postcode")) == afl_pc]
        sf_flag = "ship_to_gekozen" in (out.get("needs_review_fields") or [])
        if len(exact) == 1 and chosen and chosen != exact[0].get("ship_to_code") and not sf_flag:
            faults.append(("SHIP_TO", f"afl-postcode {afl_pc} == kandidaat {exact[0].get('ship_to_code')} "
                                      f"maar gekozen {chosen}"))
    # 3) eenheid: mix-code als verkoop_uom, geen vlag
    nr = out.get("needs_review_fields") or []
    for r in out.get("orderregels") or []:
        vu = r.get("verkoop_uom_gekozen")
        if vu and is_mix_code(vu) and f"verkoop_eenheid:{r.get('positie')}" not in nr:
            faults.append(("EENHEID", f"regel {r.get('positie')} verkoop_uom mix-code {vu} zonder vlag"))
    return faults


def regels_view(out):
    return [{"pos": r.get("positie"), "art": r.get("artikelnummer_kwabo_matched"),
             "methode": r.get("match_methode"), "eenheid": r.get("eenheid"),
             "verkoop_uom": r.get("verkoop_uom_gekozen"), "aantal": r.get("verkoop_aantal"),
             "mix_uom": r.get("mix_uom_gekozen")} for r in (out.get("orderregels") or [])]


async def run_graaf(oid, env, cfg):
    state, _ = build_state(env)
    app = get_ingest_app()
    async with nav_client_scope():
        out = await app.ainvoke(state)
    note = ""
    if cfg.get("force_klant"):
        kn, knaam = cfg["force_klant"]
        s = dict(out)
        s["klant_match"] = {"navision_klantnr": kn, "klantnaam": knaam,
                            "match_confidence": 1.0, "match_bron": "manual"}
        s = await select_ship_to_node(s)
        out = s
        note = f"ship-to re-resolve op bevestigde klant {kn}"
    km = out.get("klant_match") or {}
    flagged = "klant_match" in (out.get("needs_review_fields") or [])
    summary = {
        "id": oid, "blok": cfg["blok"], "label": cfg["label"], "note": note,
        "email_from": env["email_from"],
        "afleveradres": {k: (out.get("afleveradres") or {}).get(k) for k in ("naam", "postcode", "plaats")},
        "klant": {"nr": km.get("navision_klantnr"), "bron": km.get("match_bron"),
                  "conf": km.get("match_confidence"), "vlag": flagged,
                  "n_kandidaten": len(out.get("klant_kandidaten") or [])},
        "ship_to_gekozen": out.get("ship_to_gekozen"),
        "ship_to_kandidaten": [{"code": k.get("ship_to_code"), "pc": k.get("postcode"),
                                "plaats": k.get("plaats")} for k in (out.get("ship_to_kandidaten") or [])],
        "regels": regels_view(out),
    }
    summary["stille_fouten"] = [f"{t}: {d}" for t, d in silent_faults(env, out, flagged)]
    return summary


async def run_eenheid(oid, env):
    """Blok C: echte prod-matched regels — herresolve de eenheid uit de
    OORSPRONKELIJK bestelde eenheid (resolve_line_uom, zoals match_articles) +
    apply_mixprijzen, tegen de echte kaarten. Zo toont het de huidige-code-
    uitkomst (PAL->PALLET, mix-code->plain pallet), niet de bevroren historie."""
    from kwabo.utils.eenheid_resolve import resolve_line_uom
    from kwabo.db.repository import ArtikelkaartRepo
    st = json.loads(env["order_state"])
    klant_nr = (st.get("klant_match") or {}).get("navision_klantnr")
    regels = []
    with Session(engine) as s:
        repo = ArtikelkaartRepo(s)
        for r in (st.get("orderregels") or []):
            art = r.get("artikelnummer_kwabo_matched")
            besteld = (r.get("eenheid_origineel") or r.get("eenheid") or "").strip()
            nr = dict(r)
            # Wis afgeleide velden uit de historie zodat Branch-A vers herrekent
            # (anders blijft een stale verkoop_uom uit de oude state staan).
            for k in ("verkoop_uom_gekozen", "verkoop_aantal", "mix_uom_gekozen",
                      "mix_aantal", "mix_uom_kandidaat"):
                nr.pop(k, None)
            if art:
                kaart = repo.get(art)
                if kaart and kaart.basis_eenheid:
                    base = kaart.basis_eenheid.strip()
                    nr["eenheid_origineel"] = besteld or base
                    nr["eenheid"], _vlag = resolve_line_uom(
                        {"eenheid": besteld or base}, base, repo.list_eenheden(art))
            regels.append(nr)
    state = {"email_id": str(oid), "klant_match": {"navision_klantnr": klant_nr},
             "orderregels": regels, "needs_review_fields": [], "validatie_warnings": []}
    out = await apply_mixprijzen_node(state)
    nr = out.get("needs_review_fields") or []
    rows = []
    for r in out["orderregels"]:
        pos = r.get("positie")
        vu = r.get("verkoop_uom_gekozen")
        sf = bool(vu) and is_mix_code(vu) and f"verkoop_eenheid:{pos}" not in nr
        rows.append({"pos": pos, "art": r.get("artikelnummer_kwabo_matched"),
                     "besteld_eenheid": r.get("eenheid_origineel") or r.get("eenheid"),
                     "hoeveelheid": r.get("hoeveelheid"),
                     "nav_eenheid": r.get("eenheid"),
                     "verkoop_uom": vu, "aantal": r.get("verkoop_aantal"),
                     "mix_uom": r.get("mix_uom_gekozen"), "stille_fout": sf})
    return {"id": oid, "klant": klant_nr, "mixprijzen_actief": out.get("mixprijzen_actief"),
            "regels": rows, "warnings": [w for w in out.get("validatie_warnings") or [] if "EENHEID" in w]}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", action="store_true")
    ap.add_argument("--eenheid", action="store_true")
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()
    mirror()
    outdir = BACKEND / "_ronde2"
    outdir.mkdir(exist_ok=True)

    if args.eenheid:
        envs = pull(EENHEID)
        res = [await run_eenheid(o, envs[o]) for o in EENHEID if o in envs]
        payload = {"mode": "eenheid", "orders": res}
        (outdir / "eenheid.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        sf = sum(1 for o in res for r in o["regels"] if r["stille_fout"])
        print(f"\n# EENHEID stille fouten: {sf} -> _ronde2/eenheid.json", file=sys.stderr)
        return

    mode = "core" if args.core else "vol"
    oids = CORE if args.core else (list(GRAAF) + STEEKPROEF_EXTRA)
    envs = pull(oids)
    results = []
    for o in oids:
        if o not in envs:
            print(f"  !! order {o} niet gevonden", file=sys.stderr); continue
        cfg = GRAAF.get(o, {"blok": "E", "label": f"steekproef #{o}"})
        results.append(await run_graaf(o, envs[o], cfg))
    total_sf = sum(len(r["stille_fouten"]) for r in results)
    payload = {"mode": mode, "n": len(results),
               "stille_fouten_totaal": total_sf, "orders": results}
    (outdir / f"{mode}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n# STILLE FOUTEN (nieuwe definitie): {total_sf} -> _ronde2/{mode}.json", file=sys.stderr)
    for r in results:
        if r["stille_fouten"]:
            print(f"  #{r['id']} {r['label']}: {r['stille_fouten']}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
