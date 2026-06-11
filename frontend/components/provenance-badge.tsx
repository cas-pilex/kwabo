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
  controleer: "👁",
  navision: "🏷",
};

const LABEL: Record<string, string> = {
  pdf: "PDF",
  email_body: "AI uit e-mail",
  email_header: "E-mail header",
  klantenkaart: "Klantkaart",
  history: "Eerdere correctie",
  fuzzy: "AI fuzzy match",
  manual: "Handmatig",
  default: "Default",
  missing: "ONTBREEKT",
  controleer: "CONTROLEER",
  navision: "Navision",
};

const TONE: Record<string, string> = {
  pdf: "bg-amber-50 text-amber-800 ring-amber-300",
  email_body: "bg-amber-50 text-amber-800 ring-amber-300",
  email_header: "bg-amber-50 text-amber-800 ring-amber-300",
  fuzzy: "bg-amber-50 text-amber-800 ring-amber-300",
  klantenkaart: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  history: "bg-violet-50 text-violet-800 ring-violet-300",
  navision: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  manual: "bg-sky-50 text-sky-800 ring-sky-300",
  default: "bg-slate-50 text-slate-700 ring-slate-200",
  missing: "bg-rose-100 text-rose-900 ring-rose-300",
  controleer: "bg-amber-100 text-amber-900 ring-amber-400",
};

export function ProvenanceBadge({
  meta,
  size = "sm",
  showLabel = false,
}: {
  meta?: FieldMeta;
  size?: "xs" | "sm" | "md";
  showLabel?: boolean;
}) {
  if (!meta) return null;
  // Vlag mét ingevulde waarde = zachte "controleer"-staat (3b: naam-/fuzzy-
  // matches die de operator moet bevestigen); zonder waarde ontbreekt het veld echt.
  const heeftWaarde = meta.value != null && meta.value !== "";
  const src = meta.needs_review ? (heeftWaarde ? "controleer" : "missing") : meta.source;
  const icon = ICON[src] ?? "?";
  const label = LABEL[src] ?? src;
  const conf = meta.confidence != null ? Math.round(meta.confidence * 100) : null;
  const tone = TONE[src] ?? TONE.default;
  const sizeCls =
    size === "xs"
      ? "text-[10px] px-1 py-0"
      : size === "md"
        ? "text-xs px-2 py-0.5 font-medium"
        : "text-[11px] px-1.5 py-0.5";
  const title = `${label}${meta.source_detail ? ` — ${meta.source_detail}` : ""}${conf != null ? ` (conf ${conf}%)` : ""}`;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded ring-1 ring-inset ${sizeCls} ${tone}`}
    >
      <span aria-hidden>{icon}</span>
      {showLabel && <span>{label}</span>}
      {conf != null && <span className="font-mono opacity-70">{conf}%</span>}
    </span>
  );
}
