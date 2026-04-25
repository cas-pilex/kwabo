"""Database session + init."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from kwabo.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


# Idempotent ALTER TABLE shim: SQLModel.metadata.create_all() does NOT add
# columns to tables that already exist. For new columns on existing tables we
# attempt an ALTER if the column is missing. New tables are handled normally
# by create_all(). Keep entries minimal — one per added column.
_ADDITIVE_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, type+default)
    ("klantenkaarten", "mixprijzen", "BOOLEAN NOT NULL DEFAULT 0"),
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
    with eng.begin() as conn:
        for table, column, decl in _ADDITIVE_MIGRATIONS:
            cols = _existing_columns(conn, table)
            if not cols:
                # Table doesn't exist yet — create_all() will materialize it
                # with the column already defined on the model.
                continue
            if column in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _apply_additive_migrations()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
