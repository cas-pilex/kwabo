"""Regressie: /api/logs/stream authenticeert via ?token= (EventSource kan geen
Authorization-header sturen). Voorheen zat /stream achter de globale Bearer-gate
-> de browser kreeg 401 en de /logs-pagina bleef leeg. Nu: ongated router met
in-handler HMAC-verify van de query-token (of Bearer-header), zelfde secret als
require_admin. Ontdekt 31-05-2026. [[logs-pagina-401-geen-auth]]
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from kwabo.api.auth import issue_token
from kwabo.api.logs import _authorize_stream
from kwabo.config import settings


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "geheim", raising=False)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret", raising=False)


def test_valid_query_token_passes(auth_on):
    tok = issue_token()
    _authorize_stream(tok, None)  # geen exception = ok


def test_valid_bearer_header_passes(auth_on):
    tok = issue_token()
    _authorize_stream(None, f"Bearer {tok}")


def test_missing_token_rejected(auth_on):
    with pytest.raises(HTTPException) as exc:
        _authorize_stream(None, None)
    assert exc.value.status_code == 401


def test_garbage_token_rejected(auth_on):
    with pytest.raises(HTTPException):
        _authorize_stream("niet-een-geldige-token", None)


def test_gate_off_when_no_admin_password(monkeypatch):
    # dev/test: ADMIN_PASSWORD leeg -> stream open (zoals require_admin).
    monkeypatch.setattr(settings, "admin_password", "", raising=False)
    _authorize_stream(None, None)  # geen exception
