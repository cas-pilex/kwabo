"""Compose the chronologically ordered NAV operations for a sales order.

Pure function — no I/O, no DB. Given the OrderState dict (see
`backend/src/kwabo/graph/state.py`), produces the list of NavOperation
entries that the trigger-aware stepwise NAV client will execute. The
ordering mirrors §6 of the plan
(plans/oke-ik-wil-dat-validated-biscuit.md):

    1.  POST /salesOrders                              (customerNumber only)
    2.  PATCH /salesOrders({id})  shipToCode           (auto-pick if exactly
                                                        one ship-to candidate)
    3.  PATCH /salesOrders({id})  externalDocumentNumber
    4.  PATCH /salesOrders({id})  requestedDeliveryDate
    5.  PATCH /salesOrders({id})  shipmentDate         (today + 1 weekday)
    6.  POST  /salesOrders({id})/salesOrderLines       (lineType + itemNumber)
    7.  PATCH /salesOrderLines({line_id}) unitOfMeasureCode  (when applicable)
    8.  PATCH /salesOrderLines({line_id}) quantity     (always)
    9.  Steps 6–8 repeated for the europallet line (artikel 19820)
    10. POST  /incomingDocuments
    11. PATCH /salesOrders({id})  incomingDocumentNumber
    12. POST  /incomingDocuments({incoming_document_id})/attachments

Why this ordering matters: each PATCH fires a NAV OnValidate trigger that
computes downstream defaults (price, ship-to address, mix discount, …).
A multi-field POST bypasses those triggers — the bug we are removing.
The stepwise client (see RealNavisionClient.create_sales_order_stepwise
and MockNavisionClient.create_sales_order_stepwise) executes exactly this
list and stops on the first error.

Invariant rules enforced by `_assert_op_invariants`:
  * POST /salesOrders body  == {"customerNumber": ...}  (1 key)
  * POST .../salesOrderLines == {"lineType": "Item", "itemNumber": ...}
  * Every PATCH body == exactly one (non-marker) key

Body marker keys (e.g. `_attachment_path`) follow the underscore-prefix
convention: they ride along with the operation so the stepwise client
can act on them, but are stripped before the request hits NAV. See
`nav_operations._strip_marker_keys` for the mechanism.

Compose-time placeholders:
  * Path `{id}` — substituted at execute-time with the most recent
    sales-order or sales-order-line id, depending on context.
  * Path `{incoming_document_id}` and body value `"{incoming_document_id}"`
    — substituted with the id captured from the most-recently-POSTed
    /incomingDocuments response. We do not know that id at compose-time.

UOM emission policy (a deliberate simplification documented in the spec):
The composer does not consult the master-data DB. We emit a UOM PATCH
when the regel carries an explicit `eenheid` AND it is not already the
known item default. We rely on the optional `eenheid_default` field on
the regel (set by an earlier matching node when known) to suppress the
PATCH for default-UOM lines; absent that hint we always emit the PATCH.
This is conservative — extra single-field PATCHes are cheap and correct;
missed PATCHes change unitPrice, which is not.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from kwabo.integrations.nav_operations import NavOperation


EUROPALLET_ARTIKELNR = "19820"


def _next_business_day(today: date | None = None) -> date:
    """Return the next weekday (Mon-Fri) strictly after `today`.

    Saturday  -> Monday (+2). Sunday -> Monday (+1). Friday -> Monday (+3).
    Mon-Thu   -> next day (+1).
    """
    base = today or date.today()
    candidate = base + timedelta(days=1)
    # weekday(): Mon=0 ... Sun=6
    while candidate.weekday() >= 5:  # Sat=5, Sun=6
        candidate += timedelta(days=1)
    return candidate


def _resolved_ship_to(state: dict) -> str | None:
    """Resolve the ship-to code: explicit choice wins; otherwise auto-pick
    when there is exactly one candidate."""
    explicit = state.get("ship_to_gekozen")
    if explicit:
        return explicit
    candidates = state.get("ship_to_kandidaten") or []
    if len(candidates) == 1:
        cand = candidates[0]
        # Accept either a {"code": "..."} record or a bare string code.
        if isinstance(cand, dict):
            return cand.get("code")
        if isinstance(cand, str):
            return cand
    return None


def _line_uom_to_emit(regel: dict) -> str | None:
    """Decide whether to emit a UOM PATCH for this regel.

    Returns the UOM code to PATCH, or None to skip. Rules (see module
    docstring for rationale):

      * `mix_uom_gekozen` set by apply_mixprijzen wins outright.
      * Otherwise, if `eenheid` is non-empty AND differs from
        `eenheid_default` (when supplied) we emit `eenheid`. If no default
        is supplied we emit `eenheid` whenever it is non-empty.
      * Empty / missing eenheid -> skip.
    """
    mix_uom = regel.get("mix_uom_gekozen")
    if mix_uom:
        return mix_uom
    eenheid = regel.get("eenheid") or ""
    if not eenheid:
        return None
    default = regel.get("eenheid_default")
    if default and default == eenheid:
        return None
    return eenheid


def _emit_line_ops(
    regel: dict,
    artikelnr: str,
    label_prefix: str,
) -> list[NavOperation]:
    """Emit the POST + (optional) UOM PATCH + quantity PATCH for one line."""
    ops: list[NavOperation] = []

    ops.append(
        {
            "op": "POST",
            "path": "/salesOrders({id})/salesOrderLines",
            "body": {"lineType": "Item", "itemNumber": artikelnr},
            "label": f"{label_prefix}: regel toevoegen ({artikelnr})",
        }
    )
    uom = _line_uom_to_emit(regel)
    if uom:
        ops.append(
            {
                "op": "PATCH",
                "path": "/salesOrderLines({id})",
                "body": {"unitOfMeasureCode": uom},
                "label": f"{label_prefix}: eenheid kiezen ({uom})",
            }
        )
    quantity = regel.get("hoeveelheid")
    if quantity is not None:
        ops.append(
            {
                "op": "PATCH",
                "path": "/salesOrderLines({id})",
                "body": {"quantity": quantity},
                "label": f"{label_prefix}: aantal invullen ({quantity})",
            }
        )
    return ops


def compose_navision_operations(state: dict) -> list[NavOperation]:
    """Compose the trigger-aware NAV operation list for a sales order.

    Returns an empty list when the state lacks the prerequisites to
    create an order (no matched customer). Callers should treat that as
    "skip the push" rather than as an error — the upstream nodes
    (`match_customer`, validation gates) are responsible for surfacing
    why the customer is missing.
    """
    klant: dict[str, Any] = state.get("klant_match") or {}
    klantnr = klant.get("navision_klantnr")
    if not klantnr:
        # No customer — nothing to compose. T9's push_navision should
        # short-circuit on this signal too; we just return [] cleanly.
        return []

    ops: list[NavOperation] = []

    # ---- Step 1: header POST (single field) --------------------------------
    ops.append(
        {
            "op": "POST",
            "path": "/salesOrders",
            "body": {"customerNumber": klantnr},
            "label": f"Klant kiezen (Sell-to Customer No. {klantnr})",
        }
    )

    # ---- Step 2: ship-to ---------------------------------------------------
    ship_to_code = _resolved_ship_to(state)
    if ship_to_code:
        ops.append(
            {
                "op": "PATCH",
                "path": "/salesOrders({id})",
                "body": {"shipToCode": ship_to_code},
                "label": f"Verzendadres kiezen (Ship-to Code {ship_to_code})",
                # Re-GET so we can audit which address fields NAV autofilled.
                "expects": {"shipToAddress": "auto"},
            }
        )

    # ---- Step 3: external document number (klant's PO number) --------------
    bestelnummer = state.get("bestelnummer_klant") or ""
    if bestelnummer:
        ops.append(
            {
                "op": "PATCH",
                "path": "/salesOrders({id})",
                "body": {"externalDocumentNumber": bestelnummer},
                "label": f"PO-nummer klant ({bestelnummer})",
            }
        )

    # ---- Step 4: requested delivery date -----------------------------------
    leverdatum = state.get("gewenste_leverdatum")
    if leverdatum:
        ops.append(
            {
                "op": "PATCH",
                "path": "/salesOrders({id})",
                "body": {"requestedDeliveryDate": leverdatum},
                "label": f"Gewenste leverdatum ({leverdatum})",
            }
        )

    # ---- Step 5: shipment date (always — today + 1 weekday) ----------------
    shipment_date = _next_business_day().isoformat()
    ops.append(
        {
            "op": "PATCH",
            "path": "/salesOrders({id})",
            "body": {"shipmentDate": shipment_date},
            "label": f"Verzenddatum ({shipment_date})",
        }
    )

    # ---- Steps 6-8: per orderregel -----------------------------------------
    regels = state.get("orderregels") or []
    matched_count = 0
    for idx, regel in enumerate(regels, start=1):
        artikelnr = regel.get("artikelnummer_kwabo_matched")
        if not artikelnr:
            # Spec: only emit lines for matched articles. Unmatched regels
            # would require human intervention; the validation gate in
            # the graph blocks the push for those orders anyway.
            continue
        ops.extend(_emit_line_ops(regel, artikelnr, f"Regel {idx}"))
        matched_count += 1

    # Defensive guard: refuse to compose a header-only order. Either there
    # were zero regels (extraction failed) or every regel was unmatched
    # (matching failed). Real NAV would accept the empty order but the
    # result is structurally invalid; we'd rather surface the upstream
    # failure now than ship a header-only order to NAV.
    if matched_count == 0:
        email_id = state.get("email_id") or "<unknown>"
        raise ValueError(
            f"Cannot compose NAV order for {email_id}: no matched articles "
            f"({len(regels)} regels, all unmatched)."
        )

    # ---- Step 9: europallet (artikel 19820) --------------------------------
    europallet = state.get("europallet_regel")
    if europallet and europallet.get("kwabo_artikelnr") == EUROPALLET_ARTIKELNR:
        # Reuse _emit_line_ops; europallet is just another line. It carries
        # `kwabo_artikelnr` rather than `artikelnummer_kwabo_matched` because
        # it's synthesised by `compute_europallet`, not matched from the
        # customer's order text.
        ops.extend(_emit_line_ops(europallet, EUROPALLET_ARTIKELNR, "Europallet"))

    # ---- Steps 10-12: incoming document ------------------------------------
    incoming_path = state.get("incoming_document_path")
    if incoming_path:
        description = state.get("email_subject") or state.get("onderwerp") or ""
        vendor_name = klant.get("klantnaam", "")
        ops.append(
            {
                "op": "POST",
                "path": "/incomingDocuments",
                "body": {"description": description, "vendorName": vendor_name},
                "label": f"Bron-document aanmaken ({description!r})",
            }
        )
        # The id of the incoming document is unknown at compose-time, so we
        # leave a placeholder string. The stepwise client substitutes it
        # at execute-time using the response from the previous POST.
        ops.append(
            {
                "op": "PATCH",
                "path": "/salesOrders({id})",
                "body": {"incomingDocumentNumber": "{incoming_document_id}"},
                "label": "Bron-document koppelen aan order",
            }
        )
        # The actual byte upload is resolved in the stepwise client by
        # reading `_attachment_path` from disk; it is stripped before
        # transport. fileName is the wire payload we want NAV to record.
        filename = Path(incoming_path).name
        ops.append(
            {
                "op": "POST",
                "path": "/incomingDocuments({incoming_document_id})/attachments",
                "body": {
                    "fileName": filename,
                    "_attachment_path": incoming_path,
                },
                "label": f"Bestand uploaden ({filename})",
            }
        )

    return ops
