import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function KlantenPage() {
  const klanten = await api.listKlanten().catch(() => []);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">Klanten</h1>
        <p className="text-sm text-[var(--kwabo-muted)]">Klik op een klant om mappings en prijsafspraken te beheren.</p>
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
            {klanten.map((k) => (
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
          </tbody>
        </table>
      </div>
    </div>
  );
}
