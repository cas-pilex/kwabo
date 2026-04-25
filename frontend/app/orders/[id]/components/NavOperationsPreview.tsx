"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type NavOperation, type NavPreviewResponse } from "@/lib/api";

type Props = {
  orderId: number;
  refreshKey: number;
  /**
   * Operations may be passed in directly (when the parent already has the
   * preview response) or — when omitted — fetched via the API helper.
   */
  operations?: NavOperation[];
};

function statusBadge(status: string, missing: number) {
  if (status === "ready") {
    return {
      cls: "bg-emerald-100 text-emerald-800 ring-emerald-300",
      text: "🟢 Klaar voor push",
    };
  }
  if (status === "no_customer") {
    return {
      cls: "bg-rose-100 text-rose-800 ring-rose-300",
      text: "🔴 Klant niet gematcht",
    };
  }
  return {
    cls: "bg-amber-100 text-amber-800 ring-amber-300",
    text: `🟡 ${missing} velden ontbreken`,
  };
}

function methodBadge(op: "POST" | "PATCH") {
  return op === "POST"
    ? "bg-sky-100 text-sky-800 ring-sky-300"
    : "bg-amber-100 text-amber-900 ring-amber-300";
}

/** Highlights `{id}` and `{incoming_document_id}` placeholders inside a path. */
function HighlightedPath({ path }: { path: string }) {
  const parts = path.split(/(\{[a-z_]+\})/g);
  return (
    <span className="font-mono text-[11px] text-slate-700">
      {parts.map((p, i) =>
        /^\{[a-z_]+\}$/.test(p) ? (
          <span
            key={i}
            className="rounded bg-violet-100 px-1 text-violet-800 ring-1 ring-violet-200"
          >
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </span>
  );
}

function OperationRow({ op, idx }: { op: NavOperation; idx: number }) {
  const [open, setOpen] = useState(false);
  const bodyJson = useMemo(() => JSON.stringify(op.body, null, 2), [op.body]);
  return (
    <li
      data-testid={`nav-op-${idx}`}
      data-op-method={op.op}
      className="rounded-md border border-[var(--kwabo-border)] bg-white p-2"
    >
      <div className="flex items-center gap-2">
        <span className="w-6 text-right font-mono text-[10px] text-slate-400">
          {idx + 1}.
        </span>
        <span
          className={`inline-flex w-14 justify-center rounded px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${methodBadge(op.op)}`}
        >
          {op.op}
        </span>
        <span className="flex-1 text-xs font-medium text-slate-800">
          {op.label}
        </span>
        <button
          onClick={() => setOpen((v) => !v)}
          className="rounded border border-[var(--kwabo-border)] bg-white px-1.5 py-0.5 text-[10px] text-slate-600 hover:bg-slate-50"
          aria-expanded={open}
          aria-controls={`nav-op-body-${idx}`}
        >
          {open ? "Verberg body" : "Toon body"}
        </button>
      </div>
      <div className="ml-8 mt-1">
        <HighlightedPath path={op.path} />
      </div>
      {open && (
        <pre
          id={`nav-op-body-${idx}`}
          className="ml-8 mt-2 overflow-auto rounded bg-slate-900 p-2 font-mono text-[10px] leading-relaxed text-slate-200"
        >
          {bodyJson}
        </pre>
      )}
    </li>
  );
}

export function NavOperationsPreview({ orderId, refreshKey, operations }: Props) {
  const [preview, setPreview] = useState<NavPreviewResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .navisionPreview(orderId)
      .then((p) => {
        if (cancelled) return;
        setPreview(p);
        setErr(null);
      })
      .catch((e) => !cancelled && setErr(String(e)));
    return () => {
      cancelled = true;
    };
  }, [orderId, refreshKey]);

  if (err) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
        Kan preview niet laden: {err}
      </div>
    );
  }
  if (!preview) {
    return (
      <div className="rounded-lg bg-white p-4 text-sm text-slate-500 ring-1 ring-[var(--kwabo-border)]">
        Laden…
      </div>
    );
  }

  const ops = operations ?? preview.operations;
  const postCount = ops.filter((o) => o.op === "POST").length;
  const patchCount = ops.filter((o) => o.op === "PATCH").length;
  const badge = statusBadge(preview.status, preview.missing_count);

  return (
    <div className="space-y-3" data-testid="nav-operations-preview">
      <div className="rounded-lg bg-white p-3 text-xs ring-1 ring-[var(--kwabo-border)]">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-[var(--kwabo-muted)]">
            <span
              className="font-semibold text-[var(--kwabo-navy)]"
              data-testid="nav-op-summary"
            >
              {ops.length} operaties
            </span>
            : <span className="font-medium text-sky-800">{postCount} POST</span>
            , <span className="font-medium text-amber-800">{patchCount} PATCH</span>
          </span>
          <span
            className={`inline-flex rounded px-2 py-0.5 text-xs ring-1 ring-inset ${badge.cls}`}
          >
            {badge.text}
          </span>
        </div>
      </div>

      {ops.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs text-slate-500">
          Geen operaties — klant nog niet gematcht of preview leeg.
        </div>
      ) : (
        <ol className="space-y-1.5">
          {ops.map((op, i) => (
            <OperationRow key={i} op={op} idx={i} />
          ))}
        </ol>
      )}
    </div>
  );
}

export default NavOperationsPreview;
