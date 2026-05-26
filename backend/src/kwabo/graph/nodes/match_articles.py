"""Match articles: exact → kruisverwijzing → klantenkaart → history → fuzzy → manual."""
from __future__ import annotations

from datetime import datetime

from kwabo.utils import utcnow

from rapidfuzz import fuzz, process
from sqlmodel import Session

from kwabo.db.repository import ArtikelkaartRepo, ArtikelRepo, KruisverwijzingRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderRegel, OrderState
from kwabo.integrations.navision_api import NavisionClient, get_navision_client
from kwabo.utils.logging import log


async def _match_single(regel: dict, klant_nr: str | None, nav: NavisionClient) -> OrderRegel:
    result: OrderRegel = dict(regel)

    # 1) Exact Kwabo-nummer vermeld en bestaat in Nav
    kw = regel.get("artikelnummer_kwabo")
    if kw:
        item = await nav.get_item(kw)
        if item:
            result["artikelnummer_kwabo_matched"] = kw
            result["match_confidence"] = 1.0
            result["match_methode"] = "exact"
            return result

    if klant_nr and regel.get("artikelnummer_klant"):
        with Session(engine) as s:
            # 2) Kruisverwijzing (NAV item-reference table 5717): customer's own
            # SKU → kwabo_artikelnr. Authoritative customer-supplied mapping,
            # so it takes precedence over klantenkaart and history.
            kv_repo = KruisverwijzingRepo(s)
            kv_kwabo = kv_repo.lookup(klant_nr, regel["artikelnummer_klant"])
            if kv_kwabo and await nav.get_item(kv_kwabo):
                result["artikelnummer_kwabo_matched"] = kv_kwabo
                result["match_confidence"] = 0.95
                result["match_methode"] = "kruisverwijzing"
                return result

            repo = ArtikelRepo(s)
            # 3) Klantenkaart mapping
            mapping = repo.mapping(klant_nr, regel["artikelnummer_klant"])
            if mapping and await nav.get_item(mapping.kwabo_artikelnr):
                result["artikelnummer_kwabo_matched"] = mapping.kwabo_artikelnr
                result["match_confidence"] = 0.9
                result["match_methode"] = "klantenkaart"
                return result
            # 4) History
            hist = repo.best_history(klant_nr, regel["artikelnummer_klant"])
            if hist and await nav.get_item(hist.kwabo_artikelnr):
                result["artikelnummer_kwabo_matched"] = hist.kwabo_artikelnr
                result["match_confidence"] = 0.95
                result["match_methode"] = "history"
                return result

    # 5) Fuzzy op omschrijving tegen Nav item search
    oms = regel.get("omschrijving") or ""
    if oms:
        candidates = await nav.search_items(beschrijving=oms[:40])
        if not candidates:
            candidates = await nav.search_items()
        if candidates:
            names = {c["number"]: c.get("displayName", "") for c in candidates}
            best = process.extractOne(oms, names, scorer=fuzz.WRatio)
            if best and best[1] >= 70:
                number = best[2]
                result["artikelnummer_kwabo_matched"] = number
                result["match_confidence"] = round(best[1] / 100.0, 2)
                result["match_methode"] = "fuzzy"
                return result

    # 6) Manual
    result["artikelnummer_kwabo_matched"] = None
    result["match_confidence"] = 0.0
    result["match_methode"] = "manual"
    return result


async def match_articles_node(state: OrderState) -> OrderState:
    nav = get_navision_client()
    klant_nr = (state.get("klant_match") or {}).get("navision_klantnr")

    matched: list[OrderRegel] = []
    for idx, r in enumerate(state.get("orderregels") or []):
        try:
            matched.append(await _match_single(r, klant_nr, nav))
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "match_single_crash",
                email_id=state.get("email_id"),
                regel_idx=idx,
                klant_art=r.get("artikelnummer_klant"),
                oms=(r.get("omschrijving") or "")[:80],
                exc_type=type(exc).__name__,
                exc_msg=str(exc)[:300],
            )
            fallback = dict(r)
            fallback["artikelnummer_kwabo_matched"] = None
            fallback["match_confidence"] = 0.0
            fallback["match_methode"] = "manual"
            matched.append(fallback)

    # Enrich each matched line with the item's NAV base-UoM from the synced
    # artikelkaarten mirror. The LLM extractor guesses a UoM from the mail
    # text (often "STUK", "M1", "PC" etc.) but NAV rejects any UoM that is
    # not in the item's PLX_ItemUnitOfMeasure table (HTTP 400 "Unit of
    # Measure Code ... cannot be found in the related table").
    #
    # The base_eenheid synced from PLX_Item.Base_Unit_of_Measure is the one
    # UoM that is ALWAYS valid for an item (NAV requires it). Until we also
    # mirror PLX_ItemUnitOfMeasure and can validate alternative UoMs, the
    # safe contract is: overwrite the line's eenheid with the base. This
    # makes _line_uom_to_emit a no-op (eenheid == eenheid_default) so NAV
    # falls through to the item default during line POST. apply_mixprijzen
    # can still override later via mix_uom_gekozen for mix-priced items —
    # that path knows which UoM is valid for the mix discount.
    with Session(engine) as s:
        art_repo = ArtikelkaartRepo(s)
        for r in matched:
            artnr = r.get("artikelnummer_kwabo_matched")
            if not artnr:
                continue
            kaart = art_repo.get(artnr)
            if not kaart or not kaart.basis_eenheid:
                continue
            # Preserve the LLM-extracted unit so downstream europallet
            # detection can still see e.g. "PAL" even though we overwrite
            # the NAV-facing `eenheid` with basis. Without this, "66 PAL"
            # from a Duitse Auftrag becomes "STUK" before compute_europallet
            # gets a look — and no europallet line is generated.
            r.setdefault("eenheid_origineel", r.get("eenheid"))
            r["eenheid_default"] = kaart.basis_eenheid
            r["eenheid"] = kaart.basis_eenheid

    alle_gematcht = bool(matched) and all(r.get("artikelnummer_kwabo_matched") for r in matched)
    log.info(
        "match_articles", email_id=state.get("email_id"),
        matched=sum(1 for r in matched if r.get("artikelnummer_kwabo_matched")),
        total=len(matched),
    )

    stap = {
        "stap": "match_articles",
        "timestamp": utcnow().isoformat(),
        "beslissing": f"{sum(1 for r in matched if r.get('artikelnummer_kwabo_matched'))}/{len(matched)} regels gematcht",
        "details": {
            "per_methode": {
                m: sum(1 for r in matched if r.get("match_methode") == m)
                for m in ("exact", "kruisverwijzing", "klantenkaart", "history", "fuzzy", "manual")
            }
        },
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    # Provenance per regel (artikelnummer_kwabo_matched)
    meta = dict(state.get("_meta") or {})
    regels_meta = list(meta.get("orderregels") or [])
    while len(regels_meta) < len(matched):
        regels_meta.append({})
    needs_paths = list(state.get("needs_review_fields") or [])
    for i, r in enumerate(matched):
        rm = regels_meta[i] if isinstance(regels_meta[i], dict) else {}
        methode = r.get("match_methode")
        confidence = float(r.get("match_confidence") or 0)
        rm["artikelnummer_kwabo_matched"] = {
            "value": r.get("artikelnummer_kwabo_matched"),
            "source": methode if methode else "missing",
            "source_detail": f"match-methode={methode}",
            "confidence": confidence,
            # Confidence is the source of truth. A fuzzy match scoring ≥0.85
            # is "trusted enough" — reviewer doesn't get spammed with
            # warnings on every order. Manual (=no candidate found) still
            # triggers review because confidence is 0.0 in that path.
            "needs_review": (
                not r.get("artikelnummer_kwabo_matched")
                or confidence < 0.85
            ),
        }
        regels_meta[i] = rm
        if rm["artikelnummer_kwabo_matched"]["needs_review"]:
            path = f"orderregels[{i}].artikelnummer_kwabo_matched"
            if path not in needs_paths:
                needs_paths.append(path)
    meta["orderregels"] = regels_meta

    return {
        **state,
        "orderregels": matched,
        "alle_artikelen_gematcht": alle_gematcht,
        "stappen_log": steps,
        "_meta": meta,
        "needs_review_fields": needs_paths,
        "needs_review_count": len(needs_paths),
    }
