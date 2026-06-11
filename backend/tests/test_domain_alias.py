"""K2b: domein-alias — een beheerder koppelt een heel e-maildomein aan een
klant via een klant_email_aliases-rij van de vorm "@pontmeyer.nl".

Aanleiding (#635): mails van @pontmeyer.nl horen bij TABS Holland (61793),
maar de TABS-kaart heet anders dan het naam-signaal ("TABS Holland" fuzzyt
het dichtst op "AST Holland B.V.") zodat de kandidatenlijst de juiste klant
nooit toonde. Bewust géén conf 1.0 zoals een exacte e-mailmatch: een domein
kan bij een franchise meerdere vestigingen dekken — autopick op 0.9 krijgt
daarmee automatisch de zachte CONTROLEER-vlag (3b-conventie).
"""
from __future__ import annotations

import pytest

from kwabo.db.models import Klantenkaart
from kwabo.db.repository import KlantRepo
from kwabo.graph.nodes import match_customer as mc_mod
from kwabo.graph.nodes.match_customer import match_customer_node


class _FakeNav:
    """NAV vindt niets — dwingt de cascade voorbij K2a/K4."""

    async def search_customers(self, naam=None, email=None):
        return []


@pytest.fixture
def app_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _FakeNav())
    yield


def _add_klant(session, nr: str, naam: str, email: str | None = None) -> None:
    session.add(Klantenkaart(nav_klantnr=nr, naam=naam, email=email))
    session.commit()


def _state(**over):
    base = {
        "email_id": "p",
        "email_from": "jan.devries@pontmeyer.nl",
        "email_subject": "Bestelling 4506860196",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# repo: by_domain_alias
# ---------------------------------------------------------------------------


def test_by_domain_alias_finds_klant(session):
    repo = KlantRepo(session)
    _add_klant(session, "61793", "TABS Holland B.V.")
    repo.add_alias("61793", "@pontmeyer.nl", label="Pontmeyer-domein")
    hits = repo.by_domain_alias("jan.devries@pontmeyer.nl")
    assert [k.nav_klantnr for k in hits] == ["61793"]
    # Ander domein: geen hit.
    assert repo.by_domain_alias("jan@anders.nl") == []


def test_full_address_alias_is_not_a_domain_alias(session):
    """Een gewone alias (volledig adres) blijft het terrein van by_email
    (conf 1.0) en mag niet als domein-alias meetellen."""
    repo = KlantRepo(session)
    _add_klant(session, "61793", "TABS Holland B.V.")
    repo.add_alias("61793", "inkoop@pontmeyer.nl")
    assert repo.by_domain_alias("jan.devries@pontmeyer.nl") == []
    # En andersom raakt de domein-rij by_email niet (exacte lookup).
    repo.add_alias("61793", "@pontmeyer.nl")
    assert repo.by_email("jan.devries@pontmeyer.nl") is None


# ---------------------------------------------------------------------------
# node: K2b in de cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_alias_autopick_with_review_flag(session, app_engine):
    _add_klant(session, "61793", "TABS Holland B.V.")
    KlantRepo(session).add_alias("61793", "@pontmeyer.nl", label="Pontmeyer-domein")

    out = await match_customer_node(_state())

    assert out["klant_match"]["navision_klantnr"] == "61793"
    assert out["klant_match"]["match_confidence"] == 0.9
    assert out["klant_match"]["match_bron"] == "domein_alias"
    # 3b: conf < 1.0 → zachte CONTROLEER-vlag.
    assert "klant_match" in out["needs_review_fields"]
    # Provenance: dit komt uit de klantenkaart-mirror, niet "missing".
    assert out["_meta"]["klant_match"]["source"] == "klantenkaart"


@pytest.mark.asyncio
async def test_exact_email_match_beats_domain_alias(session, app_engine):
    _add_klant(session, "61793", "TABS Holland B.V.")
    _add_klant(session, "61999", "Jan de Vries Verf B.V.",
               email="jan.devries@pontmeyer.nl")
    KlantRepo(session).add_alias("61793", "@pontmeyer.nl")

    out = await match_customer_node(_state())

    assert out["klant_match"]["navision_klantnr"] == "61999"
    assert out["klant_match"]["match_confidence"] == 1.0
    assert out["klant_match"]["match_bron"] == "email"


@pytest.mark.asyncio
async def test_two_domain_alias_klanten_no_autopick(session, app_engine):
    """Een franchise-domein met twee vestigings-aliassen mag nooit gokken —
    beide klanten in de kandidatenlijst, handmatige selectie."""
    repo = KlantRepo(session)
    _add_klant(session, "61792", "Pontmeyer Arnhem")
    _add_klant(session, "61793", "Pontmeyer Heerenveen")
    repo.add_alias("61792", "@pontmeyer.nl")
    repo.add_alias("61793", "@pontmeyer.nl")

    out = await match_customer_node(_state())

    assert out["klant_match"] is None
    nrs = {k["navision_klantnr"] for k in out["klant_kandidaten"]}
    assert nrs == {"61792", "61793"}
    assert "klant_match" in out["needs_review_fields"]
    assert any("MEERDERE KLANTEN" in w for w in out.get("validatie_warnings") or [])


@pytest.mark.asyncio
async def test_no_alias_behaviour_unchanged(session, app_engine):
    """Zonder alias-rij blijft de cascade exact zoals hij was: NAV vindt
    niets → geen match, handmatige review."""
    _add_klant(session, "61793", "TABS Holland B.V.")

    out = await match_customer_node(_state())

    assert out["klant_match"] is None
    assert "klant_match" in out["needs_review_fields"]
