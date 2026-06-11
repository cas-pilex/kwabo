"""Fase 4: NAV-client scope tests.

Bewijst dat:
- get_navision_client() binnen een actieve scope altijd dezelfde instance
  teruggeeft (geen socket-leak meer);
- buiten een scope blijft de oude gedrag (verse client per call) — voor
  CLI scripts en tests die de factory monkey-patchen;
- aclose() wordt aangeroepen bij exit;
- match_articles mirror-first stap haalt geen NAV als artikel in de
  lokale artikelkaarten-mirror staat.
"""
from __future__ import annotations

import pytest

from kwabo.config import settings
from kwabo.db.models import Artikelkaart
from kwabo.db.session import engine
from kwabo.integrations import navision_api
from kwabo.integrations.navision_api import (
    MockNavisionClient,
    _nav_client_var,
    get_navision_client,
    nav_client_scope,
)


# ---------- scope semantics ----------


@pytest.mark.asyncio
async def test_get_navision_client_outside_scope_returns_fresh_each_call(monkeypatch):
    """Backward-compat: zonder scope blijft het oude gedrag (geen cache),
    zodat ad-hoc CLI-aanroepen niet stilletjes state delen."""
    a = get_navision_client()
    b = get_navision_client()
    assert a is not b


@pytest.mark.asyncio
async def test_scope_provides_single_shared_instance(monkeypatch):
    monkeypatch.setattr(settings, "navision_mode", "mock")
    async with nav_client_scope() as scoped:
        a = get_navision_client()
        b = get_navision_client()
        assert a is b is scoped


@pytest.mark.asyncio
async def test_scope_resets_var_on_exit(monkeypatch):
    monkeypatch.setattr(settings, "navision_mode", "mock")
    assert _nav_client_var.get() is None
    async with nav_client_scope():
        assert _nav_client_var.get() is not None
    assert _nav_client_var.get() is None


@pytest.mark.asyncio
async def test_scope_calls_aclose_on_exit(monkeypatch):
    """Voor clients met aclose() (alle httpx-gebaseerde) moet die op exit
    gedraaid worden — anders blijven sockets open per pipeline-run."""
    monkeypatch.setattr(settings, "navision_mode", "mock")

    closed = {"n": 0}

    class FakeClient:
        async def aclose(self):
            closed["n"] += 1

    monkeypatch.setattr(navision_api, "_build_navision_client", lambda: FakeClient())

    async with nav_client_scope():
        pass

    assert closed["n"] == 1


@pytest.mark.asyncio
async def test_nested_scope_reuses_outer_client(monkeypatch):
    monkeypatch.setattr(settings, "navision_mode", "mock")

    async with nav_client_scope() as outer:
        async with nav_client_scope() as inner:
            assert inner is outer
        # Outer scope nog actief
        assert get_navision_client() is outer


@pytest.mark.asyncio
async def test_aclose_failure_does_not_break_pipeline(monkeypatch):
    """Een falende aclose() mag de HTTP-respons nooit naar 500 trekken."""
    monkeypatch.setattr(settings, "navision_mode", "mock")

    class GrumpyClient:
        async def aclose(self):
            raise RuntimeError("aclose exploded")

    monkeypatch.setattr(navision_api, "_build_navision_client", lambda: GrumpyClient())

    # Mag niet raisen
    async with nav_client_scope():
        pass


# ---------- lek-gaatjes buiten de pipeline-scope (Fase 4 A-rest) ----------


class _CountingFake:
    """Telt builds + acloses. Bewust géén Nav2018ODataClient, zodat de
    isinstance-guard in _run_sync_job het faalpad raakt."""

    def __init__(self, counters: dict) -> None:
        counters["builds"] += 1
        self._counters = counters

    async def aclose(self) -> None:
        self._counters["acloses"] += 1

    async def search_items(self, beschrijving=None):
        return [{"number": "111", "displayName": "Fake artikel"}]


def _job_entry(job_id: str, selected: list[str]) -> dict:
    return {
        "job_id": job_id, "state": "running", "started_at": 0.0,
        "finished_at": None,
        "progress": {"selected": selected, "dry_run": True, "current": None},
        "result": None, "error": None,
    }


@pytest.mark.asyncio
async def test_admin_sync_job_closes_client_on_failure(monkeypatch):
    """Het faalpad is het belangrijkste lek: een sync-job die crasht moet de
    client alsnog sluiten. Vóór de fix: client = get_navision_client() zonder
    scope of aclose ⇒ open sockets per (mislukte) sync-run."""
    from kwabo.api import admin

    counters = {"builds": 0, "acloses": 0}
    monkeypatch.setattr(
        navision_api, "_build_navision_client", lambda: _CountingFake(counters)
    )
    job_id = "test-leak-faalpad"
    admin._JOBS[job_id] = _job_entry(job_id, ["customers"])
    try:
        await admin._run_sync_job(job_id, {"customers"}, dry_run=True)
        job = admin._JOBS[job_id]
        assert job["state"] == "failed"  # isinstance-guard vuurt op de fake
        assert counters == {"builds": 1, "acloses": 1}
    finally:
        admin._JOBS.pop(job_id, None)


@pytest.mark.asyncio
async def test_admin_sync_job_closes_client_happy_path(monkeypatch):
    """Happy path: precies één client gebouwd én gesloten over de hele job."""
    from kwabo.api import admin

    counters = {"builds": 0, "acloses": 0}
    monkeypatch.setattr(
        navision_api, "_build_navision_client", lambda: _CountingFake(counters)
    )
    # Laat de fake door de isinstance-guard en stub de zware sync-internals —
    # deze test gaat puur over de client-lifecycle.
    monkeypatch.setattr(admin, "Nav2018ODataClient", _CountingFake)

    async def _stub_sync(client, session, dry_run):
        return admin.SyncReport(
            domain="customers", fetched=0, upserted=0, skipped=0,
            skipped_reasons={}, sample_keys=[],
        )

    class _StubCounts:
        def model_dump(self):
            return {}

    monkeypatch.setattr(admin, "_sync_customers", _stub_sync)
    monkeypatch.setattr(admin, "db_counts", lambda: _StubCounts())

    job_id = "test-leak-happy"
    admin._JOBS[job_id] = _job_entry(job_id, ["customers"])
    try:
        await admin._run_sync_job(job_id, {"customers"}, dry_run=True)
        job = admin._JOBS[job_id]
        assert job["state"] == "done", job["error"]
        assert counters == {"builds": 1, "acloses": 1}
    finally:
        admin._JOBS.pop(job_id, None)


@pytest.mark.asyncio
async def test_artikelen_fallback_closes_client(monkeypatch, tmp_path):
    """Lege mirror ⇒ live-NAV-fallback in /api/artikelen/search. Die moet de
    client sluiten; vóór de fix lekte er één client per search-request."""
    from sqlmodel import SQLModel, create_engine

    from kwabo.api import artikelen
    from kwabo.db import session as db_session_mod

    eng = create_engine(
        f"sqlite:///{tmp_path / 'art.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)  # lege mirror: geen Artikelkaart-rijen
    monkeypatch.setattr(db_session_mod, "engine", eng)

    counters = {"builds": 0, "acloses": 0}
    monkeypatch.setattr(
        navision_api, "_build_navision_client", lambda: _CountingFake(counters)
    )

    out = await artikelen.search(q="iets")

    assert [o.number for o in out] == ["111"]
    assert counters == {"builds": 1, "acloses": 1}


# ---------- match_articles mirror-first ----------


@pytest.mark.asyncio
async def test_match_articles_mirror_hit_avoids_nav_get_item(monkeypatch, session):
    """Wanneer het kwabo-artnr in de lokale artikelkaarten-mirror staat,
    mag match_articles NOOIT nav.get_item(kw) aanroepen voor stap-1 exact-
    match. Dat is de hele winst van Fase 4 mirror-first.

    Het `session` fixture maakt een eigen engine (zie conftest); patch de
    module-level `engine` in match_articles + db.repository naar diezelfde
    engine zodat ArtikelkaartRepo(s).get() het seed-record vindt."""
    from kwabo.graph.nodes import match_articles as ma

    session.add(
        Artikelkaart(
            kwabo_artikelnr="10010",
            naam="Materiaalslang 19x7",
            basis_eenheid="ROL",
            mixprijzen=False,
        )
    )
    session.commit()
    monkeypatch.setattr(ma, "engine", session.bind)

    get_item_calls = {"n": 0}

    class TrackingNav:
        async def get_item(self, nr):
            get_item_calls["n"] += 1
            return {"number": nr, "displayName": "x"}

        async def search_items(self, **kw):
            return []

        async def search_customers(self, **kw):
            return []

    monkeypatch.setattr(ma, "get_navision_client", lambda: TrackingNav())

    state = {
        "email_id": "mirror-hit",
        "klant_match": {"navision_klantnr": "60645"},
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo": "10010", "omschrijving": "X"},
        ],
    }
    result = await ma.match_articles_node(state)

    # Mirror hit ⇒ geen NAV-call voor stap-1
    assert get_item_calls["n"] == 0
    assert result["orderregels"][0]["artikelnummer_kwabo_matched"] == "10010"
    assert result["orderregels"][0]["match_methode"] == "exact"


@pytest.mark.asyncio
async def test_match_articles_mirror_miss_falls_back_to_nav(monkeypatch, session):
    """Wanneer mirror leeg/onbekend: val terug op nav.get_item() zodat
    nieuwe (nog-niet-gesynchroniseerde) artikelen alsnog matchen."""
    from kwabo.graph.nodes import match_articles as ma

    # Geen Artikelkaart in mirror — mirror miss
    monkeypatch.setattr(ma, "engine", session.bind)
    get_item_calls = {"n": 0}

    class TrackingNav:
        async def get_item(self, nr):
            get_item_calls["n"] += 1
            return {"number": nr, "displayName": "x"}

        async def search_items(self, **kw):
            return []

        async def search_customers(self, **kw):
            return []

    monkeypatch.setattr(ma, "get_navision_client", lambda: TrackingNav())

    state = {
        "email_id": "mirror-miss",
        "klant_match": {"navision_klantnr": "60645"},
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo": "10010", "omschrijving": "X"},
        ],
    }
    result = await ma.match_articles_node(state)

    assert get_item_calls["n"] == 1  # mirror miss → live NAV check
    assert result["orderregels"][0]["match_methode"] == "exact"
