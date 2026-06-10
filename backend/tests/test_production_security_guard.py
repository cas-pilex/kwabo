"""Fail-closed guard against an insecure production (Postgres) deployment.

Two fail-OPEN patterns exist in the auth layer by design (so dev needs no
secrets):
  * require_admin() treats an empty ADMIN_PASSWORD as "auth disabled" → the
    entire API is public.
  * jwt_secret defaults to the in-repo value "dev-only-change-me-in-prod" →
    anyone reading this public repo can forge an admin session token.

Both are fine for SQLite dev/CI, but catastrophic if they reach a real
Postgres deployment. This guard turns that silent misconfig into a loud,
boot-blocking error.
"""
from __future__ import annotations

import pytest

from kwabo.config import DEV_JWT_SECRET_DEFAULT, validate_production_security


def test_sqlite_is_never_blocked_even_with_insecure_secrets():
    # Dev/CI default: no password, dev secret, sqlite → must NOT raise.
    validate_production_security(
        database_url="sqlite:///./kwabo.db",
        admin_password="",
        jwt_secret=DEV_JWT_SECRET_DEFAULT,
    )


def test_postgres_with_empty_admin_password_is_rejected():
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        validate_production_security(
            database_url="postgresql+psycopg://u:p@host:6543/postgres",
            admin_password="",
            jwt_secret="a-real-unique-secret",
        )


def test_postgres_with_default_jwt_secret_is_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_security(
            database_url="postgresql+psycopg://u:p@host:6543/postgres",
            admin_password="a-strong-password",
            jwt_secret=DEV_JWT_SECRET_DEFAULT,
        )


def test_postgres_with_strong_secrets_passes():
    validate_production_security(
        database_url="postgresql+psycopg://u:p@host:6543/postgres",
        admin_password="a-strong-password",
        jwt_secret="a-real-unique-secret",
    )
