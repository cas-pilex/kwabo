"use client";

/**
 * Compatibility shim — kept so existing imports (`@/components/navision-preview`)
 * continue to resolve. After T11 the implementation lives at
 * `app/orders/[id]/components/NavOperationsPreview.tsx`, which renders the
 * trigger-aware operation list returned by the post-T9 `/navision-preview`
 * endpoint. The legacy `header` + `lines` flat-shape variant is gone.
 *
 * Props were `{ orderId, refreshKey, orderState }`. Only `orderId` and
 * `refreshKey` are used now; `orderState` is ignored.
 */

import type { ComponentProps } from "react";
import { NavOperationsPreview } from "@/app/orders/[id]/components/NavOperationsPreview";

type Props = Omit<ComponentProps<typeof NavOperationsPreview>, "operations"> & {
  /** Legacy: kept for prop-compat; ignored. */
  orderState?: Record<string, unknown>;
};

export function NavisionPreview({ orderId, refreshKey }: Props) {
  return <NavOperationsPreview orderId={orderId} refreshKey={refreshKey} />;
}

export default NavisionPreview;
