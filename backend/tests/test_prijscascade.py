"""Tests voor PrijsRepo.best_match() cascade en sanity checks."""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from kwabo.db.models import Prijsafspraak
from kwabo.db.repository import PrijsRepo


@pytest.fixture
def prijs_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # Seed diverse prijsafspraken voor klant K1, artikel ART1
        s.add(Prijsafspraak(klant_nr="K1", kwabo_artikelnr="ART1", prijs=20.00, type="standaard",
                            geldig_van=date(2024, 1, 1), geldig_tot=date(2030, 12, 31)))
        s.add(Prijsafspraak(klant_nr="K1", kwabo_artikelnr="ART1", prijs=17.00, type="mix",
                            min_hoeveelheid=25, geldig_tot=date(2030, 12, 31)))
        s.add(Prijsafspraak(klant_nr="K1", kwabo_artikelnr="ART1", prijs=14.00, type="pallet",
                            min_hoeveelheid=50, geldig_tot=date(2030, 12, 31)))
        s.add(Prijsafspraak(klant_nr="K1", kwabo_artikelnr="ART2", prijs=100.00, type="topcoat",
                            geldig_tot=date(2030, 12, 31)))
        # Verlopen afspraak — mag NIET matchen
        s.add(Prijsafspraak(klant_nr="K1", kwabo_artikelnr="ART1", prijs=5.00, type="standaard",
                            geldig_tot=date(2020, 1, 1)))
        s.commit()
        yield s


def test_standaard_bij_lage_hoeveelheid(prijs_session):
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ART1", hoeveelheid=10)
    assert pa is not None
    assert pa.type == "standaard"
    assert pa.prijs == 20.00


def test_mix_bij_25_stuks(prijs_session):
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ART1", hoeveelheid=25)
    # Mix drempel is 25 → van toepassing; mix > standaard in prioriteit
    assert pa is not None
    assert pa.type == "mix"
    assert pa.prijs == 17.00


def test_pallet_bij_60_stuks(prijs_session):
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ART1", hoeveelheid=60)
    # Pallet drempel is 50, hoeveelheid 60 → pallet wint (hoogste prio)
    assert pa is not None
    assert pa.type == "pallet"
    assert pa.prijs == 14.00


def test_topcoat_matcht_altijd(prijs_session):
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ART2", hoeveelheid=1)
    assert pa is not None
    assert pa.type == "topcoat"
    assert pa.prijs == 100.00


def test_geen_match_voor_onbekend_artikel(prijs_session):
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ONBEKEND", hoeveelheid=10)
    assert pa is None


def test_verlopen_afspraak_niet_gebruikt(prijs_session):
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ART1", hoeveelheid=1)
    # De verlopen standaard (€5) mag niet matchen; actieve standaard (€20) moet worden gekozen
    assert pa.prijs == 20.00


def test_fallback_standaard_bij_onvoldoende_hoeveelheid(prijs_session):
    """Mix en pallet bestaan maar hoeveelheid is te laag → standaard fallback."""
    repo = PrijsRepo(prijs_session)
    pa = repo.best_match("K1", "ART1", hoeveelheid=5)
    assert pa.type == "standaard"
