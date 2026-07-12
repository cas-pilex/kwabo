"use client";

const LABELS: Record<string, string> = {
  klant_match: "Klant",
  bestelnummer_klant: "Bestelnr klant",
  gewenste_leverdatum: "Leverdatum",
  afleveradres: "Afleveradres",
  adressen: "Adres-rollen",
  ship_to_gekozen: "Afleverpunt (ship-to)",
  verzendwijze: "Verzendwijze",
  afleverinstructies: "Afleverinstructies",
  klantnaam_besteller: "Naam besteller",
  europallet: "Europallet",
  taal: "Taal",
};

// Leesbare labels voor regel-subvelden (anders toonde de chip de ruwe
// JSON-padnaam, bv. "artikelnummer_kwabo_matched").
const REGEL_VELD_LABELS: Record<string, string> = {
  artikelnummer_kwabo_matched: "artikel",
  artikelnummer_kwabo: "artikel",
  hoeveelheid: "aantal",
  eenheid: "eenheid",
  leverdatum_regel: "leverdatum",
};

function regelVeld(veld: string): string {
  return REGEL_VELD_LABELS[veld] ?? veld.replace(/_/g, " ");
}

function pretty(path: string): string {
  if (LABELS[path]) return LABELS[path];
  // Eenheid-vlaggen hebben de vorm "verkoop_eenheid:<positie>" / "mix_uom:<positie>".
  const eh = path.match(/^verkoop_eenheid:(\d+)$/);
  if (eh) return `Regel ${eh[1]} · eenheid`;
  const mx = path.match(/^mix_uom:(\d+)$/);
  if (mx) return `Regel ${mx[1]} · mix-eenheid`;
  const m = path.match(/^orderregels\[(\d+)\]\.(.+)$/);
  if (m) return `Regel ${Number(m[1]) + 1} · ${regelVeld(m[2])}`;
  return path;
}

// F2.5: elke chip hoort ergens heen te springen. Positie-vlaggen (1-based)
// landen op het eenheid-veld van hun regel; meta-loze order-vlaggen op het
// blok dat ze adresseert (ids gezet in order-review/EuropalletEditor).
function anchorFor(path: string): string {
  const pos = path.match(/^(?:verkoop_eenheid|mix_uom):(\d+)$/);
  if (pos) return `orderregels[${Number(pos[1]) - 1}].eenheid`;
  if (path === "adressen") return "afleveradres";
  return path;
}

// C2: vlaggen in AFHANDEL-volgorde — eerst de klant (die bepaalt ship-to,
// prijzen en mix), dan het afleverpunt, dan de regels (artikel vóór eenheid:
// een artikel-wissel herberekent de eenheid), dan de rest. De volgorde in de
// banner = de volgorde waarin de reviewer het beste kan werken.
const PRIORITEIT: Array<(f: string) => boolean> = [
  (f) => f === "klant_match",
  (f) => f === "afleveradres" || f === "ship_to_gekozen",
  (f) => /\.artikelnummer_kwabo(_matched)?$/.test(f),
  (f) => /\.eenheid$/.test(f) || /^verkoop_eenheid:/.test(f) || /^mix_uom:/.test(f),
  (f) => /\.hoeveelheid$/.test(f),
  (f) => f === "europallet",
];

function prioriteit(f: string): number {
  const i = PRIORITEIT.findIndex((p) => p(f));
  return i === -1 ? PRIORITEIT.length : i;
}

export function sorteerVlaggen(fields: string[]): string[] {
  // Stabiel: binnen dezelfde prioriteitsklasse blijft de server-volgorde staan.
  return [...fields].sort((a, b) => prioriteit(a) - prioriteit(b));
}

export function NeedsReviewBanner({
  fields,
  forceArmed,
  onToggleForce,
}: {
  fields: string[];
  forceArmed: boolean;
  onToggleForce: (v: boolean) => void;
}) {
  if (fields.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900">
        ✓ Alle verplichte velden ingevuld — klaar om te pushen.
      </div>
    );
  }
  return (
    <div className="sticky top-0 z-20 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-sm">
      <div className="flex flex-wrap items-center gap-3" data-testid="review-takenlijst">
        <span className="font-semibold">
          ⚠ {fields.length} {fields.length === 1 ? "ding" : "dingen"} te controleren (in volgorde):
        </span>
        {sorteerVlaggen(fields).map((f) => (
          <button
            key={f}
            onClick={() => {
              const el = document.getElementById(anchorFor(f));
              if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
                (el as HTMLInputElement).focus?.();
              }
            }}
            className="rounded border border-amber-300 bg-white px-2 py-0.5 text-xs hover:bg-amber-100"
          >
            → {pretty(f)}
          </button>
        ))}
        <label
          className="ml-auto flex items-center gap-1.5 text-xs"
          title="Stuurt de order tóch naar Navision ondanks de ontbrekende velden. Deze actie wordt gelogd en is later te auditen."
        >
          <input
            type="checkbox"
            checked={forceArmed}
            onChange={(e) => onToggleForce(e.target.checked)}
          />
          <span>Tóch goedkeuren ondanks ontbrekende velden (gelogd)</span>
        </label>
      </div>
    </div>
  );
}
