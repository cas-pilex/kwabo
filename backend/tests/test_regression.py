"""End-to-end regressie-harness over alle 17 voorbeeld-emails.

Run:
  pytest tests/test_regression.py --regression
  pytest tests/test_regression.py --regression --update-fixtures

Gebruikt de LLM cache - eerste run vult 'm (kost API); volgende runs zijn gratis.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kwabo.graph.runner import run_on_eml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DIR = ROOT / "tests" / "test_data" / "expected"
EMAILS_DIR = ROOT / "tests" / "test_data" / "emails"


def _slug(name: str) -> str:
    return (
        name.replace(".eml", "").replace(" ", "_").replace("/", "_")
            .replace(",", "").replace("(", "").replace(")", "")
            .replace("'", "").replace('"', "")
    )[:90]


def _summarise(state: dict) -> dict:
    regels = state.get("orderregels") or []
    matched = [r for r in regels if r.get("artikelnummer_kwabo_matched")]
    klant = state.get("klant_match") or {}
    extras = state.get("extra_orders_raw") or []
    return {
        "is_order": bool(state.get("is_order")),
        "klant_nr": klant.get("navision_klantnr"),
        "klant_match_bron": klant.get("match_bron"),
        "bestelnummer_klant": state.get("bestelnummer_klant"),
        "taal": state.get("taal"),
        "n_regels": len(regels),
        "n_matched": len(matched),
        "warnings_count": len(state.get("validatie_warnings") or []),
        "needs_review_count": state.get("needs_review_count") or 0,
        "sub_orders_count": len(extras),
    }


EMAIL_FILES = sorted(EMAILS_DIR.glob("*.eml"))


@pytest.fixture(scope="session", autouse=True)
def _regression_db(tmp_path_factory, request):
    """Session-scoped DB swap for regression tests.

    Swaps the app-wide engine + every consumer module that imported engine
    at load-time, then creates schema + seeds. Only activates when
    --regression is passed.
    """
    if not request.config.getoption("--regression"):
        yield
        return

    import os

    from sqlmodel import Session, SQLModel, create_engine

    path = tmp_path_factory.mktemp("regr_db") / "regr.db"
    url = f"sqlite:///{path}"
    os.environ["DATABASE_URL"] = url

    import kwabo.db.session as ks
    new_engine = create_engine(url, connect_args={"check_same_thread": False})
    ks.engine = new_engine

    # Swap in every module that imported `engine` at load time. Found via:
    # grep -rn "from kwabo.db.session import engine" backend/src
    for mod_name in [
        "kwabo.db.seed",
        "kwabo.db",
        "kwabo.graph.nodes.match_customer",
        "kwabo.graph.nodes.match_articles",
        "kwabo.graph.nodes.compose_order",
        "kwabo.graph.nodes.push_navision",
        "kwabo.graph.nodes.validate_prices",
        "kwabo.api.orders",
        "kwabo.api.klanten",
        "kwabo.api.artikelen",
        "kwabo.api.audit",
        "kwabo.api.intake_trigger",
        "kwabo.api.prijsafspraken",
        "kwabo.api.preview",
        "kwabo.main",
    ]:
        try:
            m = __import__(mod_name, fromlist=["engine"])
            if hasattr(m, "engine"):
                m.engine = new_engine
        except (ImportError, AttributeError):
            pass

    SQLModel.metadata.create_all(new_engine)
    with Session(new_engine) as s:
        from kwabo.db.seed import seed
        seed(s)
        # Prod draait nooit met een lege artikelkaarten-mirror (Fase 4
        # NAV-master-sync, 3757 artikelen): een lege mirror zet de
        # A1-vangrail (kolomwissel klant-/kwabo-nummer) droog en laat deze
        # suite prod onderschatten. Spiegel daarom de mock-NAV-items, zoals
        # de sync dat in prod doet.
        from kwabo.db.models import Artikelkaart
        from kwabo.integrations.nav_mock_fixtures import MOCK_ITEMS
        for it in MOCK_ITEMS:
            s.add(Artikelkaart(
                kwabo_artikelnr=it["number"],
                naam=it.get("displayName") or "",
                basis_eenheid=it.get("baseUnitOfMeasureCode") or "STUK",
                mixprijzen=bool(it.get("mixprijzen")),
            ))
        s.commit()
    yield


@pytest.mark.asyncio
@pytest.mark.parametrize("email_path", EMAIL_FILES, ids=lambda p: _slug(p.name))
async def test_regression(email_path, request, update_fixtures):
    if not request.config.getoption("--regression"):
        pytest.skip("Gebruik --regression om te draaien")

    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    state = await run_on_eml(email_path)
    actual = _summarise(state)

    expected_path = EXPECTED_DIR / f"{_slug(email_path.name)}.json"

    if update_fixtures or not expected_path.exists():
        expected_path.write_text(
            json.dumps(actual, indent=2, default=str, sort_keys=True),
            encoding="utf-8",
        )
        pytest.skip(f"Fixture geschreven: {expected_path.name}")

    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    # Strict: deze velden mogen niet veranderen zonder --update-fixtures
    for key in ("is_order", "klant_nr", "taal", "n_regels"):
        assert actual[key] == expected[key], (
            f"{_slug(email_path.name)}.{key}: {actual[key]} != {expected[key]}"
        )
    # Soepel: matched aantal mag niet dalen
    assert actual["n_matched"] >= expected["n_matched"], (
        f"{_slug(email_path.name)}.n_matched gedaald: "
        f"{actual['n_matched']} < {expected['n_matched']}"
    )
    # Sub-orders mogen niet dalen
    if expected.get("sub_orders_count", 0) > 0:
        assert actual["sub_orders_count"] >= expected["sub_orders_count"], (
            "sub_orders_count gedaald"
        )
