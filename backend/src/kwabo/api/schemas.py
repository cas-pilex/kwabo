"""Pydantic schemas for API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class OrderSummary(BaseModel):
    id: int
    email_id: str
    email_from: Optional[str] = None
    email_subject: Optional[str] = None
    email_date: Optional[str] = None
    status: str
    is_order: Optional[bool] = None
    klant_nr: Optional[str] = None
    klant_match_confidence: Optional[float] = None
    bestelnummer_klant: Optional[str] = None
    aantal_regels: Optional[int] = None
    alle_artikelen_gematcht: Optional[bool] = None
    alle_prijzen_valide: Optional[bool] = None
    navision_order_nr: Optional[str] = None
    warnings_count: int = 0
    needs_review_count: int = 0
    parent_log_id: Optional[int] = None
    sub_order_index: Optional[int] = None
    created_at: datetime


class OrderDetail(OrderSummary):
    warnings: list[str] = []
    stappen_log: list[dict[str, Any]] = []
    order_state: dict[str, Any] = {}


class KlantOut(BaseModel):
    nav_klantnr: str
    naam: str
    email: Optional[str] = None
    email_bestelling: Optional[str] = None
    taal: str = "NL"
    is_4plus: bool = False


class MappingOut(BaseModel):
    id: int
    klant_nr: str
    klant_artikelnr: str
    kwabo_artikelnr: str
    omschrijving: Optional[str] = None


class MappingIn(BaseModel):
    klant_artikelnr: str
    kwabo_artikelnr: str
    omschrijving: Optional[str] = None


class ItemOut(BaseModel):
    number: str
    displayName: str


class AliasOut(BaseModel):
    id: int
    klant_nr: str
    email: str
    label: Optional[str] = None


class AliasIn(BaseModel):
    email: str
    label: Optional[str] = None


class KlantDocumentOut(BaseModel):
    id: int
    klant_nr: str
    filename: str
    doc_type: str
    mime_type: Optional[str] = None
    size_bytes: int
    notes: Optional[str] = None
    created_at: datetime
    text_preview: str  # first ~500 chars


class KlantDocumentDetail(KlantDocumentOut):
    text_content: str


class ApproveRequest(BaseModel):
    corrections: Optional[dict[str, Any]] = None
    reviewer: Optional[str] = None


class RejectRequest(BaseModel):
    reason: Optional[str] = None
    reviewer: Optional[str] = None


class PatchOrderRequest(BaseModel):
    klant_nr: Optional[str] = None
    orderregels: Optional[list[dict[str, Any]]] = None
    afleveradres: Optional[dict[str, Any]] = None
    opmerkingen: Optional[str] = None


class StatsOut(BaseModel):
    total_orders: int
    by_status: dict[str, int]
    auto_match_pct: float
    avg_confidence: float | None
