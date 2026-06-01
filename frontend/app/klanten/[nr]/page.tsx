import Link from "next/link";
import { api, type Klant } from "@/lib/api";
import { KlantTabs } from "./klant-tabs";

export const dynamic = "force-dynamic";

function KlantFout({ nr, titel, uitleg }: { nr: string; titel: string; uitleg: string }) {
  return (
    <div className="space-y-4">
      <Link href="/klanten" className="text-sm text-[var(--kwabo-navy)] hover:underline">← Klanten</Link>
      <div className="rounded-lg border border-[var(--kwabo-border)] bg-white p-6 text-center shadow-sm">
        <div className="text-lg font-semibold text-[var(--kwabo-navy)]">{titel}</div>
        <p className="mx-auto mt-1 max-w-md text-sm text-[var(--kwabo-muted)]">{uitleg}</p>
        <Link
          href="/klanten"
          className="mt-4 inline-block rounded-md bg-[var(--kwabo-navy)] px-4 py-1.5 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)]"
        >
          Naar klantenlijst
        </Link>
      </div>
    </div>
  );
}

export default async function KlantDetailPage({ params }: { params: Promise<{ nr: string }> }) {
  const { nr } = await params;
  let klant: Klant;
  try {
    klant = await api.getKlant(nr);
  } catch (e) {
    // req() gooit `${status} ${body}`. 404 → klant bestaat niet; anders backend-fout.
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.startsWith("404")) {
      return (
        <KlantFout
          nr={nr}
          titel="Klant niet gevonden"
          uitleg={`Er bestaat geen klant met nummer ${nr}. Kies een klant uit de lijst.`}
        />
      );
    }
    return (
      <KlantFout
        nr={nr}
        titel="Kon klant niet laden"
        uitleg="De backend is even niet bereikbaar. Probeer het zo opnieuw of ga terug naar de lijst."
      />
    );
  }
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
