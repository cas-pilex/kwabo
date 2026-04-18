"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Tab = "algemeen" | "mappings" | "prijzen" | "import";

export function KlantTabs({
  nr,
  klant,
  initialMappings,
}: {
  nr: string;
  klant: { naam: string; email: string | null; email_bestelling: string | null; taal: string };
  initialMappings: Array<{ id: number; klant_artikelnr: string; kwabo_artikelnr: string; omschrijving: string | null }>;
}) {
  const [tab, setTab] = useState<Tab>("algemeen");
  const [mappings, setMappings] = useState(initialMappings);
  const [prijzen, setPrijzen] = useState<Awaited<ReturnType<typeof api.listPrijzen>>>([]);
  const [loadedPrijzen, setLoadedPrijzen] = useState(false);
  const [newPrijs, setNewPrijs] = useState({ kwabo_artikelnr: "", prijs: "", korting_pct: "0" });
  const [importMsg, setImportMsg] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (tab === "prijzen" && !loadedPrijzen) {
      api.listPrijzen(nr).then((p) => {
        setPrijzen(p);
        setLoadedPrijzen(true);
      });
    }
  }, [tab, loadedPrijzen, nr]);

  async function addPrijs() {
    const prijs = parseFloat(newPrijs.prijs);
    if (!newPrijs.kwabo_artikelnr || isNaN(prijs)) return;
    await api.addPrijs(nr, {
      kwabo_artikelnr: newPrijs.kwabo_artikelnr,
      prijs,
      korting_pct: parseFloat(newPrijs.korting_pct) || 0,
    });
    setNewPrijs({ kwabo_artikelnr: "", prijs: "", korting_pct: "0" });
    setPrijzen(await api.listPrijzen(nr));
  }

  async function delPrijs(id: number) {
    if (!confirm("Prijsafspraak verwijderen?")) return;
    await api.deletePrijs(nr, id);
    setPrijzen(await api.listPrijzen(nr));
  }

  async function doImport(file: File) {
    setImportMsg("Bezig…");
    try {
      const r = await api.importExcel(nr, file);
      setImportMsg(`✓ ${r.mappings_upserted} mappings + ${r.prijzen_upserted} prijzen (${r.errors.length} fouten)`);
      setLoadedPrijzen(false); // refresh on next tab visit
    } catch (e) {
      setImportMsg(`Fout: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  const tabBtn = (t: Tab, label: string) => (
    <button
      onClick={() => setTab(t)}
      className={`rounded-t px-4 py-2 text-sm font-medium ${
        tab === t
          ? "bg-white text-[var(--kwabo-navy)] border-x border-t border-[var(--kwabo-border)]"
          : "text-[var(--kwabo-muted)] hover:text-[var(--kwabo-navy)]"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="flex gap-1 border-b border-[var(--kwabo-border)]">
        {tabBtn("algemeen", "Algemeen")}
        {tabBtn("mappings", `Artikelmappings (${mappings.length})`)}
        {tabBtn("prijzen", "Prijsafspraken")}
        {tabBtn("import", "Import Excel")}
      </div>

      <div className="rounded-b-lg border-x border-b border-[var(--kwabo-border)] bg-white p-4">
        {tab === "algemeen" && (
          <div className="space-y-2 text-sm">
            <div><span className="text-[var(--kwabo-muted)] w-40 inline-block">Naam:</span> {klant.naam}</div>
            <div><span className="text-[var(--kwabo-muted)] w-40 inline-block">E-mail:</span> {klant.email}</div>
            <div><span className="text-[var(--kwabo-muted)] w-40 inline-block">Bestel-adres:</span> {klant.email_bestelling ?? "—"}</div>
            <div><span className="text-[var(--kwabo-muted)] w-40 inline-block">Taal:</span> {klant.taal}</div>
          </div>
        )}

        {tab === "mappings" && (
          <div>
            {mappings.length === 0 ? (
              <div className="text-sm text-[var(--kwabo-muted)]">Nog geen mappings. Import via Excel of voeg toe via correcties in review.</div>
            ) : (
              <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-[var(--kwabo-muted)]">
                  <tr>
                    <th className="px-3 py-1.5 text-left">Klant-artnr</th>
                    <th className="px-3 py-1.5 text-left">Kwabo-artnr</th>
                    <th className="px-3 py-1.5 text-left">Omschrijving</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--kwabo-border)]">
                  {mappings.map((m) => (
                    <tr key={m.id}>
                      <td className="px-3 py-1.5 font-mono text-xs">{m.klant_artikelnr}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{m.kwabo_artikelnr}</td>
                      <td className="px-3 py-1.5 text-[var(--kwabo-muted)]">{m.omschrijving ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === "prijzen" && (
          <div>
            <div className="mb-3 flex flex-wrap items-end gap-2 rounded bg-slate-50 p-3">
              <div>
                <label className="block text-[10px] uppercase text-[var(--kwabo-muted)]">Kwabo-artnr</label>
                <input
                  value={newPrijs.kwabo_artikelnr}
                  onChange={(e) => setNewPrijs({ ...newPrijs, kwabo_artikelnr: e.target.value })}
                  className="rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm font-mono"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase text-[var(--kwabo-muted)]">Prijs €</label>
                <input
                  type="number"
                  step="0.01"
                  value={newPrijs.prijs}
                  onChange={(e) => setNewPrijs({ ...newPrijs, prijs: e.target.value })}
                  className="w-28 rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase text-[var(--kwabo-muted)]">Korting %</label>
                <input
                  type="number"
                  step="0.1"
                  value={newPrijs.korting_pct}
                  onChange={(e) => setNewPrijs({ ...newPrijs, korting_pct: e.target.value })}
                  className="w-20 rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm"
                />
              </div>
              <button
                onClick={addPrijs}
                className="rounded-md bg-[var(--kwabo-navy)] px-3 py-1.5 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)]"
              >
                Toevoegen
              </button>
            </div>
            {prijzen.length === 0 ? (
              <div className="text-sm text-[var(--kwabo-muted)]">Geen prijsafspraken.</div>
            ) : (
              <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-[var(--kwabo-muted)]">
                  <tr>
                    <th className="px-3 py-1.5 text-left">Artikel</th>
                    <th className="px-3 py-1.5 text-right">Prijs</th>
                    <th className="px-3 py-1.5 text-right">Korting</th>
                    <th className="px-3 py-1.5 text-left">Type</th>
                    <th className="px-3 py-1.5 text-left">Geldig tot</th>
                    <th className="px-3 py-1.5"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--kwabo-border)]">
                  {prijzen.map((p) => (
                    <tr key={p.id}>
                      <td className="px-3 py-1.5 font-mono text-xs">{p.kwabo_artikelnr}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">€ {p.prijs.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{p.korting_pct}%</td>
                      <td className="px-3 py-1.5 text-xs">{p.type}</td>
                      <td className="px-3 py-1.5 text-xs">{p.geldig_tot ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">
                        <button onClick={() => delPrijs(p.id)} className="text-xs text-rose-600 hover:underline">verwijder</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === "import" && (
          <div className="space-y-3 text-sm">
            <p className="text-[var(--kwabo-muted)]">
              Upload een Excel (.xlsx) met kolommen: <code>klant_artikelnr</code>, <code>kwabo_artikelnr</code>,
              en optioneel <code>omschrijving</code>, <code>prijs</code>, <code>korting_pct</code>, <code>geldig_tot</code>.
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) doImport(f);
              }}
            />
            {importMsg && <div className={`text-sm ${importMsg.startsWith("✓") ? "text-emerald-700" : importMsg.startsWith("Fout") ? "text-rose-700" : "text-[var(--kwabo-muted)]"}`}>{importMsg}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
