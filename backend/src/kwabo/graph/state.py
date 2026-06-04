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
    # T7: optional UoM picker for mixprijzen lines (set by apply_mixprijzen)
    mix_uom_kandidaat: Optional[list[str]]
    mix_uom_gekozen: Optional[str]
    # T7: active mix price (NAV table 7002) for the chosen mix code, informational
    mix_actieve_prijs: Optional[float]
    # T3/T4: line-level default UoM (informational; lets the composer suppress
    # redundant unitOfMeasureCode PATCHes when the regel uses the item default)
    eenheid_default: Optional[str]
    # T3: customer's originally-ordered unit, preserved before match_articles
    # normalises `eenheid` to a NAV-valid code. Used by compute_europallet and
    # apply_mixprijzen to convert quantities to pallets.
    eenheid_origineel: Optional[str]


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

    # T5: ship-to selection (filled by select_ship_to_node)
    ship_to_kandidaten: list[dict]
    ship_to_gekozen: Optional[str]

    # T7: mixprijzen flag (set by apply_mixprijzen_node when customer has mix-prices)
    mixprijzen_actief: bool
    # T7: order-wide total pallets across mix lines — the staffel basis for the
    # chosen M-tier (M{order_mix_total_pallets}PAL..). Informational/audit.
    order_mix_total_pallets: Optional[int]

    # T8: europallet line, computed when an order needs a pallet
    europallet_regel: Optional[dict]

    # T9: pre-push artifacts — a path to the source document we'll attach as
    # /incomingDocuments + the chronologically ordered NAV operation list
    # composed by `compose_navision_operations`. push_navision feeds the latter
    # to `create_sales_order_stepwise` and stores the per-op outcome plus the
    # union of NAV-side autofilled fields back into state for the audit trail.
    incoming_document_path: Optional[str]
    # Supabase Storage object-key voor de bron-mail/PDF. Canoniek vanaf
    # Fase 2 (zie productie-ready plan): vervangt `incoming_document_path`
    # voor nieuwe orders. Path blijft voor legacy/back-compat — orders die
    # vóór Supabase-storage zijn aangemaakt hebben alleen `_path`.
    incoming_document_storage_key: Optional[str]
    nav_operations: list[dict]
    nav_operation_results: list[dict]
    nav_autofilled: dict

    # Diagnostic surfaced by compose_order_node when compose_navision_operations
    # raises. Populated when nav_operations cannot be built (e.g. no matched
    # articles); the dashboard shows this and push_navision refuses.
    compose_error: Optional[str]

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
