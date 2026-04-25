export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type OrderSummary = {
  id: number;
  email_id: string;
  email_from: string | null;
  email_subject: string | null;
  email_date: string | null;
  status: string;
  is_order: boolean | null;
  klant_nr: string | null;
  klant_match_confidence: number | null;
  bestelnummer_klant: string | null;
  aantal_regels: number | null;
  alle_artikelen_gematcht: boolean | null;
  alle_prijzen_valide: boolean | null;
  navision_order_nr: string | null;
  warnings_count: number;
  needs_review_count: number;
  parent_log_id?: number | null;
  sub_order_index?: number | null;
  created_at: string;
};

export type OrderDetail = OrderSummary & {
  warnings: string[];
  stappen_log: Array<Record<string, unknown>>;
  order_state: Record<string, unknown>;
};

export type OrderRegel = {
  positie: number;
  artikelnummer_klant: string | null;
  artikelnummer_kwabo: string | null;
  artikelnummer_kwabo_matched: string | null;
  omschrijving: string;
  hoeveelheid: number;
  eenheid: string;
  prijs_per_eenheid: number | null;
  prijs_validated: boolean | null;
  prijs_afwijking: string | null;
  ean_code: string | null;
  leverdatum_regel: string | null;
  opmerkingen: string | null;
  match_confidence: number | null;
  match_methode: string | null;
};

export type Klant = {
  nav_klantnr: string;
  naam: string;
  email: string | null;
  email_bestelling: string | null;
  taal: string;
  is_4plus: boolean;
};

export type Item = { number: string; displayName: string };

export type FieldMeta = {
  value?: unknown;
  source: "pdf" | "email_body" | "email_header" | "klantenkaart" | "history" | "fuzzy" | "manual" | "default" | "missing" | "navision" | string;
  source_detail?: string | null;
  confidence?: number;
  needs_review?: boolean;
  validated?: boolean | null;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export type Prijsafspraak = {
  id: number;
  klant_nr: string;
  kwabo_artikelnr: string;
  prijs: number;
  korting_pct: number;
  type: string;
  min_hoeveelheid: number | null;
  geldig_van: string | null;
  geldig_tot: string | null;
};

export async function listPrijsafspraken(nr: string): Promise<Prijsafspraak[]> {
  const r = await fetch(`${API_BASE}/api/klanten/${nr}/prijsafspraken`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function addPrijsafspraak(nr: string, body: Partial<Prijsafspraak>) {
  const r = await fetch(`${API_BASE}/api/klanten/${nr}/prijsafspraken`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      detail = j.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export async function deletePrijsafspraak(nr: string, id: number) {
  const r = await fetch(`${API_BASE}/api/klanten/${nr}/prijsafspraken/${id}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

export const api = {
  listOrders: (status?: string) =>
    req<OrderSummary[]>(`/api/orders${status ? `?status=${status}` : ""}`),
  getOrder: (id: number) => req<OrderDetail>(`/api/orders/${id}`),
  patchOrder: (id: number, body: Record<string, unknown>) =>
    req(`/api/orders/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  approve: (id: number, body: Record<string, unknown> = {}, opts?: { force?: boolean }) =>
    req<{ ok: boolean; navision_order_nr?: string; forced?: boolean }>(
      `/api/orders/${id}/approve${opts?.force ? "?force=true" : ""}`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  navisionPreview: (id: number) =>
    req<{
      method: string;
      url: string;
      headers: Record<string, string>;
      body: { header: Record<string, unknown>; lines: Array<Record<string, unknown>> };
      status: "ready" | "missing" | "no_customer";
      missing_count: number;
    }>(`/api/orders/${id}/navision-preview`),
  patchField: (id: number, path: string, value: unknown, reviewer = "dashboard") =>
    req<{ ok: boolean; needs_review_count: number; needs_review_fields: string[] }>(
      `/api/orders/${id}/patch-field`,
      { method: "PATCH", body: JSON.stringify({ path, value, reviewer }) },
    ),
  needsReview: (id: number) =>
    req<{ count: number; fields: string[] }>(`/api/orders/${id}/needs-review`),
  listPrijzen: (nr: string) =>
    req<Array<{ id: number; klant_nr: string; kwabo_artikelnr: string; prijs: number; korting_pct: number; type: string; min_hoeveelheid: number | null; geldig_van: string | null; geldig_tot: string | null }>>(
      `/api/klanten/${nr}/prijsafspraken`,
    ),
  addPrijs: (nr: string, body: { kwabo_artikelnr: string; prijs: number; korting_pct?: number; type?: string; geldig_tot?: string | null }) =>
    req<{ id: number }>(`/api/klanten/${nr}/prijsafspraken`, { method: "POST", body: JSON.stringify(body) }),
  deletePrijs: (nr: string, id: number) =>
    req<{ ok: boolean }>(`/api/klanten/${nr}/prijsafspraken/${id}`, { method: "DELETE" }),
  importExcel: async (nr: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/api/klanten/${nr}/import-excel`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json() as Promise<{ ok: boolean; mappings_upserted: number; prijzen_upserted: number; errors: string[] }>;
  },
  reject: (id: number, body: Record<string, unknown> = {}) =>
    req(`/api/orders/${id}/reject`, { method: "POST", body: JSON.stringify(body) }),
  listKlanten: () => req<Klant[]>("/api/klanten"),
  getKlant: (nr: string) => req<Klant>(`/api/klanten/${nr}`),
  listAliases: (nr: string) =>
    req<Array<{ id: number; klant_nr: string; email: string; label: string | null }>>(
      `/api/klanten/${nr}/aliases`,
    ),
  addAlias: (nr: string, body: { email: string; label?: string | null }) =>
    req<{ id: number; klant_nr: string; email: string; label: string | null }>(
      `/api/klanten/${nr}/aliases`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  deleteAlias: (nr: string, aliasId: number) =>
    req<{ ok: boolean }>(`/api/klanten/${nr}/aliases/${aliasId}`, { method: "DELETE" }),
  listDocuments: (nr: string) =>
    req<Array<{
      id: number;
      klant_nr: string;
      filename: string;
      doc_type: string;
      mime_type: string | null;
      size_bytes: number;
      notes: string | null;
      created_at: string;
      text_preview: string;
    }>>(`/api/klanten/${nr}/documenten`),
  getDocument: (nr: string, docId: number) =>
    req<{
      id: number;
      klant_nr: string;
      filename: string;
      doc_type: string;
      mime_type: string | null;
      size_bytes: number;
      notes: string | null;
      created_at: string;
      text_preview: string;
      text_content: string;
    }>(`/api/klanten/${nr}/documenten/${docId}`),
  uploadDocument: async (nr: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/api/klanten/${nr}/documenten`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json() as Promise<{
      id: number;
      klant_nr: string;
      filename: string;
      doc_type: string;
      mime_type: string | null;
      size_bytes: number;
      notes: string | null;
      created_at: string;
      text_preview: string;
    }>;
  },
  deleteDocument: (nr: string, docId: number) =>
    req<{ ok: boolean }>(`/api/klanten/${nr}/documenten/${docId}`, { method: "DELETE" }),
  listMappings: (nr: string) =>
    req<Array<{ id: number; klant_nr: string; klant_artikelnr: string; kwabo_artikelnr: string; omschrijving: string | null }>>(
      `/api/klanten/${nr}/artikelen`
    ),
  searchItems: (q?: string) =>
    req<Item[]>(`/api/artikelen/search${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  listAudit: () => req<OrderDetail[]>("/api/audit"),
  stats: () =>
    req<{ total_orders: number; by_status: Record<string, number>; auto_match_pct: number; avg_confidence: number | null }>(
      "/api/audit/stats"
    ),
  scanInbox: () => req<{ processed: Array<{ log_id: number }>; errors: Array<{ error: string }> }>(`/api/intake/scan`, { method: "POST" }),
  runFile: (path: string) =>
    req<{ email_id: string; log_id: number }>(`/api/intake/run-file?path=${encodeURIComponent(path)}`, {
      method: "POST",
    }),
  attachmentUrl: (orderId: number, naam: string, disposition: "inline" | "attachment" = "inline") =>
    `${API_BASE}/api/orders/${orderId}/bijlagen?naam=${encodeURIComponent(naam)}&disposition=${disposition}`,
  mailboxStatus: () =>
    req<{
      mode: string;
      connected: boolean;
      state: string;
      message: string;
      inbox_dir: string | null;
      inbox_pending: number;
      last_error: string | null;
      account_email?: string | null;
      expires_at?: string | null;
    }>("/api/mailbox/status"),
  oauthConfig: () =>
    req<{
      configured: boolean;
      tenant_id: string;
      client_id: string;
      has_secret: boolean;
      redirect_uri: string;
      scopes: string;
    }>("/api/mailbox/oauth/config"),
  saveOauthConfig: (body: { tenant_id: string; client_id: string; client_secret?: string; redirect_uri?: string }) =>
    req<{
      configured: boolean;
      tenant_id: string;
      client_id: string;
      has_secret: boolean;
      redirect_uri: string;
      scopes: string;
    }>("/api/mailbox/oauth/config", { method: "PUT", body: JSON.stringify(body) }),
  oauthStartUrl: () => `${API_BASE}/api/mailbox/oauth/start`,
  oauthDisconnect: () =>
    req<{ ok: boolean }>("/api/mailbox/oauth/disconnect", { method: "POST" }),
};
