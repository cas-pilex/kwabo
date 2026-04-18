"""Normalisatie van hoeveelheid-eenheden naar Navision-codes (PDF §9)."""
from __future__ import annotations

EENHEID_MAPPING = {
    "rol": "ROL", "rolle": "ROL", "roll": "ROL", "rll": "ROL", "rollen": "ROL",
    "stuk": "STUK", "stk": "STUK", "stuks": "STUK", "st": "STUK",
    "stück": "STUK", "stueck": "STUK", "pcs": "STUK", "pc": "STUK", "ea": "STUK",
    "pal": "PAL", "pallet": "PAL", "pallets": "PAL",
    "m2": "M2", "m²": "M2", "qm": "M2",
    "m1": "M1", "m": "M1", "meter": "M1", "lfm": "M1",
    "bos": "BOS",
    "doos": "DOOS", "box": "DOOS",
    "he": "STUK",
    "kg": "KG",
    "ltr": "LTR", "liter": "LTR", "l": "LTR",
}


def normalize_eenheid(raw: str | None) -> str:
    if not raw:
        return "STUK"
    return EENHEID_MAPPING.get(raw.strip().lower(), raw.strip().upper())
