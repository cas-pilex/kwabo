"""Regressie: de Postgres-engine MOET client-side connecties poolen.

Met poolclass=NullPool opende élke request een verse connectie naar de remote
Supabase-pooler (TCP+TLS+pgbouncer-auth) en gooide die daarna weg → een vaste
~1,3s setup-tax op ELKE DB-endpoint (live gemeten 31-05-2026: DB-endpoints ~1,67s
vs non-DB ~0,3s, geen warmup). De app is een persistent Railway-proces, dus een
client-side pool hergebruikt de connectie en elimineert die tax. Transaction-mode
pgbouncer blijft compatibel zolang server-side prepared statements uit staan
(prepare_threshold=None).
"""
from __future__ import annotations

from sqlalchemy.pool import NullPool, QueuePool

from kwabo.db.session import _build_engine

PG_URL = "postgresql+psycopg://u:p@db.example.supabase.com:6543/postgres"


def test_postgres_engine_pools_connections():
    eng = _build_engine(PG_URL)
    assert not isinstance(eng.pool, NullPool), "NullPool = verse connectie per request = ~1,3s tax"
    assert isinstance(eng.pool, QueuePool)


def test_postgres_engine_uses_pre_ping():
    # Pre-ping valideert (mogelijk verbroken) connecties door de bouncer heen.
    eng = _build_engine(PG_URL)
    assert eng.pool._pre_ping is True


def test_sqlite_engine_unchanged():
    # SQLite-pad (dev/test) blijft ongewijzigd werken.
    eng = _build_engine("sqlite:///:memory:")
    assert eng is not None
