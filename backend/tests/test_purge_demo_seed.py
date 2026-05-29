"""Regressie: purge_demo_seed verwijdert de demo-klanten (10001-10016) die in
productie match_customer vervuilen (ze dragen echte order-emailadressen →
push faalt op een niet-bestaand NAV-nummer). Ontdekt 29-05-2026.
"""
from __future__ import annotations

from sqlmodel import select

from kwabo.db.models import Klantenkaart, KlantenkaartArtikel, Prijsafspraak
from kwabo.db.seed import DEMO_NAV_KLANTNRS, purge_demo_seed


def _count(session, model) -> int:
    return len(session.exec(select(model)).all())


def test_purge_removes_all_demo_rows(session):
    # De seed-fixture heeft de demo-klanten al ingeschoten.
    assert _count(session, Klantenkaart) >= len(DEMO_NAV_KLANTNRS)
    assert _count(session, KlantenkaartArtikel) > 0

    removed = purge_demo_seed(session)

    assert removed["klanten"] == len(DEMO_NAV_KLANTNRS)
    assert removed["artikelmappings"] > 0
    # Geen enkele demo-klant blijft over.
    nrs = set(DEMO_NAV_KLANTNRS)
    leftover = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr.in_(nrs))
    ).all()
    assert leftover == []
    leftover_art = session.exec(
        select(KlantenkaartArtikel).where(KlantenkaartArtikel.klant_nr.in_(nrs))
    ).all()
    assert leftover_art == []
    leftover_prijs = session.exec(
        select(Prijsafspraak).where(Prijsafspraak.klant_nr.in_(nrs))
    ).all()
    assert leftover_prijs == []


def test_purge_is_idempotent(session):
    purge_demo_seed(session)
    second = purge_demo_seed(session)
    assert second == {"klanten": 0, "artikelmappings": 0, "prijsafspraken": 0}


def test_demo_nav_klantnrs_are_the_seed_set():
    # Borgt dat de purge-set synchroon blijft met de seed-definitie.
    assert "10002" in DEMO_NAV_KLANTNRS
    assert "10012" in DEMO_NAV_KLANTNRS
    assert len(DEMO_NAV_KLANTNRS) == 16
