"""Best-effort alerting voor silent-failure paths.

Doel: maak het onmogelijk om in productie een week lang met een kapotte
poller / kapotte NAV / kapotte Supabase te draaien zonder dat iemand het
merkt. De audit (§14.10) noemt dat als top-10 issue.

Aanpak:
- Vooralsnog één sink: Slack incoming-webhook (URL via env
  ``KWABO_SLACK_WEBHOOK_URL``).
- Synchroon, korte timeout. Het is een productie-error path — een Slack-
  hiccup mag niet alsnog de business-flow killen. Daarom: alle exceptions
  binnen `alert()` worden GESLIKT (na een lokale log.warning).
- Throttling: per (event, severity) maximaal 1 post per ``_THROTTLE_SECONDS``
  zodat een crash-loop ons niet bant uit het Slack-channel.

Gebruik:
    from kwabo.utils.alerts import alert
    alert("nav2018_stepwise_failure", "high", {"op_index": 3, ...})
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from kwabo.utils.logging import log

_THROTTLE_SECONDS = 300  # max 1 alert per (event, severity) per 5 min
_recent: dict[tuple[str, str], float] = {}


def _slack_webhook() -> str:
    # Lazy read — laat operators de env wijzigen zonder restart.
    return os.environ.get("KWABO_SLACK_WEBHOOK_URL", "").strip()


def _throttle_allows(key: tuple[str, str]) -> bool:
    now = time.time()
    last = _recent.get(key, 0)
    if now - last < _THROTTLE_SECONDS:
        return False
    _recent[key] = now
    return True


def _format_text(event: str, severity: str, payload: dict[str, Any]) -> str:
    sev_emoji = {"critical": "🚨", "high": "⚠️", "warning": "🟡", "info": "ℹ️"}.get(
        severity, "ℹ️"
    )
    lines = [f"{sev_emoji} *kwabo* `{event}` ({severity})"]
    for k, v in payload.items():
        # Beperk lengte per veld — geen log-spam in Slack.
        s = str(v)
        if len(s) > 400:
            s = s[:400] + "…"
        lines.append(f"• *{k}*: `{s}`")
    return "\n".join(lines)


def alert(event: str, severity: str, payload: dict[str, Any] | None = None) -> None:
    """Post a Slack alert when KWABO_SLACK_WEBHOOK_URL is set, otherwise no-op.

    Always returns cleanly — never raises. The caller's business-flow must
    not depend on the alert landing. Throttled per (event, severity) so a
    crash loop doesn't flood the channel.
    """
    payload = payload or {}
    key = (event, severity)
    if not _throttle_allows(key):
        return

    webhook = _slack_webhook()
    if not webhook:
        # Niet geconfigureerd — alleen lokaal loggen.
        # NB: structlog gebruikt 'event' als positional → noem ons attribuut
        # 'alert_event' om de naam-collision te vermijden.
        log.info("alert_no_sink", alert_alert_event=event, severity=severity, **payload)
        return

    try:
        text = _format_text(event, severity, payload)
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as c:
            resp = c.post(webhook, json={"text": text})
            if resp.status_code >= 400:
                log.warning(
                    "alert_post_failed",
                    alert_event=event,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("alert_post_exception", alert_event=event, error=str(exc)[:200])


def reset_throttle_for_tests() -> None:
    """Test-only: clear the throttle window so each test starts fresh."""
    _recent.clear()
