"""OrderState TypedDict (PDF §3.2)."""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class Address(TypedDict, total=False):
    naam: str
    straat: str
    postcode: str
    plaats: str
    land: str
    contactpersoon: Optional[str]
    telefoon: Optional[str]


class OrderRegel(TypedDict, total=False):
    positie: int
    artikelnummer_klant: Optional[str]
    artikelnummer_kwabo: Optional[str]
    artikelnummer_kwabo_matched: Optional[str]
    omschrijving: str
    hoeveelheid: float
    eenheid: str
    prijs_per_eenheid: Optional[float]
    prijs_validated: Optional[bool]
    prijs_afwijking: Optional[str]
    ean_code: Optional[str]
    leverdatum_regel: Optional[str]
    opmerkingen: Optional[str]
    match_confidence: Optional[float]
    match_methode: Optional[str]


class KlantMatch(TypedDict, total=False):
    navision_klantnr: str
    klantnaam: str
    match_confidence: float
    match_bron: str
    is_4plus: Optional[bool]
    kredietlimiet: Optional[float]
    betalingsconditie: Optional[str]


class StapLog(TypedDict, total=False):
    stap: str
    timestamp: str
    beslissing: str
    details: dict[str, Any]


class OrderState(TypedDict, total=False):
    # Input
    email_id: str
    email_from: str
    email_subject: str
    email_body: str
    email_date: str
    bijlagen: list[dict]  # [{naam, type, inhoud_tekst}]
    source_path: Optional[str]

    # Classification
    is_order: bool
    classificatie_reden: str
    classificatie_confidence: Optional[float]

    # Extraction
    taal: Optional[str]
    bestelnummer_klant: Optional[str]
    orderdatum: Optional[str]
    gewenste_leverdatum: Optional[str]
    afleveradres: Optional[Address]
    afleverinstructies: Optional[str]
    orderregels: list[OrderRegel]
    opmerkingen: Optional[str]

    # Matching
    klant_match: Optional[KlantMatch]

    # Validation
    alle_artikelen_gematcht: bool
    alle_prijzen_valide: bool
    validatie_warnings: list[str]

    # Review
    review_status: str  # "pending", "approved", "rejected", "needs_edit"
    review_corrections: Optional[dict]
    reviewer: Optional[str]

    # Navision
    navision_order_nr: Optional[str]
    navision_status: Optional[str]

    # Audit trail
    stappen_log: list[StapLog]
    errors: list[str]

    # DB linkage
    order_log_id: Optional[int]

    # Provenance + needs-review aggregation (Plan v2)
    _meta: dict[str, Any]
    needs_review_fields: list[str]
    needs_review_count: int

    # Multi-order support: remainder of extra sub-orders returned by LLM as array
    extra_orders_raw: list[dict]
    parent_log_id: Optional[int]
    sub_order_index: Optional[int]


def new_state(email_id: str, email_from: str, email_subject: str, email_body: str,
              email_date: str, bijlagen: list[dict], source_path: str | None = None) -> OrderState:
    return {
        "email_id": email_id,
        "email_from": email_from,
        "email_subject": email_subject,
        "email_body": email_body,
        "email_date": email_date,
        "bijlagen": bijlagen,
        "source_path": source_path,
        "is_order": False,
        "classificatie_reden": "",
        "orderregels": [],
        "alle_artikelen_gematcht": False,
        "alle_prijzen_valide": False,
        "validatie_warnings": [],
        "review_status": "pending",
        "stappen_log": [],
        "errors": [],
    }
