"""Regressie: een mail die telkens crasht moet na MAX_INTAKE_RETRIES
gequarantained worden (mark_seen), zodat de poll-loop niet eeuwig dezelfde
mail blijft verwerken (prod-situatie 29-05-2026: 10 mails × elke 5 min).
"""
from __future__ import annotations

import contextlib

import pytest

from kwabo.api import intake_trigger as it
from kwabo.integrations.email_client import RawEmail


def _raw(email_id: str) -> RawEmail:
    return RawEmail(
        email_id=email_id,
        email_from="klant@extern.nl",
        email_subject="Bestelling",
        email_date="",
        email_body="body",
        bijlagen=[],
        raw_eml=None,  # skip _persist_source_eml
    )


@pytest.fixture
def poison_setup(monkeypatch):
    it._intake_failures.clear()
    marked: list[str] = []

    class FakeClient:
        def list_new(self):
            return [_raw("poison")]

        def mark_seen(self, email_id):
            marked.append(email_id)

    class FakeApp:
        async def ainvoke(self, state):
            raise RuntimeError("boom in pipeline")

    @contextlib.asynccontextmanager
    async def fake_scope():
        yield None

    monkeypatch.setattr(it, "get_email_client", lambda: FakeClient())
    monkeypatch.setattr("kwabo.graph.graph.get_ingest_app", lambda: FakeApp())
    monkeypatch.setattr(
        "kwabo.integrations.navision_api.nav_client_scope", fake_scope
    )
    return marked


@pytest.mark.asyncio
async def test_poison_pill_quarantined_after_max_retries(poison_setup):
    marked = poison_setup

    # De eerste MAX_INTAKE_RETRIES-1 ticks: error, NIET gequarantained.
    for _ in range(it.MAX_INTAKE_RETRIES - 1):
        result = await it.scan_inbox()
        assert len(result["errors"]) == 1
    assert marked == [], "te vroeg gequarantained"

    # De MAX_INTAKE_RETRIES-de tick: quarantine → mark_seen.
    result = await it.scan_inbox()
    assert "poison" in marked
    # Teller is opgeruimd na quarantine.
    assert "poison" not in it._intake_failures


@pytest.mark.asyncio
async def test_success_resets_failure_counter(monkeypatch):
    it._intake_failures.clear()
    it._intake_failures["x"] = 2  # alsof 'ie 2× eerder faalde

    marked: list[str] = []

    class FakeClient:
        def list_new(self):
            return [_raw("x")]

        def mark_seen(self, email_id):
            marked.append(email_id)

    class OkApp:
        async def ainvoke(self, state):
            return {**state, "order_log_id": 1}

    @contextlib.asynccontextmanager
    async def fake_scope():
        yield None

    async def fake_extras(result, raw):
        return []

    monkeypatch.setattr(it, "get_email_client", lambda: FakeClient())
    monkeypatch.setattr("kwabo.graph.graph.get_ingest_app", lambda: OkApp())
    monkeypatch.setattr(
        "kwabo.integrations.navision_api.nav_client_scope", fake_scope
    )
    monkeypatch.setattr("kwabo.graph.runner._run_extras", fake_extras)

    result = await it.scan_inbox()
    assert len(result["processed"]) == 1
    assert "x" in marked
    assert "x" not in it._intake_failures  # teller gereset na succes
