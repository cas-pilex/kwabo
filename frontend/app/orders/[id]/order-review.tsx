"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type FieldMeta, type Item, type OrderDetail } from "@/lib/api";
import { FieldInput } from "@/components/field-input";
import { NavisionPreview } from "@/components/navision-preview";
import { NeedsReviewBanner } from "@/components/needs-review-banner";
import { ProvenanceBadge } from "@/components/provenance-badge";

type Props = { order: OrderDetail; items: Item[] };

type Regel = {
  positie: number;
  artikelnummer_klant: string | null;
  artikelnummer_kwabo: string | null;
  artikelnummer_kwabo_matched: string | null;
  omschrijving: string | null;
  hoeveelheid: number | null;
  eenheid: string | null;
  prijs_per_eenheid: number | null;
  prijs_validated: boolean | null;
  ean_code: string | null;
  leverdatum_regel: string | null;
  opmerkingen: string | null;
  match_methode?: string | null;
  match_confidence?: number | null;
};

type Address = {
  naam?: string;
  straat?: string;
  postcode?: string;
  plaats?: string;
  land?: string;
};

type State = {
  klant_match?: { navision_klantnr?: string; klantnaam?: string; match_bron?: string; match_confidence?: number; is_4plus?: boolean; kredietlimiet?: number | null; betalingsconditie?: string | null };
  bestelnummer_klant?: string | null;
  orderdatum?: string | null;
  gewenste_leverdatum?: string | null;
  afleveradres?: Address | null;
  afleverinstructies?: string | null;
  opmerkingen?: string | null;
  orderregels?: Regel[];
  bijlagen?: Array<{ naam: string; type: string; inhoud_tekst: string }>;
  email_body?: string;
  _meta?: {
    klant_match?: FieldMeta;
    bestelnummer_klant?: FieldMeta;
    orderdatum?: FieldMeta;
    gewenste_leverdatum?: FieldMeta;
    afleveradres?: FieldMeta;
    afleverinstructies?: FieldMeta;
    opmerkingen?: FieldMeta;
    orderregels?: Array<Record<string, FieldMeta>>;
  };
  needs_review_fields?: string[];
};

export function OrderReview({ order, items }: Props) {
  const router = useRouter();
  const initialState = (order.order_state || {}) as State;
  const [missing, setMissing] = useState<string[]>(initialState.needs_review_fields || []);
  const [forceArmed, setForceArmed] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const meta = initialState._meta || {};
  const regels = initialState.orderregels || [];
  const regelsMeta = meta.orderregels || [];
  const ship = initialState.afleveradres || {};

  // Refresh missing list periodically (after PATCH)
  async function refresh() {
    try {
      const r = await api.needsReview(order.id);
      setMissing(r.fields);
      setPreviewKey((k) => k + 1);
    } catch {}
  }

  useEffect(() => { /* no-op on mount; rely on initial */ }, []);

  async function patch(path: string, value: unknown) {
    try {
      const r = await api.patchField(order.id, path, value);
      setMissing(r.needs_review_fields);
      setPreviewKey((k) => k + 1);
    } catch (e) {
      setMsg(`Patch-fout: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function approve() {
    setSaving(true);
    setMsg(null);
    try {
      const r = await api.approve(order.id, { reviewer: "dashboard" }, { force: forceArmed });
      setMsg(`✓ Gepusht naar Navision: ${r.navision_order_nr}${r.forced ? " (force)" : ""}`);
      router.refresh();
    } catch (e) {
      setMsg(`Fout: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  async function reject() {
    setSaving(true);
    try {
      await api.reject(order.id, { reviewer: "dashboard", reason: "Manual reject" });
      setMsg("Afgewezen");
      router.refresh();
    } catch (e) {
      setMsg(`Fout: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  const blocked = missing.length > 0 && !forceArmed;
  const isNotOrder = order.status === "not_order";
  const canAct = order.status === "review" && !isNotOrder;

  return (
    <div className="space-y-4">
      {!isNotOrder && (
        <NeedsReviewBanner fields={missing} forceArmed={forceArmed} onToggleForce={setForceArmed} />
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* COL 1 — E-mail & PDF */}
        <section className="lg:col-span-4 rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[var(--kwabo-navy)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--kwabo-gold)]" /> E-mail &amp; PDF
          </h2>
          <div className="text-xs text-[var(--kwabo-muted)]">
            van <span className="font-medium text-[var(--kwabo-text)]">{order.email_from}</span>
            <br />
            {order.email_date}
          </div>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px] text-slate-800 ring-1 ring-slate-200">
            {initialState.email_body || "(geen body)"}
          </pre>
          <div className="mt-3 space-y-2">
            {(initialState.bijlagen || []).map((b, i) => (
              <details key={i} className="rounded border border-[var(--kwabo-border)]" open={i === 0}>
                <summary className="cursor-pointer bg-slate-50 px-2 py-1 text-xs">
                  <span className="font-medium">{b.naam}</span>
                  <span className="ml-2 rounded bg-slate-200 px-1 py-0.5 text-[10px] uppercase">{b.type}</span>
                </summary>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap p-2 text-[10px] leading-relaxed text-slate-700">
                  {b.inhoud_tekst?.slice(0, 12000)}
                </pre>
              </details>
            ))}
          </div>
        </section>

        {/* COL 2 — Extract + Klantkaart (editable) */}
        <section className="lg:col-span-4 rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[var(--kwabo-navy)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--kwabo-gold)]" /> Extract + Klantkaart
          </h2>

          {/* Klant */}
          <div className="mb-4 rounded-lg border border-[var(--kwabo-border)] bg-slate-50 p-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">Klant</div>
            <FieldInput
              label="Navision klantnr."
              path="klant_match"
              value={initialState.klant_match?.navision_klantnr ?? ""}
              meta={meta.klant_match}
              onChange={(v) => patch("klant_match", v)}
              monospace
            />
            {initialState.klant_match?.klantnaam && (
              <div className="mt-1 flex items-center gap-2 text-xs text-[var(--kwabo-muted)]">
                <span>{initialState.klant_match.klantnaam}</span>
                {initialState.klant_match?.is_4plus === true && (
                  <span className="inline-flex rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                    4+ lid
                  </span>
                )}
                {initialState.klant_match?.is_4plus === false && (
                  <span className="inline-flex rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 ring-1 ring-rose-200">
                    geen 4+
                  </span>
                )}
                {initialState.klant_match?.kredietlimiet != null && Number(initialState.klant_match.kredietlimiet) > 0 && (
                  <span className="inline-flex rounded bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 ring-1 ring-sky-200">
                    krediet € {Number(initialState.klant_match.kredietlimiet).toLocaleString("nl-NL")}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Header */}
          <div className="mb-4 grid grid-cols-2 gap-3">
            <FieldInput
              label="Bestelnr klant"
              path="bestelnummer_klant"
              value={initialState.bestelnummer_klant ?? ""}
              meta={meta.bestelnummer_klant}
              onChange={(v) => patch("bestelnummer_klant", v)}
            />
            <FieldInput
              label="Orderdatum"
              path="orderdatum"
              type="date"
              value={initialState.orderdatum ?? ""}
              meta={meta.orderdatum}
              onChange={(v) => patch("orderdatum", v)}
            />
            <FieldInput
              label="Gewenste leverdatum"
              path="gewenste_leverdatum"
              type="date"
              value={initialState.gewenste_leverdatum ?? ""}
              meta={meta.gewenste_leverdatum}
              onChange={(v) => patch("gewenste_leverdatum", v)}
            />
            <FieldInput
              label="Afleverinstructies"
              path="afleverinstructies"
              value={initialState.afleverinstructies ?? ""}
              meta={meta.afleverinstructies}
              onChange={(v) => patch("afleverinstructies", v)}
            />
          </div>

          {/* Adres */}
          <div className="mb-4 rounded-lg border border-[var(--kwabo-border)] bg-slate-50 p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
                Drop-ship adres
              </span>
              <ProvenanceBadge meta={meta.afleveradres} size="xs" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <FieldInput label="Naam" path="afleveradres.naam" value={ship.naam ?? ""}
                onChange={(v) => patch("afleveradres.naam", v)} />
              <FieldInput label="Straat" path="afleveradres.straat" value={ship.straat ?? ""}
                onChange={(v) => patch("afleveradres.straat", v)} />
              <FieldInput label="Postcode" path="afleveradres.postcode" value={ship.postcode ?? ""}
                onChange={(v) => patch("afleveradres.postcode", v)} />
              <FieldInput label="Plaats" path="afleveradres.plaats" value={ship.plaats ?? ""}
                onChange={(v) => patch("afleveradres.plaats", v)} />
              <FieldInput label="Land" path="afleveradres.land" value={ship.land ?? ""}
                onChange={(v) => patch("afleveradres.land", v)} />
            </div>
          </div>

          {/* Regels */}
          <div className="mb-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
              Orderregels ({regels.length})
            </div>
            <div className="space-y-2">
              {regels.map((r, i) => {
                const rm = regelsMeta[i] || {};
                const matchedMeta = rm.artikelnummer_kwabo_matched as FieldMeta | undefined;
                const prijsMeta = rm.prijs_per_eenheid as FieldMeta | undefined;
                const validated = r.prijs_validated;
                return (
                  <div key={i} className="rounded border border-[var(--kwabo-border)] bg-white p-2">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-xs font-semibold text-[var(--kwabo-navy)]">Regel {r.positie}</span>
                      <ProvenanceBadge meta={matchedMeta} size="xs" />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <FieldInput
                        label="Klant artnr"
                        path={`orderregels[${i}].artikelnummer_klant`}
                        value={r.artikelnummer_klant ?? ""}
                        meta={(rm.artikelnummer_klant as FieldMeta) || undefined}
                        onChange={(v) => patch(`orderregels[${i}].artikelnummer_klant`, v)}
                        monospace
                      />
                      <FieldInput
                        label="Kwabo artnr (matched)"
                        path={`orderregels[${i}].artikelnummer_kwabo_matched`}
                        value={r.artikelnummer_kwabo_matched ?? ""}
                        meta={matchedMeta}
                        list="kwabo-items"
                        onChange={(v) => patch(`orderregels[${i}].artikelnummer_kwabo_matched`, v)}
                        monospace
                      />
                      <div className="col-span-2">
                        <FieldInput
                          label="Omschrijving"
                          path={`orderregels[${i}].omschrijving`}
                          value={r.omschrijving ?? ""}
                          meta={(rm.omschrijving as FieldMeta) || undefined}
                          onChange={(v) => patch(`orderregels[${i}].omschrijving`, v)}
                        />
                      </div>
                      <FieldInput
                        label="Hoeveelheid"
                        type="number"
                        path={`orderregels[${i}].hoeveelheid`}
                        value={r.hoeveelheid ?? ""}
                        meta={(rm.hoeveelheid as FieldMeta) || undefined}
                        onChange={(v) => patch(`orderregels[${i}].hoeveelheid`, v)}
                      />
                      <FieldInput
                        label="Eenheid"
                        path={`orderregels[${i}].eenheid`}
                        value={r.eenheid ?? ""}
                        meta={(rm.eenheid as FieldMeta) || undefined}
                        onChange={(v) => patch(`orderregels[${i}].eenheid`, v)}
                      />
                      <div>
                        <FieldInput
                          label="Prijs/eenheid"
                          type="number"
                          path={`orderregels[${i}].prijs_per_eenheid`}
                          value={r.prijs_per_eenheid ?? ""}
                          meta={prijsMeta}
                          onChange={(v) => patch(`orderregels[${i}].prijs_per_eenheid`, v)}
                        />
                        <div className="mt-1 text-[10px]">
                          {validated === true && <span className="text-emerald-700">✓ Valide</span>}
                          {validated === false && <span className="text-rose-700">✗ {prijsMeta?.source_detail || "afwijking"}</span>}
                          {validated === null && <span className="text-slate-400">— geen afspraak</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <datalist id="kwabo-items">
              {items.map((it) => (
                <option key={it.number} value={it.number}>{it.displayName}</option>
              ))}
            </datalist>
          </div>

          <FieldInput
            label="Opmerkingen"
            path="opmerkingen"
            value={initialState.opmerkingen ?? ""}
            meta={meta.opmerkingen}
            onChange={(v) => patch("opmerkingen", v)}
          />

          {/* Acties */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              onClick={approve}
              disabled={saving || !canAct || blocked}
              title={blocked ? `Vul ${missing.length} velden in of activeer Force` : ""}
              className="rounded-md bg-[var(--kwabo-navy)] px-4 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-[var(--kwabo-navy-500)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Goedkeuren &amp; Push Navision
            </button>
            <button
              onClick={reject}
              disabled={saving || !canAct}
              className="rounded-md border border-rose-300 bg-white px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            >
              Afwijzen
            </button>
            <button
              onClick={refresh}
              className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
            >
              Refresh
            </button>
            {msg && (
              <span className={`text-xs ${msg.startsWith("✓") ? "text-emerald-700" : "text-rose-700"}`}>
                {msg}
              </span>
            )}
          </div>
        </section>

        {/* COL 3 — Navision request preview */}
        <section className="lg:col-span-4 rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[var(--kwabo-navy)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--kwabo-gold)]" /> Navision request
          </h2>
          <NavisionPreview orderId={order.id} refreshKey={previewKey} />
        </section>
      </div>

      {/* Audit trail full-width */}
      <section className="rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[var(--kwabo-navy)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--kwabo-gold)]" /> Audit trail (
          {order.stappen_log?.length ?? 0} stappen)
        </h2>
        <ol className="space-y-1 text-xs">
          {order.stappen_log?.map((s, i) => (
            <li key={i} className="flex gap-3 border-b border-[var(--kwabo-border)] pb-1 last:border-0">
              <span className="w-32 font-mono text-[var(--kwabo-navy-300)]">{String(s.stap)}</span>
              <span className="w-20 font-mono text-slate-400">{String(s.timestamp).slice(11, 19)}</span>
              <span className="flex-1 text-slate-700">{String(s.beslissing)}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
