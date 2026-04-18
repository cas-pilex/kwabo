"use client";
import { useCallback, useEffect, useState } from "react";
import {
  listPrijsafspraken,
  addPrijsafspraak,
  deletePrijsafspraak,
  type Prijsafspraak,
} from "@/lib/api";

export function PrijsafsprakenTab({ klantNr }: { klantNr: string }) {
  const [items, setItems] = useState<Prijsafspraak[]>([]);
  const [artnr, setArtnr] = useState("");
  const [prijs, setPrijs] = useState("");
  const [type, setType] = useState("standaard");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setItems(await listPrijsafspraken(klantNr));
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [klantNr]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await addPrijsafspraak(klantNr, {
        kwabo_artikelnr: artnr,
        prijs: parseFloat(prijs),
        type,
      });
      setArtnr("");
      setPrijs("");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDelete(id: number) {
    try {
      await deletePrijsafspraak(klantNr, id);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-4" data-testid="prijsafspraken-tab">
      <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-2 rounded bg-slate-50 p-3">
        <label className="flex flex-col">
          <span className="text-[10px] uppercase text-[var(--kwabo-muted)]">Kwabo artikelnr</span>
          <input
            required
            value={artnr}
            onChange={(e) => setArtnr(e.target.value)}
            data-testid="pa-artnr"
            className="rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm font-mono"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-[10px] uppercase text-[var(--kwabo-muted)]">Prijs €</span>
          <input
            required
            type="number"
            step="0.01"
            value={prijs}
            onChange={(e) => setPrijs(e.target.value)}
            data-testid="pa-prijs"
            className="w-28 rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-[10px] uppercase text-[var(--kwabo-muted)]">Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            data-testid="pa-type"
            className="rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm"
          >
            <option value="standaard">standaard</option>
            <option value="mix">mix</option>
            <option value="pallet">pallet</option>
            <option value="topcoat">topcoat</option>
          </select>
        </label>
        <button
          type="submit"
          data-testid="pa-add"
          className="rounded-md bg-[var(--kwabo-navy)] px-3 py-1.5 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)]"
        >
          Toevoegen
        </button>
      </form>
      {err && <div className="text-sm text-rose-600">{err}</div>}
      {loading && <div className="text-sm text-[var(--kwabo-muted)]">Laden...</div>}
      {!loading && (
        <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-[var(--kwabo-muted)]">
            <tr>
              <th className="px-3 py-1.5 text-left">Kwabo art</th>
              <th className="px-3 py-1.5 text-right">Prijs</th>
              <th className="px-3 py-1.5 text-left">Type</th>
              <th className="px-3 py-1.5 text-left">Geldig tot</th>
              <th className="px-3 py-1.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--kwabo-border)]">
            {items.map((p) => (
              <tr key={p.id} data-testid={`pa-row-${p.kwabo_artikelnr}`}>
                <td className="px-3 py-1.5 font-mono text-xs">{p.kwabo_artikelnr}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">€ {p.prijs.toFixed(2)}</td>
                <td className="px-3 py-1.5 text-xs">{p.type}</td>
                <td className="px-3 py-1.5 text-xs">{p.geldig_tot ?? "—"}</td>
                <td className="px-3 py-1.5 text-right">
                  <button
                    onClick={() => handleDelete(p.id)}
                    data-testid={`pa-del-${p.kwabo_artikelnr}`}
                    className="text-xs text-rose-600 hover:underline"
                  >
                    verwijder
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-[var(--kwabo-muted)]">
                  Geen prijsafspraken.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
