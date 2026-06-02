"""match_customer must disambiguate a franchise (one card per branch) by the
order's delivery address — never blindly take the first NAV name hit, and flag
for review when it can't tell which branch the order is for.
"""
from __future__ import annotations

import pytest

from kwabo.graph.nodes import match_customer as mc_mod
from kwabo.graph.nodes.match_customer import match_customer_node


ARNHEM = {
    "number": "61792", "displayName": "Pontmeyer Arnhem",
    "Post_Code": "6827 AT", "City": "Arnhem",
}
HEERENVEEN = {
    "number": "61793", "displayName": "Pontmeyer Heerenveen",
    "Post_Code": "8444 AB", "City": "Heerenveen",
}


class _FakeNav:
    """Returns candidates only for the NAME search; email search finds none,
    so the disambiguation path under test is exercised."""

    def __init__(self, name_results):
        self.name_results = name_results

    async def search_customers(self, naam=None, email=None):
        if email:
            return []
        return list(self.name_results)


@pytest.fixture
def app_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    yield


def _state(**over):
    base = {
        "email_id": "p",
        "email_from": "inkoop@pontmeyer.nl",
        "email_subject": "Bestelling",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_city_in_text_picks_right_branch(session, app_engine, monkeypatch):
    monkeypatch.setattr(mc_mod, "get_navision_client",
                        lambda: _FakeNav([HEERENVEEN, ARNHEM]))
    state = _state(bijlagen=[{"naam": "po.pdf", "type": "pdf",
                              "inhoud_tekst": "Pontmeyer Arnhem\nWestervoortsedijk 1"}])
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61792"
    assert "klant_match" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_postcode_picks_right_branch(session, app_engine, monkeypatch):
    monkeypatch.setattr(mc_mod, "get_navision_client",
                        lambda: _FakeNav([ARNHEM, HEERENVEEN]))
    state = _state(afleveradres={"postcode": "8444ab", "plaats": ""})
    out = await match_customer_node(state)
    assert out["klant_match"]["navision_klantnr"] == "61793"


@pytest.mark.asyncio
async def test_both_branches_named_flags_review(session, app_engine, monkeypatch):
    monkeypatch.setattr(mc_mod, "get_navision_client",
                        lambda: _FakeNav([ARNHEM, HEERENVEEN]))
    state = _state(email_subject="Pontmeyer Arnhem en Heerenveen")
    out = await match_customer_node(state)
    assert out["klant_match"] is None
    assert "klant_match" in out["needs_review_fields"]
    assert any("MEERDERE KLANTEN" in w for w in out.get("validatie_warnings") or [])


@pytest.mark.asyncio
async def test_no_signal_does_not_guess(session, app_engine, monkeypatch):
    monkeypatch.setattr(mc_mod, "get_navision_client",
                        lambda: _FakeNav([ARNHEM, HEERENVEEN]))
    out = await match_customer_node(_state())
    assert out["klant_match"] is None
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_single_candidate_still_picked(session, app_engine, monkeypatch):
    monkeypatch.setattr(mc_mod, "get_navision_client",
                        lambda: _FakeNav([ARNHEM]))
    out = await match_customer_node(_state())
    assert out["klant_match"]["navision_klantnr"] == "61792"
