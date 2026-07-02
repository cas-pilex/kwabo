"""Regression tests for Bug 3: composer must refuse header-only orders.

`compose_navision_operations` should never silently produce a NAV op-list
that creates a sales-order header but zero lines. Real NAV will accept such
an order, but it's structurally invalid (no value to ship) and was masking
upstream matching failures: every regel marked unmatched -> composer
silently skips them all -> push runs against a header-only order ->
NAV order with empty lines that someone has to clean up by hand.

The fix raises ValueError when there were `regels` but none matched.
`compose_order_node`'s existing try/except catches that and stores
`compose_error` on state, so the dashboard can surface the diagnostic and
push_navision refuses to run.
"""
from __future__ import annotations

import pytest

from kwabo.graph.nodes.compose_order import compose_order_node
from kwabo.graph.state import OrderState
from kwabo.integrations.navision_steps import compose_navision_operations


def _state_with_regels(regels: list[dict], email_id: str = "compose-guard") -> OrderState:
    return {  # type: ignore[typeddict-item]
        "email_id": email_id,
        "email_from": "test@example.com",
        "email_subject": "PO",
        "email_body": "",
        "email_date": "2026-04-25",
        "bijlagen": [],
        "is_order": True,
        "classificatie_reden": "synthetic",
        "classificatie_confidence": 1.0,
        "klant_match": {
            "navision_klantnr": "10001",
            "klantnaam": "Ferney",
            "match_confidence": 1.0,
            "match_bron": "manual",
        },
        "bestelnummer_klant": "PO-G-1",
        "orderregels": regels,
        "alle_artikelen_gematcht": False,
        "alle_prijzen_valide": False,
        "validatie_warnings": [],
        "review_status": "approved",
        "stappen_log": [],
        "errors": [],
    }


def test_composer_raises_when_all_regels_unmatched():
    """Regels present but all unmatched -> composer must raise, not produce
    a header-only ops list."""
    state = _state_with_regels([
        {"positie": 1, "artikelnummer_kwabo_matched": None,
         "hoeveelheid": 10, "eenheid": "STUK"},
        {"positie": 2, "artikelnummer_kwabo_matched": "",
         "hoeveelheid": 5, "eenheid": "STUK"},
    ])
    with pytest.raises(ValueError, match="no matched articles"):
        compose_navision_operations(dict(state))


def test_composer_raises_when_regels_empty():
    """No regels at all on an order email -> composer must raise.

    A genuine order with zero line items would mean we extracted nothing,
    and pushing a header-only order is wrong. The validation gate should
    already catch this upstream, but the composer is the last line of
    defence."""
    state = _state_with_regels([])
    with pytest.raises(ValueError, match="no matched articles"):
        compose_navision_operations(dict(state))


def test_composer_succeeds_with_at_least_one_matched_regel():
    """Sanity regression: a state with one matched regel composes normally."""
    state = _state_with_regels([
        {"positie": 1, "artikelnummer_kwabo_matched": None,
         "hoeveelheid": 10, "eenheid": "STUK"},
        {"positie": 2, "artikelnummer_kwabo_matched": "1515155",
         "hoeveelheid": 5, "eenheid": "ROL"},
    ])
    ops = compose_navision_operations(dict(state))
    assert ops, "expected ops list when at least one regel matches"
    line_posts = [
        o for o in ops
        if o["op"] == "POST" and o["path"].endswith("/salesOrderLines")
    ]
    assert len(line_posts) == 1


def test_composer_returns_empty_when_no_customer():
    """Backward-compat: missing customer is still 'skip the push', not raise.

    The composer's contract for missing klantnr is to return [] (push will
    refuse cleanly). Only the all-regels-unmatched case escalates to raise."""
    state = _state_with_regels([
        {"positie": 1, "artikelnummer_kwabo_matched": "1515155",
         "hoeveelheid": 5, "eenheid": "ROL"},
    ])
    state["klant_match"] = {}  # type: ignore[typeddict-item]
    ops = compose_navision_operations(dict(state))
    assert ops == []


@pytest.mark.asyncio
async def test_compose_order_node_warns_on_partially_unmatched_regels(
    session, monkeypatch
):
    """B3 ('1???'-klasse): een order met 1 gematchte + 1 ongematchte regel
    composet wél, maar de overgeslagen regel mag NIET geruisloos uit de
    NAV-operaties verdwijnen — expliciete validatie-warning met positie."""
    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.compose_order as compose_mod
    monkeypatch.setattr(compose_mod, "engine", session.get_bind())

    state = _state_with_regels([
        {"positie": 1, "artikelnummer_kwabo_matched": "1515155",
         "hoeveelheid": 5, "eenheid": "ROL"},
        {"positie": 2, "artikelnummer_kwabo_matched": None,
         "omschrijving": "Milieutoeslag", "hoeveelheid": 1, "eenheid": None},
    ], email_id="compose-partial-warn")

    out = await compose_order_node(state)

    assert out["nav_operations"], "gematchte regel moet gewoon composen"
    warnings = out.get("validatie_warnings") or []
    assert any("regel 2" in w.lower() and "niet in de nav-operaties" in w.lower()
               for w in warnings), warnings


@pytest.mark.asyncio
async def test_compose_order_node_records_compose_error_when_unmatched(
    session, monkeypatch
):
    """compose_order_node catches the composer's ValueError and surfaces it
    as state['compose_error'] (with empty nav_operations) so the dashboard
    can show the reviewer why no ops were prepared."""
    from kwabo.db import session as db_session_mod
    monkeypatch.setattr(db_session_mod, "engine", session.get_bind())
    import kwabo.graph.nodes.compose_order as compose_mod
    monkeypatch.setattr(compose_mod, "engine", session.get_bind())

    state = _state_with_regels([
        {"positie": 1, "artikelnummer_kwabo_matched": None,
         "hoeveelheid": 10, "eenheid": "STUK"},
    ], email_id="compose-guard-e2e")

    out = await compose_order_node(state)

    assert out["nav_operations"] == []
    assert out.get("compose_error"), (
        "compose_order should surface the composer error on state"
    )
    assert "no matched articles" in out["compose_error"].lower()
