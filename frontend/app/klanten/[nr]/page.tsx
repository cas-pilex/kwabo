import Link from "next/link";
import { api } from "@/lib/api";
import { KlantTabs } from "./klant-tabs";

export const dynamic = "force-dynamic";

export default async function KlantDetailPage({ params }: { params: Promise<{ nr: string }> }) {
  const { nr } = await params;
  const klant = await api.getKlant(nr);
  const mappings = await api.listMappings(nr).catch(() => []);
  return (
    <div className="space-y-4">
      <Link href="/klanten" className="text-sm text-[var(--kwabo-navy)] hover:underline">← Klanten</Link>
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">
        {klant.naam} <span className="font-mono text-base text-[var(--kwabo-muted)]">({klant.nav_klantnr})</span>
      </h1>
      <KlantTabs
        nr={nr}
        klant={{
          naam: klant.naam,
          email: klant.email,
          email_bestelling: klant.email_bestelling,
          taal: klant.taal,
        }}
        initialMappings={mappings.map((m) => ({
          id: m.id,
          klant_artikelnr: m.klant_artikelnr,
          kwabo_artikelnr: m.kwabo_artikelnr,
          omschrijving: m.omschrijving,
        }))}
      />
    </div>
  );
}
