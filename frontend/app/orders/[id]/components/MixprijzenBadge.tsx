"use client";

import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type RegelLike = {
  mix_uom_kandidaat?: string[] | null;
  mix_uom_gekozen?: string | null;
  mix_actieve_prijs?: number | null;
};

type Props = {
  orderId: number;
  regel: RegelLike;
  idx: number;
  onChanged?: () => void;
  /** Order-wide total pallets — the staffel basis for the chosen M-tier. */
  totalPallets?: number | null;
};

export function MixprijzenBadge({ orderId, regel, idx, onChanged, totalPallets }: Props) {
  const [busy, setBusy] = useState(false);
  const [local, setLocal] = useState<string | null>(regel.mix_uom_gekozen ?? null);

  const kandidaten = regel.mix_uom_kandidaat ?? [];

  if (!kandidaten || kandidaten.length === 0) {
    if (!local) return null;
    // Defensive: gekozen without kandidaten — still show the green pill.
  }

  async function setGekozen(value: string) {
    setBusy(true);
    const prev = local;
    setLocal(value);
    try {
      await api.patchField(
        orderId,
        `orderregels[${idx}].mix_uom_gekozen`,
        value,
      );
      // Invalidate cached nav_operations so the preview re-composes with
      // the chosen mix-UOM (it controls unitOfMeasureCode on this line).
      await api.patchField(orderId, "nav_operations", []).catch(() => {});
      toast.success(`Mix-UOM gezet: ${value}`);
      onChanged?.();
    } catch (e) {
      setLocal(prev);
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Mix-UOM patch mislukt: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  if (local) {
    const prijs = regel.mix_actieve_prijs;
    const basis =
      totalPallets != null && totalPallets > 0
        ? `order: ${totalPallets} pallet(s) → ${local}`
        : "Gekozen mix-UOM (mixprijzen actief)";
    return (
      <span
        data-testid={`mix-badge-${idx}`}
        className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800 ring-1 ring-emerald-300"
        title={basis}
      >
        Mix: {local}
        {prijs != null ? ` · €${prijs.toFixed(2)}` : ""}
      </span>
    );
  }

  return (
    <span
      data-testid={`mix-badge-${idx}`}
      className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-900 ring-1 ring-amber-300"
    >
      Mix-UOM kiezen
      <select
        aria-label="Mix-UOM kiezen"
        disabled={busy}
        value=""
        onChange={(e) => {
          const v = e.target.value;
          if (v) setGekozen(v);
        }}
        onClick={(e) => e.stopPropagation()}
        className="ml-1 rounded border border-amber-300 bg-white px-1 py-0 text-[10px] text-amber-900"
      >
        <option value="" disabled>
          —
        </option>
        {kandidaten.map((u) => (
          <option key={u} value={u}>
            {u}
          </option>
        ))}
      </select>
    </span>
  );
}

export default MixprijzenBadge;
