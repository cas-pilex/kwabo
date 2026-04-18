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
    # Try repairing unescaped inner double-quotes
    repaired = _repair_inner_quotes(text)
    if repaired is not None:
        try:
            return json.loads(repaired)
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
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    repaired = _repair_inner_quotes(candidate)
                    if repaired is not None:
                        try:
                            return json.loads(repaired)
                        except json.JSONDecodeError:
                            pass
                    break
    # Truncated JSON: try to repair by trimming to last complete element
    try:
        return _repair_truncated(text[start:], open_ch)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not parse JSON from: {text[:200]}") from e


def _repair_inner_quotes(text: str) -> str | None:
    """Best-effort fix for unescaped double-quotes INSIDE JSON string values.

    Heuristic: we walk the text tracking string-boundaries. A `"` closes a
    string ONLY if the next non-whitespace char is a JSON structural char
    (`,`, `:`, `}`, `]`) or EOF. If a `"` appears mid-string where the next
    non-whitespace char is a letter/digit/etc, we treat it as an unescaped
    inner quote and backslash-escape it.

    Returns the repaired text, or None if nothing was changed.
    """
    out: list[str] = []
    changed = False
    in_str = False
    esc = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if esc:
            out.append(c)
            esc = False
            i += 1
            continue
        if c == "\\":
            out.append(c)
            esc = True
            i += 1
            continue
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        # Inside a string
        if c != '"':
            out.append(c)
            i += 1
            continue
        # c == '"': decide if this closes the string
        # Look ahead, skipping whitespace
        j = i + 1
        while j < n and text[j] in " \t\r\n":
            j += 1
        nxt = text[j] if j < n else ""
        if nxt in (",", ":", "}", "]", ""):
            # Legitimate closing quote
            out.append(c)
            in_str = False
            i += 1
        else:
            # Unescaped inner quote -> escape it
            out.append("\\\"")
            changed = True
            i += 1
    return "".join(out) if changed else None


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
