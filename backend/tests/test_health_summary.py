"""Fase 5 (B/C): alerts-ringbuffer + /api/diagnostics/health-summary + tick-teller.

Het gekozen alert-kanaal is in-app: élke alert() landt in een in-memory
ring buffer (ook gethrottlede en ook zonder Slack-webhook) en is opvraagbaar
via GET /api/diagnostics/health-summary, samen met de poller-heartbeat,
token-expiry en worker-info.
"""
from __future__ import annotations

import asyncio

import pytest

# Module-level kwabo-import zodat SQLModel.metadata gevuld is vóór de
# session-fixture create_all draait (file-alleen-runs).
from kwabo.db.models import OAuthToken
from kwabo.utils import mail_poll_status
from kwabo.utils.alerts import alert, recent_alerts, reset_alerts_for_tests


@pytest.fixture(autouse=True)
def _clean_alerts():
    reset_alerts_for_tests()
    mail_poll_status.reset_for_tests()
    yield
    reset_alerts_for_tests()
    mail_poll_status.reset_for_tests()


# ------------------------------------------------------------- ring buffer


def test_alert_landt_in_ringbuffer_ook_zonder_webhook_en_bij_throttle():
    """De buffer is het primaire kanaal: throttling geldt alleen voor de
    webhook-push, niet voor de registratie."""
    alert("test_event_x", "high", {"detail": "eerste"})
    alert("test_event_x", "high", {"detail": "tweede (gethrottled voor webhook)"})
    entries = recent_alerts(10)
    assert len(entries) == 2, entries
    assert entries[0]["event"] == "test_event_x"
    assert entries[0]["severity"] == "high"
    assert all("ts" in e for e in entries)


def test_recent_alerts_nieuwste_eerst_en_begrensd():
    for i in range(5):
        alert("test_event_volgorde", "warning", {"i": i})
    entries = recent_alerts(3)
    assert len(entries) == 3
    assert entries[0]["payload"]["i"] == 4  # nieuwste eerst


# ---------------------------------------------------------- health-summary


def test_geforceerde_alert_verschijnt_in_health_summary(client):
    alert("test_geforceerde_failure", "high", {"bron": "test"})
    r = client.get("/api/diagnostics/health-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    events = [a["event"] for a in body["alerts"]]
    assert "test_geforceerde_failure" in events, body
    # Vaste blokken aanwezig, null-veilig zonder oauth-rij
    assert "poller" in body
    assert body["token"] is None
    assert body["workers"]["web_concurrency"] >= 1


def test_health_summary_toont_token_expiry(client, session):
    from kwabo.utils import utcnow

    session.add(OAuthToken(
        id=1, provider="microsoft", account_email="pilex@kwabo.nl",
        access_token="x", refresh_token="y", expires_at=utcnow(),
    ))
    session.commit()
    body = client.get("/api/diagnostics/health-summary").json()
    assert body["token"]["account_email"] == "pilex@kwabo.nl"
    assert body["token"]["expires_at"] is not None


# ------------------------------------------------------------ tick-teller


def test_record_poll_tick_telt_cumulatief():
    mail_poll_status.record_poll_tick(success=True, processed=0)
    mail_poll_status.record_poll_tick(success=False, error_msg="boem")
    st = mail_poll_status.get_status()
    assert st["ticks_total"] == 2
    assert st["ticks_failed"] == 1


async def test_match_single_crash_vuurt_alert(monkeypatch, session):
    """Wiring-bewijs: een échte silent-failure-site (match_single_crash)
    landt in de ring buffer — niet alleen een handmatige alert()."""
    import kwabo.graph.nodes.match_articles as ma

    async def boom(regel, klant_nr, nav, s):
        raise RuntimeError("NAV plat")

    monkeypatch.setattr(ma, "_match_single", boom)
    state = {
        "email_id": "alert-wiring-test",
        "is_order": True,
        "klant_match": {"navision_klantnr": "10001"},
        "orderregels": [{"positie": 1, "artikelnummer_klant": "X1"}],
    }
    out = await ma.match_articles_node(state)
    assert out is not None
    events = [a["event"] for a in recent_alerts(20)]
    assert "match_single_crash" in events, events


async def test_poller_heartbeat_bij_lege_inbox(monkeypatch, caplog):
    """Eén echte iteratie van _mail_poll_loop met 0 nieuwe mails →
    mail_poll_tick-log (processed=0) + teller +1 (§12.B-bewijs)."""
    import kwabo.api.intake_trigger as intake_mod
    from kwabo.config import settings
    from kwabo.main import _mail_poll_loop

    monkeypatch.setattr(settings, "email_mode", "graph")

    async def lege_scan():
        return {"processed": [], "errors": [], "partial": False}

    monkeypatch.setattr(intake_mod, "scan_inbox", lege_scan)

    real_sleep = asyncio.sleep
    calls = {"n": 0}

    async def fast_sleep(seconds):
        calls["n"] += 1
        if calls["n"] >= 2:  # 1 = initiële delay, 2 = einde eerste tick
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    with pytest.raises(asyncio.CancelledError):
        await _mail_poll_loop(35)

    st = mail_poll_status.get_status()
    assert st["ticks_total"] == 1
    assert st["last_poll_status"] == "ok"
    assert st["last_poll_processed"] == 0
    assert any(
        "mail_poll_tick" in r.message and "processed=0" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]
