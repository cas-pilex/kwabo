"""classify_node moet cache raken bij 2e identieke call."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from kwabo.graph.nodes.classify import classify_node


@pytest.mark.asyncio
async def test_cache_hit_on_second_call(tmp_path, monkeypatch):
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

    # Verify cache file was actually created on disk
    cache_files = list(Path(tmp_path).glob("*.json"))
    assert len(cache_files) == 1, f"expected 1 cache file, got {len(cache_files)}"
