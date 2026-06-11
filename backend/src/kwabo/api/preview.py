"""Provenance-aware endpoints: navision-preview, patch-field, needs-review."""
from __future__ import annotations

import json
import re
from datetime import datetime

from kwabo.utils import utcnow
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from kwabo.db import session as db_session
from kwabo.db.repository import KlantRepo, OrderLogRepo
from kwabo.integrations.navision_steps import compose_navision_operations
from kwabo.utils.logging import log

router = APIRouter(prefix="/api/orders", tags=["orders-preview"])


class PatchFieldBody(BaseModel):
    path: str            # e.g. "orderregels[2].prijs_per_eenheid", "klant_match", "afleveradres.plaats"
    value: Any
    reviewer: Optional[str] = None


class NavisionPreviewResponse(BaseModel):
    """Trigger-aware NAV preview shape (post-T9).

    Frontend (T11) renders the chronologically ordered NavOperation list
    so the reviewer sees exactly the POST/PATCH chain push_navision will
    execute via `create_sales_order_stepwise`. The legacy `{header, lines}`
    payload is gone — that flat shape bypassed NAV's OnValidate triggers.
    """

    operations: list[dict]
    expected_post_count: int
    expected_patch_count: int
    status: str          # "ready" | "missing" | "no_customer" | "no_matched_articles" | "compose_error"
    missing_count: int
    # Leesbare NL-reviewer-tekst die uitlegt WAAROM er 0 (of te weinig)
    # operaties zijn — Nico's "0 operaties zonder uitleg". None bij "ready".
    reason: Optional[str] = None


# ---------- helpers ----------

PATH_RE = re.compile(r"([a-zA-Z_]\w*)|\[(\d+)\]")
REGEL_MATCHED_RE = re.compile(r"orderregels\[(\d+)\]\.artikelnummer_kwabo_matched")


def _split_path(path: str) -> list[Any]:
    parts: list[Any] = []
    for m in PATH_RE.finditer(path):
        if m.group(1) is not None:
            parts.append(m.group(1))
        else:
            parts.append(int(m.group(2)))
    return parts


def _get(state: dict, path: str) -> Any:
    cur: Any = state
    for p in _split_path(path):
        if cur is None:
            return None
        cur = cur[p] if isinstance(p, int) else cur.get(p) if isinstance(cur, dict) else None
    return cur


def _set(state: dict, path: str, value: Any) -> None:
    parts = _split_path(path)
    cur: Any = state
    for i, p in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(p, int):
            while len(cur) <= p:
                cur.append({} if isinstance(nxt, str) else [])
            if cur[p] is None or (isinstance(nxt, int) and not isinstance(cur[p], list)) \
                    or (isinstance(nxt, str) and not isinstance(cur[p], dict)):
                cur[p] = [] if isinstance(nxt, int) else {}
            cur = cur[p]
        else:
            if cur.get(p) is None or (isinstance(nxt, int) and not isinstance(cur[p], list)) \
                    or (isinstance(nxt, str) and not isinstance(cur[p], dict)):
                cur[p] = [] if isinstance(nxt, int) else {}
            cur = cur[p]
    last = parts[-1]
    if isinstance(last, int):
        while len(cur) <= last:
            cur.append(None)
        cur[last] = value
    else:
        cur[last] = value


def _all_needs_review_paths(state: dict) -> list[str]:
    """Re-derive needs_review paths from state['_meta'] (source of truth after patches)."""
    paths: list[str] = []
    meta = state.get("_meta") or {}
    for k, v in meta.items():
        if k == "orderregels" and isinstance(v, list):
            for i, rm in enumerate(v):
                for kk, vv in (rm or {}).items():
                    if isinstance(vv, dict) and vv.get("needs_review"):
                        paths.append(f"orderregels[{i}].{kk}")
        elif isinstance(v, dict) and v.get("needs_review"):
            paths.append(k)
    return paths


def _load(order_id: int) -> tuple[dict, Any]:
    """Load order + parsed state. Returns (state, row)."""
    with Session(db_session.engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order niet gevonden")
        state = json.loads(row.order_state or "{}") if row.order_state else {}
        return state, row


def _save(order_id: int, state: dict, **extra_fields: Any) -> None:
    with Session(db_session.engine) as s:
        repo = OrderLogRepo(s)
        row = repo.get(order_id)
        if not row:
            return
        row.order_state = json.dumps(state, default=str)
        row.updated_at = utcnow()
        for k, v in extra_fields.items():
            setattr(row, k, v)
        s.add(row)
        s.commit()


# ---------- endpoints ----------


@router.get("/{order_id}/navision-preview", response_model=NavisionPreviewResponse)
def navision_preview(order_id: int) -> NavisionPreviewResponse:
    state, _ = _load(order_id)
    klant = (state.get("klant_match") or {}).get("navision_klantnr")
    missing = _all_needs_review_paths(state)
    # Prefer state["nav_operations"] if compose_order populated it (post-T9).
    # Fall back to recomposing on the fly so older review rows still preview.
    operations: list = list(state.get("nav_operations") or [])
    compose_error: str | None = None
    if not operations:
        try:
            operations = list(compose_navision_operations(state))
        except Exception as exc:  # noqa: BLE001
            # Compose weigert b.v. header-only orders (no matched articles) of
            # ongeldige invoer. Elke fout wordt een expliciete status + reden
            # voor de reviewer i.p.v. een 500 (Fase 5 A).
            compose_error = str(exc)
            operations = []
    reason: str | None = None
    if compose_error:
        if "no matched articles" in compose_error.lower():
            status = "no_matched_articles"
            reason = (
                "Geen artikelregel gematcht — vul de Kwabo-artikelnummers aan "
                "(handmatig of via de kandidaten) en probeer opnieuw."
            )
        else:
            status = "compose_error"
            reason = f"Order samenstellen mislukt: {compose_error}"
    elif not klant:
        status = "no_customer"
        reason = (
            "Geen klant gematcht — kies eerst een klant "
            "(kandidaat of handmatig klantnummer)."
        )
    elif missing:
        status = "missing"
        n = len(missing)
        reason = (
            f"{n} veld vereist aanvulling vóór push." if n == 1
            else f"{n} velden vereisen aanvulling vóór push."
        )
    else:
        status = "ready"
    post_count = sum(1 for op in operations if op.get("op") == "POST")
    patch_count = sum(1 for op in operations if op.get("op") == "PATCH")
    return NavisionPreviewResponse(
        operations=list(operations),
        expected_post_count=post_count,
        expected_patch_count=patch_count,
        status=status,
        missing_count=len(missing),
        reason=reason,
    )


@router.patch("/{order_id}/patch-field")
def patch_field(order_id: int, body: PatchFieldBody) -> dict:
    state, _ = _load(order_id)
    # Special-case top-level fields with klant_match shorthand. Het sub-pad
    # klant_match.navision_klantnr is semantisch dezelfde actie (reviewer zet
    # een klantnummer) en moet dezelfde verrijking + review-clear krijgen —
    # anders blijft _meta.klant_match.needs_review True staan en blijft de
    # rode badge na een handmatige fix zichtbaar (M1, Van Dongen-case).
    if body.path in ("klant_match", "klant_match.navision_klantnr"):
        kn = body.value if isinstance(body.value, str) else (body.value or {}).get("navision_klantnr")
        # Verrijk met de NAAM uit de klantenkaart zodat de reviewer een naam
        # ziet i.p.v. alleen een nummer. Lukt de lookup niet (klant niet in de
        # mirror), val terug op de bestaande naam ALS het nummer ongewijzigd is,
        # anders leeg (de UI toont dan het nummer).
        prev = state.get("klant_match") or {}
        naam = ""
        if kn:
            with Session(db_session.engine) as s:
                k = KlantRepo(s).by_nav_nr(kn)
                naam = k.naam if k else ""
        if not naam and prev.get("navision_klantnr") == kn:
            naam = prev.get("klantnaam") or ""
        state["klant_match"] = {
            "navision_klantnr": kn,
            "klantnaam": naam,
            "match_confidence": 1.0,
            "match_bron": "manual",
        }
        meta = dict(state.get("_meta") or {})
        meta["klant_match"] = {
            "value": kn, "source": "manual", "source_detail": "dashboard",
            "confidence": 1.0, "needs_review": not kn,
        }
        state["_meta"] = meta
    else:
        _set(state, body.path, body.value)
        # Update _meta path
        meta = state.setdefault("_meta", {})
        meta_path = "_meta." + body.path
        try:
            _set(state, meta_path, {
                "value": body.value, "source": "manual",
                "source_detail": f"reviewer:{body.reviewer or 'dashboard'}",
                "confidence": 1.0, "needs_review": False,
            })
        except Exception:  # noqa: BLE001
            pass

    # M1 (Fase 2): een handmatige artikel-match moet plakken. De generieke
    # meta-update hierboven dekt het matched-veld, maar laat de regel zelf op
    # match_methode="manual"/confidence 0.0 staan en wist de raw-extract-flag
    # (orderregels[i].artikelnummer_kwabo) niet — terwijl match_articles dat
    # bij een confident automatische match wél doet. Gevolg was een order die
    # eeuwig "ONTBREEKT" toonde na een correcte handmatige fix (#721).
    m = REGEL_MATCHED_RE.fullmatch(body.path)
    if m:
        i = int(m.group(1))
        regels = state.get("orderregels") or []
        if i < len(regels) and isinstance(regels[i], dict):
            heeft_waarde = bool(body.value)
            regels[i]["match_methode"] = "handmatig" if heeft_waarde else "manual"
            regels[i]["match_confidence"] = 1.0 if heeft_waarde else 0.0
            meta = state.setdefault("_meta", {})
            regels_meta = meta.setdefault("orderregels", [])
            while len(regels_meta) <= i:
                regels_meta.append({})
            rm = regels_meta[i] if isinstance(regels_meta[i], dict) else {}
            rm["artikelnummer_kwabo_matched"] = {
                "value": body.value, "source": "manual",
                "source_detail": f"reviewer:{body.reviewer or 'dashboard'}",
                "confidence": 1.0 if heeft_waarde else 0.0,
                # Leegmaken = de regel is wéér ongematcht en moet terug in
                # review (grondwet 5) — de generieke patch-meta zou hier
                # needs_review=False zetten.
                "needs_review": not heeft_waarde,
            }
            if heeft_waarde:
                raw = rm.get("artikelnummer_kwabo")
                if isinstance(raw, dict):
                    raw["needs_review"] = False
                    raw["source_detail"] = (
                        f"{raw.get('source_detail') or ''} | cleared by manual match"
                    ).strip(" |")
            regels_meta[i] = rm

    needs = _all_needs_review_paths(state)
    state["needs_review_fields"] = needs
    state["needs_review_count"] = len(needs)

    # Invalidate the cached compose. Any patch can affect what the next push
    # sends: klant_match → customerNumber, ship_to_gekozen → shipToCode,
    # orderregel artnr/qty/eenheid → line ops. Without clearing, the
    # navision-preview and push_navision would happily use the original
    # state's compose output and ignore the reviewer's edit. The next
    # /navision-preview (and approve→finalize) will recompose from current
    # state automatically because they fall through when nav_operations is
    # empty.
    state["nav_operations"] = []

    # If we changed an order line value, also recompute alle_artikelen_gematcht + sync columns
    extra = {}
    if body.path.startswith("orderregels[") and body.path.endswith(".artikelnummer_kwabo_matched"):
        regels = state.get("orderregels") or []
        alle_gematcht = bool(regels) and all(
            r.get("artikelnummer_kwabo_matched") for r in regels
        )
        # Zowel de OrderLog-kolom (lijstweergave) als de state-JSON (de
        # review-UI rendert uit order_state) — alleen de kolom bijwerken
        # liet de UI op "niet alles gematcht" staan na een handmatige fix.
        extra["alle_artikelen_gematcht"] = alle_gematcht
        state["alle_artikelen_gematcht"] = alle_gematcht
    if body.path in ("klant_match", "klant_match.navision_klantnr"):
        extra["klant_nr"] = (state.get("klant_match") or {}).get("navision_klantnr")

    _save(order_id, state, **extra)
    log.info(
        "patch_field", order_id=order_id, path=body.path,
        reviewer=body.reviewer, needs_review_count=len(needs),
    )
    return {"ok": True, "needs_review_count": len(needs), "needs_review_fields": needs}


@router.get("/{order_id}/needs-review")
def needs_review(order_id: int) -> dict:
    state, _ = _load(order_id)
    paths = _all_needs_review_paths(state)
    return {"count": len(paths), "fields": paths}
