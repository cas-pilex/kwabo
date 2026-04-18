"""Validate prices: compare with prijsafspraken; >5% = warning."""
from __future__ import annotations

from datetime import datetime

from kwabo.utils import utcnow

from sqlmodel import Session

from kwabo.db.repository import PrijsRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState


async def validate_prices_node(state: OrderState) -> OrderState:
    warnings = list(state.get("validatie_warnings") or [])
    klant = (state.get("klant_match") or {}).get("navision_klantnr")
    regels_out = []

    with Session(engine) as s:
        repo = PrijsRepo(s)
        for r in state.get("orderregels") or []:
            r = dict(r)
            kw = r.get("artikelnummer_kwabo_matched")
            prijs = r.get("prijs_per_eenheid")
            if not kw or prijs is None or not klant:
                r["prijs_validated"] = None
                regels_out.append(r)
                continue

            hoev = float(r.get("hoeveelheid") or 0)
            pa = repo.best_match(klant, kw, hoev)
            if not pa:
                r["prijs_validated"] = None
                warnings.append(f"GEEN PRIJSAFSPRAAK voor regel {r.get('positie')} ({kw})")
                regels_out.append(r)
                continue

            verwacht = pa.prijs * (1 - (pa.korting_pct or 0) / 100)
            prijs_type = pa.type or "standaard"
            if verwacht <= 0:
                r["prijs_validated"] = None
                regels_out.append(r)
                continue
            afwijking = abs(prijs - verwacht) / verwacht * 100
            if afwijking > 5:
                r["prijs_validated"] = False
                r["prijs_afwijking"] = f"{afwijking:.1f}% afwijking ({prijs_type}-prijs)"
                warnings.append(
                    f"PRIJS AFWIJKING regel {r.get('positie')}: klant €{prijs:.2f} vs {prijs_type}-afspraak €{verwacht:.2f} ({afwijking:.1f}%)"
                )
            else:
                r["prijs_validated"] = True
            regels_out.append(r)

    # G5: Sanity checks on hoeveelheid/eenheid
    SANITY_RULES = [
        (lambda h, e: h <= 0, "Hoeveelheid is 0 of negatief"),
        (lambda h, e: e == "PAL" and h > 100, f"Meer dan 100 pallets besteld — klopt dit?"),
        (lambda h, e: e == "STUK" and h > 50000, f"Meer dan 50.000 stuks — klopt dit?"),
        (lambda h, e: e == "ROL" and h > 5000, f"Meer dan 5.000 rollen — klopt dit?"),
        (lambda h, e: not e or e in ("ONBEKEND", ""), "Onbekende eenheid"),
    ]
    for r in regels_out:
        h = float(r.get("hoeveelheid") or 0)
        e = r.get("eenheid") or ""
        for check, msg in SANITY_RULES:
            try:
                if check(h, e):
                    warnings.append(f"SANITY regel {r.get('positie')}: {msg} (hoev={h} eenh={e})")
            except Exception:  # noqa: BLE001
                pass

    stap = {
        "stap": "validate_prices",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"{sum(1 for r in regels_out if r.get('prijs_validated') is True)}/{len(regels_out)} prijzen ok",
        "details": {"warnings_new": [w for w in warnings if w not in (state.get("validatie_warnings") or [])]},
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    # Provenance per regel (prijs_per_eenheid)
    meta = dict(state.get("_meta") or {})
    regels_meta = list(meta.get("orderregels") or [])
    while len(regels_meta) < len(regels_out):
        regels_meta.append({})
    needs_paths = list(state.get("needs_review_fields") or [])
    for i, r in enumerate(regels_out):
        rm = regels_meta[i] if isinstance(regels_meta[i], dict) else {}
        existing = rm.get("prijs_per_eenheid") or {}
        prijs = r.get("prijs_per_eenheid")
        validated = r.get("prijs_validated")
        # Prefer the source that was set by extract; only set "missing" if no value at all
        source = existing.get("source") or ("pdf" if prijs is not None else "missing")
        rm["prijs_per_eenheid"] = {
            "value": prijs,
            "source": source,
            "source_detail": existing.get("source_detail"),
            "confidence": float(existing.get("confidence") or (0.9 if prijs is not None else 0)),
            "needs_review": validated is False,  # mismatch with afspraak ⇒ explicit review
            "validated": validated,
        }
        regels_meta[i] = rm
        if rm["prijs_per_eenheid"]["needs_review"]:
            path = f"orderregels[{i}].prijs_per_eenheid"
            if path not in needs_paths:
                needs_paths.append(path)
    meta["orderregels"] = regels_meta

    return {
        **state,
        "orderregels": regels_out,
        "alle_prijzen_valide": all(
            r.get("prijs_validated") in (True, None) for r in regels_out
        ),
        "validatie_warnings": warnings,
        "stappen_log": steps,
        "_meta": meta,
        "needs_review_fields": needs_paths,
        "needs_review_count": len(needs_paths),
    }
