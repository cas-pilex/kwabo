"""Functie 4 — europallet-telling deterministisch + verklaarbaar.

De pallet-maat van een artikel met MEERDERE pallet-families (238601: PALLET30/33/
35/42) is ambigu uit de item-UoM alleen. De autoritatieve maat is de
verkoopeenheid (Artikelkaart.verkoop_eenheid, NAV Sales_Unit_of_Measure) — net
als apply_mixprijzen die familie kiest. Daarmee wordt de europallet-telling
reproduceerbaar:

  #832: 33 STUK 238601 (verkoop PALLET33=33) -> 1 europallet (niet 2/None).
  #833: 5 STUK 229231 (80) + 15 STUK 238531 (33) -> 0,06+0,45 = 0,51 -> 1.

De telregel (drempel 0,5; ceil) wordt parametrisch vastgelegd, en de onderbouwing
landt in _meta.europallet.
"""
from __future__ import annotations

import json
from math import ceil
from pathlib import Path

import pytest

from kwabo.db.models import Artikelkaart, ArtikelEenheid
from kwabo.graph.nodes import compute_europallet as ce_mod
from kwabo.graph.nodes.compute_europallet import compute_europallet_node
from kwabo.utils.pallet_logic import compute_europallet, europallet_breakdown

STATES = Path(__file__).resolve().parent / "test_data" / "states"


# --- lichtgewicht stubs (pure-logica) -----------------------------------

class _NoKennis:
    def lookup(self, artikelnr, eenheid):
        return None


class _UOM:
    def __init__(self, code: str, qty_per_base: float):
        self.eenheid_code = code
        self.qty_per_base = qty_per_base
        self.is_mix_uom = False


class _Kaart:
    def __init__(self, verkoop_eenheid):
        self.verkoop_eenheid = verkoop_eenheid


class _UomRepo:
    """uom_repo met .get (verkoop_eenheid) + .list_eenheden, per artikel."""

    def __init__(self, eenheden_per_art: dict, verkoop_per_art: dict):
        self._e = eenheden_per_art
        self._v = verkoop_per_art

    def list_eenheden(self, artikelnr):
        return self._e.get(artikelnr, [])

    def get(self, artikelnr):
        return _Kaart(self._v.get(artikelnr))


_EENHEDEN_238601 = [_UOM("STUK", 1), _UOM("PALLET30", 30), _UOM("PALLET33", 33),
                    _UOM("PALLET35", 35), _UOM("PALLET42", 42)]


def _state(regels):
    return {"email_id": "f4", "orderregels": regels}


def _stuk_repo(verkoop="PALLET33"):
    return _UomRepo({"238601": _EENHEDEN_238601}, {"238601": verkoop})


# --- DEEL A: telregel parametrisch (238601, pallet-maat 33) -------------

@pytest.mark.parametrize("qty,verwacht", [
    (0, None),     # niets
    (16, None),    # 16/33 = 0.48 < 0.5
    (17, 1),       # 0.515 -> 1
    (33, 1),       # 1.0
    (34, 2),       # 1.03 -> 2
    (66, 2),       # 2.0
    (99, 3),       # 3.0
])
def test_telregel_stuk_via_verkoopeenheid(qty, verwacht):
    state = _state([{"positie": 1, "artikelnummer_kwabo_matched": "238601",
                     "eenheid_origineel": "STUK", "hoeveelheid": qty}])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=_stuk_repo())
    if verwacht is None:
        assert regel is None
    else:
        assert regel is not None and regel["hoeveelheid"] == verwacht


def test_pal_line_counts_one_to_one():
    state = _state([{"positie": 1, "artikelnummer_kwabo_matched": "238601",
                     "eenheid_origineel": "PAL", "hoeveelheid": 3}])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=_stuk_repo())
    assert regel is not None and regel["hoeveelheid"] == 3


def test_mix_line_counts_mix_aantal():
    state = _state([{"positie": 1, "artikelnummer_kwabo_matched": "238601",
                     "eenheid_origineel": "ROL", "hoeveelheid": 805,
                     "mix_uom_gekozen": "M33PAL35", "mix_aantal": 23}])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=_stuk_repo())
    assert regel is not None and regel["hoeveelheid"] == 23


def test_geen_verkoopeenheid_blijft_conservatief():
    """Zonder verkoop_eenheid én meerdere families: terugval op _pallet_base_units
    (None) -> regel draagt niets bij (ongewijzigd gedrag, geen regressie)."""
    state = _state([{"positie": 1, "artikelnummer_kwabo_matched": "238601",
                     "eenheid_origineel": "STUK", "hoeveelheid": 66}])
    regel = compute_europallet(state, repo=_NoKennis(), uom_repo=_stuk_repo(verkoop=None))
    assert regel is None


def test_breakdown_bevat_onderbouwing():
    state = _state([{"positie": 1, "artikelnummer_kwabo_matched": "238601",
                     "eenheid_origineel": "STUK", "hoeveelheid": 33}])
    bd = europallet_breakdown(state, repo=_NoKennis(), uom_repo=_stuk_repo())
    assert bd["europallet_aantal"] == 1
    assert abs(bd["totaal_pallets"] - 1.0) < 1e-6
    assert len(bd["regels"]) == 1
    r = bd["regels"][0]
    assert r["artikelnr"] == "238601" and abs(r["pallets"] - 1.0) < 1e-6
    assert r["pallet_maat"] == 33


# --- #832 / #833 op de echte masterdata via de node (+ _meta) ----------

@pytest.fixture
def app_engine(session, monkeypatch):
    new_engine = session.get_bind()
    monkeypatch.setattr(ce_mod, "engine", new_engine)
    yield


def _seed_real(session, specs: dict[str, str | None]) -> None:
    ae = json.loads((STATES / "artikel_eenheden.json").read_text("utf-8"))
    for nr, verkoop in specs.items():
        session.add(Artikelkaart(kwabo_artikelnr=nr, naam=f"art {nr}",
                                 basis_eenheid="STUK", verkoop_eenheid=verkoop))
        for r in (x for x in ae if x["kwabo_artikelnr"] == nr):
            session.add(ArtikelEenheid(**r))
    session.commit()


@pytest.mark.asyncio
async def test_832_is_een_europallet(session, app_engine):
    _seed_real(session, {"238601": "PALLET33"})
    state = _state([{"positie": 1, "artikelnummer_kwabo_matched": "238601",
                     "eenheid_origineel": "STUK", "eenheid": "STUK", "hoeveelheid": 33}])
    out = await compute_europallet_node(state)
    assert out["europallet_regel"]["hoeveelheid"] == 1
    meta = out["_meta"]["europallet"]
    assert meta["europallet_aantal"] == 1
    assert meta["regels"][0]["pallet_maat"] == 33


@pytest.mark.asyncio
async def test_833_is_een_europallet(session, app_engine):
    _seed_real(session, {"229231": "PALLET", "238531": "PALLET33"})
    state = _state([
        {"positie": 1, "artikelnummer_kwabo_matched": "229231",
         "eenheid_origineel": "STUK", "eenheid": "STUK", "hoeveelheid": 5},
        {"positie": 2, "artikelnummer_kwabo_matched": "238531",
         "eenheid_origineel": "STUK", "eenheid": "STUK", "hoeveelheid": 15},
    ])
    out = await compute_europallet_node(state)
    assert out["europallet_regel"]["hoeveelheid"] == 1
    meta = out["_meta"]["europallet"]
    assert meta["europallet_aantal"] == 1
    assert meta["totaal_pallets"] >= 0.5
