"""Application configuration."""
from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    database_url: str = "sqlite:///./kwabo.db"
    navision_mode: str = "mock"
    email_mode: str = "file_drop"
    inbox_dir: str = "../data/inbox"
    processed_dir: str = "../data/processed"
    navision_mock_dir: str = "../data/navision_mock"
    incoming_documents_dir: str = "../data/incoming_documents"
    langchain_tracing_v2: bool = False
    langchain_project: str = "kwabo-order-intake"
    log_level: str = "INFO"
    mail_mode: str = "log"  # log | smtp | graph
    llm_cache_mode: str = "on"
    llm_cache_dir: str = "../data/llm_cache"
    # "on" to mount /api/testing/* routes. Accepts KWABO_TEST_MODE or TEST_MODE.
    test_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("KWABO_TEST_MODE", "TEST_MODE", "test_mode"),
    )

    # --- Auth ---
    # Single-admin shared password gate. When set, /api/auth/login validates
    # against this. JWT_SECRET signs the session cookie; auto-generated for
    # dev but MUST be set explicitly in production (Railway env).
    admin_password: str = ""
    jwt_secret: str = "dev-only-change-me-in-prod"
    jwt_ttl_hours: int = 24
    # HMAC secret for short-lived URL-embedded download tokens (PDF view in
    # new tab). Empty → derived from jwt_secret with a static salt; that's
    # fine because rotating jwt_secret already invalidates download tokens
    # alongside sessions. Set explicitly to rotate independently.
    signed_url_secret: str = ""
    # Default TTL for attachment download tokens. 5 minutes is enough for a
    # reviewer to click and the browser to follow the GET.
    signed_url_ttl_seconds: int = 300

    # Background mail-poll interval. 0 = disabled (manual /scan only). Set to
    # e.g. 300 in Railway to scan every 5 minutes. Only honoured when
    # email_mode != "file_drop" (no inbox to poll otherwise).
    mail_poll_interval_seconds: int = 0

    # Article number used for the synthesised europallet line. Config-driven
    # so operations can rotate it without a code deploy if NAV master-data
    # ever moves the SKU.
    europallet_artikelnr: str = "19820"

    # --- Supabase Storage (canonieke .eml + incoming-doc opslag) ---
    # Productie: Railway env-vars zetten zodat .eml-bestanden de ephemere
    # Railway-FS overleven. Lokaal/docker dev mag leeg blijven — dan valt
    # de code netjes terug op disk-persist onder INCOMING_DOCUMENTS_DIR.
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket_incoming_docs: str = "incoming-docs"
    supabase_signed_url_ttl_seconds: int = 600

    # --- Demo-seed ---
    # De seed (db/seed.py) zet 16 demo-klanten (10001-10016) met de
    # e-mailadressen van echte order-mails. In PRODUCTIE vervuilt dat
    # match_customer: een echte mail matcht op het demo-nummer i.p.v. de
    # NAV-klant, en de push faalt (nummer bestaat niet in NAV). Daarom seeden
    # we alleen in dev/test (sqlite). Deze flag is een expliciete override.
    seed_demo_data: bool = True

    # --- Frontend ---
    # Public origin of the Next.js app. Used by the OAuth callback HTML
    # page to redirect the user back to the dashboard after Microsoft sign-in.
    # Default is the local dev origin; set FRONTEND_URL on Railway to the
    # production Vercel domain (e.g. https://kwabo-pilex.vercel.app).
    frontend_url: str = "http://localhost:3000"

    # --- NAV 2018 OData V4 (Kwabo-test endpoint shape) ---
    # Used when navision_mode == "nav2018".
    # Base URL excluding the Company('...') segment, e.g.
    #   https://sf-112840.dynamicstocloud.com:1153/ST-124593-WS/ODataV4
    nav_base_url: str = ""
    # Company display name as it appears in NAV (with spaces). The client
    # URL-encodes this when building paths.
    nav_company: str = ""
    # Web Service Access Key flow — username + key (Basic auth).
    nav_username: str = ""
    nav_password: str = ""
    # Page (entity) names exposed via NAV web services. Defaults match the
    # Pilex test environment Cas provided. Override per-deployment.
    nav_page_sales_order: str = "PLX_SalesOrder"
    nav_page_sales_order_lines: str = "PLX_SalesOrderLines"
    nav_page_customer: str = "PLX_Customer"
    nav_page_item: str = "PLX_Item"
    nav_page_item_reference: str = "PLX_ItemReference"
    nav_page_ship_to: str = "PLX_ShipToAddress"
    nav_page_item_uom: str = "PLX_ItemUnitOfMeasure"
    nav_verify_ssl: bool = True
    # FUNCTIE 7: koppelt het bron-document als inkomend document aan de
    # NAV-order. NAV 2018 publiceert PLX_IncomingDocument (nog) niet via OData,
    # dus de nav2018-client slaat die ops standaard over (header+regels blijven
    # geldig; de reviewer krijgt een waarschuwing). Zet deze env-flag op true
    # zodra de partner de page publiceert EN de transport-vertaling gewired is —
    # dan worden de incoming-doc-ops uitgevoerd i.p.v. overgeslagen.
    nav2018_incoming_document_enabled: bool = False
    # Fase 4 (B2): retry/backoff voor idempotente NAV-GETs (429/5xx/transport).
    # Nooit toegepast op POST/PATCH — die zijn niet idempotent (dubbele orders).
    nav_get_retry_attempts: int = 3
    nav_get_retry_base_delay_s: float = 0.5
    nav_get_retry_max_delay_s: float = 30.0
    # Fase 4 (B1, audit §12.D.1): max parallelle regel-matches in
    # match_articles. 1 = serieel (oud gedrag). Niet >~10 zetten zonder de
    # DB-pool te herzien (5 taken × 1 connectie past in pool 5 + overflow 10).
    match_concurrency: int = 5

    @property
    def inbox_path(self) -> Path:
        return Path(self.inbox_dir).resolve()

    @property
    def processed_path(self) -> Path:
        return Path(self.processed_dir).resolve()

    @property
    def navision_mock_path(self) -> Path:
        return Path(self.navision_mock_dir).resolve()

    @property
    def incoming_documents_path(self) -> Path:
        return Path(self.incoming_documents_dir).resolve()


settings = Settings()


# Sentinel: the in-repo dev default for jwt_secret. If this value survives into
# a Postgres (production) deployment, admin session tokens are forgeable by
# anyone who reads this public repository.
DEV_JWT_SECRET_DEFAULT = "dev-only-change-me-in-prod"


def validate_production_security(
    *,
    database_url: str | None = None,
    admin_password: str | None = None,
    jwt_secret: str | None = None,
) -> None:
    """Fail closed on an insecure production (Postgres) deployment.

    SQLite (dev/CI/docker) is never blocked. On Postgres we refuse to boot when
    the API would be trivially compromised:
      * ADMIN_PASSWORD empty      → require_admin() short-circuits → API fully open.
      * JWT_SECRET == dev default → session tokens forgeable with a public secret.

    A loud failed deploy is far safer than a silently-open or forgeable prod API.
    Args default to the live settings; they're injectable for testing.
    """
    db = settings.database_url if database_url is None else database_url
    pw = settings.admin_password if admin_password is None else admin_password
    secret = settings.jwt_secret if jwt_secret is None else jwt_secret
    if not (db or "").startswith(("postgresql", "postgres")):
        return
    problems: list[str] = []
    if not pw:
        problems.append(
            "ADMIN_PASSWORD is leeg — de admin-gate staat dan UIT en de hele API "
            "is publiek. Zet ADMIN_PASSWORD in de productie-env (Railway)."
        )
    if not secret or secret == DEV_JWT_SECRET_DEFAULT:
        problems.append(
            "JWT_SECRET staat op de publieke dev-default — sessietokens zijn te "
            "vervalsen. Zet een uniek JWT_SECRET in de productie-env (Railway)."
        )
    if problems:
        raise RuntimeError(
            "Onveilige productie-config geweigerd:\n- " + "\n- ".join(problems)
        )
