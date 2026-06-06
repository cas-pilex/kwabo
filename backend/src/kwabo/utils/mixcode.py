"""Mix unit-of-measure code parsing.

Pure helpers (no I/O) for the NAV mix-price staffel codes Kwabo uses on
mixprijzen customers. Format: ``M{total_pallets_in_mix}PAL{rolls_per_pallet}``
— e.g. ``M1PAL30``, ``M7PAL30``, ``M10PAL30``, ``M33PAL35``, ``M33PAL60``.

- The ``M``-number is the staffel threshold: the TOTAL number of pallets across
  all mix lines in the order. Per article you pick the highest tier whose
  threshold is <= the order's total pallets.
- The ``PALxx`` suffix is the rolls-per-pallet, which is article-specific and
  tier-independent (article 23545 -> PAL35, 23546 -> PAL60).

This is the authoritative mix-detection for the sales-price path; it replaces
the old, unusable ``\\bMIX\\b|MENG`` heuristic for recognising mix codes.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

# Format: M{total_pallets}PAL{rolls_per_pallet}, e.g. M1PAL30, M33PAL35.
_MIX_CODE_RE = re.compile(r"^M(\d+)PAL(\d+)$", re.IGNORECASE)


class MixCode(NamedTuple):
    code: str  # canonical upper-case, e.g. "M33PAL35"
    m_threshold: int  # total-pallets staffel tier (33)
    # PAL suffix (35). NOTE: this is a human-typed *label* and is NOT a reliable
    # source of truth — live NAV has typos (item 15450: M5PAL528 / M10PAL1028
    # whose real Qty_per_Unit_of_Measure is 1728). For pallet math always use
    # ArtikelEenheid.qty_per_base; treat this suffix as cosmetic (badges only).
    rolls_per_pallet: int


def parse_mix_code(code: Optional[str]) -> Optional[MixCode]:
    """Parse a mix code, or return None if it is not a valid M-format code.

    Empty/None, plain unit codes (``PALLET``, ``PALLET22``, ``STUK``), and the
    literal word ``MIX`` all return None.
    """
    if not code:
        return None
    m = _MIX_CODE_RE.match(code.strip())
    if not m:
        return None
    return MixCode(code.strip().upper(), int(m.group(1)), int(m.group(2)))


def is_mix_code(code: Optional[str]) -> bool:
    """True iff ``code`` is a valid M-format mix unit code."""
    return parse_mix_code(code) is not None
