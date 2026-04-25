"""Mailbox connectie status + Microsoft Graph OAuth2 setup."""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from kwabo.config import settings
from kwabo.db.models import OAuthConfig, OAuthToken
from kwabo.db.session import engine
from kwabo.utils import utcnow
from kwabo.utils.logging import log

router = APIRouter(prefix="/api/mailbox", tags=["mailbox"])

# ephemere state-values (CSRF-bescherming) — in-memory is OK voor single-instance
_OAUTH_STATES: dict[str, float] = {}


# ---------- Pydantic schemas ----------


class MailboxStatus(BaseModel):
    mode: str  # file_drop | imap | graph
    connected: bool
    state: str  # active | degraded | error | not_configured
    message: str
    inbox_dir: Optional[str] = None
    inbox_pending: int = 0
    last_error: Optional[str] = None
    account_email: Optional[str] = None
    expires_at: Optional[datetime] = None


class OAuthConfigIn(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: Optional[str] = None  # leave empty to preserve existing
    redirect_uri: Optional[str] = None


class OAuthConfigOut(BaseModel):
    configured: bool
    tenant_id: str
    client_id: str
    has_secret: bool
    redirect_uri: str
    scopes: str


# ---------- Helpers ----------


def _get_config(session: Session) -> Optional[OAuthConfig]:
    return session.exec(select(OAuthConfig).where(OAuthConfig.id == 1)).first()


def _get_token(session: Session) -> Optional[OAuthToken]:
    return session.exec(select(OAuthToken).where(OAuthToken.id == 1)).first()


def _token_is_valid(tok: Optional[OAuthToken]) -> bool:
    if not tok or not tok.access_token:
        return False
    if not tok.expires_at:
        return True
    # make aware comparison robust
    exp = tok.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < exp - timedelta(seconds=30)


# ---------- Status ----------


@router.get("/status", response_model=MailboxStatus)
def get_status() -> MailboxStatus:
    mode = settings.email_mode
    if mode == "file_drop":
        inbox = Path(settings.inbox_dir).resolve()
        exists = inbox.exists()
        pending = len(list(inbox.glob("*.eml"))) if exists else 0
        return MailboxStatus(
            mode="file_drop",
            connected=exists,
            state="active" if exists else "error",
            message=(
                f"File-drop actief op {inbox}. {pending} .eml wacht op scan."
                if exists
                else f"Inbox-directory '{inbox}' bestaat niet."
            ),
            inbox_dir=str(inbox),
            inbox_pending=pending,
        )

    if mode == "graph":
        with Session(engine) as s:
            tok = _get_token(s)
        if _token_is_valid(tok):
            return MailboxStatus(
                mode="graph",
                connected=True,
                state="active",
                message=f"Graph verbonden als {tok.account_email or 'onbekend'}.",
                account_email=tok.account_email,
                expires_at=tok.expires_at,
            )
        if tok and tok.refresh_token:
            return MailboxStatus(
                mode="graph",
                connected=False,
                state="degraded",
                message="Access token verlopen — refresh nodig.",
                account_email=tok.account_email,
            )
        return MailboxStatus(
            mode="graph",
            connected=False,
            state="not_configured",
            message="Microsoft Graph-mode gekozen maar nog niet ingelogd. Klik 'Connect with Microsoft' op de E-mail-pagina.",
        )

    if mode == "imap":
        return MailboxStatus(
            mode="imap",
            connected=False,
            state="not_configured",
            message="IMAP-mode geselecteerd maar nog geen verbinding geconfigureerd.",
        )

    return MailboxStatus(
        mode=mode,
        connected=False,
        state="error",
        message=f"Onbekende EMAIL_MODE: {mode}",
    )


# ---------- Config endpoints ----------


@router.get("/oauth/config", response_model=OAuthConfigOut)
def get_oauth_config() -> OAuthConfigOut:
    with Session(engine) as s:
        cfg = _get_config(s)
    if not cfg:
        return OAuthConfigOut(
            configured=False,
            tenant_id="",
            client_id="",
            has_secret=False,
            redirect_uri="http://localhost:8000/api/mailbox/oauth/callback",
            scopes="offline_access Mail.Read User.Read",
        )
    return OAuthConfigOut(
        configured=bool(cfg.tenant_id and cfg.client_id),
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        has_secret=bool(cfg.client_secret),
        redirect_uri=cfg.redirect_uri,
        scopes=cfg.scopes,
    )


@router.put("/oauth/config", response_model=OAuthConfigOut)
def save_oauth_config(body: OAuthConfigIn) -> OAuthConfigOut:
    if not body.tenant_id.strip() or not body.client_id.strip():
        raise HTTPException(400, "tenant_id en client_id zijn verplicht")
    with Session(engine) as s:
        cfg = _get_config(s)
        if not cfg:
            cfg = OAuthConfig(id=1, provider="microsoft")
        cfg.tenant_id = body.tenant_id.strip()
        cfg.client_id = body.client_id.strip()
        if body.client_secret is not None and body.client_secret.strip():
            cfg.client_secret = body.client_secret.strip()
        if body.redirect_uri:
            cfg.redirect_uri = body.redirect_uri.strip()
        cfg.updated_at = utcnow()
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
    return OAuthConfigOut(
        configured=bool(cfg.tenant_id and cfg.client_id),
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        has_secret=bool(cfg.client_secret),
        redirect_uri=cfg.redirect_uri,
        scopes=cfg.scopes,
    )


# ---------- OAuth2 flow ----------


@router.get("/oauth/start")
def oauth_start(request: Request) -> RedirectResponse:
    with Session(engine) as s:
        cfg = _get_config(s)
    if not cfg or not cfg.tenant_id or not cfg.client_id:
        raise HTTPException(400, "OAuth2 nog niet geconfigureerd (vul tenant_id + client_id in)")

    state = secrets.token_urlsafe(24)
    _OAUTH_STATES[state] = time.time()
    # cleanup oude states (>10 min)
    cutoff = time.time() - 600
    for k in list(_OAUTH_STATES.keys()):
        if _OAUTH_STATES[k] < cutoff:
            _OAUTH_STATES.pop(k, None)

    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "response_mode": "query",
        "scope": cfg.scopes,
        "state": state,
        "prompt": "select_account",
    }
    url = (
        f"https://login.microsoftonline.com/{cfg.tenant_id}/oauth2/v2.0/authorize?"
        + urlencode(params)
    )
    log.info("oauth_start", tenant=cfg.tenant_id, client_id=cfg.client_id)
    return RedirectResponse(url, status_code=302)


def _callback_page(title: str, body_html: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang=\"nl\"><head><meta charset=\"utf-8\"><title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:560px;margin:80px auto;padding:24px;
color:#0f172a;background:#f8fafc}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;
box-shadow:0 1px 2px rgba(0,0,0,.04)}}h1{{font-size:20px;margin:0 0 8px}}
a.btn{{display:inline-block;background:#0f2744;color:#fff;padding:8px 16px;border-radius:6px;
text-decoration:none;font-weight:500;margin-top:12px}}
.err{{background:#fee2e2;border:1px solid #fecaca;color:#7f1d1d;padding:10px;border-radius:6px;
margin-top:12px;font-size:13px}}</style>
</head><body><div class=\"card\"><h1>{title}</h1>{body_html}
<a class=\"btn\" href=\"http://localhost:3000/email\">← Terug naar dashboard</a>
<script>setTimeout(function(){{location.href='http://localhost:3000/email?connected=1'}},1500)</script>
</div></body></html>"""
    return HTMLResponse(html)


@router.get("/oauth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
) -> HTMLResponse:
    if error:
        return _callback_page(
            "Microsoft login mislukt",
            f"<p>Microsoft retourneerde een fout:</p><div class=\"err\">{error}: {error_description or ''}</div>",
        )
    if not code or not state:
        return _callback_page(
            "Login mislukt",
            "<div class=\"err\">Geen code of state ontvangen van Microsoft.</div>",
        )
    if state not in _OAUTH_STATES:
        return _callback_page(
            "Login mislukt",
            "<div class=\"err\">State-mismatch (mogelijk verlopen of opnieuw gestart). Probeer opnieuw.</div>",
        )
    _OAUTH_STATES.pop(state, None)

    with Session(engine) as s:
        cfg = _get_config(s)
    if not cfg:
        return _callback_page("Fout", "<div class=\"err\">Config verdwenen.</div>")

    data = {
        "client_id": cfg.client_id,
        "scope": cfg.scopes,
        "code": code,
        "redirect_uri": cfg.redirect_uri,
        "grant_type": "authorization_code",
    }
    if cfg.client_secret:
        data["client_secret"] = cfg.client_secret

    token_url = f"https://login.microsoftonline.com/{cfg.tenant_id}/oauth2/v2.0/token"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(token_url, data=data)
    except httpx.HTTPError as e:
        return _callback_page(
            "Token-exchange mislukt",
            f"<div class=\"err\">Netwerkfout: {e}</div>",
        )

    if resp.status_code != 200:
        return _callback_page(
            "Token-exchange mislukt",
            f"<div class=\"err\">HTTP {resp.status_code} — {resp.text[:400]}</div>",
        )

    tok = resp.json()
    access_token = tok.get("access_token", "")
    refresh_token = tok.get("refresh_token", "")
    expires_in = int(tok.get("expires_in") or 3600)
    scope = tok.get("scope")

    # Ophalen van account-email via Graph
    account_email: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            me = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if me.status_code == 200:
                j = me.json()
                account_email = j.get("mail") or j.get("userPrincipalName")
    except httpx.HTTPError:
        pass

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    with Session(engine) as s:
        existing = _get_token(s)
        if not existing:
            existing = OAuthToken(id=1, provider="microsoft")
        existing.access_token = access_token
        existing.refresh_token = refresh_token or existing.refresh_token
        existing.expires_at = expires_at
        existing.scope = scope
        existing.account_email = account_email
        existing.updated_at = utcnow()
        s.add(existing)
        s.commit()

    log.info("oauth_connected", account=account_email, expires_in=expires_in)

    return _callback_page(
        "✅ Verbonden met Microsoft",
        f"<p>Ingelogd als <strong>{account_email or '(onbekend)'}</strong>. "
        f"Je wordt over een seconde teruggestuurd naar het dashboard.</p>",
    )


@router.post("/oauth/disconnect")
def oauth_disconnect() -> dict:
    with Session(engine) as s:
        tok = _get_token(s)
        if tok:
            s.delete(tok)
            s.commit()
    return {"ok": True}
