"""B4 (structurele upgrade): europallet op een EXPLICIETE databron.

Nico's voorstel: per (artikel, eenheid) een veld ``pallet_plaatsen_basis`` —
hoeveel palletplaatsen één regel-eenheid inneemt (0 = neemt geen plaats,
wordt bijgepakt). Bron-prioriteit: dit veld > NAV-eenheid (verkoop_eenheid/
PAL-familie) > NIETS. Het leerbestand ``artikel_pallet_kennis`` (per_pallet
default 24, aantoonbaar vervuild: #832 telde 33/24=1.375->2 en #716 66/24->3)
wordt GENEGEERD tot het is opgeschoond. Regels zonder enige bron krijgen een
vlag "europallet onbekend" — geen gok (de /24-DOOS-heuristiek vervalt).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import unittest.mock as um

import pytest

from kwabo.db.models import Artikelkaart
from kwabo.graph.nodes.compute_europallet import compute_europallet_node
from kwabo.utils.pallet_logic import europallet_breakdown


@dataclass
class _E:
    eenheid_code: str
    qty_per_base: float = 1.0
    is_mix_uom: bool = False


@dataclass
class _Kaart:
    verkoop_eenheid: Optional[str] = None


@dataclass
class _Kennis:
    pallet_required: bool = True
    per_pallet: int = 24


@dataclass
class _Plaatsen:
    plaatsen_per_eenheid: float = 0.0


class _KennisRepo:
    def __init__(self, waarde=None):
        self.waarde = waarde

    def lookup(self, artikelnr, eenheid):
        return self.waarde


class _UomRepo:
    def __init__(self, eenheden, verkoop_eenheid=None):
        self.eenheden = eenheden
        self.verkoop = verkoop_eenheid

    def list_eenheden(self, artikelnr):
        return self.eenheden

    def get(self, artikelnr):
        return _Kaart(verkoop_eenheid=self.verkoop)


class _PlaatsenRepo:
    def __init__(self, mapping):
        self.mapping = mapping  # (artikelnr, eenheid) -> plaatsen_per_eenheid

    def lookup(self, artikelnr, eenheid):
        v = self.mapping.get((artikelnr, (eenheid or "").upper()))
        return _Plaatsen(plaatsen_per_eenheid=v) if v is not None else None


def _state(regels):
    return {"orderregels": regels}


def _regel(art="238601", qty=33.0, eenheid="STUK"):
    return {"positie": 1, "artikelnummer_kwabo_matched": art,
            "hoeveelheid": qty, "eenheid": eenheid, "eenheid_origineel": eenheid}


_AMBIGU_UOM = [_E("STUK", 1), _E("PALLET30", 30), _E("PALLET33", 33),
               _E("PALLET35", 35), _E("PALLET42", 42)]


def test_pallet_plaatsen_basis_wint_van_leerbestand_en_uom():
    """#832: 33 STUK 238601 -> exact 1 palletplaats via het expliciete veld
    (1/33 plaats per stuk), OOK al zegt het vervuilde leerbestand 24/pallet
    en is de NAV-familie ambigu."""
    bd = europallet_breakdown(
        _state([_regel()]),
        repo=_KennisRepo(_Kennis(per_pallet=24)),
        uom_repo=_UomRepo(_AMBIGU_UOM, verkoop_eenheid="STUK"),
        plaatsen_repo=_PlaatsenRepo({("238601", "STUK"): 1 / 33}),
    )
    assert bd["europallet_aantal"] == 1
    assert bd["regels"][0]["bron"] == "pallet_plaatsen_basis"
    assert not bd["onbekend"]


def test_veld_nul_betekent_geen_palletplaats_geen_vlag():
    """plaatsen_per_eenheid=0 is een BEWUSTE waarde (bijpak-artikel):
    bijdrage 0, geen europallet en geen onbekend-vlag."""
    bd = europallet_breakdown(
        _state([_regel(art="99999", qty=10)]),
        repo=_KennisRepo(None),
        uom_repo=_UomRepo([_E("STUK", 1)]),
        plaatsen_repo=_PlaatsenRepo({("99999", "STUK"): 0.0}),
    )
    assert bd["europallet_aantal"] == 0
    assert not bd["onbekend"]


def test_leerbestand_wordt_genegeerd_nav_eenheid_geldt():
    """#832-klasse zonder veld: het leerbestand (24) mag de telling NIET meer
    sturen; de NAV-eenheid (exacte PALLET-rij, 33/base) geldt -> 33 STUK = 1."""
    bd = europallet_breakdown(
        _state([_regel()]),
        repo=_KennisRepo(_Kennis(per_pallet=24)),
        uom_repo=_UomRepo([_E("STUK", 1), _E("PALLET", 33)]),
        plaatsen_repo=_PlaatsenRepo({}),
    )
    assert bd["europallet_aantal"] == 1
    assert bd["regels"][0]["bron"] in ("uom_familie", "uom_verkoopeenheid")


def test_geen_enkele_bron_geeft_onbekend_geen_gok():
    """Geen veld, geen bruikbare NAV-eenheid -> bijdrage 0 én expliciet
    'onbekend' (de node vlagt hierop); nooit een 24-heuristiek-gok."""
    bd = europallet_breakdown(
        _state([_regel(qty=33.0)]),
        repo=_KennisRepo(_Kennis(per_pallet=24)),
        uom_repo=_UomRepo(_AMBIGU_UOM, verkoop_eenheid="STUK"),
        plaatsen_repo=_PlaatsenRepo({}),
    )
    assert bd["europallet_aantal"] == 0
    assert bd["onbekend"] and bd["onbekend"][0]["artikelnr"] == "238601"


def test_doos_heuristiek_vervalt_naar_onbekend():
    """De oude 'DOOS = /24'-gok bestaat niet meer: DOOS zonder veld/NAV-maat
    is onbekend."""
    bd = europallet_breakdown(
        _state([_regel(art="55555", qty=48, eenheid="DOOS")]),
        repo=_KennisRepo(None),
        uom_repo=_UomRepo([_E("STUK", 1)]),
        plaatsen_repo=_PlaatsenRepo({}),
    )
    assert bd["europallet_aantal"] == 0
    assert bd["onbekend"]


@pytest.mark.asyncio
async def test_node_vlagt_europallet_onbekend(session):
    """Node-niveau: onbekende regels -> needs_review 'europallet' + warning,
    zodat de reviewer (en Nico's vul-lijst) het ziet."""
    session.add(Artikelkaart(kwabo_artikelnr="88888", naam="mysterie-artikel",
                             basis_eenheid="STUK", verkoop_eenheid="STUK"))
    session.commit()
    import kwabo.graph.nodes.compute_europallet as node_mod
    state = {"email_id": "b4-test", "orderregels": [_regel(art="88888", qty=10)],
             "needs_review_fields": [], "validatie_warnings": []}
    with um.patch.object(node_mod, "engine", session.get_bind()):
        out = await compute_europallet_node(state)
    assert "europallet" in (out.get("needs_review_fields") or [])
    assert any("europallet" in w.lower() and "onbekend" in w.lower()
               for w in out.get("validatie_warnings") or [])
