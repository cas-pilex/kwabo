"""Exporteer echte faalorders + masterdata uit prod als test-fixtures (read-only).

Fase 2 (matching): de tests draaien op order_state-JSON van de ECHTE faalorders
(grondwet 4). Dit script leest ze uit de prod-DB en schrijft ze naar
backend/tests/test_data/states/. Het schrijft niets terug naar de DB.

Usage (vanuit backend/, met prod DATABASE_URL in backend/.env):
    python scripts/export_order_states.py
    python scripts/export_order_states.py --ids 706 707 --search vandongen

Output:
    tests/test_data/states/order_<id>_<slug>.json   (envelope + order_state)
    tests/test_data/states/artikelkaarten.json      (nr, naam, basis_eenheid)
    tests/test_data/states/klantenkaarten.json      (nr, naam, email, email_bestelling)
    tests/test_data/states/fuzzy_history.json       (artikel_matching_history, methode=fuzzy)
    tests/test_data/emails/order_<id>.eml           (best-effort, als bron vindbaar)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from kwabo.config import settings  # noqa: E402

STATES_DIR = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"
EMAILS_DIR = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "emails"

DEFAULT_IDS = [706, 707, 717, 718]
# Van Dongen en TABS/Jongeneel hebben (nog) geen bekend order-id — zoek op
# afzender/onderwerp. Pontmeyer-agent (Joran.de.Waard@pontmeyer.nl) is de
# TABS Holland-route.
DEFAULT_SEARCH = ["vandongenverf", "tabs", "jongeneel", "pontmeyer"]

# Binaire/zware sleutels die geen matching-signaal zijn; tekst blijft staan
# (de fuzzy-analyse en extract-verificatie hebben de echte tekst nodig).
STRIP_KEYS = {"raw", "inhoud_b64", "content_b64", "data"}


def _slug(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:max_len] or "order"


def _strip_binary(state: dict) -> dict:
    for b in state.get("bijlagen") or []:
        if isinstance(b, dict):
            for k in list(b):
                if k in STRIP_KEYS:
                    b.pop(k)
    return state


def _export_order(conn, row, dry: bool) -> None:
    oid, email_from, subject, status, raw_state = row
    if not raw_state:
        print(f"  !! order {oid}: geen order_state — overgeslagen")
        return
    state = _strip_binary(json.loads(raw_state))
    envelope = {
        "order_id": oid,
        "email_from": email_from,
        "email_subject": subject,
        "status": status,
        "order_state": state,
    }
    out = STATES_DIR / f"order_{oid}_{_slug(subject or email_from or '')}.json"
    if not dry:
        out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False, default=str),
                       encoding="utf-8")
    print(f"  -> {out.name}  (van: {email_from!r}, onderwerp: {(subject or '')[:60]!r})")

    # Best-effort .eml (Supabase storage-key / legacy pad). Faalt stil met
    # melding: de state-JSON is het primaire fixtureformaat.
    try:
        from kwabo.api.orders import _resolve_eml_bytes
        raw = _resolve_eml_bytes(state, state.get("email_id"))
        if raw:
            eml_out = EMAILS_DIR / f"order_{oid}.eml"
            if not dry:
                eml_out.write_bytes(raw)
            print(f"  -> {eml_out.name}  ({len(raw)} bytes)")
        else:
            print(f"  .. order {oid}: geen .eml-bron vindbaar (state-JSON volstaat)")
    except Exception as exc:  # noqa: BLE001
        print(f"  .. order {oid}: .eml-export faalde ({type(exc).__name__}: {exc})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", nargs="*", type=int, default=DEFAULT_IDS)
    ap.add_argument("--search", nargs="*", default=DEFAULT_SEARCH,
                    help="zoektermen voor email_from/onderwerp (Van Dongen/TABS)")
    ap.add_argument("--per-term", type=int, default=5,
                    help="max recente hits per zoekterm")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url = settings.database_url
    if url.startswith("sqlite"):
        print(f"DATABASE_URL is sqlite ({url}) — dit hoort de PROD Postgres-URL "
              "te zijn (zet hem in backend/.env). Gestopt.")
        sys.exit(1)

    STATES_DIR.mkdir(parents=True, exist_ok=True)
    EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)

    with engine.connect() as conn:
        # 1) Expliciete order-ids
        print(f"== Orders op id: {args.ids}")
        rows = conn.execute(text(
            "SELECT id, email_from, email_subject, status, order_state "
            "FROM order_log WHERE id = ANY(:ids) ORDER BY id"
        ), {"ids": args.ids}).fetchall()
        found = {r[0] for r in rows}
        for missing in sorted(set(args.ids) - found):
            print(f"  !! order {missing}: niet gevonden")
        for row in rows:
            _export_order(conn, row, args.dry_run)

        # 2) Zoektermen (Van Dongen / TABS)
        for term in args.search:
            print(f"== Zoekterm {term!r} (max {args.per_term} recentste)")
            rows = conn.execute(text(
                "SELECT id, email_from, email_subject, status, order_state "
                "FROM order_log "
                "WHERE lower(email_from) LIKE :t OR lower(email_subject) LIKE :t "
                "ORDER BY id DESC LIMIT :n"
            ), {"t": f"%{term.lower()}%", "n": args.per_term}).fetchall()
            if not rows:
                print("  (geen hits)")
            for row in rows:
                if row[0] in found:
                    print(f"  .. order {row[0]} al geëxporteerd")
                    continue
                found.add(row[0])
                _export_order(conn, row, args.dry_run)

        # 3) Masterdata voor drempel-analyse en naam-fallback-tests
        print("== Masterdata")
        ak = conn.execute(text(
            "SELECT kwabo_artikelnr, naam, basis_eenheid FROM artikelkaarten"
        )).fetchall()
        kk = conn.execute(text(
            "SELECT nav_klantnr, naam, email, email_bestelling FROM klantenkaarten"
        )).fetchall()
        fh = conn.execute(text(
            "SELECT klant_nr, klant_artikelnr, klant_omschrijving, kwabo_artikelnr, "
            "match_methode, was_correctie, order_datum, created_at "
            "FROM artikel_matching_history WHERE match_methode = 'fuzzy' "
            "ORDER BY created_at"
        )).fetchall()
        if not args.dry_run:
            (STATES_DIR / "artikelkaarten.json").write_text(json.dumps(
                [{"kwabo_artikelnr": r[0], "naam": r[1], "basis_eenheid": r[2]} for r in ak],
                indent=2, ensure_ascii=False), encoding="utf-8")
            (STATES_DIR / "klantenkaarten.json").write_text(json.dumps(
                [{"nav_klantnr": r[0], "naam": r[1], "email": r[2], "email_bestelling": r[3]}
                 for r in kk], indent=2, ensure_ascii=False), encoding="utf-8")
            (STATES_DIR / "fuzzy_history.json").write_text(json.dumps(
                [{"klant_nr": r[0], "klant_artikelnr": r[1], "klant_omschrijving": r[2],
                  "kwabo_artikelnr": r[3], "match_methode": r[4], "was_correctie": r[5],
                  "order_datum": r[6], "created_at": r[7]} for r in fh],
                indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  -> artikelkaarten.json   ({len(ak)} rijen)")
        print(f"  -> klantenkaarten.json   ({len(kk)} rijen)")
        print(f"  -> fuzzy_history.json    ({len(fh)} fuzzy-rijen)")

    print("\nKlaar. Fixtures in tests/test_data/states/ — check de inhoud vóór commit "
          "(geen secrets; klantdata blijft binnen de privérepo).")


if __name__ == "__main__":
    main()
