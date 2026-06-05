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
    mixprijzen: bool = Field(default=False, nullable=False)
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
    scopes: str = "offline_access Mail.ReadWrite User.Read"
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
    match_methode: str  # 'exact', 'kruisverwijzing', 'klantenkaart', 'history', 'fuzzy', 'manual'
    was_correctie: bool = False
    order_datum: Optional[date] = None
    created_at: datetime = Field(default_factory=utcnow)


class Artikelkaart(SQLModel, table=True):
    """NAV item card mirror — one row per Kwabo article."""

    __tablename__ = "artikelkaarten"

    kwabo_artikelnr: str = Field(primary_key=True)
    naam: str
    basis_eenheid: str  # NAV UOM code, e.g. "STUK", "ROL"
    mixprijzen: bool = Field(default=False, nullable=False)
    palletable: Optional[bool] = Field(default=None)  # nullable, computed/learned
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ArtikelEenheid(SQLModel, table=True):
    """Item Unit-of-Measure register — multiple rows per artikel."""

    __tablename__ = "artikel_eenheden"

    kwabo_artikelnr: str = Field(primary_key=True)
    eenheid_code: str = Field(primary_key=True)
    qty_per_base: float = 1.0
    is_mix_uom: bool = Field(default=False, nullable=False)


class KlantenkaartShipTo(SQLModel, table=True):
    """Ship-to address mirror (NAV table 222)."""

    __tablename__ = "klantenkaart_ship_to"

    klant_nr: str = Field(primary_key=True)
    ship_to_code: str = Field(primary_key=True)
    naam: str
    straat: str
    postcode: str
    plaats: str
    land: str
    is_default: bool = Field(default=False, nullable=False)


class ArtikelKruisverwijzing(SQLModel, table=True):
    """Item Reference (NAV table 5717) — customer artikel-nr -> Kwabo artikel-nr."""

    __tablename__ = "artikel_kruisverwijzing"

    klant_nr: str = Field(primary_key=True)
    klant_artikelnr: str = Field(primary_key=True)
    kwabo_artikelnr: str
    eenheid_klant: Optional[str] = Field(default=None)
    bron: str = Field(default="customer")


class ArtikelPalletKennis(SQLModel, table=True):
    """Self-learning europallet table — what we know per artikel/eenheid."""

    __tablename__ = "artikel_pallet_kennis"

    kwabo_artikelnr: str = Field(primary_key=True)
    eenheid: str = Field(primary_key=True)
    pallet_required: bool = Field(default=False, nullable=False)
    per_pallet: int = 24
    confidence: float = 0.0
    laatst_bevestigd_op: datetime = Field(default_factory=utcnow)
    bevestigd_door: Optional[str] = Field(default=None)


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
