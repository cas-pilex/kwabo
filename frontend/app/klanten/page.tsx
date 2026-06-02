import { api } from "@/lib/api";
import KlantenTable from "./klanten-table";

export const dynamic = "force-dynamic";

export default async function KlantenPage() {
  const klanten = await api.listKlanten().catch(() => []);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">Klanten</h1>
        <p className="text-sm text-[var(--kwabo-muted)]">Klik op een klant om mappings en prijsafspraken te beheren.</p>
      </div>
      <KlantenTable klanten={klanten} />
    </div>
  );
}
