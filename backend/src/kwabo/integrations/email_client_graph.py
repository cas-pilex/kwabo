"""Microsoft Graph email client (stub).

Plumbing for go-live: the OAuth2 plumbing already exists in
`kwabo.api.mailbox` — token storage, /api/mailbox/oauth/start, callback. What
remains is the actual `list_new()` call against Graph
(`/v1.0/me/mailFolders/inbox/messages?$filter=isRead eq false`) and a
`mark_seen()` that flips `isRead` to true. We deliberately ship a stub
right now because we don't want to depend on a live tenant for the test
suite. The factory wiring + clear error messages are in place so
`EMAIL_MODE=graph` is a config flip away from working once the operator
runs the OAuth flow and the implementation is filled in.

The stub fails loudly via `RuntimeError` (no token) or `NotImplementedError`
(method body) so a misconfigured deployment surfaces immediately rather
than silently doing nothing.
"""
from __future__ import annotations

from typing import Any

from kwabo.integrations.email_client import RawEmail


class GraphEmailClient:
    """Stub implementing the EmailClient protocol.

    Today: every call raises with a clear, actionable message. Tomorrow: the
    method bodies hit Microsoft Graph using the OAuthToken stored by the
    OAuth2 callback in `kwabo.api.mailbox`.
    """

    def __init__(self, token: Any | None = None) -> None:
        self._token = token if token is not None else self._load_token()

    @staticmethod
    def _load_token() -> Any | None:
        """Best-effort load of the persisted OAuthToken row.

        Returns None when no token is available — the caller (`list_new`)
        translates that into a clear runtime error pointing the operator
        at the OAuth setup flow."""
        try:
            from sqlmodel import Session, select

            from kwabo.db.models import OAuthToken
            from kwabo.db.session import engine
        except Exception:  # noqa: BLE001 — DB optional during early bootstrap
            return None
        try:
            with Session(engine) as s:
                row = s.exec(select(OAuthToken).limit(1)).first()
                return row
        except Exception:  # noqa: BLE001 — schema may not exist yet
            return None

    def list_new(self) -> list[RawEmail]:
        if self._token is None:
            raise RuntimeError(
                "GraphEmailClient requires OAuth setup. Visit "
                "/api/mailbox/oauth/start in the dashboard to authenticate, "
                "then retry. (See docs: oauth.md)"
            )
        raise NotImplementedError(
            "GraphEmailClient.list_new is a stub. Implementation pending — "
            "fill in the Microsoft Graph fetch using self._token.access_token "
            "and parse responses with parse_eml_bytes()."
        )

    def mark_seen(self, email_id: str) -> None:
        raise NotImplementedError(
            "GraphEmailClient.mark_seen is a stub. Implementation pending — "
            "PATCH /v1.0/me/messages/{email_id} with {isRead: true}."
        )
