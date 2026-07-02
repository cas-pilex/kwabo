"use client";

import { useState } from "react";
import { toast } from "sonner";
import type { KlantKandidaat } from "@/lib/api";

type Props = {
  kandidaten: KlantKandidaat[];
  // Parent levert de patch-functie (patcht klant_match + ververst de
  // review-status incl. router.refresh) — zelfde flow als handmatig typen.
  onPick: (navKlantnr: string) => Promise<void>;
};

function describe(k: KlantKandidaat): string {
  const plaats = k.plaats ? ` · ${k.plaats}` : "";
  const score = k.score != null ? ` · ${Math.round(k.score)}%` : "";
  return `${k.klantnaam || k.navision_klantnr}${plaats} (${k.navision_klantnr})${score}`;
}

/**
 * Fase 2 K3: de naam-fallback vond meerdere plausibele klanten — toon ze
 * als picker zodat de reviewer kiest (grondwet 5: nooit autopick).
 * Parent rendert dit alleen zolang er géén klant_match is.
 */
export function KlantPicker({ kandidaten, onPick }: Props) {
  const [busy, setBusy] = useState(false);
  // C2: doorzoekbaar — agent-/franchise-mailboxen leveren zo veel kandidaten
  // dat een kale select onwerkbaar is (TABS: tientallen vestigingen).
  const [zoek, setZoek] = useState("");

  if (!kandidaten || kandidaten.length === 0) return null;

  const term = zoek.trim().toLowerCase();
  const gefilterd = term
    ? kandidaten.filter((k) =>
        `${k.klantnaam ?? ""} ${k.plaats ?? ""} ${k.navision_klantnr}`
          .toLowerCase()
          .includes(term),
      )
    : kandidaten;

  async function onSelect(value: string) {
    setBusy(true);
    try {
      await onPick(value);
      toast.success(`Klant gezet: ${value}`);
    } catch (e) {
      toast.error(`Klant kiezen mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="mb-2 rounded-md border border-amber-300 bg-amber-50/60 p-2"
      data-testid="klant-picker"
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Klant-kandidaten
        </span>
        <span className="inline-flex rounded bg-amber-200/70 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300">
          Selectie nodig
        </span>
        <span className="ml-auto text-[10px] text-slate-500">
          {term ? `${gefilterd.length}/${kandidaten.length}` : kandidaten.length} kandidaten
        </span>
      </div>
      <input
        type="search"
        data-testid="klant-zoek"
        value={zoek}
        onChange={(e) => setZoek(e.target.value)}
        placeholder="Zoek op naam, plaats of nummer…"
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
      />
      <select
        data-testid="klant-select"
        disabled={busy}
        defaultValue=""
        onChange={(e) => {
          const v = e.target.value;
          if (!v) return;
          onSelect(v);
        }}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
      >
        <option value="" disabled>
          — Kies klant —
        </option>
        {gefilterd.map((k) => (
          <option key={k.navision_klantnr} value={k.navision_klantnr}>
            {describe(k)}
          </option>
        ))}
      </select>
      {term && gefilterd.length === 0 && (
        <div className="mt-1 text-[11px] text-slate-500">
          Geen kandidaten voor &quot;{zoek}&quot; — pas de zoekterm aan of typ het klantnr handmatig.
        </div>
      )}
    </div>
  );
}

export default KlantPicker;
