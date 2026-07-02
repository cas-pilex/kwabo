"""Startup-lock-hardening (prod-incident 2-7-2026).

`init_db()` hing de hele Railway-deploy: `_enforce_rls` vroeg bij ELKE boot
voor élke tabel een AccessExclusiveLock aan (`ALTER TABLE ... ENABLE ROW
LEVEL SECURITY`), zónder precheck en zónder lock_timeout. Eén stale
'idle in transaction'-sessie (van 26-6, via het Supabase-dashboard) hield een
share-lock op order_log → de ALTER wachtte oneindig → healthcheck-kill →
crash-loop, terwijl elke nieuwe boot wéér een exclusieve lock-aanvraag in de
wachtrij zette die ook alle gewone queries blokkeerde.

Contract na de fix:
  1. alleen tabellen waar RLS nog NIET aan staat krijgen een ALTER
     (relrowsecurity-precheck) — een normale boot vraagt dus nul locks aan;
  2. elke DDL-verbinding zet eerst een lock_timeout, zodat een geblokkeerde
     ALTER faalt-en-logt in plaats van de boot te hangen (de bestaande
     try/except vangt hem — "hardening mag de app nooit down houden").
"""
from __future__ import annotations

from kwabo.db.session import _enforce_rls, _rls_statements


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, engine):
        self.engine = engine

    def execute(self, clause, *a, **k):
        sql = str(clause)
        self.engine.executed.append(sql)
        if "relrowsecurity" in sql:
            return _FakeResult([(t,) for t in self.engine.pending])
        return _FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeEngine:
    def __init__(self, pending):
        self.pending = pending          # tabellen zonder RLS
        self.executed: list[str] = []

        class _D:  # noqa: N801
            name = "postgresql"

        self.dialect = _D()

    def connect(self):
        return _FakeConn(self)

    def begin(self):
        return _FakeConn(self)


def test_rls_statements_alleen_voor_pending_tabellen():
    """Precheck: tabellen die al RLS hebben krijgen géén ALTER (= geen
    exclusieve lock-aanvraag bij een normale boot)."""
    stmts = _rls_statements("postgresql", pending={"order_log"})
    assert stmts == ['ALTER TABLE public."order_log" ENABLE ROW LEVEL SECURITY']
    assert _rls_statements("postgresql", pending=set()) == []
    assert _rls_statements("sqlite", pending={"order_log"}) == []


def test_enforce_rls_prechecks_en_zet_lock_timeout():
    eng = _FakeEngine(pending={"order_log"})
    _enforce_rls(target_engine=eng)
    joined = "\n".join(eng.executed)
    # 1. precheck-query gedraaid
    assert "relrowsecurity" in joined
    # 2. alleen de pending tabel ge-ALTER-d
    alters = [s for s in eng.executed if s.startswith("ALTER TABLE")]
    assert alters == ['ALTER TABLE public."order_log" ENABLE ROW LEVEL SECURITY']
    # 3. lock_timeout gezet vóór de ALTER (hang -> nette fout i.p.v. boot-hang)
    idx_timeout = next(i for i, s in enumerate(eng.executed) if "lock_timeout" in s)
    idx_alter = next(i for i, s in enumerate(eng.executed) if s.startswith("ALTER TABLE"))
    assert idx_timeout < idx_alter


def test_enforce_rls_geen_pending_geen_alters():
    eng = _FakeEngine(pending=set())
    _enforce_rls(target_engine=eng)
    assert not [s for s in eng.executed if s.startswith("ALTER TABLE")]
