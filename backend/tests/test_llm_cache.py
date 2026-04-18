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


def test_cache_put_swallows_os_errors(tmp_path, monkeypatch):
    """cache_put must never raise — cache failures can't break the caller."""
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE_MODE", "on")
    key = cache_key("m", "s", "u", extras={})

    # Simulate a write failure by patching Path.replace to raise
    from unittest.mock import patch
    with patch("pathlib.Path.replace", side_effect=OSError("simulated")):
        # Should NOT raise
        cache_put(key, {"response": "x"})
