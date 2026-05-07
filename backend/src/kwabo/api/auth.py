"""Single-admin password gate.

Why this design:
  * One shared admin password (ADMIN_PASSWORD env var) — Cas distributes
    that to Kwabo personnel; once they're in, they can complete the
    Microsoft Graph OAuth flow at /email and process orders.
  * HMAC-signed bearer token. The frontend stores it in a same-origin
    cookie on the Vercel domain (`kwabo_admin`, non-HttpOnly so SSR pages
    can read it via `next/headers`); each fetch adds it as
    `Authorization: Bearer <token>`. We deliberately do NOT use a
    cross-origin Set-Cookie from Railway: that would land on the Railway
    domain and SSR pages on Vercel could never see it.
  * Token expires after JWT_TTL_HOURS (default 24h). No DB rows, no
    refresh tokens.
  * stdlib only. PyJWT for a shared-secret token is overkill.

Wire model:
  POST /api/auth/login {password}  → 200 {token, expires_at}
                                   → 401 on bad password
  GET  /api/auth/me                → 200 {ok: true, claims} (Bearer required)
                                   → 401 otherwise
  POST /api/auth/logout            → 200 {ok: true} (clientside cookie wipe)

Protection of the rest of the API:
  Every router that needs auth declares `dependencies=[Depends(require_admin)]`
  on its include. The exceptions wired in main.py are `/api/health`
  (Railway healthcheck) and `/api/auth/*` (login itself).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from kwabo.config import settings
from kwabo.utils.logging import log


COOKIE_NAME = "kwabo_admin"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = 4 - (len(data) % 4)
    if pad and pad != 4:
        data = data + ("=" * pad)
    return base64.urlsafe_b64decode(data)


def _sign(payload: dict, secret: str) -> str:
    """Compact HMAC-signed token: <b64payload>.<b64signature>.

    Not a JWT (no header, no algorithm field). For one shared secret with
    a single shared subject this is simpler and safer than rolling JWT.
    """
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return f"{_b64url_encode(raw)}.{_b64url_encode(sig)}"


def _verify(token: str, secret: str) -> Optional[dict]:
    """Validate a token and return its payload, or None on tamper/expiry."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None
    try:
        raw = _b64url_decode(body_b64)
        expected_sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        return None
    return payload


def issue_token() -> str:
    """Mint a new admin session token with TTL from settings."""
    payload = {
        "sub": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + (settings.jwt_ttl_hours * 3600),
    }
    return _sign(payload, settings.jwt_secret)


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_admin(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """FastAPI dependency: rejects with 401 unless the Authorization header
    carries a valid, unexpired admin token.

    Special-case: when ADMIN_PASSWORD is empty we treat the gate as OFF
    (development default). Tests run with the gate off because they
    don't set ADMIN_PASSWORD."""
    if not settings.admin_password:
        return {"sub": "admin", "auth_disabled": True}
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Niet ingelogd")
    payload = _verify(token, settings.jwt_secret)
    if not payload:
        raise HTTPException(status_code=401, detail="Sessie ongeldig of verlopen")
    return payload


# ------------------------------ HTTP layer ----------------------------------

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    ok: bool
    token: Optional[str] = None
    expires_at: Optional[int] = None


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    if not settings.admin_password:
        # Auth disabled (dev). Return a placeholder so the frontend can
        # still complete the flow; backend dependency short-circuits anyway.
        log.warning("admin_login_no_password_set")
        return LoginResponse(ok=True, token="dev-no-auth", expires_at=0)
    if not hmac.compare_digest(req.password, settings.admin_password):
        log.warning("admin_login_failed")
        raise HTTPException(status_code=401, detail="Ongeldig wachtwoord")
    token = issue_token()
    payload = _verify(token, settings.jwt_secret) or {}
    log.info("admin_login_ok")
    return LoginResponse(
        ok=True,
        token=token,
        expires_at=int(payload.get("exp", 0)),
    )


@router.post("/logout")
def logout() -> dict:
    # Token revocation is client-side (cookie wipe). HMAC-signed tokens
    # without a stored allowlist can't be revoked server-side without
    # introducing a denylist; the short TTL is the mitigation.
    return {"ok": True}


@router.get("/me")
def me(claims: dict = Depends(require_admin)) -> dict:
    return {"ok": True, "claims": claims}
