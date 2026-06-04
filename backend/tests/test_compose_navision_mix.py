"""Compose: a chosen mix code is emitted as the line UOM, before quantity."""
from __future__ import annotations

from kwabo.integrations.navision_steps import _emit_line_ops, _line_uom_to_emit


def test_mix_uom_gekozen_wins_over_eenheid():
    regel = {"eenheid": "ROL", "eenheid_default": "ROL", "mix_uom_gekozen": "M33PAL35"}
    assert _line_uom_to_emit(regel) == "M33PAL35"


def test_emits_uom_patch_before_quantity_and_no_unit_price():
    regel = {"hoeveelheid": 10, "eenheid": "ROL", "mix_uom_gekozen": "M33PAL35"}
    ops = _emit_line_ops(regel, "23545", "regel 1")
    kinds = []
    for op in ops:
        if op["op"] == "POST":
            kinds.append("POST")
        else:
            kinds.append("PATCH:" + next(iter(op["body"])))
    assert kinds == ["POST", "PATCH:unitOfMeasureCode", "PATCH:quantity"]
    # UOM PATCH carries the chosen mix code.
    uom_op = next(o for o in ops if o["op"] == "PATCH" and "unitOfMeasureCode" in o["body"])
    assert uom_op["body"]["unitOfMeasureCode"] == "M33PAL35"
    # The app never sends a price — NAV computes it from the mix code.
    assert not any("unitPrice" in o.get("body", {}) for o in ops)
