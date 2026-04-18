"""DB + seed + repository smoke."""
from __future__ import annotations

from kwabo.db.repository import ArtikelRepo, KlantRepo, OrderLogRepo, PrijsRepo


def test_seed_loaded(session):
    repo = KlantRepo(session)
    k = repo.by_email("purchaseorders@ferney.nl")
    assert k and k.nav_klantnr == "10001"
    assert len(repo.all()) >= 16


def test_artikel_mapping_upsert(session):
    repo = ArtikelRepo(session)
    m = repo.upsert_mapping("10001", "KLANT-X", "KWABO-Y", "test")
    assert m.kwabo_artikelnr == "KWABO-Y"
    # update
    m2 = repo.upsert_mapping("10001", "KLANT-X", "KWABO-Z", "updated")
    assert m2.kwabo_artikelnr == "KWABO-Z"
    assert m.id == m2.id


def test_history_best(session):
    repo = ArtikelRepo(session)
    repo.add_history("10001", "K1", "oms", "KWABO-1", "manual", was_correctie=True)
    repo.add_history("10001", "K1", "oms", "KWABO-1", "manual", was_correctie=True)
    repo.add_history("10001", "K1", "oms", "KWABO-2", "manual", was_correctie=True)
    best = repo.best_history("10001", "K1")
    assert best and best.kwabo_artikelnr == "KWABO-1"


def test_prijs_current(session):
    repo = PrijsRepo(session)
    p = repo.current("10001", "1515155")
    assert p and p.prijs == 15.00


def test_order_log_crud(session):
    repo = OrderLogRepo(session)
    row = repo.create(email_id="t-1", email_from="x@y.nl", email_subject="Test", status="review")
    assert row.id is not None
    got = repo.by_email("t-1")
    assert got and got.id == row.id
    updated = repo.update(row.id, status="pushed", navision_order_nr="SO-XYZ")
    assert updated.status == "pushed"
    assert updated.navision_order_nr == "SO-XYZ"


def test_order_log_status_not_order(session):
    repo = OrderLogRepo(session)
    row = repo.create(email_id="t-2", email_from="x@y.nl", email_subject="Factuur", status="not_order", is_order=False)
    assert row.status == "not_order"
    review_only = repo.list_by_status("review")
    assert all(r.status == "review" for r in review_only)
    assert row.id not in {r.id for r in review_only}
