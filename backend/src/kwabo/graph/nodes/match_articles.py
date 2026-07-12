"""Match articles: exact → exact_klantnr → kruisverwijzing → klantenkaart → history → fuzzy → manual."""
from __future__ import annotations

import asyncio
from datetime import datetime

from kwabo.utils import utcnow

from rapidfuzz import fuzz, process
from sqlmodel import Session

from kwabo.config import settings
from kwabo.db.repository import ArtikelkaartRepo, ArtikelRepo, KruisverwijzingRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderRegel, OrderState
from kwabo.integrations.navision_api import NavisionClient, get_navision_client
from kwabo.utils.eenheid_resolve import bepaal_eenheid
from kwabo.utils.logging import log


async def _artikel_bestaat(art_repo: ArtikelkaartRepo, nav: NavisionClient, nr: str) -> bool:
    """Mirror-first bestaanscheck (C2, 24-06): de gesyncde artikelkaart-mirror
    bewijst dat het artikel bestaat zónder NAV-round-trip — symmetrisch met
    stap 1. Alleen bij een mirror-miss vragen we live NAV. Vóór deze fix
    gate'den stap 2/3/4 (kruisverwijzing/klantenkaart/history) op een live
    `nav.get_item`, óók als de mirror het artikel al kende: NAV-traagheid/-storing
    of een niet-in-NAV-zichtbaar artikel zette dan een geldige klant-mapping
    stil op `manual` (gemeten op echte prod-data, order #941)."""
    if art_repo.get(nr) is not None:
        return True
    return bool(await nav.get_item(nr))


async def _match_single(
    regel: dict, klant_nr: str | None, nav: NavisionClient, s: Session
) -> OrderRegel:
    """Match één regel. `s` is de regel-eigen DB-sessie (Fase 4 C2: één
    sessie per regel i.p.v. drie — de aanroeper opent en sluit hem)."""
    result: OrderRegel = dict(regel)
    art_repo = ArtikelkaartRepo(s)

    # 1) Exact Kwabo-nummer vermeld en bestaat in Nav
    kw = regel.get("artikelnummer_kwabo")
    if kw:
        # Fase 4: mirror-first. Bij gevulde lokale artikelkaarten-mirror
        # (NAV-master-sync) bespaart dit een NAV round-trip per regel met
        # expliciet kwabo-artnr. Cache-miss (artikel niet gesynced, of mirror
        # leeg) valt door naar live NAV zodat nieuwe artikelen niet onnodig
        # de fuzzy-cascade in gaan.
        if await _artikel_bestaat(art_repo, nav, kw):
            result["artikelnummer_kwabo_matched"] = kw
            result["match_confidence"] = 1.0
            result["match_methode"] = "exact"
            return result

    # 1b) Klant-artnr dat zélf een geldig Kwabo-nummer is (Fase 2 A1).
    # De LLM zet soms het Kwabo-nummer in de klant-kolom (Witzand #718:
    # "238601" → werd fuzzy 11190 "Vloerschraper") of wisselt beide kolommen
    # om (#550/#635). Een expliciete mapping voor (klant, nummer) —
    # kruisverwijzing of klantenkaart — blijft gezaghebbend en wint van de
    # collisie-interpretatie; A1 vuurt alleen als die er niet zijn.
    # Bewust alléén de lokale mirror (geen live-NAV-fallback): elke
    # ongematchte regel zou anders een extra NAV-round-trip kosten, en een
    # nummer dat niet in de gesyncde mirror staat is vrijwel zeker geen
    # Kwabo-nummer.
    ka = regel.get("artikelnummer_klant")
    if ka:
        expliciete_mapping = klant_nr is not None and (
            KruisverwijzingRepo(s).lookup(klant_nr, ka) is not None
            or ArtikelRepo(s).mapping(klant_nr, ka) is not None
        )
        if not expliciete_mapping and art_repo.get(ka) is not None:
            result["artikelnummer_kwabo_matched"] = ka
            # Zonder klant_nr is de afwezigheid van een kruisverwijzing
            # niet verifieerbaar → onder de review-drempel (0.85) zodat de
            # reviewer de collisie-interpretatie bevestigt; na approve leert
            # _learn_from_approved de mapping anders ongezien aan (Fase 6 V3).
            result["match_confidence"] = 1.0 if klant_nr else 0.84
            result["match_methode"] = "exact_klantnr"
            return result

    if klant_nr and regel.get("artikelnummer_klant"):
        # 2) Kruisverwijzing (NAV item-reference table 5717): customer's own
        # SKU → kwabo_artikelnr. Authoritative customer-supplied mapping,
        # so it takes precedence over klantenkaart and history.
        kv_repo = KruisverwijzingRepo(s)
        kv_kwabo = kv_repo.lookup(klant_nr, regel["artikelnummer_klant"])
        if kv_kwabo and await _artikel_bestaat(art_repo, nav, kv_kwabo):
            result["artikelnummer_kwabo_matched"] = kv_kwabo
            result["match_confidence"] = 0.95
            result["match_methode"] = "kruisverwijzing"
            return result

        repo = ArtikelRepo(s)
        # 3) Klantenkaart mapping
        mapping = repo.mapping(klant_nr, regel["artikelnummer_klant"])
        if mapping and await _artikel_bestaat(art_repo, nav, mapping.kwabo_artikelnr):
            result["artikelnummer_kwabo_matched"] = mapping.kwabo_artikelnr
            result["match_confidence"] = 0.9
            result["match_methode"] = "klantenkaart"
            return result
        # 4) History
        hist = repo.best_history(klant_nr, regel["artikelnummer_klant"])
        if hist and await _artikel_bestaat(art_repo, nav, hist.kwabo_artikelnr):
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
            # Drempel 90, empirisch bepaald op de echte faalorders (Fase 2 A5,
            # scripts/analyze_fuzzy_thresholds.py, 10-06-2026): álle junk-
            # auto-fills uit prod scoorden precies 86 (WRatio's partial-ratio
            # plafond), o.a. "Stucloper grijs rol a 36m2…" → 18390 "Tork rol
            # Katrien" en "Afdekvlies 0,67x37…" → 11190 "Vloerschraper". Van
            # de 16 bekend-correcte paren koos fuzzy er 15 fout — WRatio in
            # [80,99) had op deze catalogus géén terecht-positieve waarde.
            # Onder de drempel: NIET invullen (grondwet 5) — doorvallen naar
            # manual zodat de reviewer een leeg veld ziet i.p.v. onzin.
            if best and best[1] >= 90:
                number = best[2]
                score = best[1]
                result["artikelnummer_kwabo_matched"] = number
                if score >= 99:
                    # Effectively an exact-text match on description —
                    # trust it as much as a kruisverwijzing.
                    result["match_methode"] = "description_exact"
                    result["match_confidence"] = 0.95
                else:
                    # Cap fuzzy confidence below the needs_review threshold
                    # (0.85). WRatio in [80,99) is too noisy to auto-push;
                    # the reviewer must confirm. Keeps the raw score visible
                    # via the meta provenance for debugging.
                    result["match_methode"] = "fuzzy"
                    result["match_confidence"] = min(0.84, round(score / 100.0, 2))
                return result

    # 6) Manual
    result["artikelnummer_kwabo_matched"] = None
    result["match_confidence"] = 0.0
    result["match_methode"] = "manual"
    return result


async def match_articles_node(state: OrderState) -> OrderState:
    nav = get_navision_client()
    klant_nr = (state.get("klant_match") or {}).get("navision_klantnr")
    regels_in = state.get("orderregels") or []

    # Fase 4 (B1, audit §12.D.1): regels matchen parallel met begrensde
    # concurrency. Vóór de fix waren 10 regels × 1-3 NAV-calls serieel —
    # 5-15 s pure wachttijd per order in productie. De semaphore begrenst
    # de druk op NAV én op de DB-pool (elke taak houdt 1 sessie vast).
    # Determinisme: gather bewaart argumentvolgorde; de (idx, ...)-tuples +
    # sort maken die invariant expliciet. Kanttekening: sqlmodel-sessies
    # zijn sync — elke DB-query blokkeert de event loop ~ms; geaccepteerd
    # (geen thread-executor: thread-safety-risico zonder gemeten winst).
    sem = asyncio.Semaphore(max(1, int(settings.match_concurrency)))

    async def _guarded(idx: int, regel: dict) -> tuple[int, OrderRegel, bool]:
        async with sem:
            try:
                # Fase 4 (C2): één sessie per regel (was: tot 3 per regel).
                with Session(engine) as s:
                    return idx, await _match_single(regel, klant_nr, nav, s), False
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "match_single_crash",
                    email_id=state.get("email_id"),
                    regel_idx=idx,
                    klant_art=regel.get("artikelnummer_klant"),
                    oms=(regel.get("omschrijving") or "")[:80],
                    exc_type=type(exc).__name__,
                    exc_msg=str(exc)[:300],
                )
                from kwabo.utils.alerts import alert
                alert(
                    "match_single_crash", "warning",
                    {"email_id": state.get("email_id"), "regel_idx": idx,
                     "exc": f"{type(exc).__name__}: {str(exc)[:200]}"},
                )
                fallback = dict(regel)
                fallback["artikelnummer_kwabo_matched"] = None
                fallback["match_confidence"] = 0.0
                fallback["match_methode"] = "manual"
                return idx, fallback, True

    results = await asyncio.gather(
        *(_guarded(idx, r) for idx, r in enumerate(regels_in))
    )
    results = sorted(results, key=lambda t: t[0])
    matched: list[OrderRegel] = [r for _, r, _ in results]
    crash_count = sum(1 for _, _, crashed in results if crashed)

    # If half (or more) of the lines crashed it's almost certainly a NAV
    # outage rather than per-line data quality. Add a visible warning so
    # the reviewer doesn't read "all manual" as "AI did a bad job" and
    # waste time re-running. The actual exceptions are already in
    # stappen_log via match_single_crash events.
    nav_outage_warning: str | None = None
    if regels_in and crash_count * 2 >= len(regels_in):
        nav_outage_warning = (
            f"NAV tijdelijk niet bereikbaar — {crash_count}/{len(regels_in)} "
            f"artikel-matches crashten. Re-run de pipeline of vul handmatig in."
        )

    # Resolve the NAV-facing unit of measure per line. The LLM extractor
    # guesses a UoM from the mail text (e.g. "STUK", "PAL", "ROL") but NAV
    # rejects any UoM that is not in the item's PLX_ItemUnitOfMeasure table
    # (HTTP 400 "Unit of Measure Code ... cannot be found").
    #
    # The fix for the "60 stuks -> 60 pallets" bug: do NOT blindly overwrite
    # the customer's ordered unit with the article's base unit. Validate the
    # ordered unit against the synced ArtikelEenheid (item-UOM mirror):
    #   * ordered unit is empty               -> use base (NAV default).
    #   * ordered unit == base unit           -> use base (nothing to convert).
    #   * ordered unit is a VALID item UoM    -> honour it, so "60 STUK" stays
    #     60 pieces and NAV does the pallet/price conversion itself.
    #   * ordered unit unknown OR item-UOM table not synced for this item ->
    #     fall back to base AND flag the line for review (safer than silently
    #     shipping a wrong unit; mirrors Cas' "niet de eerste beste pakken").
    # `eenheid_origineel` always preserves the raw extracted unit so
    # compute_europallet can still see e.g. "PAL". apply_mixprijzen may later
    # override via mix_uom_gekozen for mix-priced items.
    eenheid_review_idx: list[int] = []
    eenheid_warnings: list[str] = []
    with Session(engine) as s:
        art_repo = ArtikelkaartRepo(s)
        for idx, r in enumerate(matched):
            artnr = r.get("artikelnummer_kwabo_matched")
            if not artnr:
                continue
            kaart = art_repo.get(artnr)
            if not kaart or not kaart.basis_eenheid:
                continue
            base = kaart.basis_eenheid.strip()
            r.setdefault("eenheid_origineel", r.get("eenheid"))
            r["eenheid_default"] = base

            ordered = (r.get("eenheid") or "").strip()

            # Resolve the ordered unit against the item-UOM mirror. A pallet-
            # family unit ("PAL") brugt naar de artikel-eigen pallet-code
            # ("PALLET"); een echt ongeldige eenheid valt veilig terug op base
            # + review (Functie 3 — gedeelde helper, ook gebruikt door de
            # handmatige correctie in api/preview.py).
            eenheden = art_repo.list_eenheden(artnr)
            keuze = bepaal_eenheid(
                r, base, eenheden, verkoop_eenheid=kaart.verkoop_eenheid)
            r["eenheid"], eenheid_vlag = keuze.code, keuze.vlag
            # F2.3/UX: herkomst per regel — apply_mixprijzen (Branch A/mix)
            # overschrijft dit zodra hij een verdergaande keuze maakt.
            r["eenheid_bron"] = keuze.bron
            if eenheid_vlag:
                eenheid_review_idx.append(idx)
                eenheid_warnings.append(
                    f"⚠ EENHEID CONTROLEREN (regel {idx + 1}): klant bestelde "
                    f"'{ordered}' maar dit is geen geldige eenheid voor artikel "
                    f"{artnr} (gebruikt nu standaard '{base}')."
                )

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
                for m in ("exact", "exact_klantnr", "kruisverwijzing", "klantenkaart", "history", "fuzzy", "manual")
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
        # Clear the upstream raw-extract review flag when we've successfully
        # matched. The extract node flags missing `artikelnummer_kwabo` so
        # the LLM-extracted field is reviewable, but once match_articles has
        # resolved a confident `_matched`, the raw field is irrelevant for
        # the push and the warning is noise. The fuzzy path almost always
        # leaves `artikelnummer_kwabo` empty (NAV-nr comes from description
        # match, not from the email body) — without this cleanup the
        # reviewer sees a stuck warning even on perfect matches.
        if r.get("artikelnummer_kwabo_matched") and confidence >= 0.85:
            raw_meta = rm.get("artikelnummer_kwabo")
            if isinstance(raw_meta, dict):
                raw_meta["needs_review"] = False
                raw_meta["source_detail"] = (
                    f"{raw_meta.get('source_detail') or ''} | cleared by match"
                ).strip(" |")
            stale = f"orderregels[{i}].artikelnummer_kwabo"
            needs_paths = [p for p in needs_paths if p != stale]
        regels_meta[i] = rm
        if rm["artikelnummer_kwabo_matched"]["needs_review"]:
            path = f"orderregels[{i}].artikelnummer_kwabo_matched"
            if path not in needs_paths:
                needs_paths.append(path)
    meta["orderregels"] = regels_meta

    # Flag lines whose ordered unit could not be validated against the
    # item-UOM mirror (see the eenheid-resolution block above).
    for idx in eenheid_review_idx:
        path = f"orderregels[{idx}].eenheid"
        if path not in needs_paths:
            needs_paths.append(path)

    validatie_warnings = list(state.get("validatie_warnings") or [])
    if nav_outage_warning:
        validatie_warnings.append(nav_outage_warning)
    validatie_warnings.extend(eenheid_warnings)

    return {
        **state,
        "orderregels": matched,
        "alle_artikelen_gematcht": alle_gematcht,
        "stappen_log": steps,
        "_meta": meta,
        "needs_review_fields": needs_paths,
        "needs_review_count": len(needs_paths),
        "validatie_warnings": validatie_warnings,
    }
