"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type EuropalletMeta, type EuropalletRegel } from "@/lib/api";

type Props = {
  orderId: number;
  regel: EuropalletRegel | null | undefined;
  meta?: EuropalletMeta | null;
  onChanged?: () => void;
};

function Onderbouwing({ meta }: { meta?: EuropalletMeta | null }) {
  if (!meta || !meta.uitleg) return null;
  return (
    <div
      data-testid="europallet-onderbouwing"
      className="mt-2 rounded border border-amber-200 bg-amber-50/60 px-2 py-1.5 text-[11px] text-amber-900"
    >
      <div className="font-medium">{meta.uitleg}</div>
      {meta.regels?.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-[10px] text-amber-800">
          {meta.regels.map((r, i) => (
            <li key={i}>
              {r.artikelnr}: {r.qty} {r.eenheid}
              {r.pallet_maat ? ` ÷ ${r.pallet_maat}/pallet` : ""} = {r.pallets} pallet
            </li>
          ))}
        </ul>
      )}
      {/* B4: regels zonder databron tellen NIET mee — dat moet de reviewer
          zien (anders lijkt "geen europallet" een uitspraak i.p.v. een gat). */}
      {(meta.onbekend?.length ?? 0) > 0 && (
        <div
          data-testid="europallet-onbekend"
          className="mt-1.5 rounded border border-rose-200 bg-rose-50 px-1.5 py-1 text-[10px] text-rose-800"
        >
          <span className="font-semibold">Niet meegeteld (pallet-plaatsen onbekend): </span>
          {meta.onbekend!.map((o, i) => (
            <span key={i}>
              {i > 0 && ", "}
              {o.artikelnr} ({o.qty} {o.eenheid})
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const ARTIKELNR = "19820";
const EENHEID = "STUK";

export function EuropalletEditor({ orderId, regel, meta, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [local, setLocal] = useState<EuropalletRegel | null>(regel ?? null);
  const [qtyDraft, setQtyDraft] = useState<string>(
    regel?.hoeveelheid != null ? String(regel.hoeveelheid) : "1",
  );

  useEffect(() => {
    setLocal(regel ?? null);
    setQtyDraft(regel?.hoeveelheid != null ? String(regel.hoeveelheid) : "1");
  }, [regel?.hoeveelheid, regel?.kwabo_artikelnr, regel]);

  async function patch(value: EuropalletRegel | null, label: string) {
    setBusy(true);
    try {
      await api.patchField(orderId, "europallet_regel", value);
      // Invalidate the cached operations list so the preview re-composes
      // and reflects the change. The preview endpoint prefers
      // `state["nav_operations"]` when present (filled by the pipeline run);
      // touching europallet without clearing it would show a stale preview.
      await api.patchField(orderId, "nav_operations", []).catch(() => {});
      setLocal(value);
      toast.success(label);
      onChanged?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Europallet patch mislukt: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  if (!local) {
    return (
      <div className="mt-2 rounded-md border border-dashed border-slate-300 bg-slate-50 p-3 text-center">
        <button
          data-testid="europallet-add"
          disabled={busy}
          onClick={() =>
            patch(
              { kwabo_artikelnr: ARTIKELNR, hoeveelheid: 1, eenheid: EENHEID },
              "Europallet toegevoegd",
            )
          }
          className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-50"
        >
          + Voeg europallet toe
        </button>
        <Onderbouwing meta={meta} />
      </div>
    );
  }

  function commitQty() {
    const n = Number(qtyDraft);
    if (Number.isNaN(n) || n <= 0) {
      toast.error("Ongeldige hoeveelheid");
      setQtyDraft(String(local!.hoeveelheid));
      return;
    }
    if (n === local!.hoeveelheid) return;
    patch({ ...local!, hoeveelheid: n }, `Europallet aantal: ${n}`);
  }

  return (
    <div
      data-testid="europallet-editor"
      className="mt-2 rounded-md border border-[var(--kwabo-border)] bg-amber-50/40 p-3"
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Europallet (artikel {ARTIKELNR})
        </span>
        <button
          data-testid="europallet-remove"
          disabled={busy}
          onClick={() => patch(null, "Europallet verwijderd")}
          className="ml-auto rounded border border-rose-300 bg-white px-2 py-0.5 text-[11px] font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
        >
          Verwijderen
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <label className="text-xs text-[var(--kwabo-muted)]">
          Hoeveelheid
          <input
            type="number"
            min={1}
            disabled={busy}
            value={qtyDraft}
            data-testid="europallet-qty"
            onChange={(e) => setQtyDraft(e.target.value)}
            onBlur={commitQty}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-[var(--kwabo-muted)]">
          Artikel
          <input
            type="text"
            readOnly
            value={local.kwabo_artikelnr || ARTIKELNR}
            className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600"
          />
        </label>
        <label className="text-xs text-[var(--kwabo-muted)]">
          Eenheid
          <input
            type="text"
            readOnly
            value={local.eenheid || EENHEID}
            className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-sm text-slate-600"
          />
        </label>
      </div>
      <Onderbouwing meta={meta} />
    </div>
  );
}

export default EuropalletEditor;
