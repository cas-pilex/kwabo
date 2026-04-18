"""extract_from_email cachet per (prompt, blocks) hash."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from kwabo.integrations.email_client import RawEmail
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

    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
