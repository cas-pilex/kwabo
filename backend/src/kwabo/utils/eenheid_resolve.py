"""HET EENHEID+AANTAL-CONTRACT (opdracht 2c) — één module, vaste volgorde.

(artikel, bestelde eenheid, aantal, mixstatus) -> (geldige NAV-UoM,
omgerekend aantal, vlag?, herkomst) — in deze volgorde:

  a. bestelde eenheid is een geldige Item-UoM -> die canonieke code;
  b. pallet-familie ("PAL"/"Paletten") -> de artikel-pallet-UoM via
     `pallet_uom_code` (voorkeur: exacte PALLET > verkoop_eenheid > enige);
  c. mix-klant + mix-UoM -> staffel M{X}PAL{Y}; de tier-keuze heeft
     ORDER-context (staffelbasis) en leeft daarom in
     graph/nodes/apply_mixprijzen._evaluate, maar alle regel-wiskunde
     (`to_base_qty`, `mix_tiers_for`, `plain_pallet_equiv`) staat hier;
  d. anders de verkoop_eenheid/base van de kaart (`branch_a`) — NAV default
     een nieuwe regel naar de kaart-VERKOOPEENHEID, dus de composer moet
     ALTIJD expliciet PATCHen (faalgeval #716: kale 66 werd 66 pallets);
  e. NOOIT een code die niet in de Item-UoM bestaat naar NAV: onbekende
     eenheid -> base + VLAG, geen stille terugval.

Elke beslissing schrijft een BRON in gewone taal (``EenheidKeuze.bron`` /
``regel["eenheid_bron"]``) zodat de reviewer per regel ziet wáár de eenheid
vandaan komt (Fase 2-UX-eis "eenheid-herkomst per regel").

Consolidatie F2.3 (her-diagnose 10-7): de beslislogica die verspreid stond
over apply_mixprijzen (_branch_a/_verkoop_keuze/_plain_pallet_equiv/
_to_rolls/_mix_codes_for) en deze module is hier samengebracht; de node en
api/preview.py roepen uitsluitend dit contract aan.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from kwabo.utils.mixcode import is_mix_code, parse_mix_code
from kwabo.utils.pallet_logic import _qty_per_base

# Hoe dicht een omrekening bij een geheel aantal moet liggen om automatisch
# geaccepteerd te worden. Pallets zijn heel; een niet-gehele uitkomst is een
# ambigu aantal dat we nooit stil afronden.
PALLET_TOL = 0.02


class EenheidKeuze(NamedTuple):
    """Uitkomst van stap a/b/e: de NAV-eenheid voor een regel + herkomst."""

    code: str
    vlag: bool
    bron: str


class MixTier(NamedTuple):
    """Een mix-staffeltier van één artikel: de letterlijke NAV-code, de
    geparste M-drempel (betrouwbaar) en het gezaghebbende aantal per pallet
    uit ``ArtikelEenheid.qty_per_base`` (NIET het PALxx-suffix: dat is een
    handgetypt label met typefouten in live NAV, item 15450)."""

    code: str
    m_threshold: int
    units_per_pallet: float


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


def bepaal_eenheid(regel: dict, base: str, eenheden: list,
                   verkoop_eenheid: str | None = None) -> EenheidKeuze:
    """Stap a/b/e van het contract, mét herkomst. Zie moduledocstring.

    1. leeg of == base                        -> base, geen vlag
    2. bestelde code zit exact in item-UoM    -> die canonieke code, geen vlag
    3. pallet-familie ("PAL"...) + voorkeurscode -> die code (pallet-brug)
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
        return EenheidKeuze(base, False,
                            f"standaard base-eenheid '{base}' van de artikelkaart")
    if ordered_upper in code_by_upper:
        code = code_by_upper[ordered_upper]
        return EenheidKeuze(code, False,
                            f"bestelde eenheid '{ordered}' is een geldige "
                            f"NAV-eenheid van dit artikel")
    if ordered_upper.startswith("PAL"):
        pc = pallet_uom_code(eenheden, verkoop_eenheid=verkoop_eenheid)
        if pc:
            return EenheidKeuze(pc, False,
                                f"pallet-brug: bestelde '{ordered}' -> "
                                f"artikel-pallet-eenheid '{pc}'")
    return EenheidKeuze(base, True,
                        f"terugval op base '{base}' + vlag: bestelde "
                        f"'{ordered}' is geen geldige NAV-eenheid van dit artikel")


def resolve_line_uom(regel: dict, base: str, eenheden: list,
                     verkoop_eenheid: str | None = None) -> tuple[str, bool]:
    """Backwards-compatibele 2-tuple-vorm van ``bepaal_eenheid``."""
    keuze = bepaal_eenheid(regel, base, eenheden, verkoop_eenheid=verkoop_eenheid)
    return keuze.code, keuze.vlag


def to_base_qty(regel: dict, eenheden: list) -> Optional[float]:
    """Bestelde hoeveelheid -> base-eenheden (rollen/stuks).

    Gebruikt de oorspronkelijk bestelde eenheid (``eenheid_origineel``), met
    terugval op ``eenheid``. Onbekende codes tellen als base (qty_per_base
    1.0). None bij een niet-positieve hoeveelheid.
    """
    try:
        qty = float(regel.get("hoeveelheid") or 0)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None
    unit = (regel.get("eenheid_origineel") or regel.get("eenheid") or "").strip().upper()
    if not unit:
        return qty
    return qty * _qty_per_base(eenheden, unit)


def mix_tiers_for(eenheden: list) -> list[MixTier]:
    """Parse de ArtikelEenheid-rijen naar mix-staffeltiers (gededupliceerd).

    Elke tier koppelt de geparste M-drempel aan de eigen ``qty_per_base``
    (== NAV ``Qty_per_Unit_of_Measure``) als gezaghebbend aantal per pallet;
    het PALxx-suffix is cosmetisch.
    """
    out: dict[str, MixTier] = {}
    for e in eenheden:
        mc = parse_mix_code(e.eenheid_code)
        if mc:
            out[mc.code] = MixTier(mc.code, mc.m_threshold, float(e.qty_per_base or 0))
    return list(out.values())


def verkoop_keuze(kaart, eenheden: list, base: str,
                  base_qty: float) -> Optional[tuple[str, float]]:
    """Branch A (E1): kies de verkoopeenheid waarin de regel naar NAV gaat.

    Primair de kaart-`verkoop_eenheid` (NAV Sales_Unit_of_Measure), mits het
    een geldige eenheid van dit artikel is én het bestelde base-aantal er op
    een geheel aantal in past. Zonder dat veld: afleiden uit ArtikelEenheid,
    maar alleen bij PRECIES ÉÉN gehele niet-mix kandidaat (artikel 238601
    heeft b.v. PALLET33 én 'EXW PAL33', beide 33/base — twee kandidaten is
    geen keuze maar een gok). Geen keuze -> None; de caller dwingt dan de
    base-eenheid expliciet af.
    """
    per_code = {
        (e.eenheid_code or "").strip().upper(): float(e.qty_per_base or 0)
        for e in eenheden
    }

    def _heel(per: float) -> Optional[int]:
        if per <= 0:
            return None
        n = base_qty / per
        return int(round(n)) if n >= 1 and abs(n - round(n)) <= PALLET_TOL else None

    code = ((kaart.verkoop_eenheid if kaart else "") or "").strip()
    if code and code.upper() != (base or "").upper():
        per = per_code.get(code.upper(), 0.0)
        if per > 0 and _heel(per) is not None:
            return code, per
        return None  # veld bekend maar ongeldig/niet-geheel -> expliciete base

    kandidaten = [
        (e.eenheid_code.strip(), float(e.qty_per_base))
        for e in eenheden
        if (e.qty_per_base or 0) > 1
        and not parse_mix_code(e.eenheid_code)
        and (e.eenheid_code or "").strip().upper() != (base or "").upper()
        and _heel(float(e.qty_per_base)) is not None
    ]
    return kandidaten[0] if len(kandidaten) == 1 else None


def plain_pallet_equiv(mix_code: str, eenheden: list,
                       base: str) -> Optional[tuple[str, float]]:
    """De PLAIN (niet-mix) pallet-eenheid die dezelfde fysieke pallet-maat heeft
    als een mix-staffelcode (zelfde ``qty_per_base``). NAV-kaarten dragen soms
    een mix-code als Sales_Unit_of_Measure (datafout, bv. 23522 -> M1PAL30);
    de juiste verkoopeenheid is dan de canonieke ``PALLET``-UoM van het artikel.

    Voorkeur: een eenheid waarvan de code met ``PALLET`` begint (de canonieke
    pallet-UoM, bv. ``PALLET`` of ``PALLET70``); is die er niet en is er precies
    één plain niet-base eenheid met de juiste maat, dan die. Anders None (ambigu).
    Geeft ``(code, qty_per_base)`` of None.
    """
    mix_qty = next(
        (float(e.qty_per_base or 0) for e in eenheden
         if (e.eenheid_code or "").strip().upper() == mix_code.upper()),
        0.0,
    )
    if mix_qty <= 1:
        return None
    plains = [
        (e.eenheid_code.strip(), float(e.qty_per_base))
        for e in eenheden
        if e.eenheid_code and not parse_mix_code(e.eenheid_code)
        and not getattr(e, "is_mix_uom", False)
        and float(e.qty_per_base or 0) == mix_qty
        and e.eenheid_code.strip().upper() != (base or "").upper()
    ]
    pallet = [p for p in plains if p[0].upper().startswith("PALLET")]
    if len(pallet) == 1:
        return pallet[0]
    if pallet:
        exact = [p for p in pallet if p[0].upper() == "PALLET"]
        return exact[0] if len(exact) == 1 else None
    return plains[0] if len(plains) == 1 else None


def branch_a(regel: dict, kaart, eenheden: list) -> Optional[str]:
    """Stap d (E1/E2): een niet-mix-regel krijgt ALTIJD een expliciete eenheid
    + het omgerekende aantal in `verkoop_uom_gekozen`/`verkoop_aantal`, en een
    `eenheid_bron` die de keuze in gewone taal uitlegt.

    NAV default een nieuwe orderregel naar de VERKOOPEENHEID van de kaart, niet
    naar de base-eenheid (faalgeval #716: quantity 66 zonder UoM-PATCH werd 66
    PALLET33 = €45.738 i.p.v. 2 PALLET33). Op NAV's default vertrouwen kan dus
    nooit. Een geldige NIET-base bestel-eenheid blijft staan (2-6-fix: "60
    stuks blijft 60 stuks") — de composer PATCHt die al expliciet.

    Pure functie over (regel, kaart, eenheden) — de callers halen de
    mirror-data op. Returns een review-waarschuwing (str) als de
    kaart-verkoopeenheid niet bruikbaar was (mix-staffelcode als Sales-UoM),
    anders None.
    """
    art = regel.get("artikelnummer_kwabo_matched")
    if not art:
        return None
    base = ((kaart.basis_eenheid if kaart else "") or "").strip()
    if not kaart or not base:
        return None  # geen mirror-data -> geen veilige keuze mogelijk
    ordered = (regel.get("eenheid") or "").strip()
    if ordered and ordered.upper() != base.upper():
        # Klant koos expliciet een geldige alternatieve eenheid — die blijft
        # staan (composer PATCHt hem al). Wel eventuele STALE afgeleiden uit
        # een eerdere run wissen (B3-herverwerking, #819-rerun): anders pusht
        # de composer de oude verkoop-keuze i.p.v. de gebrugde eenheid.
        regel.pop("verkoop_uom_gekozen", None)
        regel.pop("verkoop_aantal", None)
        regel["eenheid_bron"] = (
            f"bestelde eenheid '{ordered}' blijft staan (geldige NAV-eenheid; "
            f"composer PATCHt expliciet)"
        )
        return None
    try:
        qty = float(regel.get("hoeveelheid") or 0)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None

    # match_articles viel bij een ONgeldige bestel-eenheid al terug op base;
    # de hoeveelheid staat dan in de oorspronkelijke eenheid. Onbekende codes
    # tellen als base (qty_per_base 1.0) — zelfde aanname als to_base_qty.
    base_qty = qty * _qty_per_base(eenheden, regel.get("eenheid_origineel") or "")

    # PPG #941: een MIX-staffelcode (M{n}PAL{n}, bv. M1PAL30 op artikel 23522)
    # als Sales_Unit_of_Measure is een NAV-datafout — geen geldige
    # verkoopeenheid op een niet-mix-order. Nooit stil als verkoopeenheid
    # zetten: expliciete base + review (zo krijgen drie zusterartikelen niet
    # STUK/M1PAL30/PALLET door een scheve kaart). Een gewone pallet-code
    # (PALLET, PALLET33) is GEEN mix-code en blijft de normale Branch-A-keuze.
    code = ((kaart.verkoop_eenheid or "")).strip()
    if code and is_mix_code(code):
        # Vertaal de mix-staffelcode naar de PLAIN pallet-eenheid (zelfde maat)
        # zodat de regel consistent is met zuster-artikelen (23522 -> PALLET 2,
        # net als 23523) en geen handmatige review vergt. Geen schone vertaling
        # -> base + review-vlag (nooit stil de mix-code zelf gebruiken).
        plain = plain_pallet_equiv(code, eenheden, base)
        if plain is not None:
            pcode, per = plain
            n = base_qty / per
            if n >= 1 and abs(n - round(n)) <= PALLET_TOL:
                regel["verkoop_uom_gekozen"] = pcode
                regel["verkoop_aantal"] = int(round(n))
                regel["eenheid_bron"] = (
                    f"NAV-verkoopeenheid was mix-code '{code}' (datafout); "
                    f"vertaald naar plain '{pcode}' ({per:g}/base): "
                    f"{base_qty:g} {base} = {int(round(n))} x {pcode}"
                )
                return None
        regel["verkoop_uom_gekozen"] = base
        regel["verkoop_aantal"] = base_qty
        regel["eenheid_bron"] = (
            f"terugval op base '{base}' + vlag: NAV-verkoopeenheid is "
            f"mix-code '{code}' zonder eenduidige pallet-eenheid"
        )
        return (
            f"⚠ VERKOOPEENHEID CONTROLEREN (regel {regel.get('positie')}): artikel "
            f"{art} heeft mix-staffelcode '{code}' als verkoopeenheid in NAV "
            f"en geen eenduidige pallet-eenheid; teruggevallen op '{base}'."
        )

    keuze = verkoop_keuze(kaart, eenheden, base, base_qty)
    if keuze is not None:
        vcode, per = keuze
        regel["verkoop_uom_gekozen"] = vcode
        regel["verkoop_aantal"] = int(round(base_qty / per))
        regel["eenheid_bron"] = (
            f"verkoopeenheid-omrekening: {base_qty:g} {base} = "
            f"{int(round(base_qty / per))} x {vcode} ({per:g} per {vcode})"
        )
    else:
        regel["verkoop_uom_gekozen"] = base
        regel["verkoop_aantal"] = base_qty
        regel["eenheid_bron"] = (
            f"expliciete base-eenheid '{base}' x {base_qty:g} (Branch A: "
            f"nooit op NAV-default vertrouwen; geen gehele omrekening naar "
            f"een verkoopeenheid beschikbaar)"
        )
    return None
