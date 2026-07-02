"use client";

import { useState } from "react";
import type { FieldMeta, Item } from "@/lib/api";
import { FieldInput } from "./field-input";
import { ProvenanceBadge } from "./provenance-badge";

export type Regel = {
  positie: number;
  artikelnummer_klant: string | null;
  artikelnummer_kwabo: string | null;
  artikelnummer_kwabo_matched: string | null;
  omschrijving: string | null;
  hoeveelheid: number | null;
  eenheid: string | null;
  // What the LLM read from the mail BEFORE match_articles overwrote eenheid
  // with the NAV-side base UoM. Shown as a tooltip / sub-line so the
  // reviewer can see "klant schreef PAL, NAV pusht STUK".
  eenheid_origineel?: string | null;
  // Branch A / mix: de eenheid + het omgerekende aantal dat daadwerkelijk
  // naar NAV gaat ("60 STUK -> 2 × PALLET"). C1: de reviewer moet de
  // omrekening zien, niet alleen de bestelde regel.
  verkoop_uom_gekozen?: string | null;
  verkoop_aantal?: number | null;
  mix_uom_gekozen?: string | null;
  mix_aantal?: number | null;
  prijs_per_eenheid: number | null;
  prijs_validated: boolean | null;
  ean_code: string | null;
  leverdatum_regel: string | null;
  opmerkingen: string | null;
  match_methode?: string | null;
  match_confidence?: number | null;
};

function fmtQty(n: number | null): string {
  if (n == null) return "—";
  return Number.isInteger(n) ? String(n) : n.toLocaleString("nl-NL");
}

function fmtPrice(n: number | null): string {
  if (n == null) return "—";
  return `€ ${n.toLocaleString("nl-NL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function OrderLinesTable({
  regels,
  regelsMeta,
  items,
  onPatch,
}: {
  regels: Regel[];
  regelsMeta: Array<Record<string, FieldMeta>>;
  items: Item[];
  onPatch: (path: string, value: unknown) => void;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function expandAll() {
    setExpanded(new Set(regels.map((_, i) => i)));
  }
  function collapseAll() {
    setExpanded(new Set());
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Orderregels ({regels.length})
        </div>
        {regels.length > 0 && (
          <div className="flex gap-2 text-[11px]">
            <button
              onClick={expandAll}
              className="rounded border border-[var(--kwabo-border)] bg-white px-2 py-0.5 hover:bg-slate-50"
            >
              Alles open
            </button>
            <button
              onClick={collapseAll}
              className="rounded border border-[var(--kwabo-border)] bg-white px-2 py-0.5 hover:bg-slate-50"
            >
              Alles dicht
            </button>
          </div>
        )}
      </div>

      {regels.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs text-slate-500">
          Geen orderregels geëxtraheerd.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-[var(--kwabo-border)]">
          <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-xs">
            <thead className="bg-slate-50 text-[10px] uppercase text-slate-500">
              <tr>
                <th className="px-2 py-1.5 text-left font-semibold">#</th>
                <th className="px-2 py-1.5 text-left font-semibold">Klant artnr</th>
                <th className="px-2 py-1.5 text-left font-semibold">Kwabo artnr</th>
                <th className="px-2 py-1.5 text-left font-semibold">Omschrijving</th>
                <th className="px-2 py-1.5 text-right font-semibold">Aantal</th>
                <th className="px-2 py-1.5 text-left font-semibold">Eenh</th>
                <th className="px-2 py-1.5 text-right font-semibold">Prijs</th>
                <th className="px-2 py-1.5 text-left font-semibold">Bron</th>
                <th className="px-2 py-1.5 text-right font-semibold"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--kwabo-border)] bg-white">
              {regels.map((r, i) => {
                const rm = regelsMeta[i] || {};
                const matchedMeta = rm.artikelnummer_kwabo_matched as FieldMeta | undefined;
                const prijsMeta = rm.prijs_per_eenheid as FieldMeta | undefined;
                const validated = r.prijs_validated;
                const isExpanded = expanded.has(i);
                const isMissing = !r.artikelnummer_kwabo_matched;
                return (
                  <FragmentRow
                    key={i}
                    i={i}
                    r={r}
                    rm={rm}
                    matchedMeta={matchedMeta}
                    prijsMeta={prijsMeta}
                    validated={validated}
                    isExpanded={isExpanded}
                    isMissing={isMissing}
                    items={items}
                    onToggle={() => toggle(i)}
                    onPatch={onPatch}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <datalist id="kwabo-items">
        {items.map((it) => (
          <option key={it.number} value={it.number}>
            {it.displayName}
          </option>
        ))}
      </datalist>
    </div>
  );
}

function FragmentRow({
  i,
  r,
  rm,
  matchedMeta,
  prijsMeta,
  validated,
  isExpanded,
  isMissing,
  items,
  onToggle,
  onPatch,
}: {
  i: number;
  r: Regel;
  rm: Record<string, FieldMeta>;
  matchedMeta?: FieldMeta;
  prijsMeta?: FieldMeta;
  validated: boolean | null;
  isExpanded: boolean;
  isMissing: boolean;
  items: Item[];
  onToggle: () => void;
  onPatch: (path: string, value: unknown) => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className={`cursor-pointer transition hover:bg-slate-50 ${
          isMissing ? "bg-rose-50/40" : ""
        } ${isExpanded ? "bg-slate-50" : ""}`}
      >
        <td className="px-2 py-1.5 font-semibold text-[var(--kwabo-navy)]">{r.positie}</td>
        <td className="px-2 py-1.5 font-mono text-[11px]">
          {r.artikelnummer_klant || <span className="text-slate-400">—</span>}
        </td>
        <td className="px-2 py-1.5 font-mono text-[11px]">
          {r.artikelnummer_kwabo_matched ? (
            (() => {
              const isFuzzySpec =
                r.match_methode === "fuzzy" &&
                (r.match_confidence ?? 1) < 0.95;
              if (isFuzzySpec) {
                return (
                  <span
                    className="inline-flex items-center gap-1 rounded border-l-4 border-amber-500 bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-900"
                    title={`Fuzzy match (conf ${(r.match_confidence ?? 0).toFixed(2)}) — controleer item handmatig. Klik om te wijzigen.`}
                  >
                    <span aria-hidden>⚠</span>
                    <span>{r.artikelnummer_kwabo_matched}</span>
                  </span>
                );
              }
              return <span className="font-semibold">{r.artikelnummer_kwabo_matched}</span>;
            })()
          ) : (
            <span className="inline-flex rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-amber-300">
              niet gematcht
            </span>
          )}
        </td>
        <td className="max-w-[14rem] truncate px-2 py-1.5" title={r.omschrijving ?? ""}>
          {r.omschrijving || <span className="text-slate-400">—</span>}
        </td>
        <td className="px-2 py-1.5 text-right tabular-nums">{fmtQty(r.hoeveelheid)}</td>
        <td className="px-2 py-1.5">
          {r.eenheid ? (
            <span className="inline-flex flex-col leading-tight">
              <span>{r.eenheid}</span>
              {r.eenheid_origineel && r.eenheid_origineel.toUpperCase() !== r.eenheid.toUpperCase() && (
                <span
                  className="text-[9px] text-slate-400"
                  title={`Klant schreef "${r.eenheid_origineel}" — NAV pusht "${r.eenheid}" (basis-UoM)`}
                >
                  ← {r.eenheid_origineel}
                </span>
              )}
              {/* C1: de daadwerkelijke NAV-regel (mix > Branch A) mét
                  omrekening — "besteld 60 STUK → 2 × PALLET". */}
              {(() => {
                const navUom = r.mix_uom_gekozen || r.verkoop_uom_gekozen;
                const navAantal = r.mix_uom_gekozen ? r.mix_aantal : r.verkoop_aantal;
                if (!navUom || navAantal == null) return null;
                if (navUom.toUpperCase() === (r.eenheid || "").toUpperCase()
                    && Number(navAantal) === Number(r.hoeveelheid)) return null;
                return (
                  <span
                    data-testid={`regel-nav-eenheid-${r.positie}`}
                    className="mt-0.5 inline-flex w-fit rounded bg-slate-100 px-1 py-0.5 text-[9px] font-semibold text-slate-700 ring-1 ring-slate-200"
                    title={`Besteld ${fmtQty(r.hoeveelheid)} ${r.eenheid_origineel || r.eenheid} — naar NAV gaat ${fmtQty(navAantal)} × ${navUom}`}
                  >
                    → NAV: {fmtQty(navAantal)} × {navUom}
                  </span>
                );
              })()}
            </span>
          ) : (
            <span className="text-slate-400">—</span>
          )}
        </td>
        <td className="px-2 py-1.5 text-right tabular-nums">
          <span
            className={
              validated === false
                ? "font-medium text-rose-700"
                : validated === true
                  ? "text-emerald-700"
                  : ""
            }
          >
            {fmtPrice(r.prijs_per_eenheid)}
          </span>
        </td>
        <td className="px-2 py-1.5">
          {matchedMeta ? <ProvenanceBadge meta={matchedMeta} size="xs" showLabel /> : (
            <span className="text-slate-300">—</span>
          )}
        </td>
        <td className="px-2 py-1.5 text-right text-slate-400">
          <span className="inline-block transition-transform duration-150" style={{ transform: isExpanded ? "rotate(90deg)" : "none" }}>
            ▶
          </span>
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-slate-50/50">
          <td colSpan={9} className="px-4 py-3">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <FieldInput
                label="Klant artnr"
                path={`orderregels[${i}].artikelnummer_klant`}
                value={r.artikelnummer_klant ?? ""}
                meta={(rm.artikelnummer_klant as FieldMeta) || undefined}
                onChange={(v) => onPatch(`orderregels[${i}].artikelnummer_klant`, v)}
                monospace
              />
              <FieldInput
                label="Kwabo artnr (matched)"
                path={`orderregels[${i}].artikelnummer_kwabo_matched`}
                value={r.artikelnummer_kwabo_matched ?? ""}
                meta={matchedMeta}
                list="kwabo-items"
                onChange={(v) => onPatch(`orderregels[${i}].artikelnummer_kwabo_matched`, v)}
                monospace
              />
              <FieldInput
                label="Hoeveelheid"
                type="number"
                path={`orderregels[${i}].hoeveelheid`}
                value={r.hoeveelheid ?? ""}
                meta={(rm.hoeveelheid as FieldMeta) || undefined}
                onChange={(v) => onPatch(`orderregels[${i}].hoeveelheid`, v)}
              />
              <FieldInput
                label="Eenheid"
                path={`orderregels[${i}].eenheid`}
                value={r.eenheid ?? ""}
                meta={(rm.eenheid as FieldMeta) || undefined}
                onChange={(v) => onPatch(`orderregels[${i}].eenheid`, v)}
              />
              <div className="md:col-span-2">
                <FieldInput
                  label="Omschrijving"
                  path={`orderregels[${i}].omschrijving`}
                  value={r.omschrijving ?? ""}
                  meta={(rm.omschrijving as FieldMeta) || undefined}
                  onChange={(v) => onPatch(`orderregels[${i}].omschrijving`, v)}
                />
              </div>
              <div>
                <FieldInput
                  label="Prijs/eenheid"
                  type="number"
                  path={`orderregels[${i}].prijs_per_eenheid`}
                  value={r.prijs_per_eenheid ?? ""}
                  meta={prijsMeta}
                  onChange={(v) => onPatch(`orderregels[${i}].prijs_per_eenheid`, v)}
                />
                <div className="mt-1 text-[10px]">
                  {validated === true && <span className="text-emerald-700">✓ Prijs valide</span>}
                  {validated === false && (
                    <span className="text-rose-700">
                      ✗ {prijsMeta?.source_detail || "afwijking t.o.v. afspraak"}
                    </span>
                  )}
                  {validated === null && <span className="text-slate-400">geen prijsafspraak</span>}
                </div>
              </div>
              <FieldInput
                label="EAN"
                path={`orderregels[${i}].ean_code`}
                value={r.ean_code ?? ""}
                meta={(rm.ean_code as FieldMeta) || undefined}
                onChange={(v) => onPatch(`orderregels[${i}].ean_code`, v)}
                monospace
              />
              <FieldInput
                label="Leverdatum regel"
                type="date"
                path={`orderregels[${i}].leverdatum_regel`}
                value={r.leverdatum_regel ?? ""}
                meta={(rm.leverdatum_regel as FieldMeta) || undefined}
                onChange={(v) => onPatch(`orderregels[${i}].leverdatum_regel`, v)}
              />
              <div className="md:col-span-4">
                <FieldInput
                  label="Opmerkingen bij regel"
                  path={`orderregels[${i}].opmerkingen`}
                  value={r.opmerkingen ?? ""}
                  meta={(rm.opmerkingen as FieldMeta) || undefined}
                  onChange={(v) => onPatch(`orderregels[${i}].opmerkingen`, v)}
                />
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
