"""Demo-/seed-klanten (10001-10016) mogen de matching nooit STIL vervuilen.

Achtergrond: de demo-seed zet 16 klanten met de ECHTE order-mailadressen van
klanten (10014 = BAUHAUS, supplier@bahag.com). Staat zo'n rij in `klantenkaarten`
(bv. per ongeluk in prod geseed), dan matcht een inkomende mail via K1
(`repo.by_email`) op conf 1.0 — en conf 1.0 is het ÉNIGE pad zonder
CONTROLEER-vlag. Resultaat: een match op een NAV-nummer dat niet in de live
company bestaat, ZONDER vlag → Approve→push faalt stil. Dit is een stille fout.

Deze tests borgen: (1) een demo-klant-match krijgt ALTIJD de CONTROLEER-vlag;
(2) `seed()` schrijft niets als de doel-DB geen sqlite is (prod-bescherming).
"""
from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine, select

from kwabo.db.models import Klantenkaart
from kwabo.db.seed import DEMO_NAV_KLANTNRS, seed
from kwabo.graph.nodes import match_customer as mc_mod
from kwabo.graph.nodes.match_customer import match_customer_node


class _NoNav:
    async def search_customers(self, naam=None, email=None):
        return []


@pytest.fixture
def app_engine(session, monkeypatch):
    """Bind matcher + repos aan de test-DB. De conftest-seed heeft 10014
    (BAUHAUS, supplier@bahag.com) al in `klantenkaarten` gezet — precies de
    'demo-rij lekt in de matching'-situatie."""
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _NoNav())
    yield session


def _state(**over):
    base = {
        "email_id": "demo-stil",
        "email_from": "supplier@bahag.com",  # = e-mail van demo-klant 10014
        "email_subject": "Bestelling",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_demo_klant_match_krijgt_altijd_controleer_vlag(app_engine):
    """K1 matcht 10014 op conf 1.0 — maar omdat het een demo-/seed-nummer is,
    MOET klant_match in needs_review_fields staan (geen stille fout)."""
    session = app_engine
    # Voorwaarde: de demo-rij staat in de DB (conftest-seed).
    hit = session.exec(
        select(Klantenkaart).where(Klantenkaart.nav_klantnr == "10014")
    ).first()
    assert hit is not None and (hit.email or "").lower() == "supplier@bahag.com"

    out = await match_customer_node(_state())

    assert (out.get("klant_match") or {}).get("navision_klantnr") == "10014"
    assert "klant_match" in (out.get("needs_review_fields") or []), (
        "demo-klant 10014 matchte ZONDER CONTROLEER-vlag — stille fout"
    )


def test_seed_target_is_sqlite_alleen_voor_sqlite():
    """De seed-guard herkent de doel-DB aan de sessie-bind (geen connectie nodig)."""
    from kwabo.db.seed import _seed_target_is_sqlite

    sqlite_s = Session(create_engine("sqlite://"))
    pg_s = Session(create_engine("postgresql+psycopg://u:p@127.0.0.1:1/db"))
    assert _seed_target_is_sqlite(sqlite_s) is True
    assert _seed_target_is_sqlite(pg_s) is False


def test_seed_weigert_niet_sqlite_zonder_te_schrijven():
    """seed() op een niet-sqlite sessie keert direct terug: geen connectie, geen
    write. (Poort 1 luistert niet — zou de guard ontbreken, dan crasht de eerste
    query op een connectie-fout.)"""
    pg_engine = create_engine("postgresql+psycopg://u:p@127.0.0.1:1/db")
    with Session(pg_engine) as s:
        seed(s)  # mag NIET raisen en niets schrijven
