"""Microsoft Graph email client.

Lists unread messages from the authenticated user's Inbox via Microsoft
Graph and returns them as `RawEmail` objects parsed from raw MIME, so the
rest of the pipeline (attachments, PDF extraction, classification) is
identical to the file-drop path.

OAuth plumbing lives in `kwabo.api.mailbox`. This module reads the stored
`OAuthToken` and `OAuthConfig` rows, refreshes the access token when
needed, then talks to Graph.

Required Graph scopes:
  - `Mail.ReadWrite` (read inbox + PATCH isRead on mark_seen)
  - `User.Read`     (account_email shown in status)
  - `offline_access` (refresh_token)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from kwabo.integrations.email_client import RawEmail, parse_eml_bytes
from kwabo.utils import utcnow
from kwabo.utils.logging import log

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
LIST_PAGE_SIZE = 50  # unread messages fetched per scan


class GraphEmailClient:
    """EmailClient implementation backed by Microsoft Graph."""

    def __init__(self, token: Any | None = None) -> None:
        self._token = token if token is not None else self._load_token()

    @staticmethod
    def _load_token() -> Any | None:
        try:
            from sqlmodel import Session, select

            from kwabo.db.models import OAuthToken
            from kwabo.db.session import engine
        except Exception:  # noqa: BLE001
            return None
        try:
            with Session(engine) as s:
                return s.exec(select(OAuthToken).limit(1)).first()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _load_config() -> Any | None:
        try:
            from sqlmodel import Session, select

            from kwabo.db.models import OAuthConfig
            from kwabo.db.session import engine

            with Session(engine) as s:
                return s.exec(select(OAuthConfig).limit(1)).first()
        except Exception:  # noqa: BLE001
            return None

    def _access_token(self) -> str:
        """Return a valid access token, refreshing on the fly when expired."""
        tok = self._token
        if tok is None or not tok.access_token:
            raise RuntimeError(
                "GraphEmailClient: geen OAuth token aanwezig. Ga naar "
                "/api/mailbox/oauth/start in het dashboard om in te loggen."
            )
        if self._is_expired(tok):
            self._refresh_token()
            tok = self._token
            if tok is None or not tok.access_token:
                raise RuntimeError(
                    "GraphEmailClient: token-refresh mislukt. Log opnieuw in via /email."
                )
        return tok.access_token

    @staticmethod
    def _is_expired(tok: Any) -> bool:
        if not tok.expires_at:
            return False
        exp = tok.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= exp - timedelta(seconds=30)

    def _refresh_token(self) -> None:
        cfg = self._load_config()
        tok = self._token
        if not cfg or not cfg.tenant_id or not cfg.client_id:
            raise RuntimeError("OAuth-config (tenant/client) ontbreekt — kan niet refreshen.")
        if not tok or not tok.refresh_token:
            raise RuntimeError("Geen refresh_token opgeslagen — log opnieuw in via /email.")

        data = {
            "client_id": cfg.client_id,
            "scope": cfg.scopes,
            "refresh_token": tok.refresh_token,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "refresh_token",
        }
        if cfg.client_secret:
            data["client_secret"] = cfg.client_secret

        url = f"https://login.microsoftonline.com/{cfg.tenant_id}/oauth2/v2.0/token"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, data=data)
        if resp.status_code != 200:
            log.warning("graph_token_refresh_failed", status=resp.status_code, body=resp.text[:300])
            raise RuntimeError(f"Token refresh failed (HTTP {resp.status_code}): {resp.text[:200]}")
        body = resp.json()

        new_access = body.get("access_token", "")
        new_refresh = body.get("refresh_token") or tok.refresh_token
        expires_in = int(body.get("expires_in") or 3600)
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Persist
        try:
            from sqlmodel import Session, select

            from kwabo.db.models import OAuthToken
            from kwabo.db.session import engine

            with Session(engine) as s:
                row = s.exec(select(OAuthToken).limit(1)).first()
                if not row:
                    row = OAuthToken(id=1, provider="microsoft")
                row.access_token = new_access
                row.refresh_token = new_refresh
                row.expires_at = new_expires_at
                if body.get("scope"):
                    row.scope = body["scope"]
                row.updated_at = utcnow()
                s.add(row)
                s.commit()
                s.refresh(row)
                self._token = row
        except Exception as e:  # noqa: BLE001
            # Update in-memory token at least, so the current scan can proceed.
            log.warning("graph_token_persist_failed", error=str(e))
            tok.access_token = new_access
            tok.refresh_token = new_refresh
            tok.expires_at = new_expires_at
            self._token = tok

        log.info("graph_token_refreshed", expires_in=expires_in)

    # ---------- EmailClient protocol ----------

    def list_new(self) -> list[RawEmail]:
        access = self._access_token()
        headers = {"Authorization": f"Bearer {access}"}

        list_url = (
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages"
            f"?$filter=isRead eq false"
            f"&$select=id,subject,from,receivedDateTime"
            f"&$top={LIST_PAGE_SIZE}"
            f"&$orderby=receivedDateTime asc"
        )

        emails: list[RawEmail] = []
        with httpx.Client(timeout=60.0, headers=headers) as client:
            list_resp = client.get(list_url)
            if list_resp.status_code == 401:
                # Token might have just expired between our check and the call; one retry.
                self._refresh_token()
                client.headers["Authorization"] = f"Bearer {self._token.access_token}"
                list_resp = client.get(list_url)
            list_resp.raise_for_status()
            messages = list_resp.json().get("value", [])
            log.info("graph_list_unread", count=len(messages))

            for m in messages:
                msg_id = m.get("id")
                if not msg_id:
                    continue
                try:
                    raw_resp = client.get(f"{GRAPH_BASE}/me/messages/{msg_id}/$value")
                    raw_resp.raise_for_status()
                    raw = raw_resp.content  # bytes — RFC 822 MIME
                    em = parse_eml_bytes(raw, email_id=msg_id, source_path=f"graph://{msg_id}")
                    emails.append(em)
                except httpx.HTTPError as e:
                    log.warning(
                        "graph_message_fetch_failed",
                        message_id=msg_id,
                        error=str(e),
                    )
                    continue

        return emails

    def mark_seen(self, email_id: str) -> None:
        access = self._access_token()
        headers = {
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
        }
        url = f"{GRAPH_BASE}/me/messages/{email_id}"
        with httpx.Client(timeout=30.0, headers=headers) as client:
            resp = client.patch(url, json={"isRead": True})
            if resp.status_code == 403:
                log.warning(
                    "graph_mark_seen_forbidden",
                    message_id=email_id,
                    hint="App registration mist Mail.ReadWrite scope — voeg toe in Azure en re-consent.",
                )
                return
            if resp.status_code >= 400:
                log.warning(
                    "graph_mark_seen_failed",
                    message_id=email_id,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
