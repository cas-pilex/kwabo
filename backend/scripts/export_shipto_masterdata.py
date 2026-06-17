"""Exporteer ontbrekende masterdata uit prod als test-fixtures (read-only).

Eindvalidatie 11-06-2026: export_order_states.py exporteert klantenkaarten/
artikelkaarten/artikel_eenheden/matching_history, maar NIET de ship-to-adressen
(NAV tabel 222), de kruisverwijzingen (NAV tabel 5717), de klantenkaart-
artikelmappings en de pallet-kennis. Die zijn nodig om de volledige sub-graph
(select_ship_to + match_articles-cascade) op echte data te herdraaien.

Usage (vanuit backend/, met prod DATABASE_URL in backend/.env):
    python scripts/export_shipto_masterdata.py

Output:
    tests/test_data/states/shipto.json
    tests/test_data/states/kruisverwijzingen.json
    tests/test_data/states/klantenkaart_artikelen.json
    tests/test_data/states/artikel_pallet_kennis.json

Dit script leest alleen (SELECT); het schrijft niets terug naar de DB.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from kwabo.config import settings  # noqa: E402

STATES_DIR = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "states"


def main() -> None:
    url = settings.database_url
    if url.startswith("sqlite"):
        print(f"DATABASE_URL is sqlite ({url}) — dit hoort de PROD Postgres-URL "
              "te zijn (zet hem in backend/.env). Gestopt.")
        sys.exit(1)

    STATES_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)

    with engine.connect() as conn:
        st = conn.execute(text(
            "SELECT klant_nr, ship_to_code, naam, straat, postcode, plaats, land, is_default "
            "FROM klantenkaart_ship_to"
        )).fetchall()
        kv = conn.execute(text(
            "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr, eenheid_klant "
            "FROM artikel_kruisverwijzing"
        )).fetchall()
        ka = conn.execute(text(
            "SELECT * FROM klantenkaart_artikelen"
        )).mappings().fetchall()
        pk = conn.execute(text(
            "SELECT * FROM artikel_pallet_kennis"
        )).mappings().fetchall()

    (STATES_DIR / "shipto.json").write_text(json.dumps(
        [{"klant_nr": r[0], "ship_to_code": r[1], "naam": r[2], "straat": r[3],
          "postcode": r[4], "plaats": r[5], "land": r[6], "is_default": bool(r[7])}
         for r in st], indent=2, ensure_ascii=False), encoding="utf-8")
    (STATES_DIR / "kruisverwijzingen.json").write_text(json.dumps(
        [{"klant_nr": r[0], "klant_artikelnr": r[1], "kwabo_artikelnr": r[2],
          "eenheid_klant": r[3]} for r in kv],
        indent=2, ensure_ascii=False), encoding="utf-8")
    (STATES_DIR / "klantenkaart_artikelen.json").write_text(json.dumps(
        [dict(r) for r in ka], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    (STATES_DIR / "artikel_pallet_kennis.json").write_text(json.dumps(
        [dict(r) for r in pk], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")

    print(f"  -> shipto.json                  ({len(st)} rijen)")
    print(f"  -> kruisverwijzingen.json       ({len(kv)} rijen)")
    print(f"  -> klantenkaart_artikelen.json  ({len(ka)} rijen)")
    print(f"  -> artikel_pallet_kennis.json   ({len(pk)} rijen)")
    print("\nKlaar (read-only export).")


if __name__ == "__main__":
    main()
