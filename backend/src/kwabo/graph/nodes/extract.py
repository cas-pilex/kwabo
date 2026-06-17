"""Extract node — Claude Vision over PDF + provenance metadata.

Produces:
  - `state["orderregels"]` and other top-level fields (flat values, backwards-compat)
  - `state["_meta"]`: per-field provenance records for the UI
  - `state["needs_review_fields"]`: list of JSON-paths that need user input
  - `state["needs_review_count"]`: int
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from kwabo.utils import utcnow
from typing import Any

from kwabo.graph.state import OrderState
from kwabo.integrations.email_client import Attachment, RawEmail
from kwabo.integrations.llm_extractor import extract_from_email
from kwabo.utils.eenheid_mapping import normalize_eenheid
from kwabo.utils.logging import log
from kwabo.utils.verzendwijze import detect_verzendwijze


# Duitse "Kalenderwoche" (KW24, KW 24, KW24/2026): catch-all so the LLM
# can't silently drop a delivery date that's expressed only as a week
# number. Matches both KW24 and "KW 24" and an optional /YYYY year suffix.
KW_WEEK_RE = re.compile(
    r"\bKW\s*(?P<week>\d{1,2})(?:\s*/\s*(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)


def _iso_week_to_date(week: int, year: int) -> date | None:
    """Convert (ISO-year, ISO-week) to the Monday of that week."""
    if not (1 <= week <= 53):
        return None
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError:
        # 53 is invalid in years without a 53rd ISO week — fall back to 52.
        try:
            return date.fromisocalendar(year, min(week, 52), 1)
        except ValueError:
            return None


def _kw_date_from_text(text: str, today: date) -> str | None:
    """If `text` mentions a Duitse Kalenderwoche (KW24, KW24/2026), return
    the Monday of that week as ISO YYYY-MM-DD. None if no KW found or the
    resolved date is in the past (then it's almost certainly a stale ref)."""
    if not text:
        return None
    m = KW_WEEK_RE.search(text)
    if not m:
        return None
    try:
        week = int(m.group("week"))
    except (TypeError, ValueError):
        return None
    year_raw = m.group("year")
    if year_raw:
        year = int(year_raw)
    else:
        year = today.year
        # If the implied week has already passed in the current year, the
        # author likely means next year (Q4 mails ordering for early-spring
        # delivery, etc.). Roll forward.
        candidate = _iso_week_to_date(week, year)
        if candidate is not None and candidate < today:
            year = today.year + 1
    d = _iso_week_to_date(week, year)
    if d is None:
        return None
    return d.isoformat()


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
        "klantnaam_besteller": take("klantnaam_besteller"),
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
    # Informatieve/optionele velden — wél tonen in het reviewscherm, maar NOOIT
    # blokkeren/als 'mist' markeren:
    #  - leverdatum (Cas: "leverdatum bij order invullen is overbodig")
    #  - opmerkingen (Cas: opmerkingen optioneel/niet-verplicht). Een lege
    #    opmerking mag de push dus nooit tegenhouden.
    #  - klantnaam_besteller (Fase 2 K3): matching-signaal voor de
    #    naam-fallback, geen push-veld — mag nooit blokkeren.
    _optioneel = {"gewenste_leverdatum", "opmerkingen", "klantnaam_besteller"}
    needs_review = [p for p in needs_review if p not in _optioneel]
    for _f in _optioneel:
        if isinstance(meta.get(_f), dict):
            meta[_f]["needs_review"] = False
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

    # Post-processor: rescue Duitse "Lieferung KW24" -style dates that the
    # LLM treats as unknown. We scan email body + opmerkingen for KW<NN>
    # and convert to ISO. Confidence 0.7 reflects "post-extracted, not the
    # LLM's primary signal".
    if not flat.get("gewenste_leverdatum"):
        haystack = " ".join(
            filter(None, [
                state.get("email_body") or "",
                state.get("email_subject") or "",
                flat.get("opmerkingen") or "",
            ])
        )
        # Also peek into PDF attachment text, where Auftragsformulare often
        # park the KW reference.
        for b in state.get("bijlagen") or []:
            haystack += " " + ((b or {}).get("inhoud_tekst") or "")
        iso = _kw_date_from_text(haystack, date.today())
        if iso:
            flat["gewenste_leverdatum"] = iso
            meta["gewenste_leverdatum"] = {
                "value": iso,
                "source": "post_processor",
                "source_detail": "kw_week_regex",
                "confidence": 0.7,
                "needs_review": False,
            }
            # Drop the path from needs_review if the LLM had flagged it.
            if "gewenste_leverdatum" in needs_review:
                needs_review = [p for p in needs_review if p != "gewenste_leverdatum"]

    # Functie 5: deterministische afhaal-/ophaal-detectie (NL/DE) over subject,
    # body, afleverinstructies, opmerkingen en bijlage-tekst. Bij een hit zetten
    # we de NAV-verzendwijze (Shipment Method Code = EXW); de composer emit dan
    # een aparte single-field PATCH. Geen needs_review-blokkade (verrijking, geen
    # ontbrekend verplicht veld) — de reviewer kan in de UI corrigeren.
    verzendwijze = detect_verzendwijze({**state, **flat})
    if verzendwijze:
        flat["verzendwijze"] = verzendwijze
        meta["verzendwijze"] = {
            "value": verzendwijze,
            "source": "post_processor",
            "source_detail": "afhaal_signaal",
            "confidence": 0.9,
            "needs_review": False,
        }

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
