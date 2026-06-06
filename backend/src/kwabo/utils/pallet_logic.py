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


# Kept as module-level constants for backwards-compat with tests and
# callers that import the symbol. Production read-path goes through
# settings.europallet_artikelnr so it can be overridden per-env without
# a code deploy. Tests still import PALLET_ARTIKELNR directly — that's
# fine, they exercise the pure logic.
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


def _pallet_base_units(eenheden: list) -> Optional[float]:
    """Base units that fit on one physical pallet for this article, read from
    the synced item-UOM rows (ArtikelEenheid). Returns ``None`` when it can't
    be determined unambiguously — prefer a plain ``PAL`` row, else a single
    PAL-prefixed row; multiple variants (PAL30/PAL35) are ambiguous so we
    don't guess and let the caller fall back to the heuristic."""
    pals = [
        e for e in eenheden
        if (e.eenheid_code or "").strip().upper().startswith("PAL")
        and (e.qty_per_base or 0) > 0
    ]
    if not pals:
        return None
    exact = [e for e in pals if (e.eenheid_code or "").strip().upper() == "PAL"]
    if exact:
        return float(exact[0].qty_per_base)
    if len(pals) == 1:
        return float(pals[0].qty_per_base)
    return None


def _qty_per_base(eenheden: list, code: str) -> float:
    """Base units contained in one of the ORDERED unit. Defaults to 1.0 when
    the unit isn't in the table (i.e. it's the base unit itself)."""
    cu = (code or "").strip().upper()
    for e in eenheden:
        if (e.eenheid_code or "").strip().upper() == cu and (e.qty_per_base or 0) > 0:
            return float(e.qty_per_base)
    return 1.0


def compute_europallet(state: dict, *, repo, uom_repo=None) -> Optional[dict]:
    """Compute the europallet (artikelnr 19820) regel based on the order's lines.

    Returns a regel-dict ready to insert into ``state["orderregels"]``, OR
    ``None`` if no europallet is needed.

    Per line (skipping unmatched lines and the europallet line itself), the
    pallet contribution is decided in priority order:

      1. Learned ``ArtikelPalletKennis`` (repo.lookup) wins — when
         ``pallet_required`` and ``per_pallet > 0``, add ``qty / per_pallet``.
      2. Else, if ``uom_repo`` is supplied and the article has unambiguous
         item-UOM data: convert via the article's units-per-pallet. A line
         ordered in a PAL-unit counts 1:1; a line in stuks/rol/etc. counts
         ``(qty * base_per_orderedunit) / base_per_pallet`` — this is Cas'
         "60 stuks, 60 per pallet -> 1 pallet". stuks/rol therefore do NOT
         map 1:1; small quantities consolidate onto a pallet.
      3. Else legacy heuristic: PAL counts 1:1, DOOS ~1 pallet per 24 units,
         everything else contributes nothing.

    ``total < 0.5`` -> ``None``; otherwise a regel with
    ``hoeveelheid=ceil(total)``, ``eenheid="STUK"``.
    """
    regels = state.get("orderregels") or []
    total = 0.0

    for regel in regels:
        kwabo_nr = regel.get("artikelnummer_kwabo_matched")
        if not kwabo_nr or kwabo_nr == PALLET_ARTIKELNR:
            # Skip unmatched regels and the europallet line itself — never
            # double-count if the input already carries one.
            continue

        # A mix line was resolved to a whole number of pallets by
        # apply_mixprijzen (mix_aantal, in the M{n}PAL{r} unit). Count those
        # pallets directly — the line's raw rolls/stuks no longer apply.
        mix_aantal = regel.get("mix_aantal")
        if regel.get("mix_uom_gekozen") and mix_aantal:
            try:
                total += float(mix_aantal)
            except (TypeError, ValueError):
                pass
            continue

        # match_articles preserves the customer's ORIGINALLY ordered unit in
        # `eenheid_origineel` (where PAL/STUK/ROL shows up), falling back to
        # the NAV-facing `eenheid` for older state.
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
            continue

        # A PAL-unit line is already expressed in pallets — count 1:1.
        if (eenheid in PALLET_EENHEDEN or eenheid.startswith("PAL")) and qty >= PALLET_MIN_QTY:
            total += qty
            continue

        eenheden = uom_repo.list_eenheden(kwabo_nr) if uom_repo is not None else []
        pal_base = _pallet_base_units(eenheden)
        if pal_base:
            # Convert the ordered unit to base units, then to pallets.
            per_unit_base = _qty_per_base(eenheden, eenheid)
            total += (qty * per_unit_base) / pal_base
        elif eenheid in HEURISTIC_EENHEDEN and qty >= HEURISTIC_MIN_QTY:
            total += qty / HEURISTIC_PER_PALLET

    if total < PALLET_THRESHOLD:
        return None

    # Read the article-number from settings so it can be rotated per-env
    # without a code change. Tests import PALLET_ARTIKELNR module-level
    # and get the default; production reads settings.europallet_artikelnr.
    try:
        from kwabo.config import settings
        configured_nr = settings.europallet_artikelnr or PALLET_ARTIKELNR
    except Exception:  # noqa: BLE001
        configured_nr = PALLET_ARTIKELNR

    return {
        "positie": _next_positie(regels),
        "artikelnummer_kwabo": configured_nr,
        "artikelnummer_kwabo_matched": configured_nr,
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
