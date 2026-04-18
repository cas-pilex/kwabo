"use client";

import type { FieldMeta } from "@/lib/api";

const ICON: Record<string, string> = {
  pdf: "📄",
  email_body: "📧",
  email_header: "📧",
  klantenkaart: "📇",
  history: "🕘",
  fuzzy: "🤖",
  manual: "✏️",
  default: "•",
  missing: "⚠️",
  navision: "🏷",
};

const LABEL: Record<string, string> = {
  pdf: "Uit PDF",
  email_body: "Uit e-mail body",
  email_header: "Uit e-mail header",
  klantenkaart: "Uit klantkaart",
  history: "Uit eerdere correctie",
  fuzzy: "AI fuzzy match",
  manual: "Handmatig ingevoerd",
  default: "Default",
  missing: "Ontbreekt — vul aan",
  navision: "Uit Navision-zoekopdracht",
};

export function ProvenanceBadge({ meta, size = "sm" }: { meta?: FieldMeta; size?: "xs" | "sm" }) {
  if (!meta) return null;
  const icon = ICON[meta.source] ?? "?";
  const label = LABEL[meta.source] ?? meta.source;
  const conf = meta.confidence != null ? Math.round(meta.confidence * 100) : null;
  const tone =
    meta.needs_review
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : (conf ?? 100) >= 90
        ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
        : (conf ?? 100) >= 70
          ? "bg-amber-50 text-amber-700 ring-amber-200"
          : "bg-slate-50 text-slate-700 ring-slate-200";
  const sizeCls = size === "xs" ? "text-[10px] px-1 py-0" : "text-[11px] px-1.5 py-0.5";
  const title = `${label}${meta.source_detail ? ` — ${meta.source_detail}` : ""}${conf != null ? ` (conf ${conf}%)` : ""}`;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded ring-1 ring-inset ${sizeCls} ${tone}`}
    >
      <span aria-hidden>{icon}</span>
      {conf != null && <span className="font-mono">{conf}%</span>}
    </span>
  );
}
