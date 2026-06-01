"""Regressie: bij approve leert het systeem van de uiteindelijke order-state.

De self-learning loop (klant-SKU -> kwabo-artikel in klantenkaart + history) werd
nooit gevoed: de dashboard-`approve()` stuurt geen `artikel_correcties`, en
reviewer-edits gaan via patch-field naar de order_state. `_learn_from_approved`
leidt de mappings af uit de definitieve orderregels, zodat een volgende identieke
regel via klantenkaart/history auto-matcht. Ontdekt 31-05-2026.
[[artikel-automatch-data-sparsity]]
"""
from __future__ import annotations

from kwabo.api.orders import _learn_from_approved
from kwabo.db.repository import ArtikelRepo


def test_records_mapping_and_history_from_state(session):
    state = {
        "klant_match": {"navision_klantnr": "69001"},
        "orderregels": [
            {"artikelnummer_klant": "CUST-AB1", "artikelnummer_kwabo_matched": "KW-900", "omschrijving": "Vlies"},
            {"artikelnummer_klant": "CUST-AB2", "artikelnummer_kwabo_matched": None},  # niet gematcht -> skip
            {"artikelnummer_klant": None, "artikelnummer_kwabo_matched": "KW-901"},      # geen klant-SKU -> skip
        ],
    }
    _learn_from_approved(session, state)
    repo = ArtikelRepo(session)
    m = repo.mapping("69001", "CUST-AB1")
    assert m and m.kwabo_artikelnr == "KW-900"
    h = repo.best_history("69001", "CUST-AB1")
    assert h and h.kwabo_artikelnr == "KW-900"
    # Regels zonder klant-SKU of zonder match zijn NIET geleerd.
    assert repo.mapping("69001", "CUST-AB2") is None


def test_no_klant_nr_is_noop(session):
    state = {"klant_match": {}, "orderregels": [
        {"artikelnummer_klant": "X", "artikelnummer_kwabo_matched": "KW-1"}]}
    _learn_from_approved(session, state)  # geen klant -> mag niet crashen, niks geleerd
    assert ArtikelRepo(session).mapping("", "X") is None
