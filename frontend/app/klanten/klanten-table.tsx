"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Klant } from "@/lib/api";

const PAGE_SIZE = 50;

export default function KlantenTable({ klanten }: { klanten: Klant[] }) {
  const [q, setQ] = useState("");
  const [visible, setVisible] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return klanten;
    return klanten.filter((k) =>
      [k.nav_klantnr, k.naam, k.email, k.email_bestelling]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(term)),
    );
  }, [klanten, q]);

  const shown = filtered.slice(0, visible);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setVisible(PAGE_SIZE);
          }}
          placeholder="Zoek op nummer, naam of e-mail…"
          className="w-full max-w-sm rounded-md border border-[var(--kwabo-border)] px-3 py-2 text-sm shadow-sm focus:border-[var(--kwabo-navy)] focus:outline-none"
        />
        <span className="shrink-0 text-xs text-[var(--kwabo-muted)]">
          {filtered.length} van {klanten.length}
        </span>
      </div>
      <div className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-[var(--kwabo-border)]">
        <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
          <thead className="bg-[var(--kwabo-navy)] text-white">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Nav #</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Naam</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">E-mail</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider">Taal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--kwabo-border)] bg-white">
            {shown.map((k) => (
              <tr key={k.nav_klantnr} className="hover:bg-slate-50">
                <td className="px-4 py-2 font-mono text-xs">
                  <Link href={`/klanten/${k.nav_klantnr}`} className="font-semibold text-[var(--kwabo-navy)] hover:underline">
                    {k.nav_klantnr}
                  </Link>
                </td>
                <td className="px-4 py-2">{k.naam}</td>
                <td className="px-4 py-2 text-[var(--kwabo-muted)]">{k.email}</td>
                <td className="px-4 py-2 text-xs">
                  <span className="inline-flex rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700">
                    {k.taal}
                  </span>
                </td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-sm text-[var(--kwabo-muted)]">
                  Geen klanten gevonden.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {visible < filtered.length && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setVisible((v) => v + PAGE_SIZE)}
            className="rounded-md border border-[var(--kwabo-border)] bg-white px-4 py-2 text-sm font-medium text-[var(--kwabo-navy)] shadow-sm hover:bg-slate-50"
          >
            Meer laden ({filtered.length - visible} resterend)
          </button>
        </div>
      )}
    </div>
  );
}
