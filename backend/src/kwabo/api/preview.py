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

from kwabo.db.repository import OrderLogRepo
from kwabo.db.session import engine
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
    status: str          # "ready" | "missing" | "no_customer"
    missing_count: int


# ---------- helpers ----------

PATH_RE = re.compile(r"([a-zA-Z_]\w*)|\[(\d+)\]")


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
    with Session(engine) as s:
        row = OrderLogRepo(s).get(order_id)
        if not row:
            raise HTTPException(404, "Order niet gevonden")
        state = json.loads(row.order_state or "{}") if row.order_state else {}
        return state, row


def _save(order_id: int, state: dict, **extra_fields: Any) -> None:
    with Session(engine) as s:
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
    # Prefer state["nav_operations"] if compose_order populated it (post-T9).
    # Fall back to recomposing on the fly so older review rows still preview.
    operations = state.get("nav_operations") or list(compose_navision_operations(state))
    klant = (state.get("klant_match") or {}).get("navision_klantnr")
    missing = _all_needs_review_paths(state)
    if not klant:
        status = "no_customer"
    elif missing:
        status = "missing"
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
    )


@router.patch("/{order_id}/patch-field")
def patch_field(order_id: int, body: PatchFieldBody) -> dict:
    state, _ = _load(order_id)
    # Special-case top-level fields with klant_match shorthand
    if body.path == "klant_match":
        kn = body.value if isinstance(body.value, str) else (body.value or {}).get("navision_klantnr")
        state["klant_match"] = {
            "navision_klantnr": kn,
            "klantnaam": (state.get("klant_match") or {}).get("klantnaam") or "",
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

    needs = _all_needs_review_paths(state)
    state["needs_review_fields"] = needs
    state["needs_review_count"] = len(needs)

    # If we changed an order line value, also recompute alle_artikelen_gematcht + sync columns
    extra = {}
    if body.path.startswith("orderregels[") and body.path.endswith(".artikelnummer_kwabo_matched"):
        regels = state.get("orderregels") or []
        extra["alle_artikelen_gematcht"] = bool(regels) and all(
            r.get("artikelnummer_kwabo_matched") for r in regels
        )
    if body.path == "klant_match":
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
