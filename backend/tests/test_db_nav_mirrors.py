"""Tests for the NAV-trigger-respecting DB additions (T1).

Each repo gets one insert + lookup smoke test. New tables are
auto-created via the conftest `session` fixture (SQLModel.create_all).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlmodel import create_engine

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
from kwabo.db.session import _apply_additive_migrations


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


def test_artikelkaart_repo_upsert_overwrites_with_false(session):
    """NAV-mirror semantics: when NAV reports False, we MUST overwrite — even
    for boolean fields. Earlier code (copied from KlantRepo) skipped fields
    where val was None/falsy, which silently preserved stale True values."""
    repo = ArtikelkaartRepo(session)

    repo.upsert(
        Artikelkaart(
            kwabo_artikelnr="KW-OVR",
            naam="Tijdelijk mix-artikel",
            basis_eenheid="STUK",
            mixprijzen=True,
            palletable=True,
        )
    )
    first = repo.get("KW-OVR")
    assert first is not None
    assert first.mixprijzen is True
    assert first.palletable is True

    # NAV now reports both flags as False — must propagate.
    repo.upsert(
        Artikelkaart(
            kwabo_artikelnr="KW-OVR",
            naam="Tijdelijk mix-artikel",
            basis_eenheid="STUK",
            mixprijzen=False,
            palletable=False,
        )
    )
    after = repo.get("KW-OVR")
    assert after is not None
    assert after.mixprijzen is False
    assert after.palletable is False


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


def test_apply_additive_migrations_adds_mixprijzen_to_legacy_db(tmp_path):
    """Coverage for the load-bearing ALTER TABLE shim in db/session.py.

    Conftest's `session` fixture builds the schema from the SQLModel model
    definitions, which already includes `mixprijzen` — that path does NOT
    exercise `_apply_additive_migrations`. Production DBs deployed before T1
    do, and a missing-column crash on first request after deploy would be
    very ugly. So here we mimic a pre-T1 deploy: a `klantenkaarten` table
    without `mixprijzen`, then run the shim and verify it patches the schema
    in place without losing existing rows.
    """
    db_file = tmp_path / "legacy.db"
    legacy_engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False}
    )

    # Step 2: pre-T1 schema for klantenkaarten (no mixprijzen column).
    # Columns mirror the model at commit ad735fa.
    pre_t1_ddl = """
    CREATE TABLE klantenkaarten (
        id INTEGER NOT NULL PRIMARY KEY,
        nav_klantnr VARCHAR NOT NULL UNIQUE,
        naam VARCHAR NOT NULL,
        email VARCHAR,
        email_bestelling VARCHAR,
        telefoon VARCHAR,
        taal VARCHAR NOT NULL,
        standaard_afleveradres VARCHAR,
        speciale_instructies VARCHAR,
        is_4plus BOOLEAN NOT NULL,
        kredietlimiet FLOAT,
        betalingsconditie VARCHAR,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """
    with legacy_engine.begin() as conn:
        conn.execute(text(pre_t1_ddl))
        # Insert a representative row that simulates a real customer record.
        conn.execute(
            text(
                "INSERT INTO klantenkaarten ("
                "id, nav_klantnr, naam, taal, is_4plus, created_at, updated_at"
                ") VALUES (1, '99999', 'Pre-T1 klant', 'NL', 0, "
                "'2024-01-01 00:00:00', '2024-01-01 00:00:00')"
            )
        )

    # Pre-condition: column is genuinely absent.
    with legacy_engine.connect() as conn:
        cols_before = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(klantenkaarten)")).fetchall()
        }
    assert "mixprijzen" not in cols_before
    assert "naam" in cols_before  # sanity: legacy schema is intact

    # Step 3: run the shim against the legacy DB.
    _apply_additive_migrations(legacy_engine)

    # Step 4: column is now present.
    with legacy_engine.connect() as conn:
        cols_after = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(klantenkaarten)")).fetchall()
        }
    assert "mixprijzen" in cols_after

    # Step 5: idempotent — second invocation must not raise.
    _apply_additive_migrations(legacy_engine)
    with legacy_engine.connect() as conn:
        cols_after2 = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(klantenkaarten)")).fetchall()
        }
    assert "mixprijzen" in cols_after2

    # Step 6: pre-existing row survives the migration with mixprijzen = 0/False.
    with legacy_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT nav_klantnr, naam, mixprijzen FROM klantenkaarten "
                "WHERE id = 1"
            )
        ).fetchone()
    assert row is not None
    assert row[0] == "99999"
    assert row[1] == "Pre-T1 klant"
    # SQLite returns 0 for the BOOLEAN DEFAULT 0 — accept either int or bool.
    assert row[2] in (0, False)
