"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { AfzendersTab } from "@/components/afzenders-tab";
import { DocumentenTab } from "@/components/documenten-tab";
import { PrijsafsprakenTab } from "@/components/prijsafspraken-tab";

type Tab = "algemeen" | "afzenders" | "mappings" | "prijzen" | "documenten" | "import";

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
  const [importMsg, setImportMsg] = useState<string>("");
  const [mapErr, setMapErr] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  async function reloadMappings() {
    try {
      setMappings(await api.listMappings(nr));
    } catch (e) {
      setMapErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function doImport(file: File) {
    setImportMsg("Bezig…");
    try {
      const r = await api.importExcel(nr, file);
      setImportMsg(`✓ ${r.mappings_upserted} mappings + ${r.prijzen_upserted} prijzen (${r.errors.length} fouten)`);
      await reloadMappings();
    } catch (e) {
      setImportMsg(`Fout: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function deleteMapping(id: number, label: string) {
    if (!window.confirm(`Mapping "${label}" verwijderen? De koppeling wordt niet meer gebruikt bij toekomstige orders.`)) {
      return;
    }
    setMapErr("");
    try {
      await api.deleteMapping(nr, id);
      await reloadMappings();
    } catch (e) {
      setMapErr(e instanceof Error ? e.message : String(e));
    }
  }

  const tabBtn = (t: Tab, label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={tab === t}
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
        {tabBtn("afzenders", "Afzenders / aliases")}
        {tabBtn("mappings", `Artikelmappings (${mappings.length})`)}
        {tabBtn("prijzen", "Prijsafspraken")}
        {tabBtn("documenten", "Documenten")}
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
            {mapErr && <div className="mb-2 text-sm text-rose-600">{mapErr}</div>}
            {mappings.length === 0 ? (
              <div className="text-sm text-[var(--kwabo-muted)]">
                Nog geen artikelmappings. Voeg ze bulksgewijs toe via de tab{" "}
                <button type="button" onClick={() => setTab("import")} className="font-medium text-[var(--kwabo-navy)] underline">
                  Import Excel
                </button>
                . Ze ontstaan ook automatisch wanneer je in een order-review een artikel handmatig koppelt.
              </div>
            ) : (
              <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-[var(--kwabo-muted)]">
                  <tr>
                    <th className="px-3 py-1.5 text-left">Klant-artnr</th>
                    <th className="px-3 py-1.5 text-left">Kwabo-artnr</th>
                    <th className="px-3 py-1.5 text-left">Omschrijving</th>
                    <th className="px-3 py-1.5"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--kwabo-border)]">
                  {mappings.map((m) => (
                    <tr key={m.id}>
                      <td className="px-3 py-1.5 font-mono text-xs">{m.klant_artikelnr}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{m.kwabo_artikelnr}</td>
                      <td className="px-3 py-1.5 text-[var(--kwabo-muted)]">{m.omschrijving ?? ""}</td>
                      <td className="px-3 py-1.5 text-right">
                        <button
                          onClick={() => deleteMapping(m.id, `${m.klant_artikelnr} → ${m.kwabo_artikelnr}`)}
                          className="text-xs text-rose-600 hover:underline"
                        >
                          verwijder
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === "afzenders" && (
          <AfzendersTab
            klantNr={nr}
            primaryEmail={klant.email}
            primaryOrderEmail={klant.email_bestelling}
          />
        )}

        {tab === "prijzen" && <PrijsafsprakenTab klantNr={nr} />}

        {tab === "documenten" && <DocumentenTab klantNr={nr} />}

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
