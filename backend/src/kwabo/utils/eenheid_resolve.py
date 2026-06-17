"""Bestelde eenheid -> canonieke artikel-UoM-code (Functie 3).

De extractor normaliseert vrije tekst naar generieke codes (``eenheid_mapping``):
"Paletten" -> "PAL". NAV's eigen item-UoM-code is echter artikel-specifiek en
heet vaak "PALLET" (qty_per_base 20/30/33...). Een exacte string-match laat
"PAL" dan vallen en valt terug op de base-eenheid (STUK) — terwijl er een
geldige pallet-verkoopeenheid bestaat (faalgeval #819).

Deze helper wordt zowel door de pipeline (``match_articles``) als door de
handmatige correctie (``api/preview.py``) gebruikt, zodat beide exact dezelfde
regels volgen.
"""
from __future__ import annotations

from typing import Optional


def pallet_uom_code(eenheden: list) -> Optional[str]:
    """De ONDUBBELZINNIGE pallet-verkoopeenheid van een artikel, of None.

    Niet-mix-rijen (``is_mix_uom`` False) met code-prefix ``PAL`` en
    ``qty_per_base > 0``: prefer een exacte ``PAL``-rij, anders precies één
    PAL-prefix-rij. Meerdere varianten (238601: PALLET33/35/42) zijn ambigu ->
    None, zodat we niet gokken. Spiegelt ``pallet_logic._pallet_base_units``.
    """
    pals = [
        e for e in eenheden
        if (e.eenheid_code or "").strip().upper().startswith("PAL")
        and not getattr(e, "is_mix_uom", False)
        and (e.qty_per_base or 0) > 0
    ]
    if not pals:
        return None
    exact = [e for e in pals if (e.eenheid_code or "").strip().upper() == "PAL"]
    if exact:
        return exact[0].eenheid_code.strip()
    if len(pals) == 1:
        return pals[0].eenheid_code.strip()
    return None


def resolve_line_uom(regel: dict, base: str, eenheden: list) -> tuple[str, bool]:
    """Bepaal de NAV-eenheid voor één regel. Geeft ``(eenheid, needs_review)``.

    1. leeg of == base                       -> base, geen vlag
    2. bestelde code zit exact in item-UoM    -> die canonieke code, geen vlag
    3. pallet-familie ("PAL"...) + ondubbelzinnige pallet-code -> die code (brug)
    4. anders (onbekende/ongeldige eenheid)   -> base, VLAG (review)
    """
    base = (base or "").strip()
    base_upper = base.upper()

    code_by_upper = {
        (e.eenheid_code or "").strip().upper(): (e.eenheid_code or "").strip()
        for e in eenheden if e.eenheid_code
    }
    code_by_upper.setdefault(base_upper, base)

    ordered = (regel.get("eenheid") or "").strip()
    ordered_upper = ordered.upper()

    if not ordered or ordered_upper == base_upper:
        return base, False
    if ordered_upper in code_by_upper:
        return code_by_upper[ordered_upper], False
    if ordered_upper.startswith("PAL"):
        pc = pallet_uom_code(eenheden)
        if pc:
            return pc, False
    return base, True
