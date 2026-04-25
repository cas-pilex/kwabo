"use client";

import type { FieldMeta } from "@/lib/api";

type Regel = {
  positie: number;
  artikelnummer_klant: string | null;
  artikelnummer_kwabo_matched: string | null;
  hoeveelheid: number | null;
  prijs_validated: boolean | null;
  match_methode?: string | null;
};

type State = {
  klant_match?: {
    navision_klantnr?: string;
    klantnaam?: string;
    match_bron?: string;
    match_confidence?: number;
    is_4plus?: boolean;
  };
  bestelnummer_klant?: string | null;
  orderdatum?: string | null;
  gewenste_leverdatum?: string | null;
  afleveradres?: { naam?: string; plaats?: string } | null;
  orderregels?: Regel[];
  _meta?: {
    klant_match?: FieldMeta;
    orderregels?: Array<Record<string, FieldMeta>>;
  };
  needs_review_fields?: string[];
};

function countBySource(regels: Regel[], regelsMeta: Array<Record<string, FieldMeta>>) {
  const counts = { klantkaart: 0, history: 0, fuzzy: 0, missing: 0, manual: 0 };
  regels.forEach((r, i) => {
    const rm = regelsMeta[i] || {};
    const m = rm.artikelnummer_kwabo_matched as FieldMeta | undefined;
    if (!r.artikelnummer_kwabo_matched) {
      counts.missing++;
      return;
    }
    const src = m?.source;
    if (src === "klantenkaart") counts.klantkaart++;
    else if (src === "history") counts.history++;
    else if (src === "manual") counts.manual++;
    else if (src === "fuzzy") counts.fuzzy++;
  });
  return counts;
}

export function ExtractSummary({
  emailFrom,
  emailSubject,
  state,
}: {
  emailFrom: string | null;
  emailSubject: string | null;
  state: State;
}) {
  const klant = state.klant_match;
  const klantMeta = state._meta?.klant_match;
  const regels = state.orderregels || [];
  const regelsMeta = state._meta?.orderregels || [];
  const missing = state.needs_review_fields || [];
  const counts = countBySource(regels, regelsMeta);
  const klantConf =
    klantMeta?.confidence != null ? Math.round(klantMeta.confidence * 100) : null;

  return (
    <div className="rounded-lg border border-[var(--kwabo-border)] bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--kwabo-gold)]" />
        AI Extract Samenvatting
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {/* E-mail */}
        <div className="rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            📧 Bron-e-mail
          </div>
          <div className="truncate text-sm font-medium text-slate-800" title={emailSubject ?? ""}>
            {emailSubject || "(geen onderwerp)"}
          </div>
          <div className="mt-0.5 truncate text-xs text-slate-500" title={emailFrom ?? ""}>
            van {emailFrom || "—"}
          </div>
        </div>

        {/* AI heeft gevonden */}
        <div className="rounded-md bg-amber-50 p-3 ring-1 ring-amber-200">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
            🤖 AI heeft gevonden
          </div>
          <div className="space-y-0.5 text-xs text-amber-900">
            <div>
              <span className="text-amber-700">Klant:</span>{" "}
              {klant?.navision_klantnr ? (
                <>
                  <span className="font-mono font-semibold">{klant.navision_klantnr}</span>
                  {klant.klantnaam && <span className="ml-1">· {klant.klantnaam}</span>}
                  {klantConf != null && (
                    <span className="ml-1 font-mono text-amber-700">({klantConf}%)</span>
                  )}
                </>
              ) : (
                <span className="font-medium text-rose-800">niet gematcht</span>
              )}
            </div>
            <div>
              <span className="text-amber-700">Bestelnr:</span>{" "}
              <span className="font-mono">{state.bestelnummer_klant || "—"}</span>
            </div>
            <div>
              <span className="text-amber-700">Leverdatum:</span>{" "}
              <span className="font-mono">{state.gewenste_leverdatum || "—"}</span>
            </div>
            <div>
              <span className="text-amber-700">Orderregels:</span>{" "}
              <span className="font-semibold">{regels.length}</span>
            </div>
          </div>
        </div>

        {/* Matching & status */}
        <div
          className={`rounded-md p-3 ring-1 ${
            missing.length === 0
              ? "bg-emerald-50 ring-emerald-200"
              : "bg-rose-50 ring-rose-200"
          }`}
        >
          <div
            className={`mb-1 text-[10px] font-semibold uppercase tracking-wide ${
              missing.length === 0 ? "text-emerald-700" : "text-rose-700"
            }`}
          >
            {missing.length === 0 ? "✅ Klaar voor push" : `⚠️ ${missing.length} veld(en) ontbreken`}
          </div>
          <div className="space-y-0.5 text-xs">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
              <span>
                Uit klantkaart: <span className="font-semibold">{counts.klantkaart}</span> regel(s)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-violet-500" />
              <span>
                Uit history: <span className="font-semibold">{counts.history}</span> regel(s)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
              <span>
                AI fuzzy: <span className="font-semibold">{counts.fuzzy}</span> regel(s)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-sky-500" />
              <span>
                Handmatig: <span className="font-semibold">{counts.manual}</span> regel(s)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-rose-500" />
              <span>
                Niet gematcht: <span className="font-semibold">{counts.missing}</span> regel(s)
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
