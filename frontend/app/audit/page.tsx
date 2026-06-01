import { api } from "@/lib/api";
import { statusLabel } from "@/lib/status";

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
      <div className="space-y-2">
        {audit.map((o) => (
          <details key={o.id} className="rounded-lg bg-white shadow-sm ring-1 ring-[var(--kwabo-border)]">
            <summary className="flex cursor-pointer items-center justify-between px-4 py-2.5 hover:bg-slate-50">
              <div className="flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-[var(--kwabo-muted)]">#{o.id}</span>
                <span className="font-medium">{o.email_subject?.slice(0, 55)}</span>
                <span className="text-xs text-[var(--kwabo-muted)]">{o.email_from?.slice(0, 38)}</span>
              </div>
              <div className="flex items-center gap-3">
                {o.needs_review_count > 0 && (
                  <span className="rounded bg-rose-50 px-1.5 py-0.5 text-xs font-medium text-rose-800 ring-1 ring-rose-200">
                    {o.needs_review_count} mist
                  </span>
                )}
                {o.warnings_count > 0 && (
                  <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
                    {o.warnings_count} warn
                  </span>
                )}
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{statusLabel(o.status)}</span>
              </div>
            </summary>
            <div className="border-t border-[var(--kwabo-border)] p-4 text-xs">
              <div className="mb-2 font-semibold text-[var(--kwabo-muted)]">Warnings</div>
              {o.warnings.length === 0 ? (
                <div className="text-slate-400">geen</div>
              ) : (
                <ul className="list-disc pl-5 text-amber-800">
                  {o.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
              <div className="mt-3 mb-1 font-semibold text-[var(--kwabo-muted)]">Stappen</div>
              <ol className="space-y-0.5">
                {o.stappen_log.map((s, i) => (
                  <li key={i} className="flex gap-2 font-mono">
                    <span className="w-32 text-[var(--kwabo-navy-300)]">{String(s.stap)}</span>
                    <span className="flex-1 text-slate-700">{String(s.beslissing)}</span>
                  </li>
                ))}
              </ol>
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
