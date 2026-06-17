"""Validate prices: compare with prijsafspraken; >5% = warning."""
from __future__ import annotations

from datetime import datetime

from kwabo.utils import utcnow

from sqlmodel import Session

from kwabo.db.repository import ArtikelRepo, KruisverwijzingRepo, PrijsRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState


def artikel_prijs_signaal(regel, klant, prijs_repo, kv_repo, art_repo):
    """Functie 6 (data-gated) — verdacht artikel op basis van de prijslijst.

    Een gematcht artikel zonder actieve prijs voor de klant is verdacht als een
    alternatief (kruisverwijzing/klantenkaart/history) voor diezelfde klant-SKU
    WÉL een actieve prijs heeft. Geeft dan ``{"kwabo", "bron"}`` terug (om te
    VLAGGEN + tonen — nooit auto-switchen, nooit zelf prijzen). Geen geprijsd
    alternatief (bv. lege prijsafspraken-tabel) → ``None`` (geen ruis).
    """
    matched = regel.get("artikelnummer_kwabo_matched")
    if not matched:
        return None
    hoev = float(regel.get("hoeveelheid") or 0)
    if prijs_repo.best_match(klant, matched, hoev):
        return None  # matched heeft zelf een prijs → niets aan de hand
    sku = regel.get("artikelnummer_klant")
    if not sku:
        return None
    kandidaten: list[tuple[str, str]] = []
    kv = kv_repo.lookup(klant, sku)
    if kv:
        kandidaten.append((kv, "kruisverwijzing"))
    m = art_repo.mapping(klant, sku)
    if m and m.kwabo_artikelnr:
        kandidaten.append((m.kwabo_artikelnr, "klantenkaart"))
    h = art_repo.best_history(klant, sku)
    if h and h.kwabo_artikelnr:
        kandidaten.append((h.kwabo_artikelnr, "history"))
    seen: set[str] = set()
    for kwabo, bron in kandidaten:
        if kwabo == matched or kwabo in seen:
            continue
        seen.add(kwabo)
        if prijs_repo.best_match(klant, kwabo, hoev):
            return {"kwabo": kwabo, "bron": bron}
    return None


async def validate_prices_node(state: OrderState) -> OrderState:
    warnings = list(state.get("validatie_warnings") or [])
    klant = (state.get("klant_match") or {}).get("navision_klantnr")
    regels_out = []

    # Fase 4 (audit §12.D.3): één sessie voor de hele node. De prijscheck-loop
    # én de provenance-loop verderop delen deze sessie; voorheen opende de
    # provenance-loop een tweede Session(engine) — een onnodige extra
    # connectie-checkout per pipeline-run.
    with Session(engine) as s:
        repo = PrijsRepo(s)
        kv_repo = KruisverwijzingRepo(s)
        art_repo = ArtikelRepo(s)
        for r in state.get("orderregels") or []:
            r = dict(r)
            kw = r.get("artikelnummer_kwabo_matched")
            prijs = r.get("prijs_per_eenheid")

            # Functie 6 (data-gated): vlag een gematcht artikel zonder prijs voor
            # de klant als een alternatief WÉL een prijs heeft. Onafhankelijk van
            # of de mail een prijs gaf (#816: klant gaf 23853 zónder prijs).
            if kw and klant:
                alt = artikel_prijs_signaal(r, klant, repo, kv_repo, art_repo)
                if alt:
                    r["artikel_prijs_alternatief"] = alt
                    warnings.append(
                        f"ARTIKEL ONZEKER regel {r.get('positie')}: {kw} heeft geen "
                        f"prijsafspraak voor deze klant; {alt['kwabo']} "
                        f"(via {alt['bron']}) heeft die wél — controleer het artikel."
                    )

            if not kw or prijs is None or not klant:
                r["prijs_validated"] = None
                regels_out.append(r)
                continue

            hoev = float(r.get("hoeveelheid") or 0)
            pa = repo.best_match(klant, kw, hoev)
            if not pa:
                # Customer sent a price but we have no contract row to check
                # it against. Informational only — NAV will accept the price
                # and the reviewer can still see the warning.
                r["prijs_validated"] = None
                # De tool stuurt nooit een prijs naar NAV — NAV berekent die
                # zelf. De mailprijs dient alleen ter controle (Functie 6 DEEL B:
                # tekst gecorrigeerd; gedrag ongewijzigd).
                warnings.append(
                    f"Geen prijsafspraak in DB voor regel {r.get('positie')} ({kw}) — "
                    f"NAV berekent de prijs zelf; de mailprijs (€{prijs}) dient "
                    f"alleen ter controle."
                )
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

        # Provenance per regel (prijs_per_eenheid) — zelfde sessie/repo als de
        # prijscheck-loop hierboven (zie Fase-4-comment bij het with-blok).
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
            kw = r.get("artikelnummer_kwabo_matched")

            # When the mail has no price for this line, decide whether the
            # reviewer NEEDS to fill it in:
            #   - if a prijsafspraak exists for klant+artikel → the customer
            #     has negotiated terms; we won't auto-push without an
            #     explicit number. needs_review=True.
            #   - if no prijsafspraak → NAV will fill the standard unit_price
            #     from the item catalog. That's the legitimate fallback for
            #     non-mix B2B orders. needs_review=False, but we flag the
            #     source so the dashboard can show "NAV-default".
            review_for_missing = False
            source_detail_override = existing.get("source_detail")
            if prijs is None and kw:
                has_afspraak = bool(
                    klant and repo.best_match(klant, kw, float(r.get("hoeveelheid") or 0))
                )
                if has_afspraak:
                    review_for_missing = True
                else:
                    source_detail_override = (
                        existing.get("source_detail")
                        or "NAV-standaard (geen prijsafspraak)"
                    )

            existing_source = existing.get("source")
            if prijs is None and not review_for_missing:
                # NAV-default kicks in. Override any "missing" that extract
                # left so the dashboard shows the right provenance.
                source = "nav_default"
            elif existing_source:
                source = existing_source
            else:
                source = "pdf" if prijs is not None else "missing"
            rm["prijs_per_eenheid"] = {
                "value": prijs,
                "source": source,
                "source_detail": source_detail_override,
                "confidence": float(existing.get("confidence") or (0.9 if prijs is not None else 0)),
                # needs_review fires only for actual mismatches OR when the
                # customer has a contract price the LLM couldn't extract.
                # Missing-price-without-contract is no longer noise.
                "needs_review": validated is False or review_for_missing,
                "validated": validated,
            }
            # Functie 6: een prijs-verdacht artikel zet de artikel-match terug in
            # review (zonder de match-waarde/-bron te overschrijven) zodat de
            # reviewer het alternatief kan kiezen via de bestaande artikelflow.
            alt = r.get("artikel_prijs_alternatief")
            if alt:
                amm = rm.get("artikelnummer_kwabo_matched")
                if isinstance(amm, dict):
                    amm["needs_review"] = True
                    amm["source_detail"] = (
                        f"{amm.get('source_detail') or ''} | geen prijsafspraak; "
                        f"alternatief {alt['kwabo']} ({alt['bron']}) heeft wél prijs"
                    ).strip(" |")
                else:
                    rm["artikelnummer_kwabo_matched"] = {
                        "value": kw, "source": "price_signal",
                        "source_detail": (f"geen prijsafspraak; alternatief "
                                          f"{alt['kwabo']} ({alt['bron']}) heeft wél prijs"),
                        "confidence": 0.0, "needs_review": True,
                    }
                amm_path = f"orderregels[{i}].artikelnummer_kwabo_matched"
                if amm_path not in needs_paths:
                    needs_paths.append(amm_path)

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
