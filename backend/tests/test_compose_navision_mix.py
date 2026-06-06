"""Compose: a chosen mix code is emitted as the line UOM (before quantity), and
the quantity is sent in the mix unit (pallets = mix_aantal), not the raw rolls."""
from __future__ import annotations

from kwabo.integrations.navision_steps import _emit_line_ops, _line_uom_to_emit


def test_mix_uom_gekozen_wins_over_eenheid():
    regel = {"eenheid": "ROL", "eenheid_default": "ROL", "mix_uom_gekozen": "M33PAL35"}
    assert _line_uom_to_emit(regel) == "M33PAL35"


def test_emits_uom_then_pallet_quantity_no_unit_price():
    # Customer ordered 350 rolls; apply_mixprijzen resolved this to 10 pallets.
    regel = {
        "hoeveelheid": 350,
        "eenheid": "ROL",
        "mix_uom_gekozen": "M33PAL35",
        "mix_aantal": 10,
    }
    ops = _emit_line_ops(regel, "23545", "regel 1")
    kinds = []
    for op in ops:
        kinds.append("POST" if op["op"] == "POST" else "PATCH:" + next(iter(op["body"])))
    assert kinds == ["POST", "PATCH:unitOfMeasureCode", "PATCH:quantity"]
    uom_op = next(o for o in ops if o["op"] == "PATCH" and "unitOfMeasureCode" in o["body"])
    assert uom_op["body"]["unitOfMeasureCode"] == "M33PAL35"
    # Quantity is the pallet count (mix_aantal), NOT the raw 350 rolls.
    qty_op = next(o for o in ops if o["op"] == "PATCH" and "quantity" in o["body"])
    assert qty_op["body"]["quantity"] == 10
    # The app never sends a price — NAV computes it from the mix code.
    assert not any("unitPrice" in o.get("body", {}) for o in ops)


def test_non_mix_line_uses_raw_quantity():
    regel = {"hoeveelheid": 60, "eenheid": "STUK"}
    ops = _emit_line_ops(regel, "50013", "regel 1")
    qty_op = next(o for o in ops if o["op"] == "PATCH" and "quantity" in o["body"])
    assert qty_op["body"]["quantity"] == 60
