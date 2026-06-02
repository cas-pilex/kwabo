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


def test_list_defers_heavy_columns_without_changing_summary(session):
    """list_all/list_by_status defer the unused heavy JSON columns
    (stappen_log, correcties) but must keep order_state intact so the
    dashboard summary counts are unchanged, and the deferred columns must
    still lazy-load correctly when explicitly accessed."""
    import json

    from kwabo.api.orders import _to_summary

    repo = OrderLogRepo(session)
    row = repo.create(
        email_id="defer-1",
        email_from="x@y.nl",
        email_subject="Defer test",
        status="review",
        warnings=json.dumps(["w1", "w2"]),
        correcties=json.dumps({"foo": "bar"}),
        stappen_log=json.dumps([{"stap": "x", "beslissing": "y"}]),
        order_state=json.dumps({"needs_review_count": 3, "parent_log_id": 7}),
    )

    listed = repo.list_all()
    got = next(r for r in listed if r.email_id == "defer-1")

    # order_state still present → summary counts correct.
    summary = _to_summary(got)
    assert summary.warnings_count == 2
    assert summary.needs_review_count == 3
    assert summary.parent_log_id == 7

    # Deferred columns lazy-load on demand (not dropped, just not eager).
    assert json.loads(got.stappen_log) == [{"stap": "x", "beslissing": "y"}]
    assert json.loads(got.correcties) == {"foo": "bar"}

    # Same via status-filtered query.
    by_status = repo.list_by_status("review")
    assert any(r.email_id == "defer-1" for r in by_status)
    assert row.id in {r.id for r in by_status}


def test_order_log_status_not_order(session):
    repo = OrderLogRepo(session)
    row = repo.create(email_id="t-2", email_from="x@y.nl", email_subject="Factuur", status="not_order", is_order=False)
    assert row.status == "not_order"
    review_only = repo.list_by_status("review")
    assert all(r.status == "review" for r in review_only)
    assert row.id not in {r.id for r in review_only}


def test_seed_count_meets_minimum(session):
    from kwabo.db.models import KlantenkaartArtikel
    from sqlmodel import select
    rows = session.exec(select(KlantenkaartArtikel)).all()
    assert len(rows) >= 25, f"Seed te klein: {len(rows)} < 25"
