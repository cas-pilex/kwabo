"""Fase 5: multi-worker poll-guard tests.

De `_mail_poll_loop` taak draait per Python-proces; in een Gunicorn-style
multi-worker setup (WEB_CONCURRENCY>1) zou hij N keer parallel de Graph-
mailbox raken. We willen daar luid voor waarschuwen en de spawn skippen.
"""
from __future__ import annotations

import asyncio
import logging
import time

import pytest
from fastapi.testclient import TestClient

from kwabo.config import settings
from kwabo.main import POLLER_BOOT_GRACE_SECONDS, app


@pytest.fixture
def admin_off(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")


def test_lifespan_skips_poll_when_web_concurrency_gt_1(
    monkeypatch, admin_off, caplog
):
    """Met WEB_CONCURRENCY=2 en email_mode=graph + interval=300 moet de
    lifespan een 'mail_poll_skipped_multi_worker' log emit en GEEN
    poll-task spawnen."""
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 300)

    spawned = {"n": 0}
    orig_create_task = asyncio.create_task

    def tracking_create_task(coro, *args, **kwargs):
        # Detecteer of het de _mail_poll_loop coroutine is.
        cname = getattr(coro, "__qualname__", "") or str(coro)
        if "_mail_poll_loop" in cname:
            spawned["n"] += 1
        return orig_create_task(coro, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", tracking_create_task)

    # TestClient triggert de lifespan-context op enter.
    with caplog.at_level(logging.WARNING):
        with TestClient(app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200

    assert spawned["n"] == 0, "poll-task gespawned ondanks WEB_CONCURRENCY=2"


def test_lifespan_spawns_poll_when_web_concurrency_1(
    monkeypatch, admin_off
):
    """Met WEB_CONCURRENCY=1 (default single-worker) moet de poll-task
    WEL gespawned worden als email_mode=graph + interval>=30."""
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 300)

    spawned = {"n": 0}
    orig_create_task = asyncio.create_task

    def tracking_create_task(coro, *args, **kwargs):
        cname = getattr(coro, "__qualname__", "") or str(coro)
        if "_mail_poll_loop" in cname:
            spawned["n"] += 1
        return orig_create_task(coro, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", tracking_create_task)

    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200

    assert spawned["n"] == 1


def test_lifespan_no_poll_when_interval_zero(monkeypatch, admin_off):
    """Default (interval=0): geen poll-task, ongeacht WEB_CONCURRENCY."""
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 0)

    spawned = {"n": 0}
    orig_create_task = asyncio.create_task

    def tracking_create_task(coro, *args, **kwargs):
        cname = getattr(coro, "__qualname__", "") or str(coro)
        if "_mail_poll_loop" in cname:
            spawned["n"] += 1
        return orig_create_task(coro, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", tracking_create_task)

    with TestClient(app) as client:
        client.get("/api/health")

    assert spawned["n"] == 0


# ---------------------------------------------------------------------------
# /api/health poller-liveness (fail-open). Railway auto-restarts on 503.
# We drive app.state directly so the test is independent of a real poller.
# ---------------------------------------------------------------------------


class _StubTask:
    """Minimal stand-in for an asyncio.Task — health only calls .done()."""

    def __init__(self, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


@pytest.fixture
def health_client(monkeypatch, admin_off):
    """A client whose lifespan does NOT spawn a real poller (file_drop), so
    we can set app.state.poll_task to a controlled stub per test."""
    monkeypatch.setattr(settings, "email_mode", "file_drop")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 0)
    with TestClient(app) as client:
        yield client


def test_health_ok_when_poller_not_expected(health_client):
    """poll_task is None (poller never expected) → 200, never 503."""
    app.state.poll_task = None
    r = health_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["poller"] == "not_running"


def test_health_ok_when_poller_alive(health_client):
    """Running poll task → 200."""
    app.state.poll_task = _StubTask(done=False)
    app.state.poll_boot_monotonic = time.monotonic() - (POLLER_BOOT_GRACE_SECONDS + 100)
    r = health_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["poller"] == "alive"


def test_health_ok_when_task_dead_within_grace(health_client):
    """A dead task during the boot grace must NOT flap to 503."""
    app.state.poll_task = _StubTask(done=True)
    app.state.poll_boot_monotonic = time.monotonic()  # fresh boot
    r = health_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["poller"] == "starting"


def test_health_503_when_task_dead_past_grace(health_client):
    """The one auto-heal case: poller was expected, task crashed, past grace."""
    app.state.poll_task = _StubTask(done=True)
    app.state.poll_boot_monotonic = time.monotonic() - (POLLER_BOOT_GRACE_SECONDS + 100)
    r = health_client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["poller"] == "dead"
