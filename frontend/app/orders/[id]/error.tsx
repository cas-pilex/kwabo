"use client";

// Error-boundary voor de order-detailroute. Zonder dit crashte de hele pagina
// zonder vriendelijke melding als api.getOrder() faalt (401/500/netwerk).
export default function OrderDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="space-y-3">
      <a href="/" className="text-sm text-[var(--kwabo-navy)] hover:underline">← Queue</a>
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        <p className="font-semibold">Kon de order niet laden.</p>
        <p className="mt-1 text-rose-700">{error.message || "Onbekende fout."}</p>
        <button
          onClick={reset}
          className="mt-3 rounded border border-rose-300 bg-white px-3 py-1 text-xs hover:bg-rose-100"
        >
          Opnieuw proberen
        </button>
      </div>
    </div>
  );
}
