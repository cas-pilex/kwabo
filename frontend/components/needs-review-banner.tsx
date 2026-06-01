"use client";

const LABELS: Record<string, string> = {
  klant_match: "Klant",
  bestelnummer_klant: "Bestelnr klant",
  gewenste_leverdatum: "Leverdatum",
  afleveradres: "Afleveradres",
};

function pretty(path: string): string {
  if (LABELS[path]) return LABELS[path];
  const m = path.match(/^orderregels\[(\d+)\]\.(.+)$/);
  if (m) return `Regel ${Number(m[1]) + 1} · ${m[2].replace(/_/g, " ")}`;
  return path;
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
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold">⚠ {fields.length} velden vereisen aanvulling:</span>
        {fields.map((f) => (
          <button
            key={f}
            onClick={() => {
              const el = document.getElementById(f);
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
