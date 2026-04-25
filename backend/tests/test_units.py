"""Snelle unit-tests op pure functies (geen LLM/DB calls nodig)."""
from __future__ import annotations

import pytest

from kwabo.api.preview import _all_needs_review_paths, _get, _set, _split_path
from kwabo.integrations.navision_steps import compose_navision_operations
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

    def test_unescaped_inner_quote_repaired(self):
        # LLM sometimes emits unescaped inner double-quotes in string values
        text = '{"desc":"Vlies "OHL-BLUE" mit Folie","n":2}'
        result = parse_json_loose(text)
        assert result["n"] == 2
        assert "OHL-BLUE" in result["desc"]

    def test_unescaped_inner_quote_in_array(self):
        # Realistic multi-order LLM response with inner quote in one element
        text = '```json\n[{"a":"ok"},{"b":"has "inner" quote","c":3}]\n```'
        result = parse_json_loose(text)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["a"] == "ok"
        assert result[1]["c"] == 3


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


class TestNavisionOperations:
    """Post-T9: pipeline emits a chronological NavOperation list, not a flat
    {header, lines} payload. These tests cover the new shape."""

    def test_builds_header_and_line_ops(self):
        state = {
            "klant_match": {"navision_klantnr": "10001"},
            "bestelnummer_klant": "PO-123",
            "gewenste_leverdatum": "2026-05-01",
            "orderregels": [
                {"artikelnummer_kwabo_matched": "1515", "hoeveelheid": 10, "eenheid": "ROL"},
                {"artikelnummer_kwabo_matched": None, "hoeveelheid": 5, "eenheid": "STUK"},  # skipped
            ],
        }
        ops = compose_navision_operations(state)

        # First op MUST be the customer POST (single field, no triggers bypassed).
        assert ops[0]["op"] == "POST"
        assert ops[0]["path"] == "/salesOrders"
        assert ops[0]["body"] == {"customerNumber": "10001"}

        # PO number + dates are PATCHes — one field each.
        po_patches = [o for o in ops if o.get("body", {}).get("externalDocumentNumber")]
        assert po_patches and po_patches[0]["body"] == {"externalDocumentNumber": "PO-123"}

        # Only the matched line is emitted.
        line_posts = [o for o in ops if o["path"].endswith("/salesOrderLines") and o["op"] == "POST"]
        assert len(line_posts) == 1
        assert line_posts[0]["body"] == {"lineType": "Item", "itemNumber": "1515"}

        # Quantity PATCH is single-field.
        qty_patches = [
            o for o in ops
            if o["op"] == "PATCH"
            and o["path"].startswith("/salesOrderLines")
            and "quantity" in o["body"]
        ]
        assert qty_patches and qty_patches[0]["body"] == {"quantity": 10}

    def test_no_klant_yields_empty(self):
        ops = compose_navision_operations({"orderregels": []})
        assert ops == []
