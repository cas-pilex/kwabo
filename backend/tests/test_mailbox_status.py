"""Tests voor de uitgebreide MailboxStatus + mail-poll observability.

Doel: bewijzen dat het dashboard kan zien of de poller daadwerkelijk draait
en wanneer de Graph-token het laatst is vernieuwd, zonder Railway-logs te
hoeven openen. Fase 1 (C-1.B/C) uit het productie-readiness plan.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from kwabo.config import settings
from kwabo.main import app
from kwabo.utils import mail_poll_status


@pytest.fixture(autouse=True)
def _reset_poll_status():
    mail_poll_status.reset_for_tests()
    yield
    mail_poll_status.reset_for_tests()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_off(monkeypatch):
    """Disable admin-gate so the status endpoint is reachable without a Bearer."""
    monkeypatch.setattr(settings, "admin_password", "")


def test_status_file_drop_includes_poll_observability_fields(
    client, admin_off, monkeypatch
):
    """In file_drop mode is `poll_enabled` false en zijn de last_poll_*
    velden None — maar de velden moeten WEL in de response staan zodat de
    UI ze kan renderen."""
    monkeypatch.setattr(settings, "email_mode", "file_drop")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 0)

    r = client.get("/api/mailbox/status")
    assert r.status_code == 200
    body = r.json()

    assert body["mode"] == "file_drop"
    # Observability fields present & correctly defaulted
    assert body["poll_interval_seconds"] == 0
    assert body["poll_enabled"] is False
    assert body["last_poll_at"] is None
    assert body["last_poll_status"] is None
    assert body["last_token_refresh_at"] is None


def test_status_graph_mode_with_poll_enabled_shows_poll_enabled_true(
    client, admin_off, monkeypatch
):
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 300)

    r = client.get("/api/mailbox/status")
    assert r.status_code == 200
    body = r.json()

    assert body["poll_interval_seconds"] == 300
    assert body["poll_enabled"] is True


def test_status_surfaces_last_successful_poll_tick(
    client, admin_off, monkeypatch
):
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 300)

    mail_poll_status.record_poll_tick(
        success=True, processed=3, errors=0, partial=False
    )

    r = client.get("/api/mailbox/status")
    assert r.status_code == 200
    body = r.json()

    assert body["last_poll_status"] == "ok"
    assert body["last_poll_processed"] == 3
    assert body["last_poll_errors"] == 0
    assert body["last_poll_partial"] is False
    assert body["last_poll_at"] is not None
    # Geen error-msg bij succes
    assert body["last_poll_error_msg"] is None


def test_status_surfaces_last_failed_poll_tick(client, admin_off, monkeypatch):
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 300)

    mail_poll_status.record_poll_tick(
        success=False, error_msg="ConnectError: graph.microsoft.com unreachable"
    )

    r = client.get("/api/mailbox/status")
    assert r.status_code == 200
    body = r.json()

    assert body["last_poll_status"] == "error"
    assert body["last_poll_error_msg"] == (
        "ConnectError: graph.microsoft.com unreachable"
    )


def test_status_surfaces_last_token_refresh(client, admin_off, monkeypatch):
    monkeypatch.setattr(settings, "email_mode", "graph")
    monkeypatch.setattr(settings, "mail_poll_interval_seconds", 300)

    mail_poll_status.record_token_refresh()

    r = client.get("/api/mailbox/status")
    assert r.status_code == 200
    body = r.json()

    assert body["last_token_refresh_at"] is not None


def test_poll_error_msg_is_truncated_to_300_chars():
    huge = "boom! " * 500
    mail_poll_status.record_poll_tick(success=False, error_msg=huge)
    snap = mail_poll_status.get_status()
    assert snap["last_poll_error_msg"] is not None
    assert len(snap["last_poll_error_msg"]) == 300


def test_record_poll_tick_overwrites_previous_state():
    mail_poll_status.record_poll_tick(success=False, error_msg="oude fout")
    mail_poll_status.record_poll_tick(success=True, processed=2, errors=0)
    snap = mail_poll_status.get_status()
    assert snap["last_poll_status"] == "ok"
    assert snap["last_poll_processed"] == 2
    # Error-msg uit de vorige (failed) tick wordt expliciet gewist op de
    # nieuwe success-tick. Anders blijft een spookfout-tekst hangen die
    # niet meer bij de huidige status hoort.
    assert snap["last_poll_error_msg"] is None


def test_reset_for_tests_clears_all_fields():
    mail_poll_status.record_poll_tick(success=True, processed=1, errors=0)
    mail_poll_status.record_token_refresh()
    mail_poll_status.reset_for_tests()
    snap = mail_poll_status.get_status()
    assert all(v is None for v in snap.values())
