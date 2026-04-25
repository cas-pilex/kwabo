import Link from "next/link";
import { api, type OrderSummary } from "@/lib/api";
import { QueueFilters } from "./queue-filters";
import { ReloadOnDone } from "@/components/reload-on-done";

export const dynamic = "force-dynamic";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    review: "bg-amber-100 text-amber-800 ring-amber-200",
    approved: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    pushed: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    rejected: "bg-rose-100 text-rose-800 ring-rose-200",
    not_order: "bg-slate-100 text-slate-500 ring-slate-200",
    error: "bg-rose-100 text-rose-800 ring-rose-200",
    processing: "bg-slate-100 text-slate-700 ring-slate-200",
  };
  const cls = map[status] ?? "bg-slate-100 text-slate-700 ring-slate-200";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function ConfidencePill({ value }: { value: number | null }) {
  if (value == null) return <span className="text-slate-400">—</span>;
  const pct = Math.round(value * 100);
  const cls =
    pct >= 90
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : pct >= 70
        ? "bg-amber-50 text-amber-700 ring-amber-200"
        : "bg-rose-50 text-rose-700 ring-rose-200";
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-mono ring-1 ring-inset ${cls}`}>
      {pct}%
    </span>
  );
}

function StatCard({ label, value, hint, tone = "navy" }: { label: string; value: string | number; hint?: string; tone?: "navy" | "amber" | "emerald" | "rose" | "slate" }) {
  const toneCls = {
    navy: "text-[var(--kwabo-navy)]",
    amber: "text-amber-700",
    emerald: "text-emerald-700",
    rose: "text-rose-700",
    slate: "text-slate-500",
  }[tone];
  return (
    <div className="rounded-lg bg-white p-4 ring-1 ring-[var(--kwabo-border)] shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--kwabo-muted)]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${toneCls}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-[var(--kwabo-muted)]">{hint}</div>}
    </div>
  );
}

async function getData(): Promise<{ orders: OrderSummary[]; err?: string }> {
  try {
    return { orders: await api.listOrders() };
  } catch (e) {
    return { orders: [], err: e instanceof Error ? e.message : String(e) };
  }
}

type FilterKey = "review" | "pushed" | "not_order" | "all";

export default async function HomePage({ searchParams }: { searchParams: Promise<{ filter?: string }> }) {
  const sp = await searchParams;
  const filter = (sp.filter as FilterKey) || "review";

  const { orders, err } = await getData();
  const counts = {
    all: orders.length,
    review: orders.filter((o) => o.status === "review").length,
    pushed: orders.filter((o) => o.status === "pushed" || o.status === "approved").length,
    not_order: orders.filter((o) => o.status === "not_order").length,
    rejected: orders.filter((o) => o.status === "rejected").length,
  };
  const reviewQueue = orders.filter((o) => o.status === "review");
  const totalMissingReview = reviewQueue.reduce((a, b) => a + b.needs_review_count, 0);
  const totalWarnReview = reviewQueue.reduce((a, b) => a + b.warnings_count, 0);

  const shown = filter === "all"
    ? orders
    : orders.filter((o) => (filter === "pushed" ? o.status === "pushed" || o.status === "approved" : o.status === filter));

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">Order Queue</h1>
          <p className="text-sm text-[var(--kwabo-muted)]">
            AI-verwerkte orders. Klik op een regel om te reviewen en te pushen naar Navision.
          </p>
        </div>
        <ReloadOnDone />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="In review" value={counts.review} tone="amber" hint={counts.review > 0 ? "wachten op jou" : "alles afgehandeld"} />
        <StatCard label="Gepusht naar Nav" value={counts.pushed} tone="emerald" />
        <StatCard label="Velden te vullen" value={totalMissingReview} tone="rose" hint={`in ${counts.review} orders`} />
        <StatCard label="Prijs-warnings" value={totalWarnReview} tone="amber" hint={counts.not_order ? `+ ${counts.not_order} not-order` : undefined} />
      </div>

      <QueueFilters current={filter} counts={counts} />

      {err && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          API niet bereikbaar: {err}. Start uvicorn op http://localhost:8000 en refresh.
        </div>
      )}

      <div className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-[var(--kwabo-border)]">
        <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
          <thead className="bg-[var(--kwabo-navy)] text-white">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">#</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Afzender</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Onderwerp</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Klant</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Conf.</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider">Regels</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider">Mist</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider">Warn</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Status</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Nav #</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--kwabo-border)] bg-white">
            {shown.length === 0 && !err && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-[var(--kwabo-muted)]">
                  {filter === "review"
                    ? "✓ Geen orders in review. Alles afgehandeld."
                    : "Geen orders in deze categorie."}
                </td>
              </tr>
            )}
            {shown.map((o) => {
              const dimNotOrder = o.status === "not_order";
              const href = `/orders/${o.id}`;
              const linkCellCls = "px-4 py-2 align-middle";
              const cellInner = "block w-full h-full py-0.5";
              return (
                <tr
                  key={o.id}
                  className={`group cursor-pointer transition hover:bg-slate-100 ${dimNotOrder ? "opacity-60" : ""}`}
                >
                  <td className={linkCellCls}>
                    <Link href={href} className={`${cellInner} flex items-center gap-1.5`}>
                      <span className="font-semibold text-[var(--kwabo-navy)] underline-offset-2 group-hover:underline">
                        #{o.id}
                      </span>
                      {o.parent_log_id && (
                        <span
                          title={`Sub-order ${o.sub_order_index} van #${o.parent_log_id}`}
                          className="inline-flex items-center rounded bg-violet-50 px-1 py-0 text-[10px] font-medium text-violet-700 ring-1 ring-violet-200"
                        >
                          sub·{o.sub_order_index}
                        </span>
                      )}
                    </Link>
                  </td>
                  <td className={`${linkCellCls} text-[var(--kwabo-muted)]`}>
                    <Link href={href} className={cellInner}>{o.email_from?.slice(0, 40)}</Link>
                  </td>
                  <td className={linkCellCls}>
                    <Link href={href} className={cellInner}>{o.email_subject?.slice(0, 50)}</Link>
                  </td>
                  <td className={`${linkCellCls} font-mono text-xs`}>
                    <Link href={href} className={cellInner}>
                      {o.klant_nr || <span className="text-slate-400">—</span>}
                    </Link>
                  </td>
                  <td className={linkCellCls}>
                    <Link href={href} className={cellInner}>
                      <ConfidencePill value={o.klant_match_confidence} />
                    </Link>
                  </td>
                  <td className={`${linkCellCls} text-right tabular-nums`}>
                    <Link href={href} className={cellInner}>{o.aantal_regels ?? 0}</Link>
                  </td>
                  <td className={`${linkCellCls} text-right`}>
                    <Link href={href} className={cellInner}>
                      {o.needs_review_count > 0 ? (
                        <span className="inline-flex rounded bg-rose-50 px-1.5 py-0.5 text-xs font-medium text-rose-800 ring-1 ring-rose-200">
                          {o.needs_review_count}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </Link>
                  </td>
                  <td className={`${linkCellCls} text-right`}>
                    <Link href={href} className={cellInner}>
                      {o.warnings_count > 0 ? (
                        <span className="inline-flex rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
                          {o.warnings_count}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </Link>
                  </td>
                  <td className={linkCellCls}>
                    <Link href={href} className={cellInner}>
                      <StatusBadge status={o.status} />
                    </Link>
                  </td>
                  <td className={`${linkCellCls} font-mono text-xs text-[var(--kwabo-muted)]`}>
                    <Link href={href} className={cellInner}>{o.navision_order_nr ?? ""}</Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
