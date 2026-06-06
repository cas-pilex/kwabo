"""Tests for the pure mix-code parser (utils/mixcode)."""
from __future__ import annotations

import pytest

from kwabo.utils.mixcode import is_mix_code, parse_mix_code


@pytest.mark.parametrize(
    "code,m,r",
    [
        ("M33PAL35", 33, 35),
        ("M1PAL30", 1, 30),
        ("M10PAL35", 10, 35),
        ("m7pal30", 7, 30),  # case-insensitive
        ("M33PAL60", 33, 60),
    ],
)
def test_parse_valid(code, m, r):
    mc = parse_mix_code(code)
    assert mc is not None
    assert mc.m_threshold == m
    assert mc.rolls_per_pallet == r
    assert mc.code == code.strip().upper()
    assert is_mix_code(code) is True


@pytest.mark.parametrize(
    "code",
    ["", None, "PALLET", "PALLET22", "STUK", "MIX", "M1", "MPAL30", "M1PAL", "PAL30", "AFHAAL"],
)
def test_parse_invalid(code):
    assert parse_mix_code(code) is None
    assert is_mix_code(code) is False
