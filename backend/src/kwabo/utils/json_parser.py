"""Robuuste JSON parsing van LLM output."""
from __future__ import annotations

import json
import re
from typing import Any


def parse_json_loose(text: str) -> Any:
    """Parse JSON from LLM output, tolerating code-fences and prose."""
    if not text:
        raise ValueError("Empty LLM response")
    # Strip triple-backtick code fences
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first { or [ and matching close
    start = min(
        [i for i in (text.find("{"), text.find("[")) if i >= 0],
        default=-1,
    )
    if start < 0:
        raise ValueError(f"No JSON object/array found in: {text[:200]}")
    # Scan via bracket balance to find the first complete JSON object/array
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
    # Truncated JSON: try to repair by trimming to last complete element
    try:
        return _repair_truncated(text[start:], open_ch)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not parse JSON from: {text[:200]}") from e


def _repair_truncated(text: str, open_ch: str) -> Any:
    """Best-effort: cut at last complete ',' sibling then close the structure."""
    # Walk forward with bracket/string tracking, record depths and last ','
    last_safe = -1  # index of last comma at depth==1 in string
    depth = 0
    in_str = False
    esc = False
    for i, c in enumerate(text):
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == "," and depth == 1:
            last_safe = i
    if last_safe <= 0:
        raise ValueError("No safe truncation point")
    truncated = text[:last_safe] + ("}" if open_ch == "[" else "}")
    # Rebalance: add closing for the outermost wrapper
    if open_ch == "[":
        truncated = text[:last_safe] + "]"
    return json.loads(truncated)
