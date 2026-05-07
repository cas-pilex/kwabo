"""Tests for the email-client factory and the GraphEmailClient stub.

Plumbing for go-live: switching to a real Microsoft Graph mailbox should be
a config flip (`EMAIL_MODE=graph`) plus credentials, not a code change. This
test pins the factory's mode dispatch and the stub's failure behaviour
(clear, actionable error rather than a mysterious AttributeError when
list_new() is invoked without OAuth setup).
"""
from __future__ import annotations

import pytest

from kwabo.integrations.email_client import (
    FileDropEmailClient,
    get_email_client,
)
from kwabo.integrations.email_client_graph import GraphEmailClient


def test_factory_returns_filedrop_for_file_drop_mode(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "file_drop")
    # Force settings re-read so the factory picks up the env override.
    from kwabo import config as cfg
    monkeypatch.setattr(cfg.settings, "email_mode", "file_drop")
    client = get_email_client()
    assert isinstance(client, FileDropEmailClient)


def test_factory_returns_graph_stub_for_graph_mode(monkeypatch):
    from kwabo import config as cfg
    monkeypatch.setattr(cfg.settings, "email_mode", "graph")
    client = get_email_client()
    assert isinstance(client, GraphEmailClient)


def test_factory_raises_for_imap_mode_until_implemented(monkeypatch):
    """IMAP plumbing is not built yet; the factory must say so loudly rather
    than silently fall back to a different client."""
    from kwabo import config as cfg
    monkeypatch.setattr(cfg.settings, "email_mode", "imap")
    with pytest.raises(NotImplementedError, match="EMAIL_MODE=imap"):
        get_email_client()


def test_factory_raises_for_unknown_mode(monkeypatch):
    from kwabo import config as cfg
    monkeypatch.setattr(cfg.settings, "email_mode", "smoke-signal")
    with pytest.raises(ValueError, match="Unknown EMAIL_MODE"):
        get_email_client()


def test_graph_stub_list_new_raises_clear_error_without_token():
    """Without an OAuth token row in the DB, list_new() must surface a clear
    error pointing the operator at the OAuth flow — not a confusing
    AttributeError or 401 from Graph."""
    client = GraphEmailClient(token=None)
    with pytest.raises(RuntimeError, match=r"oauth|OAuth"):
        client.list_new()


def test_graph_mark_seen_without_token_raises_clear_oauth_error():
    """mark_seen is implemented but, without a token row, must surface the
    same actionable OAuth error as list_new — never a confusing AttributeError."""
    client = GraphEmailClient(token=None)
    with pytest.raises(RuntimeError, match=r"oauth|OAuth"):
        client.mark_seen("any-id")
