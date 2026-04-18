"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type FilterKey = "review" | "pushed" | "not_order" | "all";

export function QueueFilters({
  current,
  counts,
}: {
  current: FilterKey;
  counts: Record<string, number>;
}) {
  const router = useRouter();
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  async function triggerScan() {
    setScanning(true);
    setScanMsg(null);
    try {
      const r = await api.scanInbox();
      const subs = r.processed.reduce(
        (a, p) => a + (((p as unknown) as { sub_orders?: number[] }).sub_orders?.length ?? 0),
        0,
      );
      setScanMsg(
        r.processed.length === 0
          ? "Geen nieuwe e-mails in inbox"
          : `✓ ${r.processed.length} verwerkt${subs ? ` (+${subs} sub-orders)` : ""}${r.errors.length ? `, ${r.errors.length} fouten` : ""}`,
      );
      router.refresh();
    } catch (e) {
      setScanMsg(`Fout: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setScanning(false);
    }
  }
  const tabs: Array<{ key: FilterKey; label: string; count: number }> = [
    { key: "review", label: "In review", count: counts.review ?? 0 },
    { key: "pushed", label: "Gepusht", count: counts.pushed ?? 0 },
    { key: "not_order", label: "Geen order", count: counts.not_order ?? 0 },
    { key: "all", label: "Alle", count: counts.all ?? 0 },
  ];

  return (
    <div className="flex items-center justify-between">
      <div className="flex gap-1 rounded-lg bg-white p-1 ring-1 ring-[var(--kwabo-border)]">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => router.push(t.key === "review" ? "/" : `/?filter=${t.key}`)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
              current === t.key
                ? "bg-[var(--kwabo-navy)] text-white"
                : "text-[var(--kwabo-muted)] hover:bg-slate-100"
            }`}
          >
            {t.label}
            <span className={`ml-1.5 rounded px-1.5 py-0.5 text-[10px] ${
              current === t.key ? "bg-white/20" : "bg-slate-200 text-[var(--kwabo-muted)]"
            }`}>{t.count}</span>
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        {scanMsg && (
          <span className={`text-xs ${scanMsg.startsWith("✓") ? "text-emerald-700" : scanMsg.startsWith("Fout") ? "text-rose-700" : "text-[var(--kwabo-muted)]"}`}>
            {scanMsg}
          </span>
        )}
        <button
          onClick={triggerScan}
          disabled={scanning}
          className="rounded-md bg-[var(--kwabo-navy)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--kwabo-navy-500)] disabled:opacity-60"
          title="Verwerk nieuwe .eml bestanden uit data/inbox/"
        >
          {scanning ? "Scannen…" : "↻ Scan inbox"}
        </button>
        <button
          onClick={() => router.refresh()}
          className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-xs font-medium hover:bg-slate-50"
        >
          Ververs
        </button>
      </div>
    </div>
  );
}
