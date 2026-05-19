"""Tests voor de mailbox-router: OAuth callback moet publiek bereikbaar zijn
(Microsoft kan geen Bearer token meesturen), maar de overige mailbox-endpoints
blijven achter het admin-gate. En _callback_page mag geen hardcoded
localhost:3000 bevatten — productie-frontend zit op een andere URL.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from kwabo.config import settings
from kwabo.db.models import OAuthConfig
from kwabo.db.session import engine
from kwabo.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def password_set(monkeypatch):
    """Activeer het admin-gate zoals in productie op Railway."""
    monkeypatch.setattr(settings, "admin_password", "test-pw")
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret")


# --- OAuth callback moet publiek zijn -------------------------------------


def test_oauth_callback_with_error_param_no_auth_returns_200(client, password_set):
    """Microsoft redirect met error-param mag geen 401 geven — de gebruiker
    moet de foutpagina kunnen zien."""
    r = client.get(
        "/api/mailbox/oauth/callback",
        params={"error": "access_denied", "error_description": "user cancelled"},
    )
    assert r.status_code == 200, (
        f"verwacht 200 (foutpagina HTML), kreeg {r.status_code}: {r.text[:200]}"
    )
    assert "Microsoft login mislukt" in r.text


def test_oauth_callback_missing_code_no_auth_returns_200(client, password_set):
    """Callback zonder code/state moet HTML-foutpagina tonen, geen 401."""
    r = client.get("/api/mailbox/oauth/callback")
    assert r.status_code == 200
    assert "Geen code of state" in r.text or "Login mislukt" in r.text


def test_oauth_callback_bad_state_no_auth_returns_200(client, password_set):
    """State-mismatch geeft HTML-foutpagina, niet 401."""
    r = client.get(
        "/api/mailbox/oauth/callback",
        params={"code": "abc", "state": "never-issued"},
    )
    assert r.status_code == 200
    assert "State-mismatch" in r.text or "Login mislukt" in r.text


# --- /oauth/start moet ook publiek zijn (Microsoft sluit OAuth-flow) -------


def test_oauth_start_no_auth_no_config_returns_400_not_401(client, password_set):
    """Zonder config: 400 (config ontbreekt) — maar in elk geval NIET 401.

    De /oauth/start route initieert de Microsoft-flow; de gebruiker komt
    daar via browser-redirect en kan geen Bearer token meesturen.
    """
    # Zorg dat er geen config in de DB staat
    with Session(engine) as s:
        cfg = s.get(OAuthConfig, 1)
        if cfg:
            s.delete(cfg)
            s.commit()

    r = client.get("/api/mailbox/oauth/start", follow_redirects=False)
    assert r.status_code == 400, (
        f"verwacht 400 (config ontbreekt), kreeg {r.status_code}"
    )


def test_oauth_start_no_auth_with_config_redirects_to_microsoft(
    client, password_set
):
    """Met config: 302 redirect naar login.microsoftonline.com — geen 401."""
    with Session(engine) as s:
        cfg = s.get(OAuthConfig, 1)
        if not cfg:
            cfg = OAuthConfig(
                id=1,
                provider="microsoft",
                tenant_id="tenant-xyz",
                client_id="client-xyz",
                client_secret="secret",
                redirect_uri="https://example.com/api/mailbox/oauth/callback",
            )
            s.add(cfg)
        else:
            cfg.tenant_id = "tenant-xyz"
            cfg.client_id = "client-xyz"
            cfg.redirect_uri = "https://example.com/api/mailbox/oauth/callback"
            s.add(cfg)
        s.commit()

    r = client.get("/api/mailbox/oauth/start", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers.get("location", "")
    assert "login.microsoftonline.com" in location, (
        f"verwacht Microsoft login URL, kreeg: {location}"
    )


# --- Andere mailbox endpoints blijven beschermd ----------------------------


def test_mailbox_status_no_auth_still_returns_401(client, password_set):
    """Regressie-check: /status mag NIET publiek worden als gevolg van de
    router-split — alleen /oauth/start en /oauth/callback zijn publiek."""
    r = client.get("/api/mailbox/status")
    assert r.status_code == 401


def test_oauth_config_get_no_auth_still_returns_401(client, password_set):
    """Regressie-check: /oauth/config blijft beschermd (bevat secrets)."""
    r = client.get("/api/mailbox/oauth/config")
    assert r.status_code == 401


def test_oauth_disconnect_no_auth_still_returns_401(client, password_set):
    """Regressie-check: disconnect blijft beschermd."""
    r = client.post("/api/mailbox/oauth/disconnect")
    assert r.status_code == 401


# --- _callback_page gebruikt settings.frontend_url, niet hardcoded localhost ---


def test_callback_page_uses_frontend_url_from_settings(client, monkeypatch):
    """De HTML callback-pagina moet de geconfigureerde frontend_url
    gebruiken, niet hardcoded http://localhost:3000."""
    monkeypatch.setattr(settings, "frontend_url", "https://kwabo-pilex.vercel.app")
    r = client.get(
        "/api/mailbox/oauth/callback",
        params={"error": "x", "error_description": "test"},
    )
    assert r.status_code == 200
    assert "https://kwabo-pilex.vercel.app/email" in r.text
    # En geen hardcoded localhost referentie meer
    assert "http://localhost:3000/email" not in r.text


def test_callback_page_default_frontend_url_is_localhost_for_dev(
    client, monkeypatch
):
    """In dev (geen FRONTEND_URL env): default blijft localhost:3000 zodat
    bestaande dev-flow werkt."""
    monkeypatch.setattr(settings, "frontend_url", "http://localhost:3000")
    r = client.get(
        "/api/mailbox/oauth/callback",
        params={"error": "x", "error_description": "test"},
    )
    assert r.status_code == 200
    assert "http://localhost:3000/email" in r.text
