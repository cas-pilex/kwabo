"""Match customer node: email → DB → NAV-email → naam-extract → NAV-domein → None."""
from __future__ import annotations

import re
from datetime import datetime

from kwabo.utils import utcnow

from rapidfuzz import fuzz, process
from sqlmodel import Session

from kwabo.db.repository import KlantRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState
from kwabo.integrations.forwarded_parser import detect_forward
from kwabo.integrations.navision_api import NavisionClient, get_navision_client
# Reuse the proven location-signal helpers from select_ship_to (the order's
# delivery address can name a vestiging in subject/body/PDF/afleveradres).
from kwabo.graph.nodes.select_ship_to import (
    _normalize_postcode,
    _order_signal_text,
    _word_in,
)
from kwabo.utils.logging import log

EMAIL_RE = re.compile(r"[\w\.\-\+]+@[\w\.\-]+")

# --- K3/K4 (Fase 2): klant-naam-fallback -----------------------------------
# Rechtsvorm-suffixen vervuilen de fuzzy-score ("B.V." matcht elke B.V.).
RECHTSVORM_RE = re.compile(
    r"\b(b\.?v\.?|n\.?v\.?|v\.?o\.?f\.?|gmbh|& ?co\.? ?kg|bv|nv)\b\.?",
    re.IGNORECASE,
)
# Pure doorstuur-portalen: het afzenderdomein noemt NOOIT de klant, dus de
# domein-substring-stap is daar actief schadelijk (K4).
PORTAL_DOMAINS = {"zevij-necomij.com", "orders.nl"}
# Drempels, empirisch bepaald op alle 1787 echte klantnamen
# (scripts/analyze_name_fallback.py, 10-06-2026, token_set_ratio na
# rechtsvorm-strip): exacte faalorder-namen (Witzand/Van Dongen/GBI Borne)
# scoren 100 met gap >= 22; franchise-/generieke namen ("Jongeneel",
# "Holland") hebben meerdere 100-scores (gap 0) en "TABS Holland" haalt
# max 87 op het VERKEERDE bedrijf (AST Holland). Autopick vereist dus een
# unieke winnaar: top >= 90 én gap >= 10. Vanaf 75 tonen we kandidaten —
# nooit automatisch kiezen (grondwet 5).
NAAM_ACCEPT = 90
NAAM_GAP = 10
NAAM_SHOW = 75


def _extract_email(addr: str) -> str:
    m = EMAIL_RE.search(addr or "")
    return m.group(0).lower() if m else ""


def _normaliseer_klantnaam(naam: str) -> str:
    n = RECHTSVORM_RE.sub(" ", (naam or "").lower())
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _match_by_name(naam_signaal: str) -> tuple[dict | None, list[dict]]:
    """K3: fuzzy-match het naam-signaal tegen klantenkaarten.naam.

    Returns ``(match, kandidaten)`` — bij een unieke duidelijke winnaar een
    match (conf 0.8); bij meerdere plausibele kaarten alleen kandidaten.
    token_set_ratio is bewust subset-vriendelijk: "Witzand" moet "Witzand
    Bouwmaterialen B.V." vinden — de gap-eis voorkomt dat generieke tokens
    ("Holland") of franchises ("Jongeneel": 1 kaart per vestiging) autopicken.
    """
    norm = _normaliseer_klantnaam(naam_signaal)
    if len(norm) < 3:
        return None, []
    with Session(engine) as s:
        kaarten = KlantRepo(s).all()
    namen = {k.nav_klantnr: _normaliseer_klantnaam(k.naam) for k in kaarten if k.naam}
    if not namen:
        return None, []
    per_kaart = {k.nav_klantnr: k for k in kaarten}
    top = process.extract(norm, namen, scorer=fuzz.token_set_ratio, limit=6)
    kandidaten = [
        {
            "navision_klantnr": nr,
            "klantnaam": per_kaart[nr].naam,
            "score": round(score, 1),
            "bron": "naam_extract",
        }
        for _, score, nr in top
        if score >= NAAM_SHOW
    ]
    if top and top[0][1] >= NAAM_ACCEPT and (
        len(top) == 1 or top[0][1] - top[1][1] >= NAAM_GAP
    ):
        kaart = per_kaart[top[0][2]]
        return {
            "navision_klantnr": kaart.nav_klantnr,
            "klantnaam": kaart.naam,
            "match_confidence": 0.8,
            # De beslis-score op de 0-100-schaal (token_set_ratio) — zichtbaar
            # in de provenance zodat naam-matches op dezelfde lat als de
            # artikel-drempel beoordeeld kunnen worden.
            "naam_score": round(top[0][1], 1),
            "match_bron": "naam_extract",
            "is_4plus": kaart.is_4plus,
            "kredietlimiet": kaart.kredietlimiet,
            "betalingsconditie": kaart.betalingsconditie,
        }, kandidaten
    return None, kandidaten


def _extract_domain_name(addr: str) -> str:
    email = _extract_email(addr)
    if not email:
        return ""
    domain = email.split("@", 1)[1]
    return domain.split(".")[0]


def _candidate_address(cand: dict) -> tuple[str, str, str]:
    """(postcode, plaats, straat) from a NAV customer candidate. The nav2018
    client preserves raw PLX_Customer fields; be tolerant of name variants."""
    postcode = cand.get("Post_Code") or cand.get("PostCode") or ""
    plaats = cand.get("City") or cand.get("Plaats") or ""
    straat = (
        cand.get("Address")
        or cand.get("Address_1")
        or cand.get("Address_Line_1")
        or ""
    )
    return str(postcode), str(plaats), str(straat)


def _score_customer(cand: dict, signal: str, afleveradres: dict) -> int:
    """Score one candidate against the order's delivery location:
    postcode exact (5) > plaats named in order text (3) > straat substring (1).
    Mirrors select_ship_to's weighting so customer- and ship-to disambiguation
    behave consistently."""
    postcode, plaats, straat = _candidate_address(cand)
    score = 0

    addr_pc = _normalize_postcode(afleveradres.get("postcode"))
    cand_pc = _normalize_postcode(postcode)
    if cand_pc and addr_pc and cand_pc == addr_pc:
        score += 5

    if plaats and _word_in(signal, plaats):
        score += 3

    s = straat.strip().lower()
    if s and s in signal:
        score += 1

    return score


def _pick_customer(
    res: list[dict], state: dict
) -> tuple[dict | None, bool, str]:
    """Choose the right candidate from a NAV search result.

    Returns ``(chosen, ambiguous, matched_on)``. With one candidate we accept
    it. With several (a franchise with one card per branch), we score on the
    delivery address and accept ONLY a single clear winner; otherwise we
    refuse to guess (``ambiguous=True``) so a human picks — shipping
    Heerenveen's order to the Arnhem card is worse than asking.
    """
    if not res:
        return None, False, "none"
    if len(res) == 1:
        return res[0], False, "single"

    signal = _order_signal_text(state)
    afleveradres = state.get("afleveradres") or {}
    scored = sorted(
        ((c, _score_customer(c, signal, afleveradres)) for c in res),
        key=lambda x: x[1],
        reverse=True,
    )
    top, top_score = scored[0]
    second_score = scored[1][1]
    if top_score > 0 and second_score < top_score:
        matched_on = "postcode" if top_score >= 5 else "plaats"
        return top, False, matched_on
    return None, True, "ambiguous"


async def match_customer_node(state: OrderState) -> OrderState:
    email_from = state.get("email_from") or ""
    email = _extract_email(email_from)

    # Forward detection: als de outer-From een Kwabo-medewerker is, haal de originele
    # afzender uit de body (Outlook/Gmail forward headers).
    bijl_blob = "\n".join((b or {}).get("inhoud_tekst") or "" for b in state.get("bijlagen") or [])[:40000]
    fwd = detect_forward(email_from, state.get("email_subject") or "", state.get("email_body") or "", bijl_blob)
    effective_email = email
    forward_note = None
    if fwd.is_forwarded and fwd.original_from_email:
        effective_email = fwd.original_from_email
        forward_note = f"Forward: {fwd.reason}; originele afzender={fwd.original_from_email}"
        log.info(
            "forward_detected",
            email_id=state.get("email_id"),
            outer_from=email,
            original_from=fwd.original_from_email,
            reason=fwd.reason,
        )

    nav: NavisionClient = get_navision_client()
    match = None

    with Session(engine) as s:
        repo = KlantRepo(s)
        klant = repo.by_email(effective_email) if effective_email else None
        if klant:
            match = {
                "navision_klantnr": klant.nav_klantnr,
                "klantnaam": klant.naam,
                "match_confidence": 1.0,
                "match_bron": "forward_email" if forward_note else "email",
                "is_4plus": klant.is_4plus,
                "kredietlimiet": klant.kredietlimiet,
                "betalingsconditie": klant.betalingsconditie,
            }

    # NAV search fallbacks. Both can return SEVERAL candidates (a franchise
    # like Pontmeyer has one customer card per branch). Never blindly take
    # res[0] — disambiguate on the order's delivery address; flag if unclear.
    ambiguous_candidates: list[dict] | None = None
    ambiguous_term: str | None = None

    if not match and effective_email:
        res = await nav.search_customers(email=effective_email)
        chosen, ambiguous, matched_on = _pick_customer(res, state)
        if chosen:
            match = {
                "navision_klantnr": chosen["number"],
                "klantnaam": chosen["displayName"],
                "match_confidence": 0.95 if matched_on == "single" else 0.9,
                "match_bron": "navision_email",
            }
        elif ambiguous:
            ambiguous_candidates = res
            ambiguous_term = effective_email

    # K3 (Fase 2): naam-fallback — de geëxtraheerde KLANTNAAM uit de
    # bestelling (niet de afzender!) fuzzy tegen de klantenkaarten-mirror.
    # Bij portaal/agent-mails (zevij-portaal, pontmeyer-agent) is dit het
    # enige betrouwbare signaal. Forward-naam als tweede signaal.
    klant_kandidaten: list[dict] = []
    naam_signaal = (
        (state.get("klantnaam_besteller") or "").strip()
        or (fwd.original_from_name or "").strip()
    )
    if not match and ambiguous_candidates is None and naam_signaal:
        match, klant_kandidaten = _match_by_name(naam_signaal)

    if not match and ambiguous_candidates is None and not klant_kandidaten:
        # Name fuzzy search via Nav — gebruik forward-domein indien aanwezig.
        # K4: pure doorstuur-portalen overslaan — hun domein noemt nooit de
        # klant, dus elke hit zou per definitie fout zijn.
        effective_from = fwd.original_from_email or email_from
        effective_addr = _extract_email(effective_from)
        full_domain = effective_addr.split("@", 1)[1] if "@" in effective_addr else ""
        domain = _extract_domain_name(effective_from)
        if domain and full_domain not in PORTAL_DOMAINS:
            res = await nav.search_customers(naam=domain)
            chosen, ambiguous, matched_on = _pick_customer(res, state)
            if chosen:
                match = {
                    "navision_klantnr": chosen["number"],
                    "klantnaam": chosen["displayName"],
                    # Disambiguated by address → trust it (0.85); a lone name
                    # hit stays the cautious 0.7 as before.
                    "match_confidence": 0.7 if matched_on == "single" else 0.85,
                    "match_bron": "navision_name",
                }
            elif ambiguous:
                ambiguous_candidates = res
                ambiguous_term = domain

    warnings = list(state.get("validatie_warnings") or [])
    if forward_note:
        warnings.append(forward_note)
    if not match and ambiguous_candidates:
        namen = ", ".join(
            f"{c.get('number')} ({c.get('displayName')})"
            for c in ambiguous_candidates[:6]
        )
        warnings.append(
            f"⚠ MEERDERE KLANTEN gevonden voor '{ambiguous_term}' "
            f"({len(ambiguous_candidates)}) — geen eenduidige adres-match. "
            f"Handmatige selectie nodig. Kandidaten: {namen}"
        )
        # Unificeer met de K3-kandidatenstructuur zodat het dashboard één
        # picker kan tonen ongeacht welke stap de kandidaten vond.
        if not klant_kandidaten:
            klant_kandidaten = [
                {
                    "navision_klantnr": c.get("number"),
                    "klantnaam": c.get("displayName"),
                    "score": None,
                    "bron": "navision",
                }
                for c in ambiguous_candidates[:6]
            ]
    elif not match and klant_kandidaten:
        namen = ", ".join(
            f"{k['navision_klantnr']} ({k['klantnaam']})" for k in klant_kandidaten
        )
        warnings.append(
            f"⚠ MEERDERE KLANTEN mogelijk voor '{naam_signaal}' — geen unieke "
            f"naam-match. Handmatige selectie nodig. Kandidaten: {namen}"
        )
    elif not match:
        warnings.append(f"KLANT NIET GEVONDEN: {email_from}. Handmatige selectie nodig.")

    # 4+ signalering + kredietcheck
    if match:
        if match.get("is_4plus") is False:
            warnings.append("⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden")
        krediet = match.get("kredietlimiet")
        if krediet and krediet > 0:
            # Bereken ordertotaal uit orderregels
            total = 0.0
            for r in (state.get("orderregels") or []):
                try:
                    total += float(r.get("hoeveelheid") or 0) * float(r.get("prijs_per_eenheid") or 0)
                except (TypeError, ValueError):
                    continue
            if total > krediet:
                warnings.append(
                    f"⚠ KREDIETLIMIET OVERSCHREDEN: ordertotaal €{total:.2f} > limiet €{krediet:.2f}"
                )
                match["kredietlimiet_status"] = "overschreden"
            else:
                match["kredietlimiet_status"] = "ok"
        log.info("klant_checks", is_4plus=match.get("is_4plus"), kredietlimiet=krediet)
    log.info(
        "match_customer", email_id=state.get("email_id"),
        klant_nr=(match or {}).get("navision_klantnr"),
        bron=(match or {}).get("match_bron"), confidence=(match or {}).get("match_confidence"),
    )

    stap = {
        "stap": "match_customer",
        "timestamp": utcnow().isoformat(),
        "beslissing": (f"Klant gematcht: {match['navision_klantnr']} ({match['match_bron']})" if match
                       else "Klant NIET gematcht"),
        "details": match or {"email": email},
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    # Provenance for klant_match
    confidence = (match or {}).get("match_confidence", 0.0)
    bron = (match or {}).get("match_bron")
    naam_score = (match or {}).get("naam_score")
    klant_meta = {
        "value": (match or {}).get("navision_klantnr"),
        "source": (
            "klantenkaart" if bron in ("email", "forward_email", "naam_extract")
            else "navision" if bron and bron.startswith("navision_")
            else "missing"
        ),
        "source_detail": (
            f"{bron} (score {naam_score:.0f}/100)" if naam_score is not None else bron
        ),
        "confidence": float(confidence),
        # 3b: alleen een directe e-mailmatch op de klantenkaart (conf 1.0) is
        # vlagvrij. Elke naam-/NAV-afgeleide match (< 1.0) krijgt een zachte
        # "controleer klant"-vlag: een foute klant stuurt prijsgroep, ship-to
        # én kredietlimiet de verkeerde kant op — liever even bevestigen.
        "needs_review": (not match) or confidence < 1.0,
    }
    needs_paths = list(state.get("needs_review_fields") or [])
    if klant_meta["needs_review"] and "klant_match" not in needs_paths:
        needs_paths.append("klant_match")
    meta = dict(state.get("_meta") or {})
    meta["klant_match"] = klant_meta

    return {
        **state,
        "klant_match": match,
        "klant_kandidaten": [] if match else klant_kandidaten,
        "validatie_warnings": warnings,
        "stappen_log": steps,
        "_meta": meta,
        "needs_review_fields": needs_paths,
        "needs_review_count": len(needs_paths),
    }
