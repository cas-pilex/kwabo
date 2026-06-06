"""End-to-end CLOSURE tests for the two self-learning loops.

The existing tests cover the write side (approve -> DB) and the read side
(node uses a seeded fact) SEPARATELY. These tests close the loop in one run:
a human approval learns a fact, and the NEXT order is shown to actually use
that fact. That is the "does it really work" guarantee.

Two loops:
  1. Article-match learning: `_learn_from_approved` writes klant-SKU -> Kwabo
     into klantenkaart_artikelen + artikel_matching_history; `match_articles_node`
     then matches a fresh identical line via klantenkaart / history before fuzzy.
  2. Europallet pallet-knowledge: `_persist_pallet_feedback` writes
     (artikel, eenheid) -> pallet ja/nee into artikel_pallet_kennis;
     `compute_europallet_node` then honours that over the heuristic.

Reuses the wiring pattern from test_match_articles_needs_review.py: the
`app_engine` fixture binds the node's module-level engine to the test DB, klant
10001 is seeded by conftest, and the mock NAV knows item 1515155.
"""
from __future__ import annotations

import pytest

from kwabo.api.orders import _learn_from_approved, _persist_pallet_feedback
from kwabo.db.repository import ArtikelRepo, PalletKennisRepo
from kwabo.graph.nodes.compute_europallet import compute_europallet_node
from kwabo.graph.nodes.match_articles import match_articles_node


@pytest.fixture
def app_engine(session, monkeypatch):
    """Bind the match_articles node's module-level engine to the test DB so
    its internal `Session(engine)` reads the rows we learn via `session`."""
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_articles as ma_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(ma_mod, "engine", new_engine)
    yield


# --------------------------------------------------------------------------- #
# Loop 1 — article-match learning: learn on approve -> used on next order
# --------------------------------------------------------------------------- #


def _approved_state(klant_nr: str, klant_sku: str, matched: str) -> dict:
    """A minimal final-approved state the way _learn_from_approved reads it."""
    return {
        "klant_match": {"navision_klantnr": klant_nr},
        "orderregels": [
            {
                "artikelnummer_klant": klant_sku,
                "artikelnummer_kwabo_matched": matched,
                "omschrijving": "Geleerd artikel",
            }
        ],
    }


def _incoming_state(klant_nr: str, klant_sku: str) -> dict:
    """A fresh incoming order line with only the customer SKU (no Kwabo nr,
    no description) so ONLY the learned mapping/history can resolve it."""
    return {
        "email_id": "selflearn-e2e",
        "email_from": "x@y.nl",
        "email_subject": "Test",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "klant_match": {"navision_klantnr": klant_nr},
        "orderregels": [
            {
                "positie": 1,
                "artikelnummer_klant": klant_sku,
                "artikelnummer_kwabo": None,
                "omschrijving": "",
                "hoeveelheid": 1,
            }
        ],
    }


@pytest.mark.asyncio
async def test_learned_mapping_is_used_next_order(session, app_engine):
    """Approve learns klant-SKU -> 1515155 (klantenkaart). A later identical
    line then matches via 'klantenkaart' instead of fuzzy/manual."""
    # Pre-condition: nothing learned yet -> the line cannot resolve (manual).
    before = await match_articles_node(_incoming_state("10001", "ZELF-SKU"))
    assert before["orderregels"][0]["match_methode"] == "manual"
    assert before["orderregels"][0]["artikelnummer_kwabo_matched"] is None

    # Human approves an order that maps ZELF-SKU -> 1515155.
    _learn_from_approved(session, _approved_state("10001", "ZELF-SKU", "1515155"))
    session.commit()

    # Next order with the same customer SKU now auto-matches via klantenkaart.
    after = await match_articles_node(_incoming_state("10001", "ZELF-SKU"))
    regel = after["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "1515155"
    assert regel["match_methode"] == "klantenkaart"
    assert regel["match_confidence"] >= 0.9


@pytest.mark.asyncio
async def test_history_path_used_when_no_mapping(session, app_engine):
    """With no klantenkaart mapping but a matching history, the frequency-best
    history entry resolves the line via the 'history' branch."""
    repo = ArtikelRepo(session)
    # Frequency: 1515155 wins (2x) over the alternative (1x).
    repo.add_history(
        klant_nr="10001", klant_artikelnr="HIST-SKU", klant_omschrijving="x",
        kwabo_artikelnr="1515155", match_methode="manual", was_correctie=True,
    )
    repo.add_history(
        klant_nr="10001", klant_artikelnr="HIST-SKU", klant_omschrijving="x",
        kwabo_artikelnr="1515155", match_methode="manual", was_correctie=True,
    )
    repo.add_history(
        klant_nr="10001", klant_artikelnr="HIST-SKU", klant_omschrijving="x",
        kwabo_artikelnr="9999999", match_methode="manual", was_correctie=True,
    )
    session.commit()
    # Guard: no klantenkaart mapping exists for this SKU.
    assert repo.mapping("10001", "HIST-SKU") is None

    out = await match_articles_node(_incoming_state("10001", "HIST-SKU"))
    regel = out["orderregels"][0]
    assert regel["artikelnummer_kwabo_matched"] == "1515155"
    assert regel["match_methode"] == "history"
    assert regel["match_confidence"] >= 0.9


# --------------------------------------------------------------------------- #
# Loop 2 — europallet pallet-knowledge: learn on approve -> used on next order
# --------------------------------------------------------------------------- #


def _pallet_state(artikelnr: str, eenheid: str, qty: float, *, europallet=None) -> dict:
    """A state with one contributing line; optional europallet_regel to signal
    the human's pallet decision to _persist_pallet_feedback."""
    return {
        "email_id": "pallet-e2e",
        "orderregels": [
            {
                "positie": 1,
                "artikelnummer_kwabo_matched": artikelnr,
                "eenheid": eenheid,
                "hoeveelheid": qty,
            }
        ],
        "europallet_regel": europallet,
    }


@pytest.mark.asyncio
async def test_learned_pallet_required_adds_europallet(session):
    """ROL is ignored by the heuristic, so without knowledge no pallet is added.
    After the human confirms a pallet (learned pallet_required=True), the next
    identical order DOES get a europallet."""
    # Pre-condition: no kennis -> ROL contributes nothing -> no europallet.
    pre = await compute_europallet_node(
        _pallet_state("ART1", "ROL", 24), repo=PalletKennisRepo(session)
    )
    assert pre["europallet_regel"] is None

    # Human approved an order WITH a europallet -> learn pallet_required=True.
    _persist_pallet_feedback(
        session,
        _pallet_state("ART1", "ROL", 24, europallet={"artikelnummer_kwabo": "19820"}),
        reviewer="cas@kwabo.nl",
    )
    # Confirm the fact was written.
    kennis = PalletKennisRepo(session).lookup("ART1", "ROL")
    assert kennis is not None and kennis.pallet_required is True

    # Next identical order now gets a europallet via the learned knowledge.
    post = await compute_europallet_node(
        _pallet_state("ART1", "ROL", 24), repo=PalletKennisRepo(session)
    )
    assert post["europallet_regel"] is not None
    assert post["europallet_regel"]["hoeveelheid"] == 1  # 24 / per_pallet(24)


@pytest.mark.asyncio
async def test_learned_pallet_suppressed_blocks_europallet(session):
    """DOOS qty>=5 normally triggers the heuristic pallet. After the human
    removes it (learned pallet_required=False), the next identical order does
    NOT get a europallet — the learned 'no' overrides the heuristic."""
    # Pre-condition: heuristic WOULD add a pallet for 24 DOOS.
    pre = await compute_europallet_node(
        _pallet_state("ART2", "DOOS", 24), repo=PalletKennisRepo(session)
    )
    assert pre["europallet_regel"] is not None

    # Human approved with europallet removed -> learn pallet_required=False.
    _persist_pallet_feedback(
        session,
        _pallet_state("ART2", "DOOS", 24, europallet=None),
        reviewer="cas@kwabo.nl",
    )
    kennis = PalletKennisRepo(session).lookup("ART2", "DOOS")
    assert kennis is not None and kennis.pallet_required is False

    # Next identical order: learned 'no' suppresses the heuristic pallet.
    post = await compute_europallet_node(
        _pallet_state("ART2", "DOOS", 24), repo=PalletKennisRepo(session)
    )
    assert post["europallet_regel"] is None
