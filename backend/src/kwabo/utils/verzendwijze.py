"""Afhaal-/ophaal-detectie → NAV-verzendwijze (Functie 5).

Sommige bestellingen worden door de klant zelf afgehaald i.p.v. verzonden
(#819: "AFHAALORDER"). Dit herkennen we deterministisch (geen LLM) uit de vrije
tekst van de order, en zetten dan de NAV Shipment Method Code op EXW (Ex Works,
af fabriek). Door Cas bevestigd: veld = Shipment Method Code, code = EXW.

Bewust conservatief (specifieke termen + word-boundaries) zodat een gewone
verzendorder nooit een valse positief oplevert; bij twijfel zet de detectie niets
en kan de reviewer handmatig EXW kiezen.
"""
from __future__ import annotations

import re
from typing import Optional

# Eén plek om de NAV-code te wijzigen mocht prod een andere code blijken te
# gebruiken (geen deploy-afhankelijke hardcode verspreid door de codebase).
AFHAAL_SHIPMENT_METHOD = "EXW"

# Afhaal-signalen (NL + DE). Word-boundaries voorkomen matches binnen andere
# woorden; de meeste termen zijn al ondubbelzinnig ("afhaalorder", "abholung").
_AFHAAL_PATTERNS = [
    r"\bafhaalorder\b",
    r"\bafhaal\w*\b",          # afhaal, afhalen, afhaling
    r"\bopgehaald\b",
    r"\bophalen\b",
    # "wij halen het zelf op" — vereist 'zelf' + een 'op'-richtingswoord, zodat
    # figuurlijk 'halen' (korting/voordeel halen) niet matcht (code review).
    r"\bhalen\b.{0,20}\bzelf\b.{0,12}\bop\b",
    r"\bzelf\b.{0,20}\bop(?:halen|gehaald)\b",
    r"\bkomen\b.{0,20}\bafhalen\b",
    # Duits
    r"\babholung\b",
    r"\babholen\b",
    r"\babzuholen\b",
    r"\bselbstabhol\w*\b",     # Selbstabholer, Selbstabholung
    r"\bwird abgeholt\b",
    r"\babgeholt\b",
    # "wir holen die Ware ab" — vereist een goederen-object tussen 'holen' en
    # 'ab', zodat 'ab Werk'/'ab Lager' (juist LEVER-incoterms) niet matcht.
    r"\bholen\b.{0,15}\b(?:ware|waren|material|paletten?|sendung|artikel|bestellung)\b.{0,10}\bab\b",
]
_AFHAAL_RE = re.compile("|".join(_AFHAAL_PATTERNS), re.IGNORECASE)


def is_afhaal(text: str | None) -> bool:
    """True als de tekst een afhaal-/ophaal-intentie bevat."""
    if not text:
        return False
    return _AFHAAL_RE.search(text) is not None


def _haystack(state: dict) -> str:
    parts = [
        state.get("email_subject") or "",
        state.get("email_body") or "",
        state.get("afleverinstructies") or "",
        state.get("opmerkingen") or "",
    ]
    for b in state.get("bijlagen") or []:
        parts.append((b or {}).get("inhoud_tekst") or "")
    return " ".join(parts)


def detect_verzendwijze(state: dict) -> Optional[str]:
    """Geef de NAV Shipment Method Code voor een afhaalorder, anders None."""
    if is_afhaal(_haystack(state)):
        return AFHAAL_SHIPMENT_METHOD
    return None
