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
