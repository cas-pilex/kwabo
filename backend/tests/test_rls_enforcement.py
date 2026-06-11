"""RLS-hardening: every public table must get ROW LEVEL SECURITY on Postgres.

Context — Supabase security advisor fired two CRITICALs:
  * rls_disabled_in_public      (any public table readable via the anon API)
  * sensitive_columns_exposed   (oauth_tokens / oauth_config = live creds)

Root cause: the app stores its data in Supabase Postgres but only ever talks
to it over a *direct* SQLAlchemy connection (DATABASE_URL, as the table-owner
`postgres` role). It never uses Supabase's auto-generated PostgREST/anon API,
and the frontend uses no supabase-js. Yet Supabase exposes every `public`
table over that API by default — so with RLS off, anyone holding the public
anon key could read oauth access/refresh tokens.

Fix: enable RLS (no policies) on every model table. PostgREST roles
(anon/authenticated) then get zero rows; the app's owner-role connection
bypasses non-forced RLS and is unaffected. SQLite (dev/CI) has no RLS → no-op.
"""
from __future__ import annotations

from sqlmodel import SQLModel, create_engine

from kwabo.db.session import _enforce_rls, _rls_statements


def test_rls_statements_are_noop_on_sqlite():
    assert _rls_statements("sqlite") == []


def test_rls_statements_cover_every_model_table_on_postgres():
    stmts = _rls_statements("postgresql")
    # One ENABLE-RLS per mapped table, nothing missed.
    assert len(stmts) == len(SQLModel.metadata.sorted_tables)
    assert all("ENABLE ROW LEVEL SECURITY" in s for s in stmts)
    # The sensitive credential tables in particular MUST be covered.
    joined = "\n".join(stmts)
    assert 'public."oauth_tokens"' in joined
    assert 'public."oauth_config"' in joined
    assert 'public."order_log"' in joined


def test_enforce_rls_is_noop_and_safe_on_sqlite():
    """Calling the enforcer against a SQLite engine must not raise and must
    leave the schema usable (no RLS dialect)."""
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    # Should be a clean no-op, never raising.
    _enforce_rls(eng)
