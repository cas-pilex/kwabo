"""T12 verificatie — run all sample emails through the ingest graph and report
on the composed NAV operations.

Outputs a markdown summary covering:
  - per-email nav_operations counts and any errors
  - aggregate operation breakdown (POST/PATCH per resource)
  - forbidden-field check (no unitPrice / description / description2 in line bodies)
  - mixprijzen and europallet stats

This is purely a verification helper for T12 — it never executes the composed
operations, only inspects them. The push-side smoke test against the mock NAV
is exercised separately by `run_single_email.py --approve`.
"""
from __future__ import annotations

import asyncio
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.seed import seed  # noqa: E402
from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.graph.runner import run_on_eml  # noqa: E402


EMAILS_DIR = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "emails"


# Forbidden body keys per the trigger-respecting design (T1-T11).
# unitPrice / description / description2 must never appear on a line body —
# NAV computes those via OnValidate triggers from itemNumber + customer.
FORBIDDEN_LINE_KEYS = {"unitPrice", "description", "description2"}


async def _run_one(path: Path) -> dict[str, Any]:
    try:
        st = await run_on_eml(path)
        return {
            "file": path.name,
            "ok": True,
            "is_order": st.get("is_order"),
            "klant": (st.get("klant_match") or {}).get("navision_klantnr"),
            "klant_naam": (st.get("klant_match") or {}).get("klantnaam"),
            "regels": len(st.get("orderregels") or []),
            "matched": sum(
                1
                for r in (st.get("orderregels") or [])
                if r.get("artikelnummer_kwabo_matched")
            ),
            "mixprijzen_actief": bool(st.get("mixprijzen_actief")),
            "europallet_regel": st.get("europallet_regel"),
            "orderregels": st.get("orderregels") or [],
            "nav_operations": st.get("nav_operations") or [],
            "validatie_warnings": st.get("validatie_warnings") or [],
        }
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}


def _classify_op(op: dict[str, Any]) -> str:
    method = op.get("op")
    path = op.get("path", "")
    # Strip placeholder + parens for grouping.
    if path.startswith("/salesOrders") and "salesOrderLines" in path:
        return f"{method} /salesOrderLines"
    if path.startswith("/salesOrderLines"):
        return f"{method} /salesOrderLines"
    if path.startswith("/salesOrders"):
        return f"{method} /salesOrders"
    if path.startswith("/incomingDocuments") and "/attachments" in path:
        return f"{method} /incomingDocuments/attachments"
    if path.startswith("/incomingDocuments"):
        return f"{method} /incomingDocuments"
    return f"{method} {path}"


def _scan_forbidden(ops: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Return a map of forbidden-key -> list[label] of any line ops that
    illegally include it. Header (/salesOrders) ops are not scanned for
    `description` because the incomingDocument POST legitimately uses it as
    a metadata field on the document itself."""
    hits: dict[str, list[str]] = defaultdict(list)
    for op in ops:
        path = op.get("path", "")
        body = op.get("body") or {}
        is_line = "salesOrderLines" in path
        is_header = path.startswith("/salesOrders") and "salesOrderLines" not in path
        is_incoming_doc = path.startswith("/incomingDocuments") and "/attachments" not in path
        for k in FORBIDDEN_LINE_KEYS:
            if k in body:
                # description is allowed on the incomingDocuments POST (doc metadata)
                if k == "description" and is_incoming_doc:
                    continue
                if is_line or is_header:
                    hits[k].append(f"{op.get('op')} {path}: {op.get('label', '')}")
    return hits


def _redundant_uom_check(ops: list[dict[str, Any]], regels: list[dict[str, Any]]) -> int:
    """Count UOM PATCHes that look redundant — i.e. the regel had
    eenheid_default == eenheid and we still emitted a PATCH. The composer's
    rule is: only emit when explicit non-default UOM. So count anomalies."""
    bad = 0
    # We only have label info to tie ops back to regels; rely on label
    # prefix Regel N to key into ordered matched regels.
    # Build list of matched regels in the same order as the composer.
    matched = [r for r in regels if r.get("artikelnummer_kwabo_matched")]
    label_to_regel: dict[int, dict[str, Any]] = {}
    for i, r in enumerate(matched, start=1):
        label_to_regel[i] = r

    for op in ops:
        if op.get("op") != "PATCH":
            continue
        if "salesOrderLines" not in op.get("path", ""):
            continue
        body = op.get("body") or {}
        if "unitOfMeasureCode" not in body:
            continue
        # Find regel index from label "Regel N: ..."
        label = op.get("label", "")
        if not label.startswith("Regel "):
            continue
        try:
            idx = int(label.split(" ", 2)[1].rstrip(":"))
        except (IndexError, ValueError):
            continue
        regel = label_to_regel.get(idx)
        if not regel:
            continue
        default = regel.get("eenheid_default")
        eenheid = regel.get("eenheid") or ""
        # mix_uom_gekozen overrides — that is an explicit choice, not redundant.
        if regel.get("mix_uom_gekozen"):
            continue
        if default and default == eenheid:
            bad += 1
    return bad


async def main() -> None:
    init_db()
    with Session(engine) as s:
        seed(s)

    files = sorted(EMAILS_DIR.glob("*.eml"))
    sem = asyncio.Semaphore(4)

    async def bounded(p: Path) -> dict[str, Any]:
        async with sem:
            return await _run_one(p)

    results = await asyncio.gather(*(bounded(p) for p in files))

    # ------------ Aggregate counters ------------
    total = len(results)
    parsed_ok = [r for r in results if r.get("ok")]
    orders = [r for r in parsed_ok if r.get("is_order")]
    klant_hits = [r for r in orders if r.get("klant")]
    with_ops = [r for r in orders if r.get("nav_operations")]
    with_lines = [
        r
        for r in orders
        if any(
            "salesOrderLines" in op.get("path", "") and op.get("op") == "POST"
            for op in r.get("nav_operations") or []
        )
    ]

    op_breakdown: Counter[str] = Counter()
    forbidden_total: dict[str, int] = defaultdict(int)
    forbidden_per_email: dict[str, dict[str, list[str]]] = {}
    redundant_uom_count = 0

    ops_per_order: list[int] = []
    post_so_per_order: list[int] = []
    patch_so_per_order: list[int] = []
    post_line_per_order: list[int] = []
    patch_line_per_order: list[int] = []
    post_inc_doc_per_order: list[int] = []

    mix_orders: list[dict[str, Any]] = []
    europallet_orders: list[dict[str, Any]] = []

    for r in orders:
        ops = r.get("nav_operations") or []
        ops_per_order.append(len(ops))

        per_kind: Counter[str] = Counter()
        for op in ops:
            kind = _classify_op(op)
            op_breakdown[kind] += 1
            per_kind[kind] += 1

        post_so_per_order.append(per_kind.get("POST /salesOrders", 0))
        patch_so_per_order.append(per_kind.get("PATCH /salesOrders", 0))
        post_line_per_order.append(per_kind.get("POST /salesOrderLines", 0))
        patch_line_per_order.append(per_kind.get("PATCH /salesOrderLines", 0))
        post_inc_doc_per_order.append(per_kind.get("POST /incomingDocuments", 0))

        # Forbidden-field scan
        hits = _scan_forbidden(ops)
        if hits:
            forbidden_per_email[r["file"]] = hits
            for k, hs in hits.items():
                forbidden_total[k] += len(hs)

        redundant_uom_count += _redundant_uom_check(ops, r.get("orderregels") or [])

        if r.get("mixprijzen_actief"):
            mix_orders.append(r)
        if r.get("europallet_regel"):
            europallet_orders.append(r)

    # ------------ Markdown report (printed to stdout) ------------
    out: list[str] = []
    out.append("# verify_t12 summary")
    out.append("")
    out.append(f"- Total emails scanned: {total}")
    out.append(f"- Parsed OK: {len(parsed_ok)}")
    out.append(f"- Classified as order: {len(orders)}")
    out.append(f"- Klant matched: {len(klant_hits)}/{len(orders)}")
    out.append(f"- Orders met nav_operations niet-leeg: {len(with_ops)}/{len(orders)}")
    out.append(f"- Orders met >=1 POST /salesOrderLines: {len(with_lines)}/{len(orders)}")
    out.append("")
    out.append("## Per-email summary")
    out.append("")
    out.append("| File | is_order | klant | regels | matched | nav_ops | mixprijzen | europallet |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        if not r.get("ok"):
            out.append(f"| {r['file']} | ERROR | - | - | - | - | - | - |")
            continue
        ep = "ja" if r.get("europallet_regel") else "nee"
        mp = "ja" if r.get("mixprijzen_actief") else "nee"
        out.append(
            f"| {r['file']} | {r.get('is_order')} | {r.get('klant') or '-'} "
            f"| {r.get('regels')} | {r.get('matched')} "
            f"| {len(r.get('nav_operations') or [])} | {mp} | {ep} |"
        )

    out.append("")
    out.append("## Forbidden field check (line POST/PATCH bodies)")
    out.append("")
    out.append(f"- `unitPrice` occurrences: {forbidden_total.get('unitPrice', 0)}")
    out.append(f"- `description` occurrences: {forbidden_total.get('description', 0)}")
    out.append(f"- `description2` occurrences: {forbidden_total.get('description2', 0)}")
    out.append(f"- redundant unitOfMeasureCode PATCHes: {redundant_uom_count}")
    if forbidden_per_email:
        out.append("")
        out.append("Detail (per file):")
        for f, hits in forbidden_per_email.items():
            for k, hs in hits.items():
                for h in hs:
                    out.append(f"  - {f}: {k} on {h}")

    out.append("")
    out.append("## Operations breakdown")
    out.append("")
    if ops_per_order:
        out.append(f"- ops per order: avg={statistics.mean(ops_per_order):.1f}, min={min(ops_per_order)}, max={max(ops_per_order)}")
    out.append("- Total per kind:")
    for kind, count in sorted(op_breakdown.items()):
        out.append(f"  - {kind}: {count}")
    if orders:
        out.append("- Avg per order:")
        out.append(f"  - POST /salesOrders: {statistics.mean(post_so_per_order):.2f}")
        out.append(f"  - PATCH /salesOrders: {statistics.mean(patch_so_per_order):.2f}")
        out.append(f"  - POST /salesOrderLines: {statistics.mean(post_line_per_order):.2f}")
        out.append(f"  - PATCH /salesOrderLines: {statistics.mean(patch_line_per_order):.2f}")
        out.append(f"  - POST /incomingDocuments: {statistics.mean(post_inc_doc_per_order):.2f}")

    out.append("")
    out.append("## Mixprijzen")
    out.append("")
    out.append(f"Orders met mixprijzen_actief=true: {len(mix_orders)}")
    for r in mix_orders:
        chosen: list[tuple[int, str]] = []
        for i, regel in enumerate(r.get("orderregels") or [], start=1):
            uom = regel.get("mix_uom_gekozen")
            if uom:
                chosen.append((i, uom))
        out.append(f"  - {r['file']}: regels met mix_uom_gekozen = {chosen}")

    out.append("")
    out.append("## Europallet")
    out.append("")
    out.append(f"Orders met europallet_regel: {len(europallet_orders)}")
    if europallet_orders:
        qts = [e.get("europallet_regel", {}).get("hoeveelheid", 0) for e in europallet_orders]
        avg = statistics.mean(qts) if qts else 0
        out.append(f"Avg europallet hoeveelheid: {avg:.2f}")
        for r in europallet_orders:
            ep = r.get("europallet_regel") or {}
            out.append(f"  - {r['file']}: hoeveelheid={ep.get('hoeveelheid')}, artikel={ep.get('kwabo_artikelnr')}")

    print("\n".join(out))


if __name__ == "__main__":
    asyncio.run(main())
