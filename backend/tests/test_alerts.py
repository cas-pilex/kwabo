"""Tests voor Fase-5 alerts.py.

Dekt: throttling, no-sink-no-op, Slack-post via respx, exception-isolation.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from kwabo.utils import alerts


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    alerts.reset_throttle_for_tests()
    # Default: geen sink — tests die er één willen zetten dat zelf via env.
    monkeypatch.delenv("KWABO_SLACK_WEBHOOK_URL", raising=False)
    yield
    alerts.reset_throttle_for_tests()


def test_alert_without_sink_is_noop():
    """Zonder env-var: alert() moet stilletjes return — geen crash, geen
    http-call."""
    # Geen mock route — als er toch een http-call uitkomt zou de test
    # falen op netwerk-fail.
    alerts.alert("test_event", "info", {"foo": "bar"})


@respx.mock
def test_alert_posts_to_slack_when_sink_configured(monkeypatch):
    monkeypatch.setenv("KWABO_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X/Y/Z")
    route = respx.post("https://hooks.slack.com/services/X/Y/Z").mock(
        return_value=httpx.Response(200, text="ok")
    )

    alerts.alert("nav2018_stepwise_failure", "high", {"op_index": 3, "status": 500})
    assert route.called
    body = route.calls.last.request.content.decode("utf-8")
    assert "nav2018_stepwise_failure" in body
    assert "op_index" in body


@respx.mock
def test_alert_swallows_post_exception(monkeypatch):
    """Slack-API down → alert() mag NIET raisen. Critical: caller's
    business-flow loopt door."""
    monkeypatch.setenv("KWABO_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X/Y/Z")
    respx.post("https://hooks.slack.com/services/X/Y/Z").mock(
        side_effect=httpx.ConnectError("dns broken")
    )
    # Mag niet raisen
    alerts.alert("any", "high", {"x": 1})


@respx.mock
def test_alert_swallows_5xx_response(monkeypatch):
    monkeypatch.setenv("KWABO_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X/Y/Z")
    respx.post("https://hooks.slack.com/services/X/Y/Z").mock(
        return_value=httpx.Response(500, text="slack down")
    )
    alerts.alert("any", "high", {"x": 1})  # mag niet raisen


@respx.mock
def test_throttling_blocks_repeated_alerts(monkeypatch):
    """Tweede call binnen 5 min met zelfde (event, severity) wordt
    geskipt — geen Slack-flood bij een crash-loop."""
    monkeypatch.setenv("KWABO_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X/Y/Z")
    route = respx.post("https://hooks.slack.com/services/X/Y/Z").mock(
        return_value=httpx.Response(200)
    )

    alerts.alert("repeat_event", "high", {"i": 1})
    alerts.alert("repeat_event", "high", {"i": 2})
    alerts.alert("repeat_event", "high", {"i": 3})

    assert route.call_count == 1  # alleen de eerste


@respx.mock
def test_throttling_per_event_and_severity(monkeypatch):
    """Verschillende events of severities krijgen aparte throttle-windows."""
    monkeypatch.setenv("KWABO_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X/Y/Z")
    route = respx.post("https://hooks.slack.com/services/X/Y/Z").mock(
        return_value=httpx.Response(200)
    )

    alerts.alert("event_a", "high", {})
    alerts.alert("event_b", "high", {})
    alerts.alert("event_a", "warning", {})  # zelfde event, andere severity

    assert route.call_count == 3


def test_format_text_truncates_long_payload_values():
    payload = {"err": "X" * 1000}
    out = alerts._format_text("e", "high", payload)
    # Veld wordt afgekapt op 400 chars + ellipsis
    assert "X" * 400 in out
    assert "X" * 500 not in out
