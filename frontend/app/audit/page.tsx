import { api } from "@/lib/api";
import AuditList from "./audit-list";

export const dynamic = "force-dynamic";

function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)] shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--kwabo-muted)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-[var(--kwabo-navy)]">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-[var(--kwabo-muted)]">{hint}</div>}
    </div>
  );
}

export default async function AuditPage() {
  const [audit, stats] = await Promise.all([
    api.listAudit().catch(() => []),
    api.stats().catch(() => null),
  ]);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">Audit log</h1>
        <p className="text-sm text-[var(--kwabo-muted)]">Volledige AI-beslissingen per order — klap open voor details.</p>
      </div>
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Totaal orders" value={stats.total_orders} />
          <StatCard label="Auto-match %" value={`${stats.auto_match_pct}%`} />
          <StatCard
            label="Gem. klant-conf."
            value={stats.avg_confidence != null ? Math.round(stats.avg_confidence * 100) + "%" : "—"}
          />
          <StatCard
            label="Per status"
            value={Object.values(stats.by_status).reduce((a, b) => a + b, 0)}
            hint={Object.entries(stats.by_status).map(([k, v]) => `${k}:${v}`).join(" · ")}
          />
        </div>
      )}
      <AuditList audit={audit} />
    </div>
  );
}
