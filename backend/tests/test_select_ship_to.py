"""Tests for select_ship_to node (T5).

Each test inserts ShipTo records via the provided session fixture and runs
the node with a ShipToRepo bound to that same session — so we don't need to
monkeypatch the module-level engine. The node accepts `repo=` for exactly
this reason.
"""
from __future__ import annotations

import pytest

from kwabo.db.models import KlantenkaartShipTo
from kwabo.db.repository import ShipToRepo
from kwabo.graph.nodes.select_ship_to import select_ship_to_node


def _add(session, **kwargs) -> None:
    session.add(KlantenkaartShipTo(**kwargs))
    session.commit()


@pytest.mark.asyncio
async def test_no_klant_match_pass_through(session):
    repo = ShipToRepo(session)
    state = {
        "email_id": "x1",
        "klant_match": None,
        "afleveradres": {"postcode": "1234 AB"},
    }
    out = await select_ship_to_node(state, repo=repo)
    # Untouched.
    assert out == state
    assert "ship_to_kandidaten" not in out
    assert "ship_to_gekozen" not in out


@pytest.mark.asyncio
async def test_zero_records_no_review_flag(session):
    repo = ShipToRepo(session)
    state = {
        "email_id": "x2",
        "klant_match": {"navision_klantnr": "10001"},
        "afleveradres": {"postcode": "1234 AB", "plaats": "Utrecht"},
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] is None
    assert out["ship_to_kandidaten"] == []
    # Zero candidates is the normal NAV-default-address case — not a review trigger.
    assert "ship_to_gekozen" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_single_record_auto_picked(session):
    _add(
        session,
        klant_nr="10001",
        ship_to_code="UTR",
        naam="Vestiging Utrecht",
        straat="Industrieweg 1",
        postcode="3500 AA",
        plaats="Utrecht",
        land="NL",
        is_default=True,
    )
    repo = ShipToRepo(session)
    state = {
        "email_id": "x3",
        "klant_match": {"navision_klantnr": "10001"},
        # Even if afleveradres is missing/empty, single record must be picked.
        "afleveradres": {},
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] == "UTR"
    assert len(out["ship_to_kandidaten"]) == 1
    assert out["ship_to_kandidaten"][0]["ship_to_code"] == "UTR"
    assert out["ship_to_kandidaten"][0]["is_default"] is True
    assert "ship_to_gekozen" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_two_records_postcode_match_wins(session):
    _add(
        session,
        klant_nr="10001",
        ship_to_code="UTR",
        naam="Vestiging Utrecht",
        straat="Industrieweg 1",
        postcode="3500 AA",
        plaats="Utrecht",
        land="NL",
        is_default=True,
    )
    _add(
        session,
        klant_nr="10001",
        ship_to_code="AMS",
        naam="Vestiging Amsterdam",
        straat="Havenkade 22",
        postcode="1000 AB",
        plaats="Amsterdam",
        land="NL",
        is_default=False,
    )
    repo = ShipToRepo(session)
    state = {
        "email_id": "x4",
        "klant_match": {"navision_klantnr": "10001"},
        "afleveradres": {
            # Same postcode as AMS, but with case + extra space variation.
            "postcode": "1000ab",
            "plaats": "Amsterdam",
        },
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] == "AMS"
    assert len(out["ship_to_kandidaten"]) == 2
    assert "ship_to_gekozen" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_two_records_equally_weak_flags_review(session):
    _add(
        session,
        klant_nr="10001",
        ship_to_code="UTR",
        naam="Vestiging Utrecht",
        straat="Industrieweg 1",
        postcode="3500 AA",
        plaats="Utrecht",
        land="NL",
        is_default=True,
    )
    _add(
        session,
        klant_nr="10001",
        ship_to_code="AMS",
        naam="Vestiging Amsterdam",
        straat="Havenkade 22",
        postcode="1000 AB",
        plaats="Amsterdam",
        land="NL",
        is_default=False,
    )
    repo = ShipToRepo(session)
    state = {
        "email_id": "x5",
        "klant_match": {"navision_klantnr": "10001"},
        # Afleveradres matches NEITHER record — both score 0, ambiguous.
        "afleveradres": {
            "postcode": "9999 ZZ",
            "plaats": "Groningen",
            "naam": "Onbekend",
            "straat": "Onbekend 1",
        },
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] is None
    assert "ship_to_gekozen" in out["needs_review_fields"]
    assert out["needs_review_count"] == 1


def _add_pontmeyer(session) -> None:
    # Arnhem is the DEFAULT — picking it for a Heerenveen order is the bug.
    _add(session, klant_nr="20001", ship_to_code="ARN", naam="Pontmeyer Arnhem",
         straat="Westervoortsedijk 1", postcode="6827 AT", plaats="Arnhem",
         land="NL", is_default=True)
    _add(session, klant_nr="20001", ship_to_code="HRV", naam="Pontmeyer Heerenveen",
         straat="Marktweg 1", postcode="8444 AB", plaats="Heerenveen",
         land="NL", is_default=False)


@pytest.mark.asyncio
async def test_multi_location_city_in_pdf_text_picks_right_branch(session):
    """The vestiging is named in the order/PDF text — pick THAT location's
    ship-to code, not the (default) other one."""
    _add_pontmeyer(session)
    repo = ShipToRepo(session)
    state = {
        "email_id": "p1",
        "klant_match": {"navision_klantnr": "20001"},
        "afleveradres": None,
        "email_subject": "Bestelling",
        "bijlagen": [{"naam": "po.pdf", "type": "pdf",
                      "inhoud_tekst": "Pontmeyer Heerenveen\nMarktweg 1\nBestelnr 123"}],
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] == "HRV"
    assert "ship_to_gekozen" not in (out.get("needs_review_fields") or [])


@pytest.mark.asyncio
async def test_multi_location_name_token_in_subject_picks_branch(session):
    """Distinguishing name token (not the city) appears in the subject."""
    _add_pontmeyer(session)
    repo = ShipToRepo(session)
    state = {
        "email_id": "p2",
        "klant_match": {"navision_klantnr": "20001"},
        "afleveradres": None,
        "email_subject": "Order voor Heerenveen vestiging",
        "email_body": "",
        "bijlagen": [],
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] == "HRV"


@pytest.mark.asyncio
async def test_multi_location_both_cities_named_flags_review(session):
    """Both locations mentioned → genuinely ambiguous → flag, do NOT guess."""
    _add_pontmeyer(session)
    repo = ShipToRepo(session)
    state = {
        "email_id": "p3",
        "klant_match": {"navision_klantnr": "20001"},
        "afleveradres": None,
        "email_subject": "Pontmeyer Heerenveen en Arnhem",
        "bijlagen": [],
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] is None
    assert "ship_to_gekozen" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_multi_location_no_signal_does_not_pick_default(session):
    """No location signal at all → flag for review; never silently use the
    default branch."""
    _add_pontmeyer(session)
    repo = ShipToRepo(session)
    state = {
        "email_id": "p4",
        "klant_match": {"navision_klantnr": "20001"},
        "afleveradres": None,
        "email_subject": "Bestelling",
        "bijlagen": [{"naam": "po.pdf", "type": "pdf", "inhoud_tekst": "Artikel 123 x 5"}],
        "needs_review_fields": [],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] is None
    assert "ship_to_gekozen" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_needs_review_field_not_duplicated(session):
    _add(
        session,
        klant_nr="10001",
        ship_to_code="UTR",
        naam="A",
        straat="X",
        postcode="3500 AA",
        plaats="Utrecht",
        land="NL",
        is_default=True,
    )
    _add(
        session,
        klant_nr="10001",
        ship_to_code="AMS",
        naam="B",
        straat="Y",
        postcode="1000 AB",
        plaats="Amsterdam",
        land="NL",
        is_default=False,
    )
    repo = ShipToRepo(session)
    state = {
        "email_id": "x6",
        "klant_match": {"navision_klantnr": "10001"},
        "afleveradres": {"postcode": "9999 ZZ", "plaats": "Groningen"},
        # Pre-existing entry from an earlier (hypothetical) run.
        "needs_review_fields": ["ship_to_gekozen"],
    }
    out = await select_ship_to_node(state, repo=repo)
    assert out["ship_to_gekozen"] is None
    assert out["needs_review_fields"].count("ship_to_gekozen") == 1
