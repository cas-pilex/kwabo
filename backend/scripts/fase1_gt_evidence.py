"""FASE 1 stap 2b — M-klasse-bewijs voor de GT-audit (STRICT READ-ONLY).

Draait de SELECT's uit FASE1_GT_AUDIT.md tegen prod (alleen lezen) en legt
de uitkomsten vast, zodat elk masterdata-afgeleid GT-label een geplakt
bewijs heeft.

Zelfde guard-mechaniek als fase1_preflight.py.

Usage (vanuit backend/):
  PYTHONPATH=.venv/Lib/site-packages python scripts/fase1_gt_evidence.py
Output:
  backend/_upgrade/fase1/gt_evidence.json
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

os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp())/'gtev.db').as_posix()}"
os.environ["ADMIN_PASSWORD"] = ""

sys.path.insert(0, str(BACKEND / "src"))
from sqlalchemy import create_engine, text  # noqa: E402
from kwabo.config import settings  # noqa: E402

assert settings.database_url.startswith("sqlite"), settings.database_url

# (label, sql) — uitsluitend SELECT's
QUERIES: list[tuple[str, str]] = [
    # klant naam -> nr
    ("944.klant_61854", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%bauhaus%'"),
    ("954.klant_50094", "SELECT nav_klantnr, naam, plaats, postcode FROM klantenkaarten WHERE naam ILIKE '%jongeneel%'"),
    ("941.klant_61483", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%driessen%'"),
    ("819.klant_61969", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%nexttcom%'"),
    ("845.klant_61745", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%lasaulec%'"),
    ("816.klant_60245", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%zevij%'"),
    ("716.klant_61030", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%rth nederland%'"),
    ("717.klant_61844", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%kuipers%'"),
    ("718.klant_60892_mix", "SELECT nav_klantnr, naam, mixprijzen FROM klantenkaarten WHERE naam ILIKE '%witzand%'"),
    ("721.klant_61472", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%dongen%'"),
    ("707.klant_61948", "SELECT nav_klantnr, naam FROM klantenkaarten WHERE naam ILIKE '%borne%'"),
    ("685.klant_60203_mix", "SELECT nav_klantnr, naam, mixprijzen FROM klantenkaarten WHERE naam ILIKE '%veris%'"),
    ("847.klant_61532", "SELECT nav_klantnr, naam, plaats FROM klantenkaarten WHERE nav_klantnr IN ('61532','60103')"),
    ("941.mix_false", "SELECT nav_klantnr, mixprijzen FROM klantenkaarten WHERE nav_klantnr = '61483'"),
    # agent-vestigingen
    ("832.pontmeyer_zoetermeer", "SELECT nav_klantnr, naam, plaats, postcode FROM klantenkaarten WHERE naam ILIKE '%pontmeyer%' AND (plaats ILIKE '%zoetermeer%' OR naam ILIKE '%zoetermeer%')"),
    ("833.pontmeyer_heemstede", "SELECT nav_klantnr, naam, plaats, postcode FROM klantenkaarten WHERE naam ILIKE '%pontmeyer%' AND (plaats ILIKE '%heemstede%' OR naam ILIKE '%heemstede%')"),
    ("834.pontmeyer_zwaag", "SELECT nav_klantnr, naam, plaats, postcode FROM klantenkaarten WHERE naam ILIKE '%pontmeyer%' AND (plaats ILIKE '%zwaag%' OR naam ILIKE '%zwaag%')"),
    ("83x.shipto_kruis", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE postcode IN ('2718 TB','2102 LL','1689 AK')"),
    # ship-to bestaan
    ("944.shipto_7559SR", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='61854' AND postcode='7559 SR'"),
    ("954.shipto_3449JE", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='50094' AND postcode='3449 JE'"),
    ("941.shipto_breda", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='61483' AND postcode IN ('4814 RR','4815 PN')"),
    ("847.shipto_94315", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE postcode='94315'"),
    ("845.shipto_8531PA", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='61745' AND postcode='8531 PA'"),
    ("816.shipto_4906CS", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='60245' AND postcode='4906 CS'"),
    ("716.shipto_5215MK", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='61030' AND postcode='5215 MK'"),
    ("717.shipto_7783DC", "SELECT klant_nr, ship_to_code, postcode, plaats FROM klantenkaart_ship_to WHERE klant_nr='61844' AND postcode='7783 DC'"),
    # artikel-kruisverwijzingen
    ("941.kruis", "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr FROM artikel_kruisverwijzing WHERE klant_artikelnr IN ('804600','804555','804430')"),
    ("83x.kruis", "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr FROM artikel_kruisverwijzing WHERE klant_artikelnr IN ('K700100070','K700100093','K700100007')"),
    ("716.kruis_ean", "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr FROM artikel_kruisverwijzing WHERE klant_artikelnr='9501017951990'"),
    ("kwabo_nrs_bestaan", "SELECT kwabo_artikelnr, naam FROM artikelkaarten WHERE kwabo_artikelnr IN ('228321','238601','23512','23730','23733','238531','23853','15620','23691','224681')"),
    # kruisverwijzing-formaat inspecteren (eerste poging gaf 0 rijen)
    ("kruis.formaat_941", "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr FROM artikel_kruisverwijzing WHERE kwabo_artikelnr IN ('23559','23522','23523')"),
    ("kruis.formaat_83x", "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr FROM artikel_kruisverwijzing WHERE kwabo_artikelnr IN ('229231','238531','228321','238601')"),
    ("kruis.sample", "SELECT klant_nr, klant_artikelnr, kwabo_artikelnr FROM artikel_kruisverwijzing LIMIT 8"),
    # qty_per_base — kern van eenheid+aantal
    ("uom.23522", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='23522'"),
    ("uom.23523", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='23523'"),
    ("uom.23559", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='23559'"),
    ("uom.23730", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='23730'"),
    ("uom.23733", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='23733'"),
    ("uom.23691", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='23691'"),
    ("uom.15620", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='15620'"),
    ("uom.238601", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='238601'"),
    ("uom.224681_rol", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='224681'"),
    ("uom.228321_rol", "SELECT kwabo_artikelnr, eenheid_code, qty_per_base FROM artikel_eenheden WHERE kwabo_artikelnr='228321'"),
    # europallet-databronnen
    ("sales_uom", "SELECT kwabo_artikelnr, basis_eenheid, verkoop_eenheid FROM artikelkaarten WHERE kwabo_artikelnr IN ('238601','238531','229231','23559','23522','23523','15620','23691')"),
    ("ppb.leeg", "SELECT count(*) AS n FROM pallet_plaatsen_basis"),
    ("apk.vervuild", "SELECT kwabo_artikelnr, eenheid, per_pallet, bevestigd_door FROM artikel_pallet_kennis WHERE kwabo_artikelnr IN ('238601','229231','238531','23559','23522','23523')"),
]


def main() -> None:
    out_dir = BACKEND / "_upgrade" / "fase1"
    out_dir.mkdir(parents=True, exist_ok=True)
    prod = create_engine(PROD_URL)
    results: dict[str, object] = {}
    with prod.connect() as pc:
        for label, sql in QUERIES:
            try:
                rows = [dict(r) for r in pc.execute(text(sql)).mappings().all()]
                results[label] = {"sql": sql, "rows": rows}
                print(f"  {label}: {len(rows)} rij(en) -> "
                      f"{json.dumps(rows[:6], ensure_ascii=False, default=str)[:220]}",
                      file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                results[label] = {"sql": sql, "error": f"{type(exc).__name__}: {exc}"}
                print(f"  !! {label}: {type(exc).__name__}: {exc}", file=sys.stderr)
                pc.rollback()  # anders blokkeert de kapotte transactie alle volgende SELECT's
    prod.dispose()
    out = out_dir / "gt_evidence.json"
    out.write_text(json.dumps({"doel": "GT-audit M-klasse-bewijs (read-only)",
                               "queries": results}, ensure_ascii=False, indent=2,
                              default=str), encoding="utf-8")
    print(f"# RESULTAAT -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
