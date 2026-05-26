"""Tests for the trigger-aware NAV operations composer (T4).

These tests are hermetic — they exercise `compose_navision_operations` as
a pure function from state dict to op list. No NAV (real or mock) is
involved. The shape of each op is asserted against the strict invariants
defined in `nav_operations._assert_op_invariants`; we also re-run those
invariants here as a belt-and-braces check.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from kwabo.integrations.nav_operations import _assert_op_invariants
from kwabo.integrations.navision_steps import (
    EUROPALLET_ARTIKELNR,
    _next_business_day,
    compose_navision_operations,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _assert_all_invariants(ops: list[dict]) -> None:
    """Every emitted op must satisfy the per-op contract."""
    for idx, op in enumerate(ops):
        _assert_op_invariants(idx, op)


def _ops_for_path(ops: list[dict], path_substr: str) -> list[dict]:
    return [o for o in ops if path_substr in o["path"]]


def _patch_bodies_for_path(ops: list[dict], path_substr: str) -> list[dict]:
    return [o["body"] for o in ops if o["op"] == "PATCH" and path_substr in o["path"]]


def _state_with_klant(**overrides: Any) -> dict:
    base: dict = {
        "klant_match": {
            "navision_klantnr": "10001",
            "klantnaam": "Ferney Diabolo B.V.",
        },
        "orderregels": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixture (a) Minimal happy path
# ---------------------------------------------------------------------------


def test_minimal_happy_path_one_line_with_auto_picked_ship_to():
    state = _state_with_klant(
        ship_to_kandidaten=[{"code": "MAIN", "name": "HQ"}],
        # no ship_to_gekozen — auto-pick when exactly one candidate
        orderregels=[
            {
                "positie": 1,
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                # no eenheid → no UOM PATCH
            }
        ],
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)

    # Order: header POST -> ship-to PATCH -> shipmentDate PATCH -> line POST
    # -> quantity PATCH. No externalDoc, no requestedDelivery, no UOM.
    assert len(ops) == 5

    # 1) POST /salesOrders — body must be EXACTLY {"customerNumber": ...}
    assert ops[0]["op"] == "POST"
    assert ops[0]["path"] == "/salesOrders"
    assert ops[0]["body"] == {"customerNumber": "10001"}
    # No accidental extra fields (description, externalDoc, …)
    assert list(ops[0]["body"].keys()) == ["customerNumber"]

    # 2) PATCH ship-to (auto-picked from the singleton candidate list)
    assert ops[1]["op"] == "PATCH"
    assert ops[1]["path"] == "/salesOrders({id})"
    assert ops[1]["body"] == {"shipToCode": "MAIN"}

    # 3) PATCH shipmentDate (always emitted)
    assert ops[2]["op"] == "PATCH"
    assert ops[2]["body"].get("shipmentDate") is not None
    assert _next_business_day().isoformat() == ops[2]["body"]["shipmentDate"]

    # 4) POST /salesOrderLines with EXACTLY {lineType, itemNumber}
    assert ops[3]["op"] == "POST"
    assert ops[3]["path"] == "/salesOrders({id})/salesOrderLines"
    assert ops[3]["body"] == {"lineType": "Item", "itemNumber": "1515155"}

    # 5) PATCH quantity (no UOM PATCH because regel.eenheid is absent)
    assert ops[4]["op"] == "PATCH"
    assert ops[4]["path"] == "/salesOrderLines({id})"
    assert ops[4]["body"] == {"quantity": 5}


def test_minimal_happy_path_uom_then_quantity_ordering():
    """When BOTH UOM and quantity PATCHes are emitted for a line, UOM
    must come strictly before quantity — NAV's quantity OnValidate uses
    the UOM to compute price."""
    state = _state_with_klant(
        orderregels=[
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 24,
                "eenheid": "PAL",
                "eenheid_default": "ROL",  # PAL != ROL -> UOM PATCH emitted
            }
        ],
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)

    line_ops = [o for o in ops if "/salesOrderLines" in o["path"]]
    # POST line, PATCH UOM, PATCH quantity
    assert len(line_ops) == 3
    assert line_ops[0]["op"] == "POST"
    assert line_ops[1] == {
        "op": "PATCH",
        "path": "/salesOrderLines({id})",
        "body": {"unitOfMeasureCode": "PAL"},
        "label": line_ops[1]["label"],  # tolerant of label phrasing
    }
    assert line_ops[2]["body"] == {"quantity": 24}


# ---------------------------------------------------------------------------
# Fixture (b) Multi-line, all default UOM -> only 2 PATCHes per line
# ---------------------------------------------------------------------------


def test_multi_line_default_uom_no_uom_patch():
    """3 lines that each carry their item-default UOM should NOT trigger
    a UOM PATCH — only the line POST + quantity PATCH per line."""
    state = _state_with_klant(
        orderregels=[
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                "eenheid": "ROL",
                "eenheid_default": "ROL",
            },
            {
                "artikelnummer_kwabo_matched": "228321",
                "hoeveelheid": 10,
                "eenheid": "STUK",
                "eenheid_default": "STUK",
            },
            {
                "artikelnummer_kwabo_matched": "2597768",
                "hoeveelheid": 2,
                "eenheid": "EMMER",
                "eenheid_default": "EMMER",
            },
        ],
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)

    # Per line we expect exactly 2 ops (POST + quantity PATCH).
    line_post_count = sum(
        1 for o in ops if o["op"] == "POST" and o["path"].endswith("/salesOrderLines")
    )
    quantity_patches = [
        o for o in _patch_bodies_for_path(ops, "/salesOrderLines") if "quantity" in o
    ]
    uom_patches = [
        o for o in _patch_bodies_for_path(ops, "/salesOrderLines")
        if "unitOfMeasureCode" in o
    ]
    assert line_post_count == 3
    assert len(quantity_patches) == 3
    assert len(uom_patches) == 0  # this is the load-bearing assertion


# ---------------------------------------------------------------------------
# Fixture (c) Multi-line with one mix-line
# ---------------------------------------------------------------------------


def test_multi_line_with_one_mix_line_emits_uom_patch_before_quantity():
    """Only the line that carries `mix_uom_gekozen` should emit a UOM
    PATCH; that PATCH must come ahead of its quantity PATCH."""
    state = _state_with_klant(
        orderregels=[
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                "eenheid": "ROL",
                "eenheid_default": "ROL",
            },
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 24,
                "eenheid": "ROL",
                "eenheid_default": "ROL",
                "mix_uom_gekozen": "PAL",   # set later by apply_mixprijzen (T7)
            },
            {
                "artikelnummer_kwabo_matched": "228321",
                "hoeveelheid": 10,
                "eenheid": "STUK",
                "eenheid_default": "STUK",
            },
        ],
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)

    # Walk ops and verify per-line shape: 3 line POSTs, only the second
    # has a UOM PATCH between POST and quantity.
    line_block_signatures = []
    cur: list[str] = []
    for o in ops:
        if o["op"] == "POST" and o["path"].endswith("/salesOrderLines"):
            if cur:
                line_block_signatures.append(cur)
            cur = ["POST"]
        elif "/salesOrderLines" in o["path"] and o["op"] == "PATCH":
            key = next(iter({k for k in o["body"] if not k.startswith("_")}))
            cur.append(f"PATCH:{key}")
    if cur:
        line_block_signatures.append(cur)

    assert line_block_signatures == [
        ["POST", "PATCH:quantity"],
        ["POST", "PATCH:unitOfMeasureCode", "PATCH:quantity"],
        ["POST", "PATCH:quantity"],
    ]

    # And the mix-line's UOM PATCH must precede its quantity PATCH.
    mix_block = line_block_signatures[1]
    assert mix_block.index("PATCH:unitOfMeasureCode") < mix_block.index("PATCH:quantity")


# ---------------------------------------------------------------------------
# Fixture (d) No customer match -> empty list
# ---------------------------------------------------------------------------


def test_no_customer_match_returns_empty_list():
    state: dict = {
        "klant_match": None,
        "orderregels": [
            {"artikelnummer_kwabo_matched": "1515155", "hoeveelheid": 5}
        ],
    }
    assert compose_navision_operations(state) == []

    # Same when klant_match has no navision_klantnr.
    state2: dict = {
        "klant_match": {"klantnaam": "Unmatched"},
        "orderregels": [
            {"artikelnummer_kwabo_matched": "1515155", "hoeveelheid": 5}
        ],
    }
    assert compose_navision_operations(state2) == []

    # And it should not crash if klant_match is missing entirely.
    assert compose_navision_operations({}) == []


# ---------------------------------------------------------------------------
# Fixture (e) Full pipeline — europallet + incoming document
# ---------------------------------------------------------------------------


def test_full_pipeline_with_europallet_and_incoming_document(tmp_path):
    # Create a real file so the path is meaningful (composer doesn't read
    # it; that happens in the stepwise client).
    incoming_doc = tmp_path / "PO-12345.eml"
    incoming_doc.write_text("dummy email", encoding="utf-8")

    state = _state_with_klant(
        bestelnummer_klant="PO-12345",
        gewenste_leverdatum="2026-05-01",
        email_subject="Bestelling PO-12345",
        ship_to_kandidaten=[
            {"code": "MAIN", "name": "HQ"},
            {"code": "DC-EAST", "name": "DC Oost"},
        ],
        ship_to_gekozen="DC-EAST",
        orderregels=[
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                "eenheid": "ROL",
                "eenheid_default": "ROL",
            },
            {
                "artikelnummer_kwabo_matched": "2597768",
                "hoeveelheid": 33,
                "eenheid": "PAL",
                "eenheid_default": "EMMER",
                "mix_uom_gekozen": "PAL",
            },
        ],
        europallet_regel={
            "artikelnummer_kwabo": EUROPALLET_ARTIKELNR,
            "hoeveelheid": 2,
            "eenheid": "STUK",
            "eenheid_default": "STUK",
        },
        incoming_document_path=str(incoming_doc),
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)

    # Path-suffix ordering check: every item line POST must come before
    # the europallet line POST; the europallet POST must come before the
    # incoming-document POST; and the attachments POST is last.
    line_post_indices = [
        i for i, o in enumerate(ops)
        if o["op"] == "POST" and o["path"].endswith("/salesOrderLines")
    ]
    incoming_post_index = next(
        i for i, o in enumerate(ops)
        if o["op"] == "POST" and o["path"] == "/incomingDocuments"
    )
    attach_post_index = next(
        i for i, o in enumerate(ops)
        if o["op"] == "POST" and o["path"].endswith("/attachments")
    )

    # Three line POSTs total: 2 item lines + 1 europallet line.
    assert len(line_post_indices) == 3
    # The last line POST is the europallet (artikel 19820).
    assert ops[line_post_indices[-1]]["body"]["itemNumber"] == EUROPALLET_ARTIKELNR
    # Europallet ops come AFTER all item ops.
    item_line_post_indices = line_post_indices[:-1]
    assert max(item_line_post_indices) < line_post_indices[-1]
    # Incoming-doc POST + attach come LAST.
    assert incoming_post_index > line_post_indices[-1]
    assert attach_post_index > incoming_post_index
    assert attach_post_index == len(ops) - 1

    # The PATCH for incomingDocumentNumber must use the placeholder marker.
    inc_patch = next(
        o for o in ops
        if o["op"] == "PATCH"
        and o["path"] == "/salesOrders({id})"
        and "incomingDocumentNumber" in o["body"]
    )
    assert inc_patch["body"] == {"incomingDocumentNumber": "{incoming_document_id}"}

    # The attachments POST uses the {incoming_document_id} placeholder in its path
    # (resolved at execute-time by the stepwise client) and carries the
    # composer-side `_attachment_path` marker that the client strips.
    attach_op = ops[attach_post_index]
    assert attach_op["path"] == "/incomingDocuments({incoming_document_id})/attachments"
    assert attach_op["body"]["fileName"] == "PO-12345.eml"
    assert attach_op["body"]["_attachment_path"] == str(incoming_doc)
    # Underscore-prefix marker keys are tolerated by the invariants.
    _assert_op_invariants(attach_post_index, attach_op)

    # The header phase emitted the explicit ship-to (not the auto-pick).
    ship_patches = [
        o for o in _patch_bodies_for_path(ops, "/salesOrders({id})")
        if "shipToCode" in o
    ]
    assert ship_patches == [{"shipToCode": "DC-EAST"}]

    # External doc + requested delivery date PATCHes were emitted.
    ext_patches = [
        o for o in _patch_bodies_for_path(ops, "/salesOrders({id})")
        if "externalDocumentNumber" in o
    ]
    assert ext_patches == [{"externalDocumentNumber": "PO-12345"}]
    rdd_patches = [
        o for o in _patch_bodies_for_path(ops, "/salesOrders({id})")
        if "requestedDeliveryDate" in o
    ]
    assert rdd_patches == [{"requestedDeliveryDate": "2026-05-01"}]

    # Mix-line emitted UOM PATCH ahead of quantity PATCH.
    line_patches = _ops_for_path(ops, "/salesOrderLines(")
    line_patch_keys = [
        next(iter([k for k in o["body"] if not k.startswith("_")]))
        for o in line_patches
    ]
    # Order across the three lines: q (line 1), uom + q (mix line), uom + q (europallet because eenheid_default == eenheid? no, equal -> skip)
    # Europallet has eenheid==eenheid_default=="STUK" so no UOM PATCH.
    assert line_patch_keys == ["quantity", "unitOfMeasureCode", "quantity", "quantity"]


# ---------------------------------------------------------------------------
# additional sanity: shipment date computation
# ---------------------------------------------------------------------------


def test_next_business_day_skips_weekend():
    # Friday  -> Monday (+3)
    fri = date(2026, 4, 24)  # known Friday
    assert _next_business_day(fri) == date(2026, 4, 27)
    # Saturday -> Monday (+2)
    sat = date(2026, 4, 25)
    assert _next_business_day(sat) == date(2026, 4, 27)
    # Sunday   -> Monday (+1)
    sun = date(2026, 4, 26)
    assert _next_business_day(sun) == date(2026, 4, 27)
    # Monday   -> Tuesday (+1)
    mon = date(2026, 4, 27)
    assert _next_business_day(mon) == date(2026, 4, 28)


def test_europallet_uses_artikelnummer_kwabo_key():
    """compute_europallet emits the artikel under `artikelnummer_kwabo`
    (matching the orderregel shape). compose must read THAT key, not the
    legacy/wrong `kwabo_artikelnr` which never matched (pre-existing bug:
    europallet lines never reached NAV).
    """
    state = _state_with_klant(
        orderregels=[
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                "eenheid": "ROL",
                "eenheid_default": "ROL",
            }
        ],
        europallet_regel={"artikelnummer_kwabo": "98765", "hoeveelheid": 1},
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)
    line_posts = [
        o for o in ops if o["op"] == "POST" and o["path"].endswith("/salesOrderLines")
    ]
    assert len(line_posts) == 2
    assert line_posts[0]["body"]["itemNumber"] == "1515155"
    assert line_posts[1]["body"]["itemNumber"] == "98765"


def test_europallet_skipped_when_artikelnr_missing():
    """Empty/missing artikelnummer on europallet_regel → no line emitted."""
    state = _state_with_klant(
        orderregels=[
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 5,
                "eenheid": "ROL",
                "eenheid_default": "ROL",
            }
        ],
        europallet_regel={"artikelnummer_kwabo": "", "hoeveelheid": 1},
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)
    line_posts = [
        o for o in ops if o["op"] == "POST" and o["path"].endswith("/salesOrderLines")
    ]
    assert len(line_posts) == 1
    assert line_posts[0]["body"]["itemNumber"] == "1515155"


def test_unmatched_regels_are_skipped():
    """Regels without artikelnummer_kwabo_matched should not produce ops."""
    state = _state_with_klant(
        orderregels=[
            {"artikelnummer_klant": "FER-X", "hoeveelheid": 5},  # not matched
            {
                "artikelnummer_kwabo_matched": "1515155",
                "hoeveelheid": 3,
            },
        ]
    )
    ops = compose_navision_operations(state)
    _assert_all_invariants(ops)
    line_posts = [
        o for o in ops if o["op"] == "POST" and o["path"].endswith("/salesOrderLines")
    ]
    assert len(line_posts) == 1
    assert line_posts[0]["body"]["itemNumber"] == "1515155"
