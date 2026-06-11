"""Fase 4 (C1, audit §12.D.3): validate_prices opent precies één DB-sessie.

Vóór de fix opende de provenance-loop een tweede `Session(engine)` per run,
terwijl alle data al via de eerste sessie beschikbaar is.
"""
from __future__ import annotations

import pytest

from kwabo.graph.nodes import validate_prices as vp


@pytest.mark.asyncio
async def test_validate_prices_opent_precies_een_sessie(monkeypatch, session):
    monkeypatch.setattr(vp, "engine", session.get_bind())

    calls = {"n": 0}
    real_session = vp.Session

    def counting_session(*args, **kwargs):
        calls["n"] += 1
        return real_session(*args, **kwargs)

    monkeypatch.setattr(vp, "Session", counting_session)

    state = {
        "email_id": "sessie-telling",
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [
            {"positie": 1, "artikelnummer_kwabo_matched": "238601",
             "hoeveelheid": 10.0, "eenheid": "STUK", "prijs_per_eenheid": 12.5},
            {"positie": 2, "artikelnummer_kwabo_matched": None,
             "hoeveelheid": 5.0, "eenheid": "STUK", "prijs_per_eenheid": None},
        ],
        "needs_review_fields": [],
    }
    out = await vp.validate_prices_node(state)

    assert len(out["orderregels"]) == 2  # node draaide volledig
    assert calls["n"] == 1, f"verwacht 1 sessie, maar er werden {calls['n']} geopend"
