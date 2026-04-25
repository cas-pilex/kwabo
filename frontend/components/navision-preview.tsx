"use client";

import { useEffect, useState } from "react";
import { api, type FieldMeta } from "@/lib/api";
import { ProvenanceBadge } from "./provenance-badge";

type Preview = Awaited<ReturnType<typeof api.navisionPreview>>;

const REQUIRED_HEADER = new Set([
  "customerNumber",
  "externalDocumentNumber",
  "requestedDeliveryDate",
]);
const REQUIRED_LINE = new Set(["itemNumber", "quantity", "unitOfMeasureCode"]);

const HEADER_LABELS: Record<string, string> = {
  customerNumber: "Klantnummer",
  externalDocumentNumber: "Bestelnr klant",
  requestedDeliveryDate: "Gewenste leverdatum",
  shipToName: "Afleveradres · naam",
  shipToAddressLine1: "Afleveradres · straat",
  shipToCity: "Afleveradres · plaats",
  shipToPostCode: "Afleveradres · postcode",
  shipToCountry: "Afleveradres · land",
  comment: "Opmerkingen",
  shippingInstructions: "Afleverinstructies",
};

const LINE_LABELS: Record<string, string> = {
  itemNumber: "Artikel",
  quantity: "Aantal",
  unitOfMeasureCode: "Eenheid",
  unitPrice: "Prijs/eenheid",
  shipmentDate: "Leverdatum",
  description2: "Omschrijving 2",
};

function deriveHeaderMeta(
  orderState: Record<string, unknown>,
  field: string,
): FieldMeta | undefined {
  const meta = (orderState?._meta as Record<string, FieldMeta> | undefined) || {};
  if (field === "customerNumber") return meta.klant_match;
  if (field === "externalDocumentNumber") return meta.bestelnummer_klant;
  if (field === "requestedDeliveryDate") return meta.gewenste_leverdatum;
  if (field.startsWith("shipTo")) return meta.afleveradres;
  if (field === "comment") return meta.opmerkingen;
  if (field === "shippingInstructions") return meta.afleverinstructies;
  return undefined;
}

function deriveLineMeta(
  orderState: Record<string, unknown>,
  lineIdx: number,
  field: string,
): FieldMeta | undefined {
  const m = orderState?._meta as { orderregels?: Array<Record<string, FieldMeta>> } | undefined;
  const lineMeta = m?.orderregels?.[lineIdx] || {};
  if (field === "itemNumber") return lineMeta.artikelnummer_kwabo_matched;
  if (field === "quantity") return lineMeta.hoeveelheid;
  if (field === "unitOfMeasureCode") return lineMeta.eenheid;
  if (field === "unitPrice") return lineMeta.prijs_per_eenheid;
  if (field === "shipmentDate") return lineMeta.leverdatum_regel;
  if (field === "description2") return lineMeta.opmerkingen;
  return undefined;
}

function isEmpty(v: unknown): boolean {
  return v == null || v === "" || (typeof v === "string" && v.trim() === "");
}

function fmtVal(v: unknown): string {
  if (v == null || v === "") return "";
  if (typeof v === "number") return String(v);
  return String(v);
}

export function NavisionPreview({
  orderId,
  refreshKey,
  orderState,
}: {
  orderId: number;
  refreshKey: number;
  orderState?: Record<string, unknown>;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.navisionPreview(orderId)
      .then((p) => !cancelled && (setPreview(p), setErr(null)))
      .catch((e) => !cancelled && setErr(String(e)));
    return () => {
      cancelled = true;
    };
  }, [orderId, refreshKey]);

  if (err) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
        Kan preview niet laden: {err}
      </div>
    );
  }
  if (!preview) {
    return (
      <div className="rounded-lg bg-white p-4 text-sm text-slate-500 ring-1 ring-[var(--kwabo-border)]">
        Laden…
      </div>
    );
  }

  const header = preview.body.header || {};
  const lines = preview.body.lines || [];
  const statusBadge =
    preview.status === "ready"
      ? { cls: "bg-emerald-100 text-emerald-800 ring-emerald-300", text: "🟢 Klaar voor push" }
      : preview.status === "no_customer"
        ? { cls: "bg-rose-100 text-rose-800 ring-rose-300", text: "🔴 Klant niet gematcht" }
        : {
            cls: "bg-amber-100 text-amber-800 ring-amber-300",
            text: `🟡 ${preview.missing_count} velden ontbreken`,
          };

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(preview!.body, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }

  // Full list of header-keys to show (includes empties for required fields that aren't in payload yet)
  const allHeaderKeys = Array.from(
    new Set<string>([
      ...REQUIRED_HEADER,
      ...Object.keys(header),
      "shipToName",
      "shipToAddressLine1",
      "shipToPostCode",
      "shipToCity",
      "shipToCountry",
    ]),
  );

  return (
    <div className="space-y-3">
      {/* Endpoint + status */}
      <div className="rounded-lg bg-white p-3 text-xs ring-1 ring-[var(--kwabo-border)]">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[11px] text-[var(--kwabo-muted)]">
            <span className="font-semibold text-[var(--kwabo-navy)]">{preview.method}</span>{" "}
            {preview.url}
          </span>
          <span
            className={`inline-flex rounded px-2 py-0.5 text-xs ring-1 ring-inset ${statusBadge.cls}`}
          >
            {statusBadge.text}
          </span>
        </div>
      </div>

      {/* Header table */}
      <div className="overflow-hidden rounded-lg bg-white ring-1 ring-[var(--kwabo-border)]">
        <div className="bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Header
        </div>
        <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-xs">
          <thead className="bg-slate-50 text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-3 py-1.5 text-left font-semibold">Veld</th>
              <th className="px-3 py-1.5 text-left font-semibold">Waarde</th>
              <th className="px-3 py-1.5 text-left font-semibold">Bron</th>
              <th className="px-3 py-1.5 text-left font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--kwabo-border)]">
            {allHeaderKeys.map((k) => {
              const val = (header as Record<string, unknown>)[k];
              const empty = isEmpty(val);
              const required = REQUIRED_HEADER.has(k);
              const meta = orderState ? deriveHeaderMeta(orderState, k) : undefined;
              return (
                <tr key={k} className={empty && required ? "bg-rose-50/40" : ""}>
                  <td className="px-3 py-1.5 font-medium text-slate-700">
                    {HEADER_LABELS[k] ?? k}
                    {required && <span className="ml-1 text-rose-600">*</span>}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px]">
                    {empty ? (
                      <span className="italic text-slate-400">(leeg)</span>
                    ) : (
                      fmtVal(val)
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    {meta ? <ProvenanceBadge meta={meta} size="xs" showLabel /> : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    {empty && required ? (
                      <span className="inline-flex rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800 ring-1 ring-rose-300">
                        VERPLICHT — ontbreekt
                      </span>
                    ) : empty ? (
                      <span className="text-slate-400">optioneel</span>
                    ) : (
                      <span className="text-emerald-700">✓</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Lines */}
      <div className="overflow-hidden rounded-lg bg-white ring-1 ring-[var(--kwabo-border)]">
        <div className="bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Orderregels ({lines.length})
        </div>
        {lines.length === 0 ? (
          <div className="px-3 py-4 text-xs text-slate-500">
            Geen regels met gematchte artikelnummers — voeg eerst minstens één kwabo-artikelnr toe links.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-xs">
            <thead className="bg-slate-50 text-[10px] uppercase text-slate-500">
              <tr>
                <th className="px-3 py-1.5 text-left font-semibold">#</th>
                <th className="px-3 py-1.5 text-left font-semibold">Veld</th>
                <th className="px-3 py-1.5 text-left font-semibold">Waarde</th>
                <th className="px-3 py-1.5 text-left font-semibold">Bron</th>
                <th className="px-3 py-1.5 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--kwabo-border)]">
              {lines.map((line, li) => {
                const keys = Array.from(
                  new Set<string>([
                    ...REQUIRED_LINE,
                    ...Object.keys(line),
                  ]),
                );
                return keys.map((k, ki) => {
                  const val = (line as Record<string, unknown>)[k];
                  const empty = isEmpty(val);
                  const required = REQUIRED_LINE.has(k);
                  const meta = orderState ? deriveLineMeta(orderState, li, k) : undefined;
                  return (
                    <tr
                      key={`${li}-${k}`}
                      className={empty && required ? "bg-rose-50/40" : ""}
                    >
                      <td className="px-3 py-1.5 font-semibold text-[var(--kwabo-navy)]">
                        {ki === 0 ? li + 1 : ""}
                      </td>
                      <td className="px-3 py-1.5 font-medium text-slate-700">
                        {LINE_LABELS[k] ?? k}
                        {required && <span className="ml-1 text-rose-600">*</span>}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[11px]">
                        {empty ? (
                          <span className="italic text-slate-400">(leeg)</span>
                        ) : (
                          fmtVal(val)
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {meta ? (
                          <ProvenanceBadge meta={meta} size="xs" showLabel />
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {empty && required ? (
                          <span className="inline-flex rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800 ring-1 ring-rose-300">
                            VERPLICHT
                          </span>
                        ) : empty ? (
                          <span className="text-slate-400">optioneel</span>
                        ) : (
                          <span className="text-emerald-700">✓</span>
                        )}
                      </td>
                    </tr>
                  );
                });
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Toggle raw JSON */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-xs text-[var(--kwabo-muted)] underline underline-offset-2 hover:text-[var(--kwabo-navy)]"
        >
          {showRaw ? "← Verberg raw JSON" : "Toon raw JSON payload →"}
        </button>
        <button
          onClick={copyJson}
          className="rounded border border-[var(--kwabo-border)] bg-white px-2 py-1 text-xs hover:bg-slate-50"
        >
          {copied ? "✓ Gekopieerd" : "Kopieer JSON"}
        </button>
      </div>
      {showRaw && (
        <pre className="max-h-96 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-200">
          {JSON.stringify(preview.body, null, 2)}
        </pre>
      )}
    </div>
  );
}
