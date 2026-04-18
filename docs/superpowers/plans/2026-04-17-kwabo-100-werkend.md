# Kwabo 100% werkend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End-to-end Kwabo order-intake flow 100% werkend maken met geautomatiseerde harness die 10× reproduceerbaar draait zonder API-budget op te jagen.

**Architecture:** Test-infrastructuur eerst (LLM cache + pytest regressie-harness + Playwright), daarna 8 functionele fixes. Elke fix wordt geverifieerd door de harness voor "klaar" gezegd wordt.

**Tech Stack:** Python 3.14 (FastAPI, LangGraph, SQLModel, pytest), Node 24 (Next.js 16, React 19, Playwright), SQLite, Anthropic Claude Sonnet 4.5.

**Spec:** `docs/superpowers/specs/2026-04-17-kwabo-100-werkend-design.md`

---

## Task 0: Git init + baseline commit

**Rationale:** Project heeft nog geen `.git/`. Commits per taak vereisen een repo.

**Files:**
- Create: `.git/` (via `git init`)
- Verify: `.gitignore` dekt `data/llm_cache/`, `data/navision_mock/`, `data/inbox/`, `data/processed/`, `backend/kwabo.db`, `backend/kwabo.log`, `__pycache__/`, `node_modules/`, `.next/`, `frontend/test-results/`, `frontend/playwright-report/`

- [ ] **Step 1:** Controleer `.gitignore`

```bash
cat C:/Kwabo/kwabo-order-intake/.gitignore
```

Als onvolledig, vul aan:

```
# data runtime
data/llm_cache/
data/navision_mock/orders/
data/inbox/*.eml
data/processed/*.eml

# backend runtime
backend/kwabo.db
backend/kwabo.log
backend/**/__pycache__/
backend/.venv/
backend/.pytest_cache/

# frontend runtime
frontend/node_modules/
frontend/.next/
frontend/test-results/
frontend/playwright-report/
frontend/tests/fixtures/*.eml.backup

# editor / OS
.DS_Store
*.swp
.vscode/
```

- [ ] **Step 2:** `git init` en initial commit

```bash
cd C:/Kwabo/kwabo-order-intake
git init -q
git add .
git commit -m "chore: initial baseline before 100-werkend plan"
```

Expected: commit succeeds; `git log --oneline` toont 1 commit.

---

## Task 1: LLM response cache module

**Files:**
- Create: `backend/src/kwabo/graph/llm_cache.py`
- Create: `backend/tests/test_llm_cache.py`
- Modify: `backend/src/kwabo/config.py` — voeg `llm_cache_mode: str = "on"` toe

**Goal:** File-based content-addressable cache voor Anthropic-calls. `classify_node` (langchain messages) en `extract_from_email` (raw blocks) roepen dezelfde cache-laag aan.

- [ ] **Step 1:** Breid `config.py` uit

Lees eerst `backend/src/kwabo/config.py`, voeg toe tussen andere velden:

```python
llm_cache_mode: str = "on"  # on | read-only | off
llm_cache_dir: str = "../data/llm_cache"
```

- [ ] **Step 2:** Schrijf failing test

Create `backend/tests/test_llm_cache.py`:

```python
"""Unit tests voor LLM response cache."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kwabo.graph.llm_cache import cache_get, cache_put, cache_key


def test_key_is_deterministic():
    k1 = cache_key("sonnet", "system A", "user B", extras={"max_tokens": 1000})
    k2 = cache_key("sonnet", "system A", "user B", extras={"max_tokens": 1000})
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


def test_key_changes_on_input(tmp_path):
    a = cache_key("sonnet", "s", "u", extras={})
    b = cache_key("sonnet", "s", "u2", extras={})
    assert a != b


def test_put_and_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    key = cache_key("sonnet", "system", "user", extras={})
    cache_put(key, {"response": "hello", "input_tokens": 5, "output_tokens": 3})
    got = cache_get(key)
    assert got is not None
    assert got["response"] == "hello"


def test_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    assert cache_get("nonexistent_key_aaaa") is None


def test_corrupt_cache_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    key = "deadbeef" * 8
    (tmp_path / f"{key}.json").write_text("{not valid json")
    assert cache_get(key) is None


def test_mode_off_never_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_MODE", "off")
    key = cache_key("m", "s", "u", extras={})
    cache_put(key, {"response": "x"})
    assert cache_get(key) is None


def test_mode_readonly_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_MODE", "read-only")
    key = cache_key("m", "s", "u", extras={})
    cache_put(key, {"response": "should not persist"})
    assert cache_get(key) is None
```

- [ ] **Step 3:** Run test — expect FAIL (module niet bestaat)

```bash
cd C:/Kwabo/kwabo-order-intake/backend
PYTHONPATH=src python -m pytest tests/test_llm_cache.py -v
```

Expected: ModuleNotFoundError / FAIL op alle 7 tests.

- [ ] **Step 4:** Implementeer `llm_cache.py`

```python
"""File-based content-addressable cache voor LLM-calls.

Key = SHA-256(model + system + user + sorted(extras)).
Storage = {LLM_CACHE_DIR}/{key}.json with {model, response, input_tokens, output_tokens, ts}.
Mode (env LLM_CACHE_MODE): 'on' (read+write) | 'read-only' (read, no write) | 'off' (bypass).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _mode() -> str:
    return os.getenv("LLM_CACHE_MODE", "on").lower()


def _dir() -> Path:
    d = Path(os.getenv("LLM_CACHE_DIR", "../data/llm_cache"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(model: str, system: str, user: str, *, extras: dict[str, Any]) -> str:
    payload = {
        "model": model,
        "system": system,
        "user": user,
        "extras": dict(sorted((extras or {}).items())),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_get(key: str) -> dict[str, Any] | None:
    if _mode() == "off":
        return None
    path = _dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cache_put(key: str, payload: dict[str, Any]) -> None:
    if _mode() != "on":
        return
    path = _dir() / f"{key}.json"
    payload = {**payload, "ts": datetime.now(tz=timezone.utc).isoformat()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    tmp.replace(path)
```

- [ ] **Step 5:** Run test — expect PASS

```bash
cd C:/Kwabo/kwabo-order-intake/backend
PYTHONPATH=src python -m pytest tests/test_llm_cache.py -v
```

Expected: 7 passed.

- [ ] **Step 6:** Commit

```bash
cd C:/Kwabo/kwabo-order-intake
git add backend/src/kwabo/graph/llm_cache.py backend/src/kwabo/config.py backend/tests/test_llm_cache.py
git commit -m "feat(cache): file-based LLM response cache with mode control"
```

---

## Task 2: Integreer cache in classify-node

**Files:**
- Modify: `backend/src/kwabo/graph/nodes/classify.py`
- Create: `backend/tests/test_classify_cache.py`

**Goal:** `classify_node` roept eerst de cache aan; bij miss → echte API call → schrijft cache.

- [ ] **Step 1:** Schrijf failing test

Create `backend/tests/test_classify_cache.py`:

```python
"""classify_node moet cache raken bij 2e identieke call."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from kwabo.graph.nodes.classify import classify_node


@pytest.mark.asyncio
async def test_cache_hit_on_second_call(tmp_path, monkeypatch, session):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_MODE", "on")

    fake_resp = type("R", (), {"content": '{"is_order": true, "reden": "x", "confidence": 0.9}'})()
    mock_ainvoke = AsyncMock(return_value=fake_resp)

    with patch("kwabo.graph.nodes.classify.get_llm") as glm:
        glm.return_value.ainvoke = mock_ainvoke
        state = {
            "email_id": "t1", "email_from": "a@b.nl", "email_subject": "Order",
            "email_body": "Hallo, graag 10x stuks.", "bijlagen": [], "stappen_log": [],
        }
        out1 = await classify_node(state)
        out2 = await classify_node(state)

    assert out1["is_order"] is True
    assert out2["is_order"] is True
    assert mock_ainvoke.call_count == 1, "2e call moet uit cache komen"
```

- [ ] **Step 2:** Run — expect FAIL (call_count zal 2 zijn)

```bash
cd C:/Kwabo/kwabo-order-intake/backend
PYTHONPATH=src python -m pytest tests/test_classify_cache.py -v
```

- [ ] **Step 3:** Pas `classify.py` aan

Vervang de section `llm = get_llm(); resp = await llm.ainvoke(...)` door cache-lookup-pattern:

```python
from kwabo.graph.llm_cache import cache_get, cache_key, cache_put
from kwabo.config import settings

# ... in classify_node, na `human = (...)`:
ck = cache_key(
    settings.anthropic_model, system, human,
    extras={"max_tokens": 16000, "temperature": 0, "node": "classify"},
)
cached = cache_get(ck)
if cached is not None:
    content = cached["response"]
else:
    llm = get_llm()
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    content = resp.content
    cache_put(ck, {
        "response": content,
        "model": settings.anthropic_model,
        "input_tokens": getattr(resp, "response_metadata", {}).get("usage", {}).get("input_tokens"),
        "output_tokens": getattr(resp, "response_metadata", {}).get("usage", {}).get("output_tokens"),
    })

try:
    parsed = parse_json_loose(content)
except Exception as e:  # noqa: BLE001
    parsed = {"is_order": True, "reden": f"parse-fallback: {e}", "confidence": 0.3}
```

- [ ] **Step 4:** Run — expect PASS

```bash
PYTHONPATH=src python -m pytest tests/test_classify_cache.py -v
```

- [ ] **Step 5:** Verifieer bestaande tests nog groen

```bash
PYTHONPATH=src python -m pytest -x --tb=short
```

- [ ] **Step 6:** Commit

```bash
git add backend/src/kwabo/graph/nodes/classify.py backend/tests/test_classify_cache.py
git commit -m "feat(cache): cache classify LLM calls"
```

---

## Task 3: Integreer cache in extract

**Files:**
- Modify: `backend/src/kwabo/integrations/llm_extractor.py`
- Create: `backend/tests/test_extract_cache.py`

**Goal:** `extract_from_email` cachet op hash van (system prompt + serialized blocks inclusief base64 van PDFs).

- [ ] **Step 1:** Schrijf failing test

```python
"""extract_from_email cachet per (prompt, blocks) hash."""
from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from kwabo.integrations.email_client import RawEmail, Attachment
from kwabo.integrations.llm_extractor import extract_from_email


@pytest.mark.asyncio
async def test_extract_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_MODE", "on")

    fake_msg = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"taal": "NL", "orderregels": []}')]
    )
    mock_create = AsyncMock(return_value=fake_msg)

    raw = RawEmail(email_id="x", email_from="a@b.nl", email_subject="s",
                   email_date="", email_body="body", bijlagen=[])

    with patch("kwabo.integrations.llm_extractor._get_client") as gc:
        gc.return_value.messages.create = mock_create
        r1 = await extract_from_email(raw)
        r2 = await extract_from_email(raw)

    assert r1 == r2 == {"taal": "NL", "orderregels": []}
    assert mock_create.call_count == 1
```

- [ ] **Step 2:** Run — expect FAIL

- [ ] **Step 3:** Pas `llm_extractor.py` aan

Voeg na `system = PROMPT_PATH.read_text(...)`:

```python
from kwabo.graph.llm_cache import cache_get, cache_key, cache_put

# ... in extract_from_email, na `blocks = _build_blocks(raw)`:
ck = cache_key(
    model or settings.anthropic_model,
    system,
    # User content = JSON-serialised blocks (includes base64 PDF data)
    __import__("json").dumps(blocks, default=str, sort_keys=True),
    extras={"max_tokens": 16000, "node": "extract"},
)
cached = cache_get(ck)
if cached is not None:
    return parse_json_loose(cached["response"])
```

Dan na de succesvolle API call, voeg toe voor de `return parse_json_loose(text)`:

```python
cache_put(ck, {"response": text, "model": model or settings.anthropic_model})
return parse_json_loose(text)
```

- [ ] **Step 4:** Run — expect PASS, plus bestaande tests nog groen

```bash
PYTHONPATH=src python -m pytest -x
```

- [ ] **Step 5:** Commit

```bash
git add backend/src/kwabo/integrations/llm_extractor.py backend/tests/test_extract_cache.py
git commit -m "feat(cache): cache extract LLM calls"
```

---

## Task 4: clear-cache script

**Files:**
- Create: `backend/scripts/clear_llm_cache.py`

- [ ] **Step 1:** Create script

```python
"""Wipe the LLM response cache."""
from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    from kwabo.config import settings

    d = Path(settings.llm_cache_dir)
    if not d.exists():
        print(f"(geen cache-dir: {d})")
        return
    n = sum(1 for _ in d.glob("*.json"))
    shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    print(f"Wiped {n} cache entries at {d}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Smoke-run

```bash
cd C:/Kwabo/kwabo-order-intake/backend
PYTHONPATH=src python scripts/clear_llm_cache.py
```

- [ ] **Step 3:** Commit

```bash
git add backend/scripts/clear_llm_cache.py
git commit -m "chore: clear-cache script"
```

---

## Task 5: Seed artikel-mappings uit 17 voorbeelden

**Files:**
- Modify: `backend/src/kwabo/db/seed.py` — breid `ARTIKEL_MAPPING_SEED` uit
- Modify: `backend/tests/test_db.py` — assert minimum aantal mappings

**Goal:** Voor elke email-klant de klant-artikelnummers die voorkomen in de voorbeeld-emails toevoegen, zodat `match_articles` via `klantenkaart`-strategie ~80% kan matchen.

- [ ] **Step 1:** Lees de 17 emails om klant-artikelnummers te extraheren

```bash
cd C:/Kwabo/kwabo-order-intake/backend
# Quick grep voor artikelnummer-patronen in de bijlage-tekst. Haal per email de 'klant_artikelnr'-waardes uit bestaande log als die is gedraaid, anders handmatig per email PDF bekijken:
PYTHONPATH=src python -c "
from pathlib import Path
from kwabo.integrations.email_client import parse_eml_file
for p in sorted(Path('tests/test_data/emails').glob('*.eml')):
    raw = parse_eml_file(p)
    print(p.name)
    for b in raw.bijlagen:
        txt = (b.inhoud_tekst or '')[:2000]
        print('  --', b.naam)
        print('    ', ' | '.join(l.strip() for l in txt.splitlines() if l.strip())[:400])
    print()
"
```

Output: lijst met artikel-regels per email. Per klant noteer de klant-artikelnummers.

- [ ] **Step 2:** Verwachte uitbreidingen

Voeg toe aan `ARTIKEL_MAPPING_SEED` (als de grep-output bevestigt dat deze nummers voorkomen):

```python
# Aanvullingen uit de 17 voorbeeld-emails
("10001", "23533", "DUMMY-FERNEY-23533", "Ferney product 23533"),
("10001", "23534", "DUMMY-FERNEY-23534", "Ferney product 23534"),
("10002", "K700100008", "DUMMY-TABS-K700100008", "TABS variant"),
("10003", "24301", "DUMMY-ISERO-24301", "Isero variant"),
("10007", "IOR26xxx", "DUMMY-STUKBOUW", "Stukbouw bestelling"),
("10008", "OT3478-A", "DUMMY-ENKA-A", "Enka OT3478 variant A"),
("10009", "IO2029003", "DUMMY-CONNECT", "Connect Products IO"),
("10010", "AB123", "DUMMY-STORCH", "Storch-Ciret Abdeckvlies"),
("10011", "238535", "DUMMY-KIRCHNER-238535", "Kirchner extra item"),
("10012", "24198", "DUMMY-DIETRICH-24198", "Werkzeuge Dietrich variant"),
("10013", "1673", "DUMMY-BUGEL-1673", "Bugel extra"),
("10015", "24463", "DUMMY-TECTIS-24463", "Tectis extra"),
("10016", "24246", "DUMMY-DEVOS-24246", "L. De Vos extra"),
```

**Belangrijk:** Pas de exacte nummers aan op wat daadwerkelijk uit de PDFs komt. Als een nummer niet in de mapping komt, past fuzzy nog steeds toe.

- [ ] **Step 3:** Uitbreiden `test_db.py`

```python
def test_seed_count_meets_minimum(session):
    from kwabo.db.models import KlantenkaartArtikel
    from sqlmodel import select
    rows = session.exec(select(KlantenkaartArtikel)).all()
    assert len(rows) >= 25, f"Seed te klein: {len(rows)} < 25"
```

- [ ] **Step 4:** Run tests

```bash
PYTHONPATH=src python -m pytest tests/test_db.py -v
```

- [ ] **Step 5:** Commit

```bash
git add backend/src/kwabo/db/seed.py backend/tests/test_db.py
git commit -m "feat(seed): expand artikel-mappings uit 17 voorbeeld-emails"
```

---

## Task 6: Kredietlimiet-warning finaliseren

**Files:**
- Modify: `backend/src/kwabo/graph/nodes/match_customer.py` — vervang placeholder rond regel 107-111
- Modify: `backend/src/kwabo/db/seed.py` — geef enkele klanten een `kredietlimiet`
- Create: `backend/tests/test_kredietlimiet.py`

**Context:** `Klantenkaart.kredietlimiet` bestaat al als Optional[float] in `models.py`. Nog niet ingevuld in seed, nog niet gebruikt voor warning.

- [ ] **Step 1:** Failing test

```python
"""match_customer zet warning als ordertotaal > kredietlimiet."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from kwabo.graph.nodes.match_customer import match_customer_node


@pytest.mark.asyncio
async def test_warning_bij_overschrijding(session, monkeypatch):
    from kwabo.db.models import Klantenkaart
    k = session.exec(__import__("sqlmodel").select(Klantenkaart).where(
        Klantenkaart.nav_klantnr == "10001")).first()
    k.kredietlimiet = 100.0
    session.add(k)
    session.commit()

    state = {
        "email_id": "k1",
        "email_from": "purchaseorders@ferney.nl",
        "email_subject": "Order",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [
            {"positie": 1, "hoeveelheid": 10, "prijs_per_eenheid": 20.0},
        ],
    }
    out = await match_customer_node(state)
    assert any("kredietlimiet" in w.lower() for w in out.get("validatie_warnings", []))


@pytest.mark.asyncio
async def test_geen_warning_onder_limiet(session):
    from kwabo.db.models import Klantenkaart
    k = session.exec(__import__("sqlmodel").select(Klantenkaart).where(
        Klantenkaart.nav_klantnr == "10001")).first()
    k.kredietlimiet = 1000.0
    session.add(k)
    session.commit()

    state = {
        "email_id": "k2",
        "email_from": "purchaseorders@ferney.nl",
        "email_subject": "Order",
        "email_body": "",
        "bijlagen": [],
        "stappen_log": [],
        "orderregels": [
            {"positie": 1, "hoeveelheid": 10, "prijs_per_eenheid": 20.0},
        ],
    }
    out = await match_customer_node(state)
    assert not any("kredietlimiet" in w.lower() for w in out.get("validatie_warnings", []))
```

- [ ] **Step 2:** Run — expect FAIL

- [ ] **Step 3:** Pas `match_customer.py` aan

Vervang de block (~regel 104-112):

```python
# 4+ signalering + kredietcheck
if match:
    if match.get("is_4plus") is False:
        warnings.append("⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden")
    krediet = match.get("kredietlimiet")
    if krediet and krediet > 0:
        # Bereken ordertotaal uit orderregels
        total = 0.0
        for r in (state.get("orderregels") or []):
            try:
                total += float(r.get("hoeveelheid") or 0) * float(r.get("prijs_per_eenheid") or 0)
            except (TypeError, ValueError):
                continue
        if total > krediet:
            warnings.append(
                f"⚠ KREDIETLIMIET OVERSCHREDEN: ordertotaal €{total:.2f} > limiet €{krediet:.2f}"
            )
            match["kredietlimiet_status"] = "overschreden"
        else:
            match["kredietlimiet_status"] = "ok"
    log.info("klant_checks", is_4plus=match.get("is_4plus"), kredietlimiet=krediet)
```

- [ ] **Step 4:** Run — expect PASS

- [ ] **Step 5:** Voeg demo-limieten toe in seed

In `KLANTEN_SEED` kan geen extra veld — voeg nieuwe helper toe in `seed()` functie na de bestaande loop:

```python
# Demo kredietlimieten (voor warning-test; realistische waarden)
DEMO_LIMITS = {"10001": 5000.0, "10011": 10000.0, "10012": 2000.0}
for nav, limit in DEMO_LIMITS.items():
    k = session.exec(select(Klantenkaart).where(Klantenkaart.nav_klantnr == nav)).first()
    if k and k.kredietlimiet is None:
        k.kredietlimiet = limit
        session.add(k)
session.commit()
```

- [ ] **Step 6:** Full test-run

```bash
PYTHONPATH=src python -m pytest -x
```

- [ ] **Step 7:** Commit

```bash
git add backend/src/kwabo/graph/nodes/match_customer.py backend/src/kwabo/db/seed.py backend/tests/test_kredietlimiet.py
git commit -m "feat(match_customer): kredietlimiet-warning bij overschrijding"
```

---

## Task 7: Regressie-harness met update-fixtures flag

**Files:**
- Create: `backend/tests/test_regression.py`
- Create: `backend/tests/test_data/expected/.gitkeep`
- Modify: `backend/tests/conftest.py` — voeg `--update-fixtures` en `--regression` CLI opties toe

**Goal:** `pytest test_regression.py` draait alle 17 emails door de pipeline, vergelijkt met `expected/*.json`. `--update-fixtures` schrijft verwachte waarden weg bij eerste groene run.

- [ ] **Step 1:** Voeg CLI opties toe aan conftest

Append aan `backend/tests/conftest.py`:

```python
def pytest_addoption(parser):
    parser.addoption("--update-fixtures", action="store_true", default=False,
                     help="Overschrijf expected/*.json met de huidige run-output")
    parser.addoption("--regression", action="store_true", default=False,
                     help="Run regressie-tests (vereist ANTHROPIC_API_KEY of gevulde cache)")


@pytest.fixture
def update_fixtures(request) -> bool:
    return request.config.getoption("--update-fixtures")
```

- [ ] **Step 2:** Schrijf harness

```python
"""End-to-end regressie-harness over alle 17 voorbeeld-emails.

Run:
  pytest tests/test_regression.py --regression           (asserts)
  pytest tests/test_regression.py --regression --update-fixtures  (refresh expected/)

Gebruikt de LLM cache — als cache leeg: eerste run slaat alles op (kost API).
Tweede run is gratis.
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
    return name.replace(".eml", "").replace(" ", "_").replace("/", "_")[:80]


def _summarise(state: dict) -> dict:
    regels = state.get("orderregels") or []
    matched = [r for r in regels if r.get("artikelnummer_kwabo_matched")]
    klant = state.get("klant_match") or {}
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
    }


EMAIL_FILES = sorted(EMAILS_DIR.glob("*.eml"))


@pytest.mark.asyncio
@pytest.mark.parametrize("email_path", EMAIL_FILES, ids=lambda p: _slug(p.name))
async def test_regression(email_path, request, session, update_fixtures, monkeypatch):
    if not request.config.getoption("--regression"):
        pytest.skip("Gebruik --regression om te draaien")

    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    state = await run_on_eml(email_path)
    actual = _summarise(state)

    expected_path = EXPECTED_DIR / f"{_slug(email_path.name)}.json"

    if update_fixtures or not expected_path.exists():
        expected_path.write_text(json.dumps(actual, indent=2, default=str), encoding="utf-8")
        pytest.skip(f"Fixture geschreven: {expected_path.name}")

    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    # Strict assertions — regressie faalt bij elke afwijking
    for key in ("is_order", "klant_nr", "taal", "n_regels"):
        assert actual[key] == expected[key], f"{key}: {actual[key]} != {expected[key]}"
    # Soepeler: matched_ratio mag niet dalen
    assert actual["n_matched"] >= expected["n_matched"], \
        f"n_matched gedaald: {actual['n_matched']} < {expected['n_matched']}"
```

- [ ] **Step 3:** Maak `expected/` dir met placeholder

```bash
mkdir -p C:/Kwabo/kwabo-order-intake/backend/tests/test_data/expected
touch C:/Kwabo/kwabo-order-intake/backend/tests/test_data/expected/.gitkeep
```

- [ ] **Step 4:** Seed-run (vult cache + expected fixtures)

```bash
cd C:/Kwabo/kwabo-order-intake/backend
# Vereist ANTHROPIC_API_KEY in environment
PYTHONPATH=src python -m pytest tests/test_regression.py --regression --update-fixtures -v
```

Expected: 17 tests "skipped (Fixture geschreven)". Cache-map vol, expected/ vol.

- [ ] **Step 5:** Tweede run — nu alle groen

```bash
PYTHONPATH=src python -m pytest tests/test_regression.py --regression -v
```

Expected: 17 passed (allemaal uit cache, snelle run).

- [ ] **Step 6:** Commit harness + fixtures

```bash
git add backend/tests/test_regression.py backend/tests/conftest.py backend/tests/test_data/expected/
git commit -m "feat(tests): regression harness over 17 voorbeeld-emails met fixture-updates"
```

---

## Task 8: `test-10x` scripts

**Files:**
- Create: `backend/scripts/test_10x.sh`
- Create: `backend/scripts/test_10x.ps1`
- Create: `backend/Makefile`

- [ ] **Step 1:** Bash script

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for i in $(seq 1 10); do
  echo "=== run $i/10 ==="
  PYTHONPATH=src python -m pytest tests/test_regression.py --regression -x --tb=short
done
echo "All 10 runs green."
```

- [ ] **Step 2:** PowerShell script

```powershell
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
1..10 | ForEach-Object {
  Write-Host "=== run $_/10 ==="
  $env:PYTHONPATH = "src"
  python -m pytest tests/test_regression.py --regression -x --tb=short
  if ($LASTEXITCODE -ne 0) { throw "Run $_ faalde" }
}
Write-Host "All 10 runs green."
```

- [ ] **Step 3:** Makefile

```makefile
.PHONY: test test-regression test-10x cache-clear

test:
	PYTHONPATH=src python -m pytest -x

test-regression:
	PYTHONPATH=src python -m pytest tests/test_regression.py --regression -v

test-10x:
	bash scripts/test_10x.sh

cache-clear:
	PYTHONPATH=src python scripts/clear_llm_cache.py
```

- [ ] **Step 4:** Maak scripts uitvoerbaar (Windows: niet nodig; bash wordt via `bash scripts/test_10x.sh` gedraaid)

- [ ] **Step 5:** Smoke-run

```bash
cd C:/Kwabo/kwabo-order-intake/backend
bash scripts/test_10x.sh
```

Expected: 10× groen (uit cache → snel).

- [ ] **Step 6:** Commit

```bash
git add backend/scripts/test_10x.sh backend/scripts/test_10x.ps1 backend/Makefile
git commit -m "feat(tests): 10x regression runner + Makefile"
```

---

## Task 9: Forwarded-parser tests uitbreiden

**Files:**
- Modify: `backend/tests/test_forwarded_parser.py`

**Goal:** De 4 forwards uit de voorbeeld-set (FW_ Inkooporder IO2029003, FW_ New order OT3478, FW_ Bestellungen Abdeckvlies 160gr, FW_ Stukbouw B.V. - IOR2601198, FW_ VO2602754 - Kirchner, Fwd_ Nieuwe order) elk asserten.

- [ ] **Step 1:** Inventariseer wat er al in de test staat

```bash
cat C:/Kwabo/kwabo-order-intake/backend/tests/test_forwarded_parser.py
```

- [ ] **Step 2:** Voeg per forward-email een test toe

```python
# Append deze helper + tests:
from pathlib import Path
from kwabo.integrations.email_client import parse_eml_file
from kwabo.integrations.forwarded_parser import detect_forward


def _load(name: str):
    p = Path(__file__).resolve().parent / "test_data" / "emails" / name
    return parse_eml_file(p)


def _detect_on_email(name: str):
    raw = _load(name)
    bijl_blob = "\n".join((b.inhoud_tekst or "") for b in raw.bijlagen)[:40000]
    return detect_forward(raw.email_from, raw.email_subject, raw.email_body, bijl_blob)


def test_forward_io2029003_detected():
    fwd = _detect_on_email("FW_ Inkooporder IO2029003.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email and "@" in fwd.original_from_email
    assert "kwabo.nl" not in fwd.original_from_email


def test_forward_ot3478_detected():
    fwd = _detect_on_email("FW_ New order OT3478.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email


def test_forward_stukbouw_detected():
    fwd = _detect_on_email("FW_ Stukbouw B.V. -  IOR2601198.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email


def test_forward_kirchner_detected():
    fwd = _detect_on_email("FW_ VO2602754 - Kirchner GmbH - 27-2-2026.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email and "kirchner" in fwd.original_from_email.lower()


def test_forward_abdeckvlies_detected():
    fwd = _detect_on_email("FW_ Bestellungen Abdeckvlies 160gr.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email


def test_forward_nieuwe_order_detected():
    fwd = _detect_on_email("Fwd_ Nieuwe order.eml")
    assert fwd.is_forwarded
    assert fwd.original_from_email
```

- [ ] **Step 3:** Run

```bash
PYTHONPATH=src python -m pytest tests/test_forwarded_parser.py -v
```

Als één of meer assertions falen (bv. email ontbreekt of parser pakt 'm niet): onderzoek `forwarded_parser.py` patterns, pas regex uit voor de specifieke forward-header.

- [ ] **Step 4:** Commit

```bash
git add backend/tests/test_forwarded_parser.py
git commit -m "test(forwarded): coverage voor 6 real-world forwards"
```

---

## Task 10: Kirchner multi-order regressie

**Files:**
- Modify: `backend/tests/test_regression.py` — voeg `sub_orders_count` toe aan fixture-summary
- Mogelijk: `backend/src/kwabo/graph/runner.py` — zorg dat sub-order log ID terugkomt

**Goal:** De fixture voor "FW_ VO2602754 - Kirchner GmbH" moet `sub_orders_count ≥ 1` hebben als de PDF meerdere orders bevat (als de LLM een array teruggeeft).

- [ ] **Step 1:** Breid `_summarise()` uit

In `backend/tests/test_regression.py`:

```python
def _summarise(state: dict) -> dict:
    # ... bestaande ...
    extras = state.get("extra_orders_raw") or []
    return {
        ...bestaande velden...
        "sub_orders_count": len(extras),
    }
```

En update de assertion-loop:

```python
# Alleen voor Kirchner (of elke email met sub_orders): assert niet gedaald
if expected.get("sub_orders_count", 0) > 0:
    assert actual["sub_orders_count"] >= expected["sub_orders_count"], \
        f"sub_orders_count gedaald"
```

- [ ] **Step 2:** Refresh fixtures

```bash
cd C:/Kwabo/kwabo-order-intake/backend
PYTHONPATH=src python -m pytest tests/test_regression.py --regression --update-fixtures -v
```

- [ ] **Step 3:** Inspecteer Kirchner fixture

```bash
cat tests/test_data/expected/FW__VO2602754_-_Kirchner_GmbH_-_27-2-2026.json
```

Als `sub_orders_count == 0` terwijl de PDF meerdere orders heeft: onderzoek `extract_v2.txt` prompt — moet array opleveren. Eventueel prompt-regel aanscherpen: "Als meerdere orders in één mail: ALTIJD JSON ARRAY met alle orders".

- [ ] **Step 4:** Run regressie → groen

```bash
PYTHONPATH=src python -m pytest tests/test_regression.py --regression -v
```

- [ ] **Step 5:** Commit

```bash
git add backend/tests/test_regression.py backend/tests/test_data/expected/
git commit -m "test(kirchner): sub_orders_count in regression fixtures"
```

---

## Task 11: Playwright setup (backend)

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/fixtures/` met 3 .eml
- Modify: `frontend/package.json` — devDep `@playwright/test`, scripts

- [ ] **Step 1:** Installeer Playwright

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm add -D @playwright/test@latest
pnpm exec playwright install chromium
```

- [ ] **Step 2:** package.json scripts

Voeg toe in `scripts`:

```json
"test:e2e": "playwright test",
"test:e2e:ui": "playwright test --ui"
```

- [ ] **Step 3:** playwright.config.ts

```ts
import { defineConfig } from "@playwright/test";

const FRONTEND_PORT = Number(process.env.FRONTEND_PORT ?? 3100);
const BACKEND_PORT = Number(process.env.BACKEND_PORT ?? 8100);

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  fullyParallel: false, // file-drop + shared db — moet sequentieel
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `cd ../backend && PYTHONPATH=src python -m uvicorn kwabo.main:app --port ${BACKEND_PORT}`,
      url: `http://localhost:${BACKEND_PORT}/docs`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: "sqlite:///./kwabo-e2e.db",
        NAVISION_MODE: "mock",
        EMAIL_MODE: "file_drop",
        INBOX_DIR: "../data/inbox_e2e",
        PROCESSED_DIR: "../data/processed_e2e",
        NAVISION_MOCK_DIR: "../data/navision_mock_e2e",
        LLM_CACHE_MODE: "on",
        LLM_CACHE_DIR: "../data/llm_cache",
      },
    },
    {
      command: `pnpm start --port ${FRONTEND_PORT}`,
      url: `http://localhost:${FRONTEND_PORT}`,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_BASE: `http://localhost:${BACKEND_PORT}` },
    },
  ],
});
```

- [ ] **Step 4:** Kopieer 3 fixture-emails

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
mkdir -p tests/fixtures
cp "../backend/tests/test_data/emails/Ferney inkooporder 4200056148.eml" tests/fixtures/
cp "../backend/tests/test_data/emails/Bestelling 4506782407 157.eml" tests/fixtures/
cp "../backend/tests/test_data/emails/Inkooporder 00176482.eml" tests/fixtures/
```

- [ ] **Step 5:** Verifieer dat de frontend de env-var `NEXT_PUBLIC_API_BASE` gebruikt

```bash
grep -rn "API_BASE\|API_URL" frontend/lib/ frontend/app/ 2>&1 | head
```

Als de frontend hardcoded `http://localhost:8000` gebruikt: pas aan naar `process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"`.

- [ ] **Step 6:** Smoke

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm build  # productie-build vereist voor pnpm start
```

- [ ] **Step 7:** Commit

```bash
git add frontend/playwright.config.ts frontend/package.json frontend/pnpm-lock.yaml frontend/tests/fixtures/
git commit -m "feat(e2e): playwright config met backend+frontend webServer"
```

---

## Task 12: Playwright smoke — queue → review → approve

**Files:**
- Create: `frontend/tests/smoke.spec.ts`
- Create: `frontend/tests/helpers.ts`

- [ ] **Step 1:** Helpers (DB reset + inbox drop)

```typescript
// tests/helpers.ts
import { test as base } from "@playwright/test";
import { promises as fs } from "fs";
import * as path from "path";

const INBOX = path.resolve(__dirname, "../../data/inbox_e2e");
const PROCESSED = path.resolve(__dirname, "../../data/processed_e2e");
const NAV_MOCK = path.resolve(__dirname, "../../data/navision_mock_e2e/orders");
const DB = path.resolve(__dirname, "../../backend/kwabo-e2e.db");
const FIX = path.resolve(__dirname, "fixtures");

async function rmrf(p: string) {
  try { await fs.rm(p, { recursive: true, force: true }); } catch {}
}

export async function resetEnv() {
  await rmrf(INBOX);  await fs.mkdir(INBOX, { recursive: true });
  await rmrf(PROCESSED);  await fs.mkdir(PROCESSED, { recursive: true });
  await rmrf(NAV_MOCK);  await fs.mkdir(NAV_MOCK, { recursive: true });
  await rmrf(DB);
}

export async function dropEml(name: string) {
  await fs.copyFile(path.join(FIX, name), path.join(INBOX, name));
}

export const BACKEND = `http://localhost:${process.env.BACKEND_PORT ?? 8100}`;

export const test = base.extend({});
```

- [ ] **Step 2:** Smoke test

```typescript
// tests/smoke.spec.ts
import { expect } from "@playwright/test";
import { test, resetEnv, dropEml, BACKEND } from "./helpers";

test.beforeEach(async ({ request }) => {
  await resetEnv();
  // Backend seed runs automatically op startup; geef 'm even tijd
});

test("queue toont 3 orders na scan", async ({ page, request }) => {
  await dropEml("Ferney inkooporder 4200056148.eml");
  await dropEml("Bestelling 4506782407 157.eml");
  await dropEml("Inkooporder 00176482.eml");

  const r = await request.post(`${BACKEND}/api/intake/scan`);
  expect(r.ok()).toBeTruthy();

  await page.goto("/");
  await expect(page.locator("table tbody tr")).toHaveCount(3, { timeout: 10_000 });
});

test("approve → Navision push → status pushed", async ({ page, request }) => {
  await dropEml("Ferney inkooporder 4200056148.eml");
  await request.post(`${BACKEND}/api/intake/scan`);

  await page.goto("/");
  await page.locator("table tbody tr").first().click();

  // Rechts op detail-pagina: "Goedkeuren & Push Navision"
  await page.getByRole("button", { name: /goedkeuren/i }).click();

  // Verwacht status-badge "pushed" ergens zichtbaar
  await expect(page.locator('text=/pushed/i').first()).toBeVisible({ timeout: 15_000 });
});
```

- [ ] **Step 3:** Run

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm test:e2e tests/smoke.spec.ts
```

Expected: 2 passed.

Debug-tips bij faal:
- `pnpm test:e2e --ui` voor interactieve debugger
- Check `test-results/` voor screenshot en trace
- Verifieer backend-log in console-output van playwright

- [ ] **Step 4:** Commit

```bash
git add frontend/tests/smoke.spec.ts frontend/tests/helpers.ts
git commit -m "test(e2e): queue → review → approve smoke"
```

---

## Task 13: Email-upload knop

**Files:**
- Modify: `frontend/app/page.tsx` — upload-knop + state
- Mogelijk: `frontend/components/upload-button.tsx` (nieuw)
- Create: `frontend/tests/upload.spec.ts`

**Context:** `POST /api/intake/upload` bestaat al. Alleen UI-knop ontbreekt.

- [ ] **Step 1:** Lees huidige page.tsx

```bash
cat C:/Kwabo/kwabo-order-intake/frontend/app/page.tsx
```

- [ ] **Step 2:** Voeg upload-component toe

```tsx
// frontend/components/upload-button.tsx
"use client";
import { useState, useRef } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export function UploadButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  async function handle(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true); setError(null);
    try {
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch(`${API}/api/intake/upload`, { method: "POST", body: fd });
        if (!r.ok) throw new Error(`upload ${f.name}: HTTP ${r.status}`);
      }
      onDone?.();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div className="flex items-center gap-3">
      <input
        ref={ref}
        type="file"
        accept=".eml"
        multiple
        onChange={(e) => handle(e.target.files)}
        className="hidden"
        data-testid="eml-upload-input"
      />
      <button
        onClick={() => ref.current?.click()}
        disabled={busy}
        data-testid="eml-upload-button"
        className="px-4 py-2 rounded-md bg-[#0b2545] text-white hover:bg-[#13345e] disabled:opacity-50"
      >
        {busy ? "Bezig…" : "Upload .eml"}
      </button>
      {error && <span className="text-rose-600 text-sm">{error}</span>}
    </div>
  );
}
```

- [ ] **Step 3:** Integreer in page.tsx

Zoek de header/stat-cards-sectie en voeg de knop toe naast de titel of bij een filter-bar. Voorbeeld:

```tsx
import { UploadButton } from "@/components/upload-button";

// binnen de page-component, bovenaan naast stat-cards:
<div className="flex items-center justify-between mb-4">
  <h1 className="text-2xl font-semibold">Order Queue</h1>
  <UploadButton onDone={() => window.location.reload()} />
</div>
```

- [ ] **Step 4:** Playwright test

```typescript
// frontend/tests/upload.spec.ts
import { expect } from "@playwright/test";
import { test, resetEnv } from "./helpers";
import * as path from "path";

test.beforeEach(resetEnv);

test("upload .eml verschijnt in queue", async ({ page }) => {
  await page.goto("/");
  const initialCount = await page.locator("table tbody tr").count();

  const file = path.resolve(__dirname, "fixtures/Ferney inkooporder 4200056148.eml");
  await page.locator('[data-testid="eml-upload-input"]').setInputFiles(file);

  // na upload: pagina reload door onDone — nieuwe order verschijnt
  await expect(page.locator("table tbody tr")).toHaveCount(initialCount + 1, { timeout: 30_000 });
});
```

- [ ] **Step 5:** Run

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm build
pnpm test:e2e tests/upload.spec.ts
```

- [ ] **Step 6:** Commit

```bash
git add frontend/app/page.tsx frontend/components/upload-button.tsx frontend/tests/upload.spec.ts
git commit -m "feat(ui): upload .eml knop in queue"
```

---

## Task 14: Prijsafspraken UI-tab

**Files:**
- Create: `frontend/components/prijsafspraken-tab.tsx`
- Modify: `frontend/app/klanten/[nr]/page.tsx` (of de bestaande `klant-tabs.tsx`) — tab toevoegen
- Modify: `frontend/lib/api.ts` — helpers voor prijsafspraken CRUD
- Create: `frontend/tests/prijsafspraken.spec.ts`

- [ ] **Step 1:** Inventariseer huidige klant-detail-pagina

```bash
cat C:/Kwabo/kwabo-order-intake/frontend/app/klanten/\[nr\]/*.tsx
cat C:/Kwabo/kwabo-order-intake/frontend/lib/api.ts
```

- [ ] **Step 2:** API-helpers toevoegen

In `frontend/lib/api.ts` (of maak nieuwe module), voeg toe:

```typescript
export type Prijsafspraak = {
  id: number;
  klant_nr: string;
  kwabo_artikelnr: string;
  prijs: number;
  type: string;
  min_hoeveelheid: number | null;
  geldig_van: string | null;
  geldig_tot: string | null;
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function listPrijsafspraken(nr: string): Promise<Prijsafspraak[]> {
  const r = await fetch(`${API}/api/prijsafspraken/${nr}/prijsafspraken`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function addPrijsafspraak(nr: string, body: Partial<Prijsafspraak>) {
  const r = await fetch(`${API}/api/prijsafspraken/${nr}/prijsafspraken`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function deletePrijsafspraak(nr: string, id: number) {
  const r = await fetch(`${API}/api/prijsafspraken/${nr}/prijsafspraken/${id}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}
```

- [ ] **Step 3:** Tab-component

```tsx
// frontend/components/prijsafspraken-tab.tsx
"use client";
import { useEffect, useState } from "react";
import { listPrijsafspraken, addPrijsafspraak, deletePrijsafspraak, Prijsafspraak } from "@/lib/api";

export function PrijsafsprakenTab({ klantNr }: { klantNr: string }) {
  const [items, setItems] = useState<Prijsafspraak[]>([]);
  const [artnr, setArtnr] = useState("");
  const [prijs, setPrijs] = useState("");
  const [type, setType] = useState("standaard");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try { setItems(await listPrijsafspraken(klantNr)); }
    catch (e: any) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [klantNr]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await addPrijsafspraak(klantNr, {
        kwabo_artikelnr: artnr, prijs: parseFloat(prijs), type,
      });
      setArtnr(""); setPrijs("");
      await load();
    } catch (e: any) { setErr(e.message); }
  }

  async function handleDelete(id: number) {
    try { await deletePrijsafspraak(klantNr, id); await load(); }
    catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="space-y-4" data-testid="prijsafspraken-tab">
      <form onSubmit={handleAdd} className="flex gap-2 flex-wrap items-end">
        <label className="flex flex-col">
          <span className="text-sm text-slate-600">Kwabo artikelnr</span>
          <input
            required value={artnr} onChange={(e) => setArtnr(e.target.value)}
            data-testid="pa-artnr" className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-slate-600">Prijs</span>
          <input
            required type="number" step="0.01" value={prijs}
            onChange={(e) => setPrijs(e.target.value)}
            data-testid="pa-prijs" className="border rounded px-2 py-1 w-24"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-sm text-slate-600">Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}
                  data-testid="pa-type" className="border rounded px-2 py-1">
            <option value="standaard">standaard</option>
            <option value="mix">mix</option>
            <option value="pallet">pallet</option>
            <option value="topcoat">topcoat</option>
          </select>
        </label>
        <button type="submit" data-testid="pa-add"
                className="px-3 py-1 bg-[#0b2545] text-white rounded">Toevoegen</button>
      </form>
      {err && <div className="text-rose-600 text-sm">{err}</div>}
      <table className="w-full text-sm">
        <thead><tr className="bg-slate-50">
          <th className="text-left p-2">Kwabo art</th>
          <th className="text-left p-2">Prijs</th>
          <th className="text-left p-2">Type</th>
          <th className="p-2"></th>
        </tr></thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.id} data-testid={`pa-row-${p.kwabo_artikelnr}`}>
              <td className="p-2">{p.kwabo_artikelnr}</td>
              <td className="p-2">€ {p.prijs.toFixed(2)}</td>
              <td className="p-2">{p.type}</td>
              <td className="p-2">
                <button onClick={() => handleDelete(p.id)}
                        data-testid={`pa-del-${p.kwabo_artikelnr}`}
                        className="text-rose-600 hover:underline">verwijder</button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={4} className="p-4 text-slate-500 text-center">Geen prijsafspraken.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4:** Koppel aan klant-detail

Zoek in `klanten/[nr]/` de bestaande tab-switch en voeg een nieuwe tab "Prijsafspraken" toe. Als er een `klant-tabs.tsx` bestaat dat een `tabs`-array heeft: voeg `{id: "prijsafspraken", label: "Prijsafspraken"}` toe en render `<PrijsafsprakenTab klantNr={nr} />` wanneer actief.

- [ ] **Step 5:** Playwright test

```typescript
// frontend/tests/prijsafspraken.spec.ts
import { expect } from "@playwright/test";
import { test, resetEnv } from "./helpers";

test.beforeEach(resetEnv);

test("prijsafspraken CRUD", async ({ page }) => {
  await page.goto("/klanten/10001");
  await page.getByRole("tab", { name: /prijsafspraken/i }).click().catch(async () => {
    // Als tabs niet via ARIA: klik op button met tekst
    await page.getByRole("button", { name: /prijsafspraken/i }).click();
  });

  await expect(page.locator('[data-testid="prijsafspraken-tab"]')).toBeVisible();

  await page.locator('[data-testid="pa-artnr"]').fill("TEST-999");
  await page.locator('[data-testid="pa-prijs"]').fill("9.99");
  await page.locator('[data-testid="pa-add"]').click();

  await expect(page.locator('[data-testid="pa-row-TEST-999"]')).toBeVisible();

  await page.locator('[data-testid="pa-del-TEST-999"]').click();
  await expect(page.locator('[data-testid="pa-row-TEST-999"]')).toHaveCount(0);
});
```

- [ ] **Step 6:** Run

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm build && pnpm test:e2e tests/prijsafspraken.spec.ts
```

- [ ] **Step 7:** Commit

```bash
git add frontend/components/prijsafspraken-tab.tsx frontend/app/klanten/ frontend/lib/api.ts frontend/tests/prijsafspraken.spec.ts
git commit -m "feat(ui): prijsafspraken CRUD tab op klant-detail"
```

---

## Task 15: Forwarded-email e2e check

**Files:**
- Create: `frontend/tests/forwarded.spec.ts`

**Goal:** Verifieer dat op de order-review pagina de juiste (originele) klant gematcht is bij een forwarded email.

- [ ] **Step 1:** Kopieer 1 forward naar fixtures

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
cp "../backend/tests/test_data/emails/FW_ VO2602754 - Kirchner GmbH - 27-2-2026.eml" tests/fixtures/kirchner-forward.eml
```

- [ ] **Step 2:** Test

```typescript
import { expect } from "@playwright/test";
import { test, resetEnv, dropEml, BACKEND } from "./helpers";
import { promises as fs } from "fs";
import * as path from "path";

test.beforeEach(resetEnv);

test("forwarded email matcht originele klant (Kirchner)", async ({ page, request }) => {
  // dropEml helper verwacht naam binnen fixtures/; alternatief: manual copy
  const src = path.resolve(__dirname, "fixtures/kirchner-forward.eml");
  const dst = path.resolve(__dirname, "../../data/inbox_e2e/kirchner-forward.eml");
  await fs.copyFile(src, dst);

  const r = await request.post(`${BACKEND}/api/intake/scan`);
  expect(r.ok()).toBeTruthy();

  await page.goto("/");
  await page.locator("table tbody tr").first().click();

  // Klant-kaart moet Kirchner noemen (niet bv. Kwabo-medewerker)
  await expect(page.locator("body")).toContainText(/kirchner/i, { timeout: 15_000 });
});
```

- [ ] **Step 3:** Run

```bash
pnpm test:e2e tests/forwarded.spec.ts
```

- [ ] **Step 4:** Commit

```bash
git add frontend/tests/forwarded.spec.ts frontend/tests/fixtures/kirchner-forward.eml
git commit -m "test(e2e): forwarded email matcht originele klant"
```

---

## Task 16: Dev-mode hydration — onderzoek + documenteer

**Files:**
- Modify: `frontend/next.config.ts` (optioneel)
- Modify: `README.md` — sectie "Dev-mode op Windows"

**Context:** STATUS.md meldt dat `pnpm dev` op Windows hydration-fails oplevert met Next 16 + Turbopack. Handmatige test bepaalt wat er werkt.

- [ ] **Step 1:** Test `--no-turbo` flag

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm exec next dev --no-turbo -p 3200
# In browser: http://localhost:3200 — open devtools → console.
# Verwacht: geen hydration error. Klik "Upload .eml"-knop — werkt deze?
# Stop met Ctrl+C.
```

- [ ] **Step 2:** Als `--no-turbo` werkt

Voeg toe aan `package.json`:

```json
"scripts": {
  "dev": "next dev --no-turbo",
  "dev:turbo": "next dev"
}
```

Documenteer in README (sectie "Dev-mode"): `pnpm dev` werkt; `pnpm dev:turbo` is experimenteel en kan hydration-issues geven op Windows.

- [ ] **Step 3:** Als `--no-turbo` niet werkt

Behoud `pnpm start` (productie-build) als canonieke dev-flow. Documenteer in README de workaround en dat Playwright tegen productie draait.

- [ ] **Step 4:** Commit

```bash
git add frontend/package.json README.md frontend/next.config.ts
git commit -m "docs(frontend): dev-mode op Windows — werkend commando"
```

---

## Task 17: Toast + loading states (error-polish)

**Files:**
- Create: `frontend/components/toaster.tsx` (sonner-based)
- Modify: `frontend/app/layout.tsx` — `<Toaster />` toevoegen
- Modify: `frontend/components/upload-button.tsx` — toast i.p.v. inline error
- Modify: de order-review approve-button (waar die ook zit) — loading spinner
- Create: `frontend/tests/error-toast.spec.ts`

- [ ] **Step 1:** Installeer sonner

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm add sonner
```

- [ ] **Step 2:** Toaster-component

```tsx
// frontend/components/toaster.tsx
"use client";
import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      richColors
      closeButton
      toastOptions={{
        duration: 5000,
      }}
    />
  );
}
```

- [ ] **Step 3:** Koppel in layout.tsx

Voeg import en component-render toe:

```tsx
import { Toaster } from "@/components/toaster";

// in <body>:
{children}
<Toaster />
```

- [ ] **Step 4:** Gebruik toast in upload-button (vervang inline error)

In `upload-button.tsx`:

```tsx
import { toast } from "sonner";

// vervang setError-calls:
// catch: toast.error(`Upload mislukt: ${e.message}`)
// success (na loop): toast.success(`${files.length} bestand(en) geüpload`)
```

- [ ] **Step 5:** Approve-button loading

Zoek de approve-button in order-review (bijv. `orders/[id]/order-review.tsx`). Voeg `useState` voor `busy`, disable tijdens call, toon spinner. Bij error: `toast.error`.

- [ ] **Step 6:** Sad-path test

```typescript
// frontend/tests/error-toast.spec.ts
import { expect } from "@playwright/test";
import { test, resetEnv, BACKEND } from "./helpers";
import * as path from "path";

test.beforeEach(resetEnv);

test("upload van non-eml toont toast-error", async ({ page }) => {
  await page.goto("/");
  // Maak tijdelijk NEP-bestand (geen .eml → backend 400)
  const badFile = path.resolve(__dirname, "fixtures/bad.txt");
  await require("fs").promises.writeFile(badFile, "niet een eml");
  await page.locator('[data-testid="eml-upload-input"]').setInputFiles(badFile);

  // Sonner toast verschijnt met error
  await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({ timeout: 5_000 });
});
```

- [ ] **Step 7:** Run

```bash
pnpm build && pnpm test:e2e
```

- [ ] **Step 8:** Commit

```bash
git add frontend/components/toaster.tsx frontend/components/upload-button.tsx frontend/app/layout.tsx frontend/app/orders/ frontend/package.json frontend/tests/error-toast.spec.ts
git commit -m "feat(ui): sonner toasts + loading spinner op approve"
```

---

## Task 18: Final — 10× regressie + Playwright suite

**Files:** geen nieuwe

- [ ] **Step 1:** Schone cache-run om te bevestigen dat nieuwe cache vanaf 0 gevuld wordt

```bash
cd C:/Kwabo/kwabo-order-intake/backend
PYTHONPATH=src python scripts/clear_llm_cache.py
# (vereist ANTHROPIC_API_KEY)
PYTHONPATH=src python -m pytest tests/test_regression.py --regression -v
```

Expected: alle 17 groen (eerste run doet API calls, traag). Cache is nu gevuld.

- [ ] **Step 2:** `test-10x`

```bash
bash scripts/test_10x.sh
```

Expected: 10× groen, < 1 minuut per run (cached).

- [ ] **Step 3:** Playwright volledige suite

```bash
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm build
pnpm test:e2e
```

Expected: alle tests groen.

- [ ] **Step 4:** Handmatige rook-test (10 punten uit STATUS.md)

```bash
# 1) schone start
cd C:/Kwabo/kwabo-order-intake/backend
rm -f kwabo.db kwabo.log
rm -f ../data/navision_mock/orders/*.json
PYTHONPATH=src python -m uvicorn kwabo.main:app --port 8000 &

# 2) frontend
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm build && pnpm start --port 3000 &

# 3) drop 3 emails + scan
cp "../backend/tests/test_data/emails/Ferney inkooporder 4200056148.eml" ../data/inbox/
cp "../backend/tests/test_data/emails/Bestelling 4506782407 157.eml" ../data/inbox/
cp "../backend/tests/test_data/emails/Inkooporder 00176482.eml" ../data/inbox/
curl -X POST http://localhost:8000/api/intake/scan
```

Open browser → doorloop de 10 punten uit STATUS.md ("Test-plan om het zelf na te lopen", regel 101-132):
1. / queue toont 3 orders ✓
2. /logs streamt ✓
3. Klik een `#` → review-pagina ✓
4. Order regels zichtbaar ✓
5. Upload .eml-knop werkt (vierde order verschijnt) ✓
6. Goedkeuren → status pushed + Nav-nr verschijnt ✓
7. `data/navision_mock/orders/SO-xxx.json` bestaat ✓
8. /audit stats kloppen ✓
9. /klanten/10002 toont mappings + prijsafspraken-tab ✓
10. /docs toont alle endpoints ✓

- [ ] **Step 5:** Final commit

```bash
cd C:/Kwabo/kwabo-order-intake
git status
git add -A  # nog wat losse fixtures / logs gitignored
git commit -m "chore: green regressie + playwright suite"  # alleen als er nog iets te committen is
```

---

## Self-review addendum

Dit plan dekt:
- ✅ LLM cache (Task 1–4)
- ✅ Seed-uitbreiding (Task 5)
- ✅ Kredietlimiet (Task 6)
- ✅ Regressie-harness + 10× (Task 7–8, 18)
- ✅ Forwarded-parser coverage (Task 9)
- ✅ Kirchner multi-order regressie (Task 10)
- ✅ Playwright setup + smoke (Task 11–12)
- ✅ Upload-knop (Task 13)
- ✅ Prijsafspraken UI (Task 14)
- ✅ Forwarded e2e (Task 15)
- ✅ Dev-mode hydration (Task 16)
- ✅ Toast + spinner (Task 17)

**Open risico's bij uitvoering:**
- Seed-uitbreiding (Task 5): exacte artikelnummers uit PDF-content moeten bevestigd; dummy-nummers zijn OK zolang ze niet botsen.
- Playwright webServer op Windows: als `uvicorn`-spawn via cmd-syntax faalt, splits commando in `cmd /c`-wrapper.
- Real Kirchner-multi-PDF: als LLM één order returned waar er twee zijn, moet `extract_v2.txt` prompt aangescherpt worden (valt onder Task 10).
- Als `--no-turbo` flag niet bestaat in Next 16: Task 16 valt terug op documenteren van `pnpm start`.
