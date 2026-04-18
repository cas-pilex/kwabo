"""Snelle unit-tests op pure functies (geen LLM/DB calls nodig)."""
from __future__ import annotations

import pytest

from kwabo.api.preview import _all_needs_review_paths, _get, _set, _split_path
from kwabo.integrations.navision_api import build_sales_order_payload
from kwabo.utils.eenheid_mapping import normalize_eenheid
from kwabo.utils.json_parser import parse_json_loose


class TestEenheid:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Rolle", "ROL"),
            ("ROL", "ROL"),
            ("stuks", "STUK"),
            ("pcs", "STUK"),
            ("m²", "M2"),
            ("pallet", "PAL"),
            (None, "STUK"),
            ("", "STUK"),
            ("onbekend", "ONBEKEND"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_eenheid(raw) == expected


class TestJsonParser:
    def test_strips_code_fence(self):
        assert parse_json_loose('```json\n{"a":1}\n```') == {"a": 1}

    def test_plain(self):
        assert parse_json_loose('{"a":1}') == {"a": 1}

    def test_array(self):
        assert parse_json_loose("[1,2,3]") == [1, 2, 3]

    def test_with_prose_prefix(self):
        assert parse_json_loose('Here is the answer: {"x":42}') == {"x": 42}

    def test_truncated_array_repaired(self):
        # Incomplete second element
        text = '[{"a":1},{"a":2},{"a":'
        result = parse_json_loose(text)
        assert len(result) == 2
        assert result[0]["a"] == 1


class TestPathUtils:
    def test_split_simple(self):
        assert _split_path("a.b.c") == ["a", "b", "c"]

    def test_split_with_index(self):
        assert _split_path("orderregels[2].prijs_per_eenheid") == ["orderregels", 2, "prijs_per_eenheid"]

    def test_get_nested(self):
        state = {"orderregels": [{"prijs": 10}, {"prijs": 20}]}
        assert _get(state, "orderregels[1].prijs") == 20

    def test_set_creates_path(self):
        state = {}
        _set(state, "orderregels[0].artikelnummer_kwabo_matched", "X")
        assert state == {"orderregels": [{"artikelnummer_kwabo_matched": "X"}]}


class TestNeedsReviewPaths:
    def test_aggregation(self):
        state = {
            "_meta": {
                "klant_match": {"needs_review": True},
                "gewenste_leverdatum": {"needs_review": False},
                "orderregels": [
                    {"prijs_per_eenheid": {"needs_review": True}},
                    {"artikelnummer_kwabo_matched": {"needs_review": True}, "prijs_per_eenheid": {"needs_review": False}},
                ],
            }
        }
        paths = _all_needs_review_paths(state)
        assert "klant_match" in paths
        assert "orderregels[0].prijs_per_eenheid" in paths
        assert "orderregels[1].artikelnummer_kwabo_matched" in paths
        assert len(paths) == 3


class TestNavisionPayload:
    def test_builds_header_and_lines(self):
        state = {
            "klant_match": {"navision_klantnr": "10001"},
            "bestelnummer_klant": "PO-123",
            "gewenste_leverdatum": "2026-05-01",
            "afleveradres": {"naam": "A", "straat": "B 1", "postcode": "1000AA", "plaats": "AMS", "land": "NL"},
            "orderregels": [
                {"artikelnummer_kwabo_matched": "1515", "hoeveelheid": 10, "eenheid": "ROL", "prijs_per_eenheid": 15, "prijs_validated": True},
                {"artikelnummer_kwabo_matched": None, "hoeveelheid": 5, "eenheid": "STUK"},  # skipped
            ],
        }
        payload = build_sales_order_payload(state)
        assert payload["header"]["customerNumber"] == "10001"
        assert payload["header"]["externalDocumentNumber"] == "PO-123"
        assert payload["header"]["shipToName"] == "A"
        assert len(payload["lines"]) == 1
        assert payload["lines"][0]["itemNumber"] == "1515"
        assert payload["lines"][0]["unitPrice"] == 15

    def test_skips_price_when_not_validated(self):
        state = {
            "klant_match": {"navision_klantnr": "10001"},
            "orderregels": [
                {"artikelnummer_kwabo_matched": "X", "hoeveelheid": 1, "eenheid": "STUK", "prijs_per_eenheid": 10, "prijs_validated": False},
            ],
        }
        payload = build_sales_order_payload(state)
        assert "unitPrice" not in payload["lines"][0]
