"""Pure pallet/europallet computation (T8).

Self-learning europallet logic. Given an order's regels, decide whether an
extra "europallet" line (artikelnr 19820) should be added and if so, with
what quantity.

Two layers of knowledge:

1. ``ArtikelPalletKennis`` (table ``artikel_pallet_kennis``) — the learned
   ground truth per (artikelnr, eenheid). When present we use
   ``pallet_required`` + ``per_pallet`` directly.
2. Heuristic fallback when no kennis exists — if eenheid is DOOS or PAL and
   hoeveelheid >= 5, assume one pallet per 24 units. Anything else is
   ignored (no contribution).

The output is a *separate* state slot: callers (the operations composer in
T4) read ``state["europallet_regel"]`` and decide where/how to attach it
to the NAV payload. We deliberately do NOT mutate ``state["orderregels"]``
here — keeping this pure and easy to reason about.
"""
from __future__ import annotations

from math import ceil
from typing import Optional


PALLET_ARTIKELNR = "19820"
PALLET_OMSCHRIJVING = "Europallet"
HEURISTIC_PER_PALLET = 24.0
HEURISTIC_MIN_QTY = 5.0
# DOOS is unit-of-secondary-packing; PAL is the pallet itself. Treat them
# differently: "5 DOOS" probably needs a pallet (heuristic-per-pallet=24),
# but "1 PAL" is already a pallet — one regel = one europallet, no qty
# threshold. Keeps Duitse orders ("66 Paletten") from being silently
# ignored just because the heuristic was built around DOOS.
HEURISTIC_EENHEDEN = ("DOOS",)
PALLET_EENHEDEN = ("PAL",)
PALLET_MIN_QTY = 1.0
PALLET_THRESHOLD = 0.5
DEFAULT_CONFIDENCE = 0.7


def compute_europallet(state: dict, *, repo) -> Optional[dict]:
    """Compute the europallet (artikelnr 19820) regel based on the order's lines.

    Returns a regel-dict ready to insert into ``state["orderregels"]``, OR
    ``None`` if no europallet is needed.

    Rules:
      - For each regel with a matched ``kwabo_artikelnr``, check
        ``PalletKennisRepo.lookup(artikelnr, eenheid)``.
      - If known: when ``pallet_required`` and ``per_pallet > 0``, add
        ``hoeveelheid / per_pallet`` to ``total_pallets``.
      - If unknown: fall back to heuristic — if ``eenheid in {"DOOS", "PAL"}``
        and ``hoeveelheid >= 5``, ``total_pallets += hoeveelheid / 24``.
      - If ``total_pallets < 0.5`` -> return ``None``.
      - Otherwise return a regel-dict with ``artikelnummer_kwabo="19820"``,
        ``hoeveelheid=ceil(total_pallets)``, ``eenheid="STUK"``.
    """
    regels = state.get("orderregels") or []
    total = 0.0

    for regel in regels:
        kwabo_nr = regel.get("artikelnummer_kwabo_matched")
        if not kwabo_nr or kwabo_nr == PALLET_ARTIKELNR:
            # Skip unmatched regels and the europallet line itself — never
            # double-count if the input already carries one.
            continue

        # match_articles overwrites `eenheid` with the item's NAV base UoM
        # (so the PATCH doesn't 400 on an unknown UoM). For pallet detection
        # we want the ORIGINALLY extracted unit (where PAL/PALETTE shows up),
        # falling back to the overwritten one for older state.
        eenheid = (
            regel.get("eenheid_origineel") or regel.get("eenheid") or ""
        ).upper()
        try:
            qty = float(regel.get("hoeveelheid") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue

        kennis = repo.lookup(kwabo_nr, eenheid)
        if kennis is not None:
            if kennis.pallet_required and kennis.per_pallet:
                total += qty / max(kennis.per_pallet, 1)
        else:
            if eenheid in PALLET_EENHEDEN and qty >= PALLET_MIN_QTY:
                # Each PAL unit IS a pallet — count 1:1, no division.
                total += qty
            elif eenheid in HEURISTIC_EENHEDEN and qty >= HEURISTIC_MIN_QTY:
                total += qty / HEURISTIC_PER_PALLET

    if total < PALLET_THRESHOLD:
        return None

    return {
        "positie": _next_positie(regels),
        "artikelnummer_kwabo": PALLET_ARTIKELNR,
        "artikelnummer_kwabo_matched": PALLET_ARTIKELNR,
        "omschrijving": PALLET_OMSCHRIJVING,
        "hoeveelheid": int(ceil(total)),
        "eenheid": "STUK",
        "match_methode": "europallet_compute",
        "confidence": DEFAULT_CONFIDENCE,
    }


def _next_positie(regels: list) -> int:
    if not regels:
        return 1
    return max((r.get("positie") or 0) for r in regels) + 1
