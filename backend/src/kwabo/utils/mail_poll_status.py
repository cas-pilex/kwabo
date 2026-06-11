"""In-process heartbeat voor de mail-poll loop en Graph token-refresh.

Module-level state — herstart wist hem, dat is OK voor pure observability.
De /api/mailbox/status endpoint leest hier uit zodat operators in het
dashboard kunnen zien of de poller daadwerkelijk draait en wanneer de
laatste tick + token-refresh plaatsvonden, zonder Railway-logs te hoeven
graven.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

_STATE: dict[str, Any] = {
    "last_poll_at": None,
    "last_poll_status": None,        # "ok" | "error" | None
    "last_poll_processed": None,     # int or None
    "last_poll_errors": None,        # int or None
    "last_poll_partial": None,       # bool or None
    "last_poll_error_msg": None,     # str or None
    "last_token_refresh_at": None,   # datetime or None
    # Fase 5 (C): cumulatieve tellers sinds proces-start — de heartbeat
    # bewijst óók bij 0 mails dat de poller daadwerkelijk tikt (§12.B).
    "ticks_total": 0,
    "ticks_failed": 0,
}


def record_poll_tick(
    *,
    success: bool,
    processed: int = 0,
    errors: int = 0,
    partial: bool = False,
    error_msg: Optional[str] = None,
) -> None:
    """Called by _mail_poll_loop after each tick (success or exception)."""
    _STATE["ticks_total"] = int(_STATE.get("ticks_total") or 0) + 1
    if not success:
        _STATE["ticks_failed"] = int(_STATE.get("ticks_failed") or 0) + 1
    _STATE["last_poll_at"] = datetime.now(timezone.utc)
    _STATE["last_poll_status"] = "ok" if success else "error"
    _STATE["last_poll_processed"] = processed
    _STATE["last_poll_errors"] = errors
    _STATE["last_poll_partial"] = partial
    _STATE["last_poll_error_msg"] = (error_msg or "")[:300] if error_msg else None


def record_token_refresh() -> None:
    """Called by GraphEmailClient._refresh_token after a successful refresh."""
    _STATE["last_token_refresh_at"] = datetime.now(timezone.utc)


def get_status() -> dict[str, Any]:
    """Return a shallow copy for /api/mailbox/status to embed."""
    return dict(_STATE)


def reset_for_tests() -> None:
    """Test-only: wipe state so assertions start from a clean slate."""
    for k in _STATE:
        _STATE[k] = 0 if k.startswith("ticks_") else None
