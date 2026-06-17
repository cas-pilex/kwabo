"use client";

// FUNCTIE 7: zolang NAV 2018 geen PLX_IncomingDocument-page heeft, kan het
// bron-document niet automatisch aan de NAV-order gekoppeld worden. De backend
// zet dan een waarschuwing op de order (push_navision._skipped_attachment_warning).
// Die boodschap stond tot nu toe als één bullet tussen de overige
// waarschuwingen — makkelijk te missen. Deze dedicated banner maakt hem
// onmisbaar, met een knop naar het bron-document-paneel, zodat de reviewer
// (Nico) weet dat hij het document NAV-zijdig handmatig moet hangen.
export const SOURCE_DOC_WARNING_PREFIX = "Bron-document is NIET";

export function isSourceDocWarning(warning: string): boolean {
  return warning.startsWith(SOURCE_DOC_WARNING_PREFIX);
}

export function SourceDocLinkBanner({
  warnings,
  targetId,
}: {
  warnings: string[];
  targetId: string;
}) {
  const warning = warnings.find(isSourceDocWarning);
  if (!warning) return null;
  return (
    <div
      data-testid="source-doc-link-banner"
      className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold">
          📎 Bron-document nog niet aan NAV gekoppeld
        </span>
        <button
          type="button"
          onClick={() => {
            const el = document.getElementById(targetId);
            if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
          className="rounded border border-amber-300 bg-white px-2 py-0.5 text-xs hover:bg-amber-100"
        >
          → Naar bron-document
        </button>
      </div>
      <p className="mt-1">{warning}</p>
    </div>
  );
}
