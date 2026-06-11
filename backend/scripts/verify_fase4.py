"""Fase 4 perf-verificatie: voor/na wall-clock van match_articles én de
post-extract-pipeline op dezelfde fixture, plus determinisme-bewijs.

Meet met een latency-injecterende wrapper om MockNavisionClient (200 ms per
NAV-call, zoals een echte OData-roundtrip naar dynamicstocloud.com):
  A. alleen match_articles_node — 10 regels, ~15 NAV-calls;
  B. de hele sub-order-pipeline (match_customer → … → compose; géén LLM).
Per meting: wall-clock, aantal NAV-calls en max parallelle calls in flight.
Draait elke meting bij MATCH_CONCURRENCY=1 (≡ oud serieel gedrag) en =5, en
bewijst dat de node-uitkomst identiek is (timestamps gestript, json-equal).

Op code vóór Fase-4-stap-4 bestaat de concurrency-knop niet: beide runs zijn
dan serieel — dat is de "voor"-meting.

Usage (vanuit backend/): python scripts/verify_fase4.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

# Vóór elke kwabo-import: nooit de echte DB raken (backend/.env wijst naar prod).
_tmpdb = Path(tempfile.mkdtemp()) / "verify_fase4.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"
os.environ["NAVISION_MODE"] = "mock"

from sqlmodel import Session, SQLModel  # noqa: E402

from kwabo.config import settings  # noqa: E402
from kwabo.db.seed import seed  # noqa: E402
from kwabo.db.session import engine  # noqa: E402
from kwabo.graph.graph import get_sub_order_app  # noqa: E402
from kwabo.graph.nodes import match_articles as ma  # noqa: E402
from kwabo.integrations import navision_api  # noqa: E402
from kwabo.integrations.navision_api import (  # noqa: E402
    MockNavisionClient,
    nav_client_scope,
)

NAV_LATENCY_S = 0.2  # ~echte OData-roundtrip productie (audit §12.D.1: 200-500 ms)


class LatencyNav:
    """MockNavisionClient + kunstmatige call-latency + concurrency-telling."""

    def __init__(self) -> None:
        self._inner = MockNavisionClient(out_dir=Path(tempfile.mkdtemp()))
        self.call_count = 0
        self._in_flight = 0
        self.max_in_flight = 0

    async def _timed(self, coro):
        self.call_count += 1
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(NAV_LATENCY_S)
            return await coro
        finally:
            self._in_flight -= 1

    async def get_customer(self, nr):
        return await self._timed(self._inner.get_customer(nr))

    async def search_customers(self, *a, **kw):
        return await self._timed(self._inner.search_customers(*a, **kw))

    async def get_item(self, nr):
        return await self._timed(self._inner.get_item(nr))

    async def search_items(self, beschrijving=None):
        return await self._timed(self._inner.search_items(beschrijving))

    def __getattr__(self, name):  # overige calls (uoms, push) zonder latency
        return getattr(self._inner, name)


def build_regels() -> list[dict]:
    """10 regels: 5 × expliciet kwabo-nr zonder mirror-rij (→ 1 get_item p/st)
    + 5 × alleen onmatchbare omschrijving (→ 2 search_items p/st) ≈ 15 calls."""
    bekend = ["238601", "1515155", "228321", "2597768", "201291"]
    regels = [
        {"positie": i + 1, "artikelnummer_kwabo": nr, "artikelnummer_klant": None,
         "omschrijving": f"Artikel {nr}", "hoeveelheid": 10.0, "eenheid": "STUK"}
        for i, nr in enumerate(bekend)
    ]
    regels += [
        {"positie": i + 6, "artikelnummer_kwabo": None, "artikelnummer_klant": None,
         "omschrijving": f"Volstrekt onbekend fantasieproduct nr {i} qqxyz",
         "hoeveelheid": 5.0, "eenheid": "STUK"}
        for i in range(5)
    ]
    return regels


def _strip_volatile(state: dict) -> dict:
    uit = json.loads(json.dumps(state))
    for stap in uit.get("stappen_log") or []:
        stap.pop("timestamp", None)
    return uit


def _set_concurrency(n: int) -> bool:
    try:
        settings.match_concurrency = n
        return True
    except Exception:
        return False  # pre-Fase-4-code: knop bestaat nog niet → serieel


async def meet_node(conc: int) -> tuple[float, dict, LatencyNav]:
    nav = LatencyNav()
    orig = ma.get_navision_client
    ma.get_navision_client = lambda: nav
    try:
        knop = _set_concurrency(conc)
        state = {"email_id": "verify-f4-node",
                 "klant_match": {"navision_klantnr": "10001"},
                 "orderregels": build_regels(), "needs_review_fields": []}
        t0 = time.perf_counter()
        uit = await ma.match_articles_node(state)
        dt = time.perf_counter() - t0
        label = f"conc={conc}" if knop else f"conc-knop afwezig (serieel), gevraagd {conc}"
        print(f"  [A:{label:<42}] wall-clock={dt:6.2f}s  nav_calls={nav.call_count}  "
              f"max_in_flight={nav.max_in_flight}")
        return dt, _strip_volatile(uit), nav
    finally:
        ma.get_navision_client = orig


async def meet_pipeline(conc: int) -> float:
    nav = LatencyNav()
    orig = navision_api._build_navision_client
    navision_api._build_navision_client = lambda: nav
    try:
        _set_concurrency(conc)
        state = {"email_id": f"verify-f4-pipe-c{conc}",
                 "email_from": "purchaseorders@ferney.nl",
                 "email_subject": "Bestelling", "email_body": "zie regels",
                 "is_order": True, "taal": "NL",
                 "orderregels": build_regels(),
                 "stappen_log": [], "needs_review_fields": []}
        t0 = time.perf_counter()
        async with nav_client_scope():
            await get_sub_order_app().ainvoke(state)
        dt = time.perf_counter() - t0
        print(f"  [B:conc={conc}] wall-clock={dt:6.2f}s  nav_calls={nav.call_count}  "
              f"max_in_flight={nav.max_in_flight}")
        return dt
    finally:
        navision_api._build_navision_client = orig


async def main() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed(s)

    print(f"=== Meting A: match_articles_node (10 regels, latency {NAV_LATENCY_S*1000:.0f} ms/call) ===")
    _, uit1, _ = await meet_node(1)
    _, uit5, nav5 = await meet_node(5)

    if json.dumps(uit1, sort_keys=True) == json.dumps(uit5, sort_keys=True):
        print("  DETERMINISME OK: uitkomst conc=1 ≡ conc=5 (json-identiek, timestamps gestript)")
    else:
        print("  !! DETERMINISME GEBROKEN: conc=1 en conc=5 verschillen !!")
        raise SystemExit(1)
    if nav5.max_in_flight > 5:
        print(f"  !! SEMAPHORE GESCHONDEN: max_in_flight={nav5.max_in_flight} > 5 !!")
        raise SystemExit(1)

    print("\n=== Meting B: post-extract-pipeline (match_customer → … → compose; géén LLM) ===")
    await meet_pipeline(1)
    await meet_pipeline(5)


if __name__ == "__main__":
    asyncio.run(main())
