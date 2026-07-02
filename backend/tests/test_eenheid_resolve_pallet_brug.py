"""B3 (structurele upgrade): de pallet-brug mag niet weigeren zodra een artikel
meer dan één pallet-variant heeft.

Faalgeval #845/#203 (Lasaulec, artikel 15620): besteld "2 PAL"; het artikel
heeft PALLET(30) én PALLET35(35). ``pallet_uom_code`` gaf None (ambigu) ->
terugval STUK + vlag -> NAV zou 2 STUK krijgen waar 2 pallets (=60 stuks)
besteld is. Deterministische voorkeursorde: exacte "PAL"/"PALLET"-code >
verkoop_eenheid-van-de-kaart (mits pallet-familie) > precies één variant >
anders None (echt ambigu blijft vlaggen, bv. 238601 PALLET30/33/35/42).
"""
from __future__ import annotations

from dataclasses import dataclass

from kwabo.utils.eenheid_resolve import pallet_uom_code, resolve_line_uom


@dataclass
class _E:
    eenheid_code: str
    qty_per_base: float = 1.0
    is_mix_uom: bool = False


def test_exacte_pallet_code_wint_bij_meerdere_varianten():
    """15620: PALLET(30) + PALLET35(35) -> exacte 'PALLET' wint, geen vlag."""
    eenheden = [_E("STUK", 1), _E("KG", 1), _E("PALLET", 30), _E("PALLET35", 35),
                _E("M5PAL30", 30, is_mix_uom=True)]
    assert pallet_uom_code(eenheden) == "PALLET"
    eenheid, vlag = resolve_line_uom({"eenheid": "PAL"}, "STUK", eenheden)
    assert eenheid == "PALLET"
    assert vlag is False


def test_verkoop_eenheid_breekt_variantkeuze():
    """Geen exacte PALLET-code, wel meerdere varianten: de kaart-verkoopeenheid
    (NAV Sales_Unit_of_Measure) wijst de juiste pallet-maat aan."""
    eenheden = [_E("STUK", 1), _E("PALLET30", 30), _E("PALLET42", 42)]
    assert pallet_uom_code(eenheden, verkoop_eenheid="PALLET42") == "PALLET42"
    eenheid, vlag = resolve_line_uom({"eenheid": "PAL"}, "STUK", eenheden,
                                     verkoop_eenheid="PALLET42")
    assert eenheid == "PALLET42"
    assert vlag is False


def test_echt_ambigu_blijft_vlaggen():
    """238601-patroon: meerdere varianten, verkoopeenheid geen pallet-familie
    -> geen gok: terugval base + vlag (e-regel: nooit ongeldig naar NAV)."""
    eenheden = [_E("STUK", 1), _E("PALLET30", 30), _E("PALLET42", 42)]
    assert pallet_uom_code(eenheden, verkoop_eenheid="STUK") is None
    eenheid, vlag = resolve_line_uom({"eenheid": "PAL"}, "STUK", eenheden,
                                     verkoop_eenheid="STUK")
    assert eenheid == "STUK"
    assert vlag is True


def test_mix_verkoop_eenheid_telt_niet_als_pallet_keuze():
    """Een mix-staffelcode als verkoopeenheid (NAV-datafout, #941) mag de
    pallet-brug niet sturen."""
    eenheden = [_E("STUK", 1), _E("PALLET30", 30), _E("PALLET42", 42),
                _E("M1PAL30", 30, is_mix_uom=True)]
    assert pallet_uom_code(eenheden, verkoop_eenheid="M1PAL30") is None


def test_herverwerking_brugt_op_eenheid_origineel():
    """Herverwerking van een opgeslagen order (#819/#845-rerun, stale prod-
    records): `eenheid` is dan al eerder op base teruggevallen en de bestelde
    eenheid staat in `eenheid_origineel` — de brug moet dáárop werken, anders
    is herverwerken nooit idempotent."""
    eenheden = [_E("STUK", 1), _E("PALLET", 20)]
    regel = {"eenheid": "STUK", "eenheid_origineel": "PAL"}
    eenheid, vlag = resolve_line_uom(regel, "STUK", eenheden)
    assert eenheid == "PALLET"
    assert vlag is False


def test_enkele_variant_blijft_werken():
    """#819 (23691): precies één pallet-rij -> die (bestaand gedrag)."""
    eenheden = [_E("STUK", 1), _E("PALLET", 20)]
    assert pallet_uom_code(eenheden) == "PALLET"
