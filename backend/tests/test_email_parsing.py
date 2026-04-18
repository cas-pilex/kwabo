"""All 17 voorbeeld-.eml moeten parseren zonder fouten."""
from __future__ import annotations

import pytest

from kwabo.integrations.email_client import parse_eml_file


def test_alle_17_emls_parseren(eml_dir):
    files = sorted(eml_dir.glob("*.eml"))
    assert len(files) == 17, f"verwachtte 17 test-emls, vond {len(files)}"
    errors = []
    for f in files:
        try:
            em = parse_eml_file(f)
            assert em.email_from, f"{f.name}: lege email_from"
            assert em.email_subject, f"{f.name}: lege email_subject"
        except Exception as e:  # noqa: BLE001
            errors.append((f.name, str(e)[:200]))
    assert not errors, f"parse errors: {errors}"


@pytest.mark.parametrize(
    "eml_name,min_bijlagen",
    [
        ("Ferney inkooporder 4200056148.eml", 1),
        ("Bestelling 4506782407 157.eml", 1),
        ("Bestellung BD26200984.eml", 1),
        ("Inkooporder 00176482.eml", 1),
        ("L. De Vos sa_nv - Order IOR26_00083 - PK Greenboard - B1 - B_W - 75 m² - private label Proshield.eml", 1),
    ],
)
def test_bijlagen_worden_ge_extraheerd(eml_dir, eml_name, min_bijlagen):
    em = parse_eml_file(eml_dir / eml_name)
    assert len(em.bijlagen) >= min_bijlagen


def test_zip_bauhaus_bevat_pdf(eml_dir):
    # BAUHAUS stuurt ZIP met PDF erin — moet automatisch unzipped + extract
    files = list(eml_dir.glob("*122338*.eml"))
    assert files, "BAUHAUS test-eml niet gevonden"
    em = parse_eml_file(files[0])
    pdfs = [b for b in em.bijlagen if b.type == "pdf"]
    assert pdfs, "verwachtte PDF uit BAUHAUS ZIP"
