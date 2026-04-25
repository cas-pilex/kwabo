"""Database session + init."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from kwabo.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


# Idempotent ALTER TABLE shim: SQLModel.metadata.create_all() does NOT add
# columns to tables that already exist. For new columns on existing tables we
# attempt an ALTER and swallow "duplicate column" errors. New tables are
# handled normally by create_all(). Keep entries minimal — one per added column.
_ADDITIVE_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, type+default)
    ("klantenkaarten", "mixprijzen", "BOOLEAN NOT NULL DEFAULT 0"),
]


def _apply_additive_migrations() -> None:
    with engine.begin() as conn:
        for table, column, decl in _ADDITIVE_MIGRATIONS:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))
            except Exception as exc:  # noqa: BLE001
                # SQLite raises OperationalError "duplicate column name: <col>";
                # other backends raise similar messages. We only swallow that
                # specific class — anything else should still surface.
                msg = str(exc).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    continue
                raise


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _apply_additive_migrations()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
