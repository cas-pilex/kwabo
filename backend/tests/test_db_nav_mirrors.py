"""Tests for the NAV-trigger-respecting DB additions (T1).

Each repo gets one insert + lookup smoke test. New tables are
auto-created via the conftest `session` fixture (SQLModel.create_all).
"""
from __future__ import annotations

from kwabo.db.models import (
    ArtikelKruisverwijzing,
    ArtikelPalletKennis,
    Artikelkaart,
    KlantenkaartShipTo,
)
from kwabo.db.repository import (
    ArtikelkaartRepo,
    KruisverwijzingRepo,
    PalletKennisRepo,
    ShipToRepo,
)


def test_artikelkaart_repo_upsert_and_get(session):
    repo = ArtikelkaartRepo(session)
    rec = Artikelkaart(
        kwabo_artikelnr="KW-100",
        naam="Stucloper wit",
        basis_eenheid="STUK",
        mixprijzen=False,
    )
    saved = repo.upsert(rec)
    assert saved.kwabo_artikelnr == "KW-100"

    got = repo.get("KW-100")
    assert got is not None
    assert got.naam == "Stucloper wit"
    assert got.basis_eenheid == "STUK"

    # Update path: flip mixprijzen to True so list_with_mixprijzen picks it up.
    rec_updated = Artikelkaart(
        kwabo_artikelnr="KW-100",
        naam="Stucloper wit",
        basis_eenheid="STUK",
        mixprijzen=True,
    )
    repo.upsert(rec_updated)

    with_mix = repo.list_with_mixprijzen()
    assert any(a.kwabo_artikelnr == "KW-100" for a in with_mix)


def test_ship_to_repo_upsert_and_list(session):
    repo = ShipToRepo(session)
    repo.upsert(
        KlantenkaartShipTo(
            klant_nr="10001",
            ship_to_code="UTR",
            naam="Vestiging Utrecht",
            straat="Industrieweg 1",
            postcode="3500 AA",
            plaats="Utrecht",
            land="NL",
            is_default=True,
        )
    )
    repo.upsert(
        KlantenkaartShipTo(
            klant_nr="10001",
            ship_to_code="AMS",
            naam="Vestiging Amsterdam",
            straat="Havenkade 22",
            postcode="1000 AB",
            plaats="Amsterdam",
            land="NL",
            is_default=False,
        )
    )

    rows = repo.list_for_klant("10001")
    assert len(rows) == 2
    codes = {r.ship_to_code for r in rows}
    assert codes == {"UTR", "AMS"}

    # Update existing — naam change must not duplicate the row.
    repo.upsert(
        KlantenkaartShipTo(
            klant_nr="10001",
            ship_to_code="UTR",
            naam="Vestiging Utrecht (renamed)",
            straat="Industrieweg 1",
            postcode="3500 AA",
            plaats="Utrecht",
            land="NL",
            is_default=True,
        )
    )
    rows2 = repo.list_for_klant("10001")
    assert len(rows2) == 2
    utr = next(r for r in rows2 if r.ship_to_code == "UTR")
    assert utr.naam == "Vestiging Utrecht (renamed)"


def test_kruisverwijzing_repo_lookup(session):
    repo = KruisverwijzingRepo(session)
    repo.upsert(
        ArtikelKruisverwijzing(
            klant_nr="10001",
            klant_artikelnr="CUST-AAA",
            kwabo_artikelnr="KW-1",
            eenheid_klant="STUK",
            bron="customer",
        )
    )
    assert repo.lookup("10001", "CUST-AAA") == "KW-1"
    assert repo.lookup("10001", "DOES-NOT-EXIST") is None

    # Update mapping target.
    repo.upsert(
        ArtikelKruisverwijzing(
            klant_nr="10001",
            klant_artikelnr="CUST-AAA",
            kwabo_artikelnr="KW-2",
            bron="manual",
        )
    )
    assert repo.lookup("10001", "CUST-AAA") == "KW-2"


def test_pallet_kennis_repo_lookup_and_upsert(session):
    repo = PalletKennisRepo(session)
    rec = ArtikelPalletKennis(
        kwabo_artikelnr="KW-100",
        eenheid="ROL",
        pallet_required=True,
        per_pallet=24,
        confidence=0.5,
    )
    saved = repo.upsert(rec)
    assert saved.kwabo_artikelnr == "KW-100"
    assert saved.eenheid == "ROL"

    got = repo.lookup("KW-100", "ROL")
    assert got is not None
    assert got.pallet_required is True
    assert got.per_pallet == 24
    assert got.laatst_bevestigd_op is not None

    # Increase confidence — must overwrite, not duplicate.
    repo.upsert(
        ArtikelPalletKennis(
            kwabo_artikelnr="KW-100",
            eenheid="ROL",
            pallet_required=True,
            per_pallet=24,
            confidence=0.95,
            bevestigd_door="cas",
        )
    )
    got2 = repo.lookup("KW-100", "ROL")
    assert got2.confidence == 0.95
    assert got2.bevestigd_door == "cas"

    # Different eenheid is a separate composite-key row.
    assert repo.lookup("KW-100", "STUK") is None


def test_klantenkaart_mixprijzen_column(session):
    """The new column on the existing klantenkaarten table is reachable."""
    from sqlmodel import select

    from kwabo.db.models import Klantenkaart

    k = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10001")
    ).first()
    assert k is not None
    # Default is False per the schema.
    assert k.mixprijzen is False
    k.mixprijzen = True
    session.add(k)
    session.commit()
    session.refresh(k)
    assert k.mixprijzen is True
