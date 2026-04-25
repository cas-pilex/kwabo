"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Status = Awaited<ReturnType<typeof api.mailboxStatus>>;

function dotColor(state: string): string {
  if (state === "active") return "bg-emerald-400";
  if (state === "degraded") return "bg-amber-400";
  if (state === "not_configured") return "bg-amber-400";
  if (state === "error") return "bg-rose-500";
  return "bg-slate-400";
}

export function MailboxNavItem() {
  const [status, setStatus] = useState<Status | null>(null);

  async function load() {
    try {
      setStatus(await api.mailboxStatus());
    } catch {
      setStatus({
        mode: "?",
        connected: false,
        state: "error",
        message: "Backend niet bereikbaar",
        inbox_dir: null,
        inbox_pending: 0,
        last_error: null,
      });
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const tone = dotColor(status?.state ?? "unknown");
  const tooltip = status
    ? `${status.mode.toUpperCase()} · ${status.state} — ${status.message}`
    : "Laden…";

  return (
    <Link
      href="/email"
      className="flex items-center gap-1.5 hover:text-white"
      title={tooltip}
    >
      <span className="relative inline-flex h-2 w-2">
        <span
          className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${tone}`}
          aria-hidden
        />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${tone}`} />
      </span>
      <span>E-mail</span>
    </Link>
  );
}
