"""File-based content-addressable cache voor LLM-calls.

Key = SHA-256(model + system + user + sorted(extras)).
Storage = {LLM_CACHE_DIR}/{key}.json with {model, response, input_tokens, output_tokens, ts}.
Mode (env LLM_CACHE_MODE): 'on' (read+write) | 'read-only' (read, no write) | 'off' (bypass).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
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
    tmp = path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try:
        tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        # Cache write failures should never break the caller — just skip.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
