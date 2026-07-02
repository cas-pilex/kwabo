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


def pallet_uom_code(eenheden: list, verkoop_eenheid: str | None = None) -> Optional[str]:
    """De ONDUBBELZINNIGE pallet-verkoopeenheid van een artikel, of None.

    Niet-mix-rijen (``is_mix_uom`` False) met code-prefix ``PAL`` en
    ``qty_per_base > 0``, deterministische voorkeursorde (B3):
      1. exacte ``PAL``- of ``PALLET``-rij (de canonieke NAV-code; #845:
         15620 heeft PALLET(30) én PALLET35 — 'PALLET' is de verkoopcode)
      2. de kaart-``verkoop_eenheid`` (NAV Sales_Unit_of_Measure), mits die
         zelf een niet-mix pallet-rij van dit artikel is
      3. precies één PAL-prefix-rij
    Meerdere varianten zonder zo'n voorkeur (238601: PALLET30/33/35/42) zijn
    ambigu -> None, zodat we niet gokken. Spiegelt ``pallet_logic``.
    """
    pals = [
        e for e in eenheden
        if (e.eenheid_code or "").strip().upper().startswith("PAL")
        and not getattr(e, "is_mix_uom", False)
        and (e.qty_per_base or 0) > 0
    ]
    if not pals:
        return None
    exact = [e for e in pals
             if (e.eenheid_code or "").strip().upper() in ("PAL", "PALLET")]
    if exact:
        return exact[0].eenheid_code.strip()
    vk = (verkoop_eenheid or "").strip().upper()
    if vk:
        vk_rij = [e for e in pals if (e.eenheid_code or "").strip().upper() == vk]
        if vk_rij:
            return vk_rij[0].eenheid_code.strip()
    if len(pals) == 1:
        return pals[0].eenheid_code.strip()
    return None


def resolve_line_uom(regel: dict, base: str, eenheden: list,
                     verkoop_eenheid: str | None = None) -> tuple[str, bool]:
    """Bepaal de NAV-eenheid voor één regel. Geeft ``(eenheid, needs_review)``.

    HET EENHEID-CONTRACT (B3) — vaste volgorde, overal dezelfde uitkomst:
      a. bestelde eenheid is een geldige Item-UoM -> die canonieke code
         (omrekenen naar base doet Branch A / `_verkoop_keuze` in
         apply_mixprijzen; de composer emit áltijd expliciet)
      b. pallet-familie ("PAL"/"Paletten") -> de artikel-pallet-UoM via
         `pallet_uom_code` (voorkeur: exacte PALLET > verkoop_eenheid > enige)
      c. mix-klant + mix-UoM -> staffel M{X}PAL{Y} (apply_mixprijzen._evaluate)
      d. anders de verkoop_eenheid/base van de kaart (Branch A)
      e. NOOIT een code die niet in de Item-UoM bestaat naar NAV: onbekende
         eenheid -> base + VLAG (review), geen stille terugval.

    1. leeg of == base                       -> base, geen vlag
    2. bestelde code zit exact in item-UoM    -> die canonieke code, geen vlag
    3. pallet-familie ("PAL"...) + pallet-voorkeurscode -> die code (brug)
    4. anders (onbekende/ongeldige eenheid)   -> base, VLAG (review)
    """
    base = (base or "").strip()
    base_upper = base.upper()

    code_by_upper = {
        (e.eenheid_code or "").strip().upper(): (e.eenheid_code or "").strip()
        for e in eenheden if e.eenheid_code
    }
    code_by_upper.setdefault(base_upper, base)

    # Herverwerking/handmatige artikel-match: `eenheid` kan al eerder op base
    # zijn teruggevallen; de BESTELDE eenheid staat dan in `eenheid_origineel`.
    # Die is leidend — anders is herverwerken nooit idempotent (#819/#845-rerun).
    ordered = (regel.get("eenheid_origineel") or regel.get("eenheid") or "").strip()
    ordered_upper = ordered.upper()

    if not ordered or ordered_upper == base_upper:
        return base, False
    if ordered_upper in code_by_upper:
        return code_by_upper[ordered_upper], False
    if ordered_upper.startswith("PAL"):
        pc = pallet_uom_code(eenheden, verkoop_eenheid=verkoop_eenheid)
        if pc:
            return pc, False
    return base, True
