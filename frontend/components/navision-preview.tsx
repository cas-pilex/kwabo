"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Preview = Awaited<ReturnType<typeof api.navisionPreview>>;

function colorJson(s: string): string {
  return s
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(?=\s*:))/g, '<span class="text-amber-300">$1</span>')
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*")(?!\s*:)/g, '<span class="text-emerald-300">$1</span>')
    .replace(/\b(true|false|null)\b/g, '<span class="text-violet-300">$1</span>')
    .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="text-sky-300">$1</span>');
}

export function NavisionPreview({ orderId, refreshKey }: { orderId: number; refreshKey: number }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.navisionPreview(orderId)
      .then((p) => {
        if (!cancelled) {
          setPreview(p);
          setErr(null);
        }
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
    return <div className="rounded-lg bg-white p-4 text-sm text-slate-500 ring-1 ring-[var(--kwabo-border)]">Laden…</div>;
  }

  const json = JSON.stringify(preview.body, null, 2);
  const statusBadge =
    preview.status === "ready"
      ? { cls: "bg-emerald-100 text-emerald-800 ring-emerald-200", text: "🟢 Klaar voor push" }
      : preview.status === "no_customer"
        ? { cls: "bg-rose-100 text-rose-800 ring-rose-200", text: "🔴 Klant niet gematcht" }
        : { cls: "bg-amber-100 text-amber-800 ring-amber-200", text: `🟡 ${preview.missing_count} velden ontbreken` };

  async function copy() {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-white p-3 text-xs ring-1 ring-[var(--kwabo-border)]">
        <div className="font-mono text-[11px] text-[var(--kwabo-muted)]">
          <div>
            <span className="font-semibold text-[var(--kwabo-navy)]">{preview.method}</span> {preview.url}
          </div>
          {Object.entries(preview.headers).map(([k, v]) => (
            <div key={k}>
              <span className="text-slate-500">{k}:</span> {v}
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-lg bg-[var(--kwabo-navy)] p-3">
        <pre
          className="max-h-[60vh] overflow-auto font-mono text-[11px] leading-relaxed text-slate-200"
          dangerouslySetInnerHTML={{ __html: colorJson(json) }}
        />
      </div>
      <div className="flex items-center justify-between">
        <span className={`inline-flex rounded px-2 py-0.5 text-xs ring-1 ring-inset ${statusBadge.cls}`}>
          {statusBadge.text}
        </span>
        <button
          onClick={copy}
          className="rounded border border-[var(--kwabo-border)] bg-white px-2 py-1 text-xs hover:bg-slate-50"
        >
          {copied ? "✓ Gekopieerd" : "Kopieer JSON"}
        </button>
      </div>
    </div>
  );
}
