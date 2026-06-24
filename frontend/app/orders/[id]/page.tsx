import Link from "next/link";
import { api } from "@/lib/api";
import { statusLabel } from "@/lib/status";
import { OrderReview } from "./order-review";

export const dynamic = "force-dynamic";

export default async function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [order, items] = await Promise.all([
    api.getOrder(Number(id)),
    api.searchItems().catch(() => [] as Awaited<ReturnType<typeof api.searchItems>>),
  ]);
  const state = (order.order_state || {}) as Record<string, unknown>;
  const parentId = (state.parent_log_id as number | undefined) ?? order.parent_log_id ?? null;
  const subIdx = (state.sub_order_index as number | undefined) ?? order.sub_order_index ?? null;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-sm text-[var(--kwabo-navy)] hover:underline">← Queue</Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">
            Order #{order.id} · {order.bestelnummer_klant || order.email_subject?.slice(0, 50)}
          </h1>
          <div className="mt-0.5 flex items-center gap-3 text-sm text-[var(--kwabo-muted)]">
            <span>Status: <span className="font-medium">{statusLabel(order.status)}</span></span>
            {parentId && (
              <Link
                href={`/orders/${parentId}`}
                className="inline-flex items-center gap-1 rounded bg-violet-50 px-2 py-0.5 text-xs text-violet-800 ring-1 ring-violet-200 hover:bg-violet-100"
              >
                🔗 Sub-order {subIdx} · uit parent #{parentId}
              </Link>
            )}
          </div>
        </div>
        {order.navision_order_nr && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Navision: <span className="font-mono font-medium">{order.navision_order_nr}</span>
          </div>
        )}
      </div>
      {order.status === "not_order" && (
        <div className="rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
          ℹ Deze e-mail is <strong>niet geclassificeerd als inkooporder</strong> (bijv. pakbon / orderbevestiging / spam).
          Er is geen extractie of push uitgevoerd. Als dit wél een order is, heropen via &quot;Heropen als order&quot;.
        </div>
      )}
      <OrderReview order={order} items={items} />
    </div>
  );
}
