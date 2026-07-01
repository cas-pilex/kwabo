"""Configuratie-endpoints: prompts (override/rollback/reset) + instellingen.

Draait zonder LLM-calls. Gebruikt de `client`-fixture uit conftest, die
db.session.engine naar de test-DB rebindt — config_store leest de engine
dynamisch, dus resolve_prompt/effective_setting zien diezelfde test-DB.
"""
from __future__ import annotations


def test_list_prompts_defaults_to_file(client):
    from kwabo.config_store import default_prompt_text

    r = client.get("/api/config/prompts")
    assert r.status_code == 200
    prompts = {p["key"]: p for p in r.json()}
    assert set(prompts) == {"classify", "extract"}
    for key, p in prompts.items():
        assert p["is_overridden"] is False
        assert p["content"] == default_prompt_text(key)
        assert p["active_version_id"] is None


def test_save_prompt_takes_effect_immediately(client):
    from kwabo.config_store import resolve_prompt

    new_text = "SYSTEM: test-override voor classify\nGeef JSON terug."
    r = client.put("/api/config/prompts/classify", json={"content": new_text, "note": "test"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_overridden"] is True
    assert body["content"] == new_text

    # Resolver (wat de agent gebruikt) ziet de wijziging meteen.
    assert resolve_prompt("classify") == new_text
    # Andere prompt blijft ongemoeid.
    r2 = client.get("/api/config/prompts")
    extract = next(p for p in r2.json() if p["key"] == "extract")
    assert extract["is_overridden"] is False


def test_empty_prompt_rejected(client):
    r = client.put("/api/config/prompts/classify", json={"content": "   "})
    assert r.status_code == 400


def test_unknown_prompt_404(client):
    assert client.put("/api/config/prompts/nope", json={"content": "x"}).status_code == 404
    assert client.get("/api/config/prompts/nope/versions").status_code == 404


def test_versions_and_rollback(client):
    from kwabo.config_store import resolve_prompt

    client.put("/api/config/prompts/classify", json={"content": "versie A"})
    client.put("/api/config/prompts/classify", json={"content": "versie B"})
    assert resolve_prompt("classify") == "versie B"

    versions = client.get("/api/config/prompts/classify/versions").json()
    assert len(versions) == 2
    assert versions[0]["is_active"] is True  # nieuwste eerst
    version_a = next(v for v in versions if v["content"] == "versie A")

    r = client.post(f"/api/config/prompts/classify/rollback/{version_a['id']}")
    assert r.status_code == 200
    assert r.json()["content"] == "versie A"
    assert resolve_prompt("classify") == "versie A"
    # Rollback voegt een nieuwe (derde) versie toe — historie blijft lineair.
    assert len(client.get("/api/config/prompts/classify/versions").json()) == 3


def test_reset_restores_file_default(client):
    from kwabo.config_store import default_prompt_text, resolve_prompt

    client.put("/api/config/prompts/extract", json={"content": "afwijkend"})
    assert resolve_prompt("extract") != default_prompt_text("extract")

    r = client.post("/api/config/prompts/extract/reset")
    assert r.status_code == 200
    assert resolve_prompt("extract") == default_prompt_text("extract")
    # Er is nog een actieve override-rij, maar de inhoud = het bestand.
    assert r.json()["is_overridden"] is True


def test_settings_get_and_override(client):
    from kwabo.config import settings
    from kwabo.config_store import effective_setting

    rows = {s["key"]: s for s in client.get("/api/config/settings").json()}
    assert rows["anthropic_model"]["value"] == settings.anthropic_model
    assert rows["anthropic_model"]["is_overridden"] is False

    r = client.put("/api/config/settings", json={"anthropic_model": "claude-opus-4-8", "llm_temperature": 0.4})
    assert r.status_code == 200
    assert effective_setting("anthropic_model", settings.anthropic_model) == "claude-opus-4-8"
    assert effective_setting("llm_temperature", 0.0) == 0.4

    rows2 = {s["key"]: s for s in r.json()}
    assert rows2["anthropic_model"]["is_overridden"] is True
    assert rows2["llm_temperature"]["value"] == 0.4


def test_settings_unknown_key_rejected(client):
    r = client.put("/api/config/settings", json={"totally_unknown": 1})
    assert r.status_code == 400


def test_steps_overview(client):
    d = client.get("/api/config/steps").json()
    keys = [s["key"] for s in d["steps"]]
    assert keys[:3] == ["intake", "classify", "extract"]
    llm_steps = [s for s in d["steps"] if s["type"] == "llm-prompt"]
    assert {s["prompt_key"] for s in llm_steps} == {"classify", "extract"}
