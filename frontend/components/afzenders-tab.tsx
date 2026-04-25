"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Alias = { id: number; klant_nr: string; email: string; label: string | null };

export function AfzendersTab({
  klantNr,
  primaryEmail,
  primaryOrderEmail,
}: {
  klantNr: string;
  primaryEmail: string | null;
  primaryOrderEmail: string | null;
}) {
  const [aliases, setAliases] = useState<Alias[]>([]);
  const [email, setEmail] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setAliases(await api.listAliases(klantNr));
    } catch (e) {
      toast.error(`Laden mislukt: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  useEffect(() => {
    load();
  }, [klantNr]);

  async function add() {
    if (!email.trim()) return;
    setBusy(true);
    try {
      await api.addAlias(klantNr, { email: email.trim(), label: label.trim() || null });
      setEmail("");
      setLabel("");
      toast.success("Alias toegevoegd");
      await load();
    } catch (e) {
      toast.error(`Toevoegen mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Alias verwijderen?")) return;
    try {
      await api.deleteAlias(klantNr, id);
      toast.success("Alias verwijderd");
      await load();
    } catch (e) {
      toast.error(`Verwijderen mislukt: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <div className="space-y-4 text-sm">
      <p className="text-[var(--kwabo-muted)]">
        E-mailadressen die <strong>ook</strong> aan deze klant worden gekoppeld wanneer een order
        van dat adres binnenkomt. Handig als één klant meerdere inkopers, filialen of postbussen
        heeft.
      </p>

      {/* Primary addresses (read-only info) */}
      <div className="rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Hoofdadressen (uit klantkaart)
        </div>
        <div className="space-y-0.5 text-xs">
          <div>
            <span className="inline-block w-28 text-slate-500">Primair:</span>
            <span className="font-mono">{primaryEmail || "—"}</span>
          </div>
          <div>
            <span className="inline-block w-28 text-slate-500">Bestel-adres:</span>
            <span className="font-mono">{primaryOrderEmail || "—"}</span>
          </div>
        </div>
      </div>

      {/* Add alias */}
      <div className="rounded-md border border-[var(--kwabo-border)] bg-white p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Alias toevoegen
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            type="email"
            placeholder="bv. inkoop@klant.nl"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="flex-1 min-w-[220px] rounded-md border border-slate-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
          />
          <input
            type="text"
            placeholder="Label (optioneel, bv. 'Vestiging Utrecht')"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="flex-1 min-w-[220px] rounded-md border border-slate-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
          />
          <button
            onClick={add}
            disabled={busy || !email.trim()}
            className="rounded-md bg-[var(--kwabo-navy)] px-3 py-1.5 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Toevoegen
          </button>
        </div>
      </div>

      {/* Aliases list */}
      <div className="overflow-hidden rounded-md border border-[var(--kwabo-border)] bg-white">
        <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-[var(--kwabo-muted)]">
            <tr>
              <th className="px-3 py-1.5 text-left">E-mail</th>
              <th className="px-3 py-1.5 text-left">Label</th>
              <th className="px-3 py-1.5 text-right"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--kwabo-border)]">
            {aliases.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-6 text-center text-[var(--kwabo-muted)]">
                  Nog geen aliases.
                </td>
              </tr>
            )}
            {aliases.map((a) => (
              <tr key={a.id}>
                <td className="px-3 py-1.5 font-mono text-xs">{a.email}</td>
                <td className="px-3 py-1.5 text-xs text-[var(--kwabo-muted)]">
                  {a.label ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <button
                    onClick={() => remove(a.id)}
                    className="text-xs text-rose-700 hover:underline"
                  >
                    Verwijder
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
