"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import {
  api,
  type EuropalletRegel,
  type EuropalletMeta,
  type FieldMeta,
  type Item,
  type KlantKandidaat,
  type OrderDetail,
  type ShipToKandidaat,
} from "@/lib/api";
import { EmailSourceViewer } from "@/components/email-source-viewer";
import { FieldInput } from "@/components/field-input";
import { NeedsReviewBanner } from "@/components/needs-review-banner";
import { OrderLinesTable } from "@/components/order-lines-table";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { EuropalletEditor } from "./components/EuropalletEditor";
import { IncomingDocumentPanel } from "./components/IncomingDocumentPanel";
import { MixprijzenBadge } from "./components/MixprijzenBadge";
import { NavOperationsPreview } from "./components/NavOperationsPreview";
import { KlantPicker } from "./components/KlantPicker";
import { ShipToPicker } from "./components/ShipToPicker";
import {
  SourceDocLinkBanner,
  isSourceDocWarning,
} from "./components/SourceDocLinkBanner";

type Props = { order: OrderDetail; items: Item[] };

type Regel = {
  positie: number;
  artikelnummer_klant: string | null;
  artikelnummer_kwabo: string | null;
  artikelnummer_kwabo_matched: string | null;
  omschrijving: string | null;
  hoeveelheid: number | null;
  eenheid: string | null;
  eenheid_origineel?: string | null;
  prijs_per_eenheid: number | null;
  prijs_validated: boolean | null;
  ean_code: string | null;
  leverdatum_regel: string | null;
  opmerkingen: string | null;
  match_methode?: string | null;
  match_confidence?: number | null;
  mix_uom_kandidaat?: string[] | null;
  mix_uom_gekozen?: string | null;
};

type Address = {
  naam?: string;
  straat?: string;
  postcode?: string;
  plaats?: string;
  land?: string;
};

type State = {
  klant_match?: { navision_klantnr?: string; klantnaam?: string; plaats?: string | null; match_bron?: string; match_uitleg?: string; match_confidence?: number; leveradres_bevestigd?: boolean; is_4plus?: boolean; kredietlimiet?: number | null; betalingsconditie?: string | null };
  bestelnummer_klant?: string | null;
  orderdatum?: string | null;
  gewenste_leverdatum?: string | null;
  afleveradres?: Address | null;
  // B1: adressen mét rol uit de extractie (aflever/eindontvanger sturen
  // ship-to; besteller/factuur zijn context en mogen dat nooit).
  adres_rollen?: Partial<Record<"besteller" | "factuur" | "aflever" | "eindontvanger", Address | null>> | null;
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
    europallet?: EuropalletMeta;
    verzendwijze?: FieldMeta;
  };
  needs_review_fields?: string[];
  klant_kandidaten?: KlantKandidaat[];
  ship_to_kandidaten?: ShipToKandidaat[];
  ship_to_gekozen?: string | null;
  mixprijzen_actief?: boolean;
  order_mix_total_pallets?: number | null;
  verzendwijze?: string | null;
  europallet_regel?: EuropalletRegel | null;
  incoming_document_path?: string | null;
  navision_status?: string | null;
  errors?: string[] | null;
};

/* Cockpit-cel: het enige terugkerende bouwblok van de pagina. Eén vorm,
   één kleur — rust komt uit herhaling, niet uit variatie. */
function Cel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--kwabo-border)] bg-slate-50 p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
        {label}
      </div>
      {children}
    </div>
  );
}

/* Rustige, uniforme detail-sectie onder de vouw. */
function Sectie({
  titel,
  open,
  children,
}: {
  titel: string;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details
      open={open}
      className="group rounded-lg bg-white ring-1 ring-[var(--kwabo-border)]"
    >
      <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-semibold text-[var(--kwabo-navy)] hover:bg-slate-50">
        <span className="mr-1 inline-block text-[var(--kwabo-muted)] transition-transform group-open:rotate-90">▸</span>
        {titel}
      </summary>
      <div className="border-t border-[var(--kwabo-border)] p-4">{children}</div>
    </details>
  );
}

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
    } catch (e) {
      // Een stille catch liet de Refresh-knop (en alle onChanged-callbacks van
      // ShipToPicker/Europallet/IncomingDocument) niets doen bij een fout —
      // de reviewer zag dan geen reactie. Toon het wél.
      toast.error(`Verversen mislukt: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function patch(path: string, value: unknown) {
    try {
      const r = await api.patchField(order.id, path, value);
      setMissing(r.needs_review_fields);
      setPreviewKey((k) => k + 1);
      // Alle badges/pills (ProvenanceBadge "ONTBREEKT", "niet gematcht",
      // klantnaam) renderen uit initialState — zonder server-refresh blijft
      // de rode status na een handmatige fix staan (M1, Van Dongen-case).
      // router.refresh() haalt de page-props opnieuw op en behoudt
      // client-state, dus in-flight edits in andere velden overleven dit.
      router.refresh();
    } catch (e) {
      const errMsg = `Patch-fout: ${e instanceof Error ? e.message : String(e)}`;
      setMsg(errMsg);
      toast.error(errMsg);
    }
  }

  async function approve() {
    setSaving(true);
    setMsg(null);
    try {
      const r = await api.approve(order.id, { reviewer: "dashboard" }, { force: forceArmed });
      if (r.nav_status === "failed") {
        // The HTTP call succeeded but the NAV push itself failed. Surface
        // the exact error so the reviewer doesn't have to dig in logs.
        const errMsg = `NAV-push mislukt: ${r.nav_error ?? "onbekende fout"} (${r.nav_failed_op_count}/${r.nav_operation_count} operaties faalden)`;
        setMsg(errMsg);
        toast.error(errMsg);
        router.refresh();
        return;
      }
      const successMsg = `✓ Gepusht naar Navision: ${r.navision_order_nr} (${r.nav_operation_count} ops)${r.forced ? " (force)" : ""}`;
      setMsg(successMsg);
      toast.success(`Gepusht als ${r.navision_order_nr || "Navision order"}${r.forced ? " (force)" : ""}`);
      router.refresh();
    } catch (e) {
      const errMsg = `Fout: ${e instanceof Error ? e.message : String(e)}`;
      setMsg(errMsg);
      toast.error(`Goedkeuren mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  async function reject() {
    if (!window.confirm("Deze order afwijzen? Hij verdwijnt uit de review-wachtrij en wordt niet naar Navision gepusht.")) {
      return;
    }
    setSaving(true);
    try {
      await api.reject(order.id, { reviewer: "dashboard", reason: "Manual reject" });
      // Prefix met ✓ zodat de inline-status groen kleurt (de kleurcheck in de
      // actieregel gebruikt msg.startsWith("✓")); zonder dit kleurde een
      // geslaagde afwijzing rood alsof hij mislukte.
      setMsg("✓ Afgewezen");
      toast.success("Order afgewezen");
      router.refresh();
    } catch (e) {
      const errMsg = `Fout: ${e instanceof Error ? e.message : String(e)}`;
      setMsg(errMsg);
      toast.error(`Afwijzen mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  const blocked = missing.length > 0 && !forceArmed;
  const isNotOrder = order.status === "not_order";
  const canAct = order.status === "review" && !isNotOrder;
  const nMatched = regels.filter((r) => r.artikelnummer_kwabo_matched).length;
  const overigeWarnings = order.warnings.filter((w) => !isSourceDocWarning(w));

  return (
    <div className="space-y-3">
      {/* ════ COCKPIT — alles om te beslissen, zonder scrollen ════ */}
      <section className="rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
        {/* Actieregel: status links, knoppen rechts. */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {!isNotOrder && missing.length === 0 && (
            <span className="inline-flex items-center rounded bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
              ✓ Klaar om te pushen
            </span>
          )}
          {msg && (
            <span className={`text-xs ${msg.startsWith("✓") ? "text-emerald-700" : "text-amber-800"}`}>
              {msg}
            </span>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              onClick={refresh}
              className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
            >
              Refresh
            </button>
            <button
              onClick={reject}
              disabled={saving || !canAct}
              className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Afwijzen
            </button>
            <button
              onClick={approve}
              disabled={saving || !canAct || blocked}
              title={blocked ? `Vul ${missing.length} velden in of activeer Force` : ""}
              className="inline-flex items-center gap-2 rounded-md bg-[var(--kwabo-navy)] px-4 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-[var(--kwabo-navy-500)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving && (
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
                  <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
                </svg>
              )}
              {saving ? "Bezig…" : "Goedkeuren & Push Navision"}
            </button>
          </div>
        </div>

        {/* Takenlijst (alleen als er iets te doen is) — incl. force-checkbox. */}
        {!isNotOrder && missing.length > 0 && (
          <div className="mb-3">
            <NeedsReviewBanner fields={missing} forceArmed={forceArmed} onToggleForce={setForceArmed} />
          </div>
        )}

      </section>

      {/* ════ BRON LINKS, BESLISSINGEN RECHTS — naast elkaar nachecken ════ */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        {/* Bron: e-mail & bijlagen — linksboven, altijd direct zichtbaar zodat
            de reviewer de order zonder scrollen tegen het origineel kan
            nachecken. Op mobiel komt hij ná de beslissingen (order-2). */}
        <section className="order-2 lg:order-1 lg:col-span-5 rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
            Bron: e-mail &amp; bijlagen ({(initialState.bijlagen || []).length})
          </div>
          <EmailSourceViewer
            orderId={order.id}
            emailFrom={order.email_from}
            emailDate={order.email_date}
            emailBody={initialState.email_body ?? ""}
            bijlagen={initialState.bijlagen || []}
          />
          <div id="incoming-document-panel" className="mt-3">
            <IncomingDocumentPanel
              orderId={order.id}
              incomingPath={initialState.incoming_document_path ?? null}
              onChanged={refresh}
            />
          </div>
        </section>

        {/* De drie beslissingen — rechts naast de bron, gestapeld. */}
        <div className="order-1 lg:order-2 lg:col-span-7 grid content-start gap-3">
          {/* ── KLANT ── */}
          <Cel label="Klant">
            {/* K3: kandidaten uit de naam-fallback — alleen zolang er geen
                klant gekozen is; een keuze loopt via dezelfde patch-flow als
                handmatig typen (incl. refresh). */}
            {!initialState.klant_match?.navision_klantnr && (
              <KlantPicker
                kandidaten={initialState.klant_kandidaten || []}
                onPick={(nr) => patch("klant_match", nr)}
              />
            )}
            {initialState.klant_match?.klantnaam && (
              <div className="mb-1 text-sm font-semibold text-[var(--kwabo-navy)]" data-testid="klant-naam">
                {initialState.klant_match.klantnaam}
                {initialState.klant_match.plaats && (
                  <span className="font-normal text-[var(--kwabo-muted)]"> · {initialState.klant_match.plaats}</span>
                )}
              </div>
            )}
            {/* C1: de match-reden is er ALTIJD — "afleveradres Woerden →
                Jongeneel Woerden" laat in één oogopslag zien waaróm. */}
            {(initialState.klant_match?.match_uitleg || initialState.klant_match?.match_bron) && (
              <div className="mb-1.5 text-[11px] text-[var(--kwabo-muted)]" data-testid="klant-match-reden">
                {initialState.klant_match?.match_uitleg
                  ? initialState.klant_match.match_uitleg
                  : `gematcht via ${initialState.klant_match!.match_bron}`}
                {initialState.klant_match?.leveradres_bevestigd && (
                  <span className="ml-1 inline-flex rounded bg-emerald-50 px-1 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                    leveradres bevestigd
                  </span>
                )}
              </div>
            )}
            <FieldInput
              label="Navision klantnr."
              path="klant_match"
              value={initialState.klant_match?.navision_klantnr ?? ""}
              meta={meta.klant_match}
              onChange={(v) => patch("klant_match", v)}
              monospace
            />
            {/* Fase 6 V2: één klik her-patcht hetzelfde nummer; de backend
                wist dan de CONTROLEER-vlag en behoudt 4+/krediet-context. */}
            {canAct && meta.klant_match?.needs_review && initialState.klant_match?.navision_klantnr && (
              <button
                type="button"
                data-testid="klant-bevestig"
                onClick={() => patch("klant_match", initialState.klant_match!.navision_klantnr)}
                title="CONTROLEER verschijnt bij elke match die geen directe e-mailmatch op de klantenkaart is (naam, NAV-zoektocht of domein-alias). Een directe e-mailmatch is zeker en draagt geen vlag."
                className="mt-1.5 inline-flex items-center gap-1 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-800 hover:bg-amber-100"
              >
                ✓ Bevestig deze klant
              </button>
            )}
            {/* Context in één rustige regel — geen kleur-pillen. */}
            {initialState.klant_match?.klantnaam && (
              <div className="mt-1.5 text-[11px] text-[var(--kwabo-muted)]">
                {[
                  initialState.klant_match?.is_4plus === true ? "4+ lid" : initialState.klant_match?.is_4plus === false ? "geen 4+" : null,
                  initialState.klant_match?.kredietlimiet != null && Number(initialState.klant_match.kredietlimiet) > 0
                    ? `krediet € ${Number(initialState.klant_match.kredietlimiet).toLocaleString("nl-NL")}`
                    : null,
                ].filter(Boolean).join(" · ")}
              </div>
            )}
          </Cel>

          {/* ── LEVERING ── */}
          <Cel label="Levering">
            <ShipToPicker
              orderId={order.id}
              kandidaten={initialState.ship_to_kandidaten || []}
              gekozen={initialState.ship_to_gekozen ?? null}
              needsReviewFields={missing}
              onChanged={refresh}
            />
            {(ship.naam || ship.postcode || ship.plaats) && (
              <div className="mt-1 text-sm text-slate-800">
                <div className="font-medium">{ship.naam || "—"}</div>
                <div className="text-[12px] text-[var(--kwabo-muted)]">
                  {[ship.straat, [ship.postcode, ship.plaats].filter(Boolean).join(" "), ship.land]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </div>
            )}
            {/* B1/C1: adresrollen — besteller ≠ aflever in één oogopslag,
                zonder kleurenwaaier: het leveradres is gewoon zwart, context
                is grijs. */}
            {initialState.adres_rollen && Object.keys(initialState.adres_rollen).length > 0 && (
              <div className="mt-2 space-y-0.5 text-[11px]" data-testid="adres-rollen">
                {(["aflever", "eindontvanger", "besteller", "factuur"] as const).map((rol) => {
                  const a = initialState.adres_rollen?.[rol];
                  if (!a) return null;
                  const kort = [a.naam, a.postcode, a.plaats].filter(Boolean).join(", ");
                  const isLever = rol === "aflever" || rol === "eindontvanger";
                  return (
                    <div key={rol} className={isLever ? "text-slate-700" : "text-[var(--kwabo-muted)]"}>
                      <span className="mr-1 inline-block w-24 font-semibold uppercase tracking-wide text-[10px]">{rol}</span>
                      {kort || "—"}
                    </div>
                  );
                })}
              </div>
            )}
            {/* Functie 5: afhaalorder → verzendwijze (Shipment Method Code). */}
            {initialState.verzendwijze && (
              <div data-testid="verzendwijze" className="mt-2">
                <span className="mb-1 inline-flex rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-amber-200">
                  Afhaalorder
                </span>
                <FieldInput
                  label="Verzendwijze (Shipment Method Code)"
                  path="verzendwijze"
                  value={initialState.verzendwijze ?? ""}
                  meta={meta.verzendwijze}
                  onChange={(v) => patch("verzendwijze", v)}
                  monospace
                />
              </div>
            )}
          </Cel>

          {/* ── ORDER ── */}
          <Cel label="Order">
            <div className="grid grid-cols-2 gap-2">
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
            </div>
            <div className="mt-2 text-[11px] text-[var(--kwabo-muted)]">
              {regels.length} {regels.length === 1 ? "regel" : "regels"} · {nMatched} gematcht
              {initialState.europallet_regel?.hoeveelheid != null && (
                <> · europallet: {initialState.europallet_regel.hoeveelheid}</>
              )}
            </div>
          </Cel>
        </div>
      </div>

      {/* Incidentele banners — alleen als er echt iets is. */}
      {order.status === "failed" && (
        <NavFailureBanner
          orderId={order.id}
          firstError={
            (initialState.errors || []).find((e) => e.startsWith("push_navision:"))
              ?.replace(/^push_navision:\s*/, "") ?? null
          }
        />
      )}
      {/* FUNCTIE 7: dedicated, onmisbare banner voor de bron-doc-skip met een
          knop naar het bron-document-paneel. */}
      <SourceDocLinkBanner warnings={order.warnings} targetId="incoming-document-panel" />
      {/* Fase 5 (D): overige row.warnings — de bron-doc-warning heeft de
          dedicated banner hierboven (geen dubbeling). */}
      {overigeWarnings.length > 0 && (
        <div
          data-testid="order-warnings-banner"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <div className="font-semibold">
            ⚠ {overigeWarnings.length === 1 ? "1 waarschuwing" : `${overigeWarnings.length} waarschuwingen`}
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {overigeWarnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ════ REGELS — direct onder de cockpit, full width ════ */}
      {!isNotOrder && (
        <section className="rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)]">
          <OrderLinesTable
            regels={regels as unknown as import("@/components/order-lines-table").Regel[]}
            regelsMeta={regelsMeta}
            items={items}
            onPatch={patch}
          />
          {/* Mix-UOM badges — appear next to lines when mixprijzen is active */}
          {initialState.mixprijzen_actief && regels.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="mix-badges-row">
              <span className="text-[11px] text-[var(--kwabo-muted)]">Mixprijzen actief:</span>
              {regels.map((r, i) => (
                <MixprijzenBadge
                  key={i}
                  orderId={order.id}
                  regel={r}
                  idx={i}
                  onChanged={refresh}
                  totalPallets={initialState.order_mix_total_pallets ?? null}
                />
              ))}
            </div>
          )}
          <EuropalletEditor
            orderId={order.id}
            regel={initialState.europallet_regel ?? null}
            meta={meta.europallet ?? null}
            onChanged={refresh}
          />
        </section>
      )}

      {/* ════ Details onder de vouw — uniforme, rustige secties ════ */}
      <Sectie titel="Adres & overige velden bewerken">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
            Drop-ship adres
          </span>
          <ProvenanceBadge meta={meta.afleveradres} size="xs" />
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
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
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          <FieldInput
            label="Afleverinstructies"
            path="afleverinstructies"
            value={initialState.afleverinstructies ?? ""}
            meta={meta.afleverinstructies}
            onChange={(v) => patch("afleverinstructies", v)}
          />
          <FieldInput
            label="Opmerkingen"
            path="opmerkingen"
            value={initialState.opmerkingen ?? ""}
            meta={meta.opmerkingen}
            onChange={(v) => patch("opmerkingen", v)}
          />
        </div>
      </Sectie>

      <Sectie titel="Navision request" open>
        <NavOperationsPreview orderId={order.id} refreshKey={previewKey} />
      </Sectie>

      <Sectie titel={`Audit trail (${order.stappen_log?.length ?? 0} stappen)`}>
        <ol className="space-y-1 text-xs">
          {order.stappen_log?.map((s, i) => (
            <li key={i} className="flex gap-3 border-b border-[var(--kwabo-border)] pb-1 last:border-0">
              <span className="w-32 font-mono text-[var(--kwabo-navy-300)]">{String(s.stap)}</span>
              <span className="w-20 font-mono text-slate-400">{String(s.timestamp).slice(11, 19)}</span>
              <span className="flex-1 text-slate-700">{String(s.beslissing)}</span>
            </li>
          ))}
        </ol>
      </Sectie>
    </div>
  );
}


function NavFailureBanner({ orderId, firstError }: { orderId: number; firstError: string | null }) {
  const [open, setOpen] = useState(false);
  const [debug, setDebug] = useState<Awaited<ReturnType<typeof api.navDebug>> | null>(null);
  const [loading, setLoading] = useState(false);
  async function load() {
    if (debug) {
      setOpen((v) => !v);
      return;
    }
    setLoading(true);
    try {
      const d = await api.navDebug(orderId);
      setDebug(d);
      setOpen(true);
    } catch (e) {
      toast.error(`Kan operations-log niet laden: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">NAV-push mislukt</div>
          {firstError && (
            <div className="mt-1 break-words font-mono text-[11px] text-rose-800">
              {firstError}
            </div>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="shrink-0 rounded border border-rose-400 bg-white px-2 py-1 text-[11px] font-medium text-rose-900 hover:bg-rose-100 disabled:opacity-50"
        >
          {loading ? "Laden…" : open ? "Verberg operations-log" : "Bekijk operations-log"}
        </button>
      </div>
      {open && debug && (
        <div className="mt-3 space-y-1 rounded bg-white p-2 text-[10px] font-mono text-slate-700 ring-1 ring-rose-200">
          {debug.nav_operation_results.length === 0 && (
            <div className="text-slate-400">Geen operations geregistreerd.</div>
          )}
          {debug.nav_operation_results.map((op, i) => {
            const meta = (op.operation || {}) as Record<string, unknown>;
            const labelRaw = meta["label"] ?? meta["path"] ?? "(op)";
            const label = typeof labelRaw === "string" ? labelRaw : JSON.stringify(labelRaw);
            return (
              <div
                key={i}
                className={op.error ? "text-rose-700" : "text-emerald-700"}
              >
                <span className="font-semibold">{i + 1}.</span>{" "}
                {(meta["op"] as string) ?? ""} {label}
                {op.status != null && <span className="ml-1 text-slate-400">[{op.status}]</span>}
                {op.error && <div className="ml-4 text-rose-900">↳ {op.error}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
