"""Database session + init."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from kwabo.config import settings


def _build_engine(url: str) -> Engine:
    """Engine factory with dialect-specific knobs.

    sqlite — share connection across threads (FastAPI dev server).
    postgres on Supabase pgbouncer (port 6543, transaction mode) — keep a
        CLIENT-SIDE connection pool. The app is a long-running Railway process,
        so reusing the app->bouncer connection avoids a fresh TCP+TLS+auth
        handshake on every request (that NullPool tax was ~1.3s per DB call in
        production). pgbouncer still pools server connections per transaction;
        the only requirement for transaction mode is no server-side prepared
        statements (prepare_threshold=None). pool_pre_ping validates a pooled
        connection before use so a bouncer-dropped socket is transparently
        replaced instead of erroring.
    """
    if url.startswith("sqlite"):
        return create_engine(url, echo=False, connect_args={"check_same_thread": False})
    if url.startswith("postgresql") or url.startswith("postgres"):
        return create_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
            connect_args={"prepare_threshold": None},
        )
    return create_engine(url, echo=False)


engine = _build_engine(settings.database_url)


# Per-dialect SQL fragments — `BOOLEAN DEFAULT 0` is SQLite syntax; Postgres
# wants `FALSE`. Add a row per (table, column) — the helper picks the right
# fragment based on the active dialect.
_ADDITIVE_MIGRATIONS: list[tuple[str, str, dict[str, str]]] = [
    (
        "klantenkaarten",
        "mixprijzen",
        {
            "sqlite": "BOOLEAN NOT NULL DEFAULT 0",
            "postgresql": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
    ),
    # Fase 3 (E1): NAV Item "Sales Unit of Measure" — sturend voor de
    # Branch-A-eenheidskeuze. Nullable; de master-sync vult hem.
    (
        "artikelkaarten",
        "verkoop_eenheid",
        {"sqlite": "VARCHAR", "postgresql": "VARCHAR"},
    ),
]


def _existing_columns(conn, table: str) -> set[str]:
    """Return the set of column names on `table`, or empty set if the table
    does not exist. Uses PRAGMA on SQLite, falls back to information_schema
    on other backends."""
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def _apply_additive_migrations(target_engine: Optional[Engine] = None) -> None:
    """Add new columns to existing tables on already-deployed DBs.

    Idempotent: skips columns that already exist (PRAGMA / information_schema
    pre-check). Skips entirely if the table itself doesn't exist yet — that
    means it'll be created by `create_all()` with the column already in place.
    """
    eng = target_engine if target_engine is not None else engine
    dialect = eng.dialect.name
    with eng.begin() as conn:
        for table, column, decl_by_dialect in _ADDITIVE_MIGRATIONS:
            cols = _existing_columns(conn, table)
            if not cols:
                # Table doesn't exist yet — create_all() will materialize it
                # with the column already defined on the model.
                continue
            if column in cols:
                continue
            decl = decl_by_dialect.get(dialect)
            if decl is None:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))


def _rls_statements(dialect_name: str) -> list[str]:
    """ALTER TABLE ... ENABLE ROW LEVEL SECURITY for every mapped table.

    Postgres-only. Supabase auto-exposes every ``public`` table over its
    PostgREST/anon API; with RLS off and a *public* anon key, anyone could read
    sensitive rows (e.g. ``oauth_tokens`` access/refresh tokens). This app never
    uses that API — it talks to Postgres over a direct SQLAlchemy connection as
    the table-owner ``postgres`` role, and the frontend hits only the FastAPI
    backend. Enabling RLS with **no policies** therefore denies the anon API
    (zero rows) while the owner connection — which bypasses non-forced RLS —
    keeps full read/write. SQLite has no RLS, so this is a no-op there.
    """
    if dialect_name != "postgresql":
        return []
    return [
        f'ALTER TABLE public."{table.name}" ENABLE ROW LEVEL SECURITY'
        for table in SQLModel.metadata.sorted_tables
    ]


def _enforce_rls(target_engine: Optional[Engine] = None) -> None:
    """Lock the PostgREST API for every table by enabling RLS (idempotent).

    Defensive by design: each ALTER runs in its own transaction and a failure
    (e.g. the connecting role doesn't own a table) is logged and skipped —
    a security-hardening step must never take the app down on boot.
    """
    eng = target_engine if target_engine is not None else engine
    stmts = _rls_statements(eng.dialect.name)
    if not stmts:
        return
    from kwabo.utils.logging import log

    for stmt in stmts:
        try:
            with eng.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001
            log.warning("rls_enable_failed", stmt=stmt, error=str(exc))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _apply_additive_migrations()
    _enforce_rls()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
