"""Pytest fixtures: in-memory DB + seed for fast isolated tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def pytest_addoption(parser):
    parser.addoption(
        "--update-fixtures",
        action="store_true",
        default=False,
        help="Overschrijf expected/*.json met de huidige run-output",
    )
    parser.addoption(
        "--regression",
        action="store_true",
        default=False,
        help="Run regressie-tests (vereist ANTHROPIC_API_KEY of gevulde cache)",
    )


@pytest.fixture
def update_fixtures(request) -> bool:
    return request.config.getoption("--update-fixtures")


@pytest.fixture(scope="session")
def test_db_url(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("db") / "test.db"
    return f"sqlite:///{path}"


@pytest.fixture(autouse=True)
def _env(monkeypatch, test_db_url):
    """Isolate each test: in-memory DB, mock Navision, no real API calls by default."""
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setenv("NAVISION_MODE", "mock")
    monkeypatch.setenv("EMAIL_MODE", "file_drop")
    # Disable LangSmith for unit tests
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    # Keep real Anthropic key if present, else dummy (vision calls are mocked per-test)
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", "sk-test"))
    yield


@pytest.fixture
def session(test_db_url):
    # Re-initialize schema each test
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        from kwabo.db.seed import seed

        seed(s)
        yield s


@pytest.fixture
def client(session):
    """TestClient backed by the seeded test DB (engine rebound to the test session)."""
    from kwabo.db import session as db_session_mod

    original_engine = db_session_mod.engine
    db_session_mod.engine = session.get_bind()

    from kwabo.main import create_app

    app = create_app()
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c

    db_session_mod.engine = original_engine


@pytest.fixture
def eml_dir() -> Path:
    return ROOT / "tests" / "test_data" / "emails"


STATES_DIR = ROOT / "tests" / "test_data" / "states"


def load_state(name: str) -> dict:
    """Laad een geëxporteerde echte-order fixture (zie scripts/export_order_states.py).

    `name` mag een prefix zijn ("order_706") of een volledige bestandsnaam.
    Geeft de envelope terug: {order_id, email_from, email_subject, status, order_state}.
    """
    import json

    candidates = sorted(STATES_DIR.glob(f"{name}*")) if not name.endswith(".json") \
        else [STATES_DIR / name]
    matches = [p for p in candidates if p.is_file()]
    if not matches:
        pytest.skip(f"Echte-order fixture '{name}' ontbreekt — draai eerst "
                    "scripts/export_order_states.py (vereist prod DATABASE_URL)")
    return json.loads(matches[0].read_text(encoding="utf-8"))


@pytest.fixture
def fixtures_dir() -> Path:
    return ROOT / "tests" / "fixtures"
