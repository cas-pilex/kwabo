// Nederlandse, eindgebruiker-vriendelijke labels voor de ruwe order-statussen.
// De backend levert codes als "not_order" / "pushed"; een order-invoerder denkt
// niet in die termen. Eén bron van waarheid, gedeeld door queue + audit.
const STATUS_LABELS: Record<string, string> = {
  review: "Te reviewen",
  approved: "Goedgekeurd",
  pushed: "Naar Navision",
  rejected: "Afgewezen",
  not_order: "Geen order",
  error: "Fout",
  processing: "Bezig",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}
