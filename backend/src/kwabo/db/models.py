"""SQLModel database schema per PDF §6."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from kwabo.utils import utcnow


class Klantenkaart(SQLModel, table=True):
    __tablename__ = "klantenkaarten"

    id: Optional[int] = Field(default=None, primary_key=True)
    nav_klantnr: str = Field(unique=True, index=True)
    naam: str
    email: Optional[str] = Field(default=None, index=True)
    email_bestelling: Optional[str] = Field(default=None, index=True)
    telefoon: Optional[str] = None
    taal: str = "NL"
    standaard_afleveradres: Optional[str] = None  # JSON
    speciale_instructies: Optional[str] = None
    is_4plus: bool = False
    kredietlimiet: Optional[float] = None
    betalingsconditie: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class KlantEmailAlias(SQLModel, table=True):
    __tablename__ = "klant_email_aliases"

    id: Optional[int] = Field(default=None, primary_key=True)
    klant_nr: str = Field(index=True)
    email: str = Field(index=True)
    label: Optional[str] = None  # e.g. "Vestiging Utrecht", "Inkoop algemeen"
    created_at: datetime = Field(default_factory=utcnow)


class KlantDocument(SQLModel, table=True):
    __tablename__ = "klant_documenten"

    id: Optional[int] = Field(default=None, primary_key=True)
    klant_nr: str = Field(index=True)
    filename: str
    doc_type: str  # pdf | excel | docx | csv | txt | other
    mime_type: Optional[str] = None
    size_bytes: int = 0
    text_content: str = ""  # geëxtraheerde platte tekst
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class OAuthConfig(SQLModel, table=True):
    """Singleton (id=1) config for Microsoft Graph OAuth2."""

    __tablename__ = "oauth_config"

    id: Optional[int] = Field(default=1, primary_key=True)
    provider: str = "microsoft"  # microsoft | google (future)
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/api/mailbox/oauth/callback"
    scopes: str = "offline_access Mail.Read User.Read"
    updated_at: datetime = Field(default_factory=utcnow)


class OAuthToken(SQLModel, table=True):
    """Stored tokens for the Graph mailbox. Singleton (id=1) for now."""

    __tablename__ = "oauth_tokens"

    id: Optional[int] = Field(default=1, primary_key=True)
    provider: str = "microsoft"
    account_email: Optional[str] = None
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None
    updated_at: datetime = Field(default_factory=utcnow)


class KlantenkaartArtikel(SQLModel, table=True):
    __tablename__ = "klantenkaart_artikelen"

    id: Optional[int] = Field(default=None, primary_key=True)
    klant_nr: str = Field(index=True)
    klant_artikelnr: str = Field(index=True)
    kwabo_artikelnr: str
    omschrijving: Optional[str] = None
    standaard_prijs: Optional[float] = None
    korting_pct: float = 0.0
    geldig_tot: Optional[date] = None


class Prijsafspraak(SQLModel, table=True):
    __tablename__ = "prijsafspraken"

    id: Optional[int] = Field(default=None, primary_key=True)
    klant_nr: str = Field(index=True)
    kwabo_artikelnr: str = Field(index=True)
    prijs: float
    korting_pct: float = 0.0
    type: str = "standaard"  # 'standaard', 'mix', 'pallet', 'topcoat'
    min_hoeveelheid: Optional[float] = None
    geldig_van: Optional[date] = None
    geldig_tot: Optional[date] = None


class ArtikelMatchingHistory(SQLModel, table=True):
    __tablename__ = "artikel_matching_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    klant_nr: str = Field(index=True)
    klant_artikelnr: Optional[str] = Field(default=None, index=True)
    klant_omschrijving: Optional[str] = None
    kwabo_artikelnr: str
    match_methode: str  # 'exact', 'history', 'fuzzy', 'manual'
    was_correctie: bool = False
    order_datum: Optional[date] = None
    created_at: datetime = Field(default_factory=utcnow)


class OrderLog(SQLModel, table=True):
    __tablename__ = "order_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    email_id: str = Field(index=True)
    email_from: Optional[str] = None
    email_subject: Optional[str] = None
    email_date: Optional[str] = None
    status: str = Field(default="processing", index=True)
    # processing, review, approved, pushed, rejected, error
    is_order: Optional[bool] = None
    classificatie_confidence: Optional[float] = None
    klant_nr: Optional[str] = None
    klant_match_confidence: Optional[float] = None
    klant_match_methode: Optional[str] = None
    bestelnummer_klant: Optional[str] = None
    navision_order_nr: Optional[str] = None
    aantal_regels: Optional[int] = None
    alle_artikelen_gematcht: Optional[bool] = None
    alle_prijzen_valide: Optional[bool] = None
    warnings: Optional[str] = None  # JSON
    correcties: Optional[str] = None  # JSON
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    stappen_log: Optional[str] = None  # JSON
    order_state: Optional[str] = None  # Full OrderState JSON
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
