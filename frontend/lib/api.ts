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

// ---- T11: trigger-aware NAV preview shapes ----

export type NavOperation = {
  op: "POST" | "PATCH";
  path: string;
  body: Record<string, unknown>;
  label: string;
  expects?: Record<string, unknown>;
};

export type NavPreviewResponse = {
  operations: NavOperation[];
  expected_post_count: number;
  expected_patch_count: number;
  status: string;
  missing_count: number;
};

export type ShipToKandidaat = {
  klant_nr: string;
  ship_to_code: string;
  naam: string;
  straat: string;
  postcode: string;
  plaats: string;
  land: string;
  is_default: boolean;
};

export type EuropalletRegel = {
  kwabo_artikelnr: string;
  hoeveelheid: number;
  eenheid: string;
  positie?: number;
};

export const AUTH_COOKIE = "kwabo_admin";

// Read the admin token from wherever it lives in the current execution
// context. Server-side: Next.js cookies() helper. Client-side: document.cookie.
// Returns null when no token is set — req() turns that into a /login bounce
// for browsers, or just lets the request go un-authenticated for SSR (the
// backend then 401s and the page boundary surfaces that to middleware).
export async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") {
    try {
      const mod = await import("next/headers");
      const store = await mod.cookies();
      return store.get(AUTH_COOKIE)?.value ?? null;
    } catch {
      return null;
    }
  }
  const m = document.cookie.match(/(?:^|;\s*)kwabo_admin=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  // Note: NO automatic redirect on 401. Earlier code did
  // `window.location.href = "/login"` here, but background pollers
  // (MailboxNavItem hits /api/mailbox/status every 30s) would race
  // with the post-login navigation, kicking the user out before the
  // page had even rendered. Middleware handles the not-logged-in case
  // upstream of the page; if a request still 401s in the wild, the
  // caller surfaces the error and the user can re-login manually.
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

async function authHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra };
}

export async function listPrijsafspraken(nr: string): Promise<Prijsafspraak[]> {
  const r = await fetch(`${API_BASE}/api/klanten/${nr}/prijsafspraken`, {
    cache: "no-store",
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function addPrijsafspraak(nr: string, body: Partial<Prijsafspraak>) {
  const r = await fetch(`${API_BASE}/api/klanten/${nr}/prijsafspraken`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
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
    headers: await authHeaders(),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

// ---- Auth helpers ----
// Login/logout go through Vercel-side routes (/api/auth/{login,logout}) that
// set the kwabo_admin cookie via Set-Cookie. We deliberately do NOT use
// `document.cookie =` — that races with the post-login redirect (cookie
// sometimes lands AFTER navigation, causing the middleware to bounce back
// to /login → infinite loop).

type LoginResponse = { ok: boolean };

export async function authLogin(password: string): Promise<LoginResponse> {
  // Note the relative path — this hits the Next.js route on Vercel, not
  // the Railway API directly. The route forwards the password upstream
  // and translates the upstream response into a Set-Cookie on Vercel.
  const res = await fetch(`/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.status === 401) {
    throw new Error("Ongeldig wachtwoord");
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export async function authLogout(): Promise<void> {
  // Best-effort: clear cookie via Vercel route (canonical), then ping
  // upstream for log purposes. Either failure is non-fatal — the user
  // is going to /login regardless.
  try {
    await fetch(`/api/auth/logout`, { method: "POST" });
  } catch {
    /* ignore */
  }
  try {
    await fetch(`${API_BASE}/api/auth/logout`, { method: "POST" });
  } catch {
    /* ignore */
  }
}

export async function authMe(): Promise<{ ok: boolean } | null> {
  // Returns null on 401 instead of redirecting — callers (login page)
  // need to differentiate "not logged in" from "session ok".
  try {
    const token = await getAuthToken();
    if (!token) return null;
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (res.status === 401) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export const api = {
  listOrders: (status?: string) =>
    req<OrderSummary[]>(`/api/orders${status ? `?status=${status}` : ""}`),
  getOrder: (id: number) => req<OrderDetail>(`/api/orders/${id}`),
  patchOrder: (id: number, body: Record<string, unknown>) =>
    req(`/api/orders/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  approve: (id: number, body: Record<string, unknown> = {}, opts?: { force?: boolean }) =>
    req<{
      ok: boolean;
      navision_order_nr?: string | null;
      status: "pushed" | "failed";
      nav_status: "pushed" | "failed" | string;
      nav_error?: string | null;
      nav_operation_count: number;
      nav_failed_op_count: number;
      forced?: boolean;
    }>(
      `/api/orders/${id}/approve${opts?.force ? "?force=true" : ""}`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  navDebug: (id: number) =>
    req<{
      order_id: number;
      status: string;
      navision_order_nr: string | null;
      navision_status: string | null;
      errors: string[];
      nav_autofilled: Record<string, unknown>;
      nav_operation_results: Array<{
        operation: Record<string, unknown>;
        status?: number | null;
        response_body?: Record<string, unknown>;
        autofilled?: Record<string, unknown>;
        error?: string | null;
      }>;
    }>(`/api/orders/${id}/nav-debug`),
  navisionPreview: (id: number) =>
    req<NavPreviewResponse>(`/api/orders/${id}/navision-preview`),
  uploadIncomingDoc: async (
    id: number,
    file: File,
  ): Promise<{ saved_path: string; file_size: number; content_type: string }> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/api/orders/${id}/incoming-doc`, {
      method: "POST",
      body: fd,
      headers: await authHeaders(),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
  },
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
    const res = await fetch(`${API_BASE}/api/klanten/${nr}/import-excel`, {
      method: "POST",
      body: fd,
      headers: await authHeaders(),
    });
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
      headers: await authHeaders(),
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
  attachmentToken: (orderId: number, naam: string, disposition: "inline" | "attachment" = "inline") =>
    req<{ token: string; expires_at: number }>(
      `/api/orders/${orderId}/bijlagen-token`,
      { method: "POST", body: JSON.stringify({ naam, disposition }) },
    ),
  attachmentSignedUrl: async (
    orderId: number,
    naam: string,
    disposition: "inline" | "attachment" = "inline",
  ) => {
    const { token } = await req<{ token: string; expires_at: number }>(
      `/api/orders/${orderId}/bijlagen-token`,
      { method: "POST", body: JSON.stringify({ naam, disposition }) },
    );
    return `${API_BASE}/api/orders/${orderId}/bijlagen?naam=${encodeURIComponent(naam)}&disposition=${disposition}&token=${encodeURIComponent(token)}`;
  },
  // Signed-URL voor de losse "Bron-document" upload (POST /incoming-doc).
  // Aparte route dan bijlagen-in-eml want de bytes liggen niet binnen een
  // .eml maar als losstaand bestand in Supabase / op disk. Token-bind is
  // (order_id, "incoming-doc", disposition) — er is maar één per order.
  incomingDocSignedUrl: async (
    orderId: number,
    disposition: "inline" | "attachment" = "inline",
  ) => {
    const { token } = await req<{ token: string; expires_at: number }>(
      `/api/orders/${orderId}/incoming-doc-token`,
      {
        method: "POST",
        body: JSON.stringify({ naam: "incoming-doc", disposition }),
      },
    );
    return `${API_BASE}/api/orders/${orderId}/incoming-doc/file?disposition=${disposition}&token=${encodeURIComponent(token)}`;
  },
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
