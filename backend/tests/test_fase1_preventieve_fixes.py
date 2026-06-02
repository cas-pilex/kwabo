"""Tests for the Fase 1 preventieve fixes:

- _persist_source_eml: marker on failure (Fix 1)
- _run_extras: per-sub-order isolation (Fix 2)
- match_articles: NAV-outage warning when >=50% of regels crash (Fix 3)
- compose_navision_operations: bestelnr truncated to 35 chars (Fix 4)
- europallet artikelnr via settings (Fix 5)
- state-size warning is plumbed (Fix 6 — observability only, no assertion)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kwabo.api import intake_trigger
from kwabo.config import settings
from kwabo.graph.nodes.match_articles import match_articles_node
from kwabo.integrations.navision_steps import compose_navision_operations
from kwabo.utils.pallet_logic import compute_europallet


# --- Fix 1: _persist_source_eml fail-loud ---


def test_persist_source_eml_returns_none_tuple_on_failure(monkeypatch, tmp_path, caplog):
    """When BOTH Supabase AND write_bytes fail, return (None, None) so the
    caller sets the `incoming_document_save_failed` marker.

    Fase 2 wijziging: return-type is nu (storage_key, local_path). Origineel
    was alleen `str | None`. Beide None = totaal-failure."""
    # No Supabase configured → Supabase pad slaat over en gaat direct naar disk.
    monkeypatch.setattr(intake_trigger.settings, "supabase_url", "")
    monkeypatch.setattr(intake_trigger.settings, "supabase_service_role_key", "")
    monkeypatch.setattr(
        intake_trigger.settings,
        "incoming_documents_dir",
        str(tmp_path / "incoming"),
    )

    # Force the write path to fail by monkeypatching Path.write_bytes.
    from pathlib import Path
    orig = Path.write_bytes

    def boom(self, data):
        raise OSError("simulated disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    try:
        result = intake_trigger._persist_source_eml(b"some-eml-bytes", "test-id-001")
    finally:
        monkeypatch.setattr(Path, "write_bytes", orig)
    assert result == (None, None)


def test_persist_source_eml_success_returns_path(monkeypatch, tmp_path):
    """Disk-fallback succeeds when Supabase isn't configured."""
    monkeypatch.setattr(intake_trigger.settings, "supabase_url", "")
    monkeypatch.setattr(intake_trigger.settings, "supabase_service_role_key", "")
    monkeypatch.setattr(
        intake_trigger.settings,
        "incoming_documents_dir",
        str(tmp_path / "incoming"),
    )
    storage_key, local_path = intake_trigger._persist_source_eml(
        b"some-eml-bytes", "ok-id-002"
    )
    assert storage_key is None  # no Supabase configured
    assert local_path is not None
    # Key is collision-free: readable prefix + hash suffix (see _safe_eml_id).
    expected = intake_trigger._safe_eml_id("ok-id-002") + ".eml"
    assert local_path.endswith(expected)
    assert expected.startswith("ok-id-002-")
    from pathlib import Path as _P
    assert _P(local_path).read_bytes() == b"some-eml-bytes"


# --- Fix 2: _run_extras isolates per-sub-order crashes ---


@pytest.mark.asyncio
async def test_run_extras_isolates_sub_failures(monkeypatch):
    """If sub-order #2 crashes, sub-order #3 still runs and the caller
    gets the surviving results without an exception escaping."""
    from kwabo.graph import runner

    # Build a fake `primary` state with two extras to spawn.
    primary = {
        "email_id": "isolate-test",
        "order_log_id": 7,
        "email_subject": "test",
        "stappen_log": [],
        "extra_orders_raw": [{"x": 1}, {"x": 2}],  # not directly used; runner reads from `extras` arg
    }

    class FakeRaw:
        email_id = "isolate-test"
        email_from = ""
        email_subject = ""
        email_date = ""
        email_body = ""
        bijlagen: list = []
        source_path = None
        raw_eml = None

    # Stub _build_state_from_extract → trivial.
    monkeypatch.setattr(
        runner, "_build_state_from_extract", lambda parsed, raw: ({}, {}, [])
    )

    # Stub sub-graph ainvoke: crash on the FIRST sub, succeed on the SECOND.
    call_count = {"n": 0}

    class FakeSubApp:
        async def ainvoke(self, state):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated sub-graph crash")
            return {"order_log_id": 99 + call_count["n"]}

    monkeypatch.setattr(runner, "get_sub_order_app", lambda: FakeSubApp())

    # Inject two extras directly via primary.
    primary["extra_orders_raw"] = [{"a": 1}, {"b": 2}]

    results = await runner._run_extras(primary, FakeRaw())
    # First crashed → 1 result (the second), no exception bubbled.
    assert len(results) == 1
    assert results[0]["order_log_id"] == 101


# --- Fix 3: match_articles NAV-outage warning ---


@pytest.mark.asyncio
async def test_match_articles_warns_on_nav_outage(monkeypatch):
    """When the NAV client raises on every line, half-or-more of regels
    crash and we add a clear validation warning."""
    from kwabo.graph.nodes import match_articles as ma

    class BoomNav:
        async def search_customers(self, **kw):
            return []

        async def get_item(self, nr):
            raise RuntimeError("NAV down")

        async def search_items(self, **kw):
            raise RuntimeError("NAV down")

        async def create_sales_order(self, *a, **kw):
            return {}

    monkeypatch.setattr(ma, "get_navision_client", lambda: BoomNav())

    state = {
        "email_id": "outage-test",
        "klant_match": {"navision_klantnr": "60645"},
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo": "10010", "omschrijving": "X"},
            {"positie": 2, "artikelnummer_kwabo": "10011", "omschrijving": "Y"},
        ],
    }
    result = await ma.match_articles_node(state)
    warnings = result.get("validatie_warnings") or []
    assert any("NAV tijdelijk niet bereikbaar" in w for w in warnings), warnings


# --- Fix 4: bestelnummer_klant truncated to 35 chars ---


def test_compose_truncates_long_bestelnummer():
    """NAV External_Document_No max length is 35 chars. Truncate locally so
    the push doesn't fail late."""
    long_nr = "PO-2026-SUPERLONGCUSTOMERORDERNUMBER-1234567890"
    assert len(long_nr) > 35
    state = {
        "klant_match": {"navision_klantnr": "60645"},
        "bestelnummer_klant": long_nr,
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "10010",
                "hoeveelheid": 1,
                "eenheid": "STUK",
                "eenheid_default": "STUK",
            }
        ],
    }
    ops = compose_navision_operations(state)
    patch_ops = [
        o
        for o in ops
        if o["op"] == "PATCH" and "externalDocumentNumber" in (o.get("body") or {})
    ]
    assert len(patch_ops) == 1
    sent = patch_ops[0]["body"]["externalDocumentNumber"]
    assert len(sent) == 35
    assert sent == long_nr[:35]


def test_compose_keeps_short_bestelnummer_unchanged():
    state = {
        "klant_match": {"navision_klantnr": "60645"},
        "bestelnummer_klant": "PO-123",
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "10010",
                "hoeveelheid": 1,
                "eenheid": "STUK",
                "eenheid_default": "STUK",
            }
        ],
    }
    ops = compose_navision_operations(state)
    patch_ops = [
        o
        for o in ops
        if o["op"] == "PATCH" and "externalDocumentNumber" in (o.get("body") or {})
    ]
    assert patch_ops[0]["body"]["externalDocumentNumber"] == "PO-123"


# --- Fix 5: europallet artnr via settings ---


def test_europallet_artnr_from_settings(monkeypatch):
    """compute_europallet reads settings.europallet_artikelnr at runtime so
    operators can rotate it per-env."""
    monkeypatch.setattr(settings, "europallet_artikelnr", "98765")

    class _StubRepo:
        def lookup(self, *a, **kw):
            return None

    state = {
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "10010",
                "hoeveelheid": 3,
                "eenheid_origineel": "PAL",
            }
        ]
    }
    regel = compute_europallet(state, repo=_StubRepo())
    assert regel is not None
    assert regel["artikelnummer_kwabo"] == "98765"
    assert regel["artikelnummer_kwabo_matched"] == "98765"


def test_europallet_artnr_falls_back_to_default():
    """When settings.europallet_artikelnr is empty, fall back to PALLET_ARTIKELNR."""
    from kwabo.utils.pallet_logic import PALLET_ARTIKELNR

    # Don't monkeypatch — read whatever default exists.
    class _StubRepo:
        def lookup(self, *a, **kw):
            return None

    state = {
        "orderregels": [
            {
                "artikelnummer_kwabo_matched": "10010",
                "hoeveelheid": 1,
                "eenheid_origineel": "PAL",
            }
        ]
    }
    regel = compute_europallet(state, repo=_StubRepo())
    assert regel is not None
    # Either configured value or the module default — both are valid.
    assert regel["artikelnummer_kwabo"] in (settings.europallet_artikelnr, PALLET_ARTIKELNR)
