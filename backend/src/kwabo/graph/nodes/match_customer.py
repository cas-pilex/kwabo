"""Match customer node: email → DB → Navision search → None."""
from __future__ import annotations

import re
from datetime import datetime

from kwabo.utils import utcnow

from sqlmodel import Session

from kwabo.db.repository import KlantRepo
from kwabo.db.session import engine
from kwabo.graph.state import OrderState
from kwabo.integrations.forwarded_parser import detect_forward
from kwabo.integrations.navision_api import NavisionClient, get_navision_client
from kwabo.utils.logging import log

EMAIL_RE = re.compile(r"[\w\.\-\+]+@[\w\.\-]+")


def _extract_email(addr: str) -> str:
    m = EMAIL_RE.search(addr or "")
    return m.group(0).lower() if m else ""


def _extract_domain_name(addr: str) -> str:
    email = _extract_email(addr)
    if not email:
        return ""
    domain = email.split("@", 1)[1]
    return domain.split(".")[0]


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

    if not match and effective_email:
        # Nav email search
        res = await nav.search_customers(email=effective_email)
        if res:
            match = {
                "navision_klantnr": res[0]["number"],
                "klantnaam": res[0]["displayName"],
                "match_confidence": 0.95,
                "match_bron": "navision_email",
            }

    if not match:
        # Name fuzzy search via Nav — gebruik forward-domein indien aanwezig
        effective_from = fwd.original_from_email or email_from
        domain = _extract_domain_name(effective_from)
        if domain:
            res = await nav.search_customers(naam=domain)
            if res:
                match = {
                    "navision_klantnr": res[0]["number"],
                    "klantnaam": res[0]["displayName"],
                    "match_confidence": 0.7,
                    "match_bron": "navision_name",
                }

    warnings = list(state.get("validatie_warnings") or [])
    if forward_note:
        warnings.append(forward_note)
    if not match:
        warnings.append(f"KLANT NIET GEVONDEN: {email_from}. Handmatige selectie nodig.")

    # 4+ signalering + kredietcheck
    if match:
        if match.get("is_4plus") is False:
            warnings.append("⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden")
        krediet = match.get("kredietlimiet")
        if krediet and krediet > 0:
            match["kredietlimiet_status"] = "ok"  # placeholder; echte Nav-check vereist openstaand-saldo API
            # Wanneer echte Nav beschikbaar: GET /salesOrders?$filter=customerNumber eq 'X' and status eq 'Open'
            # en tel openstaande bedragen op. Nu: toon kredietlimiet in UI als informatief.
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
    klant_meta = {
        "value": (match or {}).get("navision_klantnr"),
        "source": (
            "klantenkaart" if bron == "email"
            else "navision" if bron and bron.startswith("navision_")
            else "missing"
        ),
        "source_detail": bron,
        "confidence": float(confidence),
        "needs_review": (not match) or confidence < 0.7,
    }
    needs_paths = list(state.get("needs_review_fields") or [])
    if klant_meta["needs_review"] and "klant_match" not in needs_paths:
        needs_paths.append("klant_match")
    meta = dict(state.get("_meta") or {})
    meta["klant_match"] = klant_meta

    return {
        **state,
        "klant_match": match,
        "validatie_warnings": warnings,
        "stappen_log": steps,
        "_meta": meta,
        "needs_review_fields": needs_paths,
        "needs_review_count": len(needs_paths),
    }
