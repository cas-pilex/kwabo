"use client";

import { useMemo, useState } from "react";
import type { OrderDetail } from "@/lib/api";
import { statusLabel } from "@/lib/status";

const PAGE_SIZE = 50;

export default function AuditList({ audit }: { audit: OrderDetail[] }) {
  const [q, setQ] = useState("");
  const [visible, setVisible] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return audit;
    return audit.filter((o) =>
      [String(o.id), o.email_subject, o.email_from, o.status]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(term)),
    );
  }, [audit, q]);

  const shown = filtered.slice(0, visible);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setVisible(PAGE_SIZE);
          }}
          placeholder="Zoek op #, onderwerp, afzender of status…"
          className="w-full max-w-sm rounded-md border border-[var(--kwabo-border)] px-3 py-2 text-sm shadow-sm focus:border-[var(--kwabo-navy)] focus:outline-none"
        />
        <span className="shrink-0 text-xs text-[var(--kwabo-muted)]">
          {filtered.length} van {audit.length}
        </span>
      </div>
      <div className="space-y-2">
        {shown.map((o) => (
          <details key={o.id} className="rounded-lg bg-white shadow-sm ring-1 ring-[var(--kwabo-border)]">
            <summary className="flex cursor-pointer items-center justify-between px-4 py-2.5 hover:bg-slate-50">
              <div className="flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-[var(--kwabo-muted)]">#{o.id}</span>
                <span className="font-medium">{o.email_subject?.slice(0, 55)}</span>
                <span className="text-xs text-[var(--kwabo-muted)]">{o.email_from?.slice(0, 38)}</span>
              </div>
              <div className="flex items-center gap-3">
                {o.needs_review_count > 0 && (
                  <span className="rounded bg-rose-50 px-1.5 py-0.5 text-xs font-medium text-rose-800 ring-1 ring-rose-200">
                    {o.needs_review_count} mist
                  </span>
                )}
                {o.warnings_count > 0 && (
                  <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
                    {o.warnings_count} warn
                  </span>
                )}
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{statusLabel(o.status)}</span>
              </div>
            </summary>
            <div className="border-t border-[var(--kwabo-border)] p-4 text-xs">
              <div className="mb-2 font-semibold text-[var(--kwabo-muted)]">Warnings</div>
              {o.warnings.length === 0 ? (
                <div className="text-slate-400">geen</div>
              ) : (
                <ul className="list-disc pl-5 text-amber-800">
                  {o.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
              <div className="mt-3 mb-1 font-semibold text-[var(--kwabo-muted)]">Stappen</div>
              <ol className="space-y-0.5">
                {o.stappen_log.map((s, i) => (
                  <li key={i} className="flex gap-2 font-mono">
                    <span className="w-32 text-[var(--kwabo-navy-300)]">{String(s.stap)}</span>
                    <span className="flex-1 text-slate-700">{String(s.beslissing)}</span>
                  </li>
                ))}
              </ol>
            </div>
          </details>
        ))}
        {shown.length === 0 && (
          <div className="rounded-lg bg-white px-4 py-6 text-center text-sm text-[var(--kwabo-muted)] ring-1 ring-[var(--kwabo-border)]">
            Geen orders gevonden.
          </div>
        )}
      </div>
      {visible < filtered.length && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setVisible((v) => v + PAGE_SIZE)}
            className="rounded-md border border-[var(--kwabo-border)] bg-white px-4 py-2 text-sm font-medium text-[var(--kwabo-navy)] shadow-sm hover:bg-slate-50"
          >
            Meer laden ({filtered.length - visible} resterend)
          </button>
        </div>
      )}
    </div>
  );
}
