"use client";

import { useState } from "react";
import { toast } from "sonner";
import { api, type ShipToKandidaat } from "@/lib/api";

type Props = {
  orderId: number;
  kandidaten: ShipToKandidaat[];
  gekozen: string | null;
  needsReviewFields: string[];
  onChanged?: () => void;
};

function describe(c: ShipToKandidaat): string {
  const parts = [c.naam || c.ship_to_code, [c.plaats, c.postcode].filter(Boolean).join(", ")];
  return parts.filter(Boolean).join(" — ") || c.ship_to_code;
}

export function ShipToPicker({
  orderId,
  kandidaten,
  gekozen,
  needsReviewFields,
  onChanged,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [local, setLocal] = useState<string | null>(gekozen ?? null);

  const flagged =
    needsReviewFields.includes("ship_to_gekozen") && !local;

  if (!kandidaten || kandidaten.length === 0) {
    return (
      <div className="rounded-md border border-[var(--kwabo-border)] bg-slate-50 px-3 py-2 text-xs text-slate-600">
        Verzendadres: <span className="italic text-slate-400">geen kandidaten — NAV gebruikt klant-default</span>
      </div>
    );
  }

  if (kandidaten.length === 1) {
    const only = kandidaten[0];
    return (
      <div className="rounded-md border border-[var(--kwabo-border)] bg-slate-50 px-3 py-2 text-xs text-slate-700">
        Verzendadres:{" "}
        <span className="font-medium">{describe(only)}</span>{" "}
        <span className="ml-1 inline-flex rounded bg-slate-200/70 px-1 py-0.5 text-[10px] text-slate-600">
          auto-pick · {only.ship_to_code}
        </span>
      </div>
    );
  }

  async function onSelect(value: string) {
    setBusy(true);
    setLocal(value);
    try {
      await api.patchField(orderId, "ship_to_gekozen", value);
      // Invalidate cached nav_operations so the preview reflects the new ship-to.
      await api.patchField(orderId, "nav_operations", []).catch(() => {});
      toast.success(`Verzendadres gezet: ${value}`);
      onChanged?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Verzendadres patch mislukt: ${msg}`);
      setLocal(gekozen ?? null);
    } finally {
      setBusy(false);
    }
  }

  const wrapCls = flagged
    ? "rounded-md border border-amber-300 bg-amber-50/60 p-2"
    : "rounded-md border border-[var(--kwabo-border)] bg-slate-50 p-2";

  return (
    <div className={wrapCls} data-testid="ship-to-picker">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Verzendadres
        </span>
        {flagged && (
          <span className="inline-flex rounded bg-amber-200/70 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300">
            Selectie nodig
          </span>
        )}
        <span className="ml-auto text-[10px] text-slate-500">
          {kandidaten.length} kandidaten
        </span>
      </div>
      <select
        id="ship_to_gekozen"
        data-testid="ship-to-select"
        disabled={busy}
        value={local ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          if (!v) return;
          onSelect(v);
        }}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
      >
        <option value="" disabled>
          — Kies verzendadres —
        </option>
        {kandidaten.map((c) => (
          <option key={c.ship_to_code} value={c.ship_to_code}>
            {describe(c)} {c.is_default ? "· (default)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

export default ShipToPicker;
