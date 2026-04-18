"""Extract node — Claude Vision over PDF + provenance metadata.

Produces:
  - `state["orderregels"]` and other top-level fields (flat values, backwards-compat)
  - `state["_meta"]`: per-field provenance records for the UI
  - `state["needs_review_fields"]`: list of JSON-paths that need user input
  - `state["needs_review_count"]`: int
"""
from __future__ import annotations

from datetime import datetime

from kwabo.utils import utcnow
from typing import Any

from kwabo.graph.state import OrderState
from kwabo.integrations.email_client import Attachment, RawEmail
from kwabo.integrations.llm_extractor import extract_from_email
from kwabo.utils.eenheid_mapping import normalize_eenheid
from kwabo.utils.logging import log


def _coerce_meta(field: Any) -> dict[str, Any]:
    """Accept either a raw value or a {value,source,...} dict; always return a meta dict."""
    if isinstance(field, dict) and "value" in field and "source" in field:
        return {
            "value": field.get("value"),
            "source": field.get("source") or "missing",
            "source_detail": field.get("source_detail"),
            "confidence": float(field.get("confidence") or 0),
            "needs_review": bool(field.get("needs_review", field.get("value") in (None, ""))),
        }
    # Plain value (legacy)
    return {
        "value": field,
        "source": "pdf" if field not in (None, "") else "missing",
        "source_detail": None,
        "confidence": 0.5 if field not in (None, "") else 0,
        "needs_review": field in (None, ""),
    }


def _val(meta: dict[str, Any]) -> Any:
    return meta.get("value")


def _build_state_from_extract(parsed: dict, raw: RawEmail) -> tuple[dict, dict, list[str]]:
    """Convert the LLM JSON into (flat_state_patch, meta, needs_review_paths)."""
    needs_review: list[str] = []
    meta: dict[str, Any] = {}

    def take(field_name: str) -> Any:
        m = _coerce_meta(parsed.get(field_name))
        meta[field_name] = m
        if m["needs_review"]:
            needs_review.append(field_name)
        return _val(m)

    flat: dict[str, Any] = {
        "taal": take("taal"),
        "bestelnummer_klant": take("bestelnummer_klant"),
        "orderdatum": take("orderdatum"),
        "gewenste_leverdatum": take("gewenste_leverdatum"),
        "afleveradres": take("afleveradres"),
        "afleverinstructies": take("afleverinstructies"),
        "opmerkingen": take("opmerkingen"),
    }

    regels_in = parsed.get("orderregels") or []
    regels_out: list[dict[str, Any]] = []
    regels_meta: list[dict[str, Any]] = []
    for i, r in enumerate(regels_in):
        positie = r.get("positie") or i + 1
        rmeta: dict[str, Any] = {}
        flat_r: dict[str, Any] = {"positie": positie}
        for k in (
            "artikelnummer_klant",
            "artikelnummer_kwabo",
            "omschrijving",
            "hoeveelheid",
            "eenheid",
            "prijs_per_eenheid",
            "ean_code",
            "leverdatum_regel",
            "opmerkingen",
        ):
            m = _coerce_meta(r.get(k))
            rmeta[k] = m
            v = _val(m)
            flat_r[k] = v
            if m["needs_review"] and k in ("artikelnummer_kwabo", "hoeveelheid", "eenheid"):
                needs_review.append(f"orderregels[{i}].{k}")
        # Normalise hoeveelheid + eenheid
        try:
            flat_r["hoeveelheid"] = float(flat_r.get("hoeveelheid") or 0)
        except (TypeError, ValueError):
            flat_r["hoeveelheid"] = 0.0
        flat_r["eenheid"] = normalize_eenheid(flat_r.get("eenheid"))
        if flat_r.get("prijs_per_eenheid") is not None:
            try:
                flat_r["prijs_per_eenheid"] = float(flat_r["prijs_per_eenheid"])
            except (TypeError, ValueError):
                flat_r["prijs_per_eenheid"] = None
        regels_out.append(flat_r)
        regels_meta.append(rmeta)

    flat["orderregels"] = regels_out
    meta["orderregels"] = regels_meta
    return flat, meta, needs_review


async def extract_node(state: OrderState) -> OrderState:
    raw = _state_to_raw(state)
    parsed = await extract_from_email(raw)
    if isinstance(parsed, list):
        parsed_list = parsed
        primary = parsed_list[0] if parsed_list else {}
        extras = parsed_list[1:] if len(parsed_list) > 1 else []
    else:
        parsed_list = None
        primary = parsed or {}
        extras = []

    flat, meta, needs_review = _build_state_from_extract(primary, raw)

    log.info(
        "extract",
        email_id=state.get("email_id"),
        taal=flat.get("taal"),
        bestelnr=flat.get("bestelnummer_klant"),
        regels=len(flat.get("orderregels") or []),
        multi_orders=len(parsed_list) if parsed_list else 1,
        needs_review_count=len(needs_review),
    )

    stap = {
        "stap": "extract",
        "timestamp": utcnow().isoformat(),
        "beslissing": (
            f"Geëxtraheerd: {len(flat.get('orderregels') or [])} regels, taal={flat.get('taal')}, "
            f"{len(needs_review)} velden needs_review"
        ),
        "details": {
            "bestelnummer": flat.get("bestelnummer_klant"),
            "multi_orders": len(parsed_list) if parsed_list else 1,
        },
    }
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)

    existing_meta = dict(state.get("_meta") or {})
    existing_meta.update(meta)

    return {
        **state,
        **flat,
        "_meta": existing_meta,
        "stappen_log": steps,
        "needs_review_fields": list(state.get("needs_review_fields") or []) + needs_review,
        "needs_review_count": (state.get("needs_review_count") or 0) + len(needs_review),
        # Extra sub-orders to be processed after the primary graph completes
        "extra_orders_raw": extras,
    }


def _state_to_raw(state: OrderState) -> RawEmail:
    """Reconstruct a RawEmail from the in-state bijlagen dicts (decode raw if present)."""
    bijlagen: list[Attachment] = []
    for b in state.get("bijlagen") or []:
        bijlagen.append(
            Attachment(
                naam=b.get("naam") or "",
                type=b.get("type") or "other",
                inhoud_tekst=b.get("inhoud_tekst") or "",
                raw=b.get("raw"),  # may be bytes or None depending on caller
            )
        )
    return RawEmail(
        email_id=state.get("email_id") or "",
        email_from=state.get("email_from") or "",
        email_subject=state.get("email_subject") or "",
        email_date=state.get("email_date") or "",
        email_body=state.get("email_body") or "",
        bijlagen=bijlagen,
    )
