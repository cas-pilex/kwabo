"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Status = Awaited<ReturnType<typeof api.mailboxStatus>>;
type OAuthCfg = Awaited<ReturnType<typeof api.oauthConfig>>;

function stateClass(state: string): string {
  if (state === "active") return "bg-emerald-50 text-emerald-800 ring-emerald-300";
  if (state === "not_configured" || state === "degraded")
    return "bg-amber-50 text-amber-800 ring-amber-300";
  if (state === "error") return "bg-rose-50 text-rose-800 ring-rose-300";
  return "bg-slate-50 text-slate-700 ring-slate-200";
}

function modeLabel(mode: string): string {
  if (mode === "file_drop") return "📂 File-drop (lokale inbox)";
  if (mode === "imap") return "📨 IMAP";
  if (mode === "graph") return "☁️ Microsoft Graph";
  return mode;
}

export default function EmailPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [cfg, setCfg] = useState<OAuthCfg | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [tenant, setTenant] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  async function load() {
    try {
      const [s, c] = await Promise.all([api.mailboxStatus(), api.oauthConfig()]);
      setStatus(s);
      setCfg(c);
      setTenant(c.tenant_id);
      setClientId(c.client_id);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "1") {
      toast.success("Microsoft account verbonden!");
      window.history.replaceState({}, "", "/email");
    }
  }, []);

  async function saveConfig() {
    if (!tenant.trim() || !clientId.trim()) {
      toast.error("Tenant ID en Client ID zijn verplicht");
      return;
    }
    setBusy(true);
    try {
      const updated = await api.saveOauthConfig({
        tenant_id: tenant.trim(),
        client_id: clientId.trim(),
        client_secret: clientSecret.trim() || undefined,
      });
      setCfg(updated);
      setClientSecret("");
      toast.success("Config opgeslagen");
      await load();
    } catch (e) {
      toast.error(`Opslaan mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!confirm("Weet je zeker dat je wilt loskoppelen?")) return;
    try {
      await api.oauthDisconnect();
      toast.success("Losgekoppeld");
      await load();
    } catch (e) {
      toast.error(`Mislukt: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  function startOAuth() {
    window.location.href = api.oauthStartUrl();
  }

  const canConnect = cfg?.configured && cfg?.has_secret;
  const isConnected = status?.connected && status.mode === "graph";

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">
            E-mail connectie
          </h1>
          <p className="text-sm text-[var(--kwabo-muted)]">
            Beheer hoe inkomende orders opgehaald worden.
          </p>
        </div>
        <button
          onClick={load}
          className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          Vernieuwen
        </button>
      </div>

      {err && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          Backend niet bereikbaar: {err}
        </div>
      )}

      {/* Status card */}
      {status && (
        <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-[var(--kwabo-border)]">
          <div className="mb-3 flex items-center justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
                Huidige mode
              </div>
              <div className="mt-1 text-lg font-semibold text-[var(--kwabo-navy)]">
                {modeLabel(status.mode)}
              </div>
              {status.account_email && (
                <div className="mt-0.5 text-xs text-[var(--kwabo-muted)]">
                  Verbonden als{" "}
                  <span className="font-mono text-slate-800">{status.account_email}</span>
                </div>
              )}
            </div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${stateClass(status.state)}`}
            >
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  status.state === "active"
                    ? "bg-emerald-500"
                    : status.state === "error"
                      ? "bg-rose-500"
                      : "bg-amber-500"
                }`}
              />
              {status.state}
            </span>
          </div>

          <p className="text-sm text-slate-700">{status.message}</p>

          {status.mode === "file_drop" && (
            <div className="mt-3 space-y-1 rounded-md bg-slate-50 p-3 text-xs ring-1 ring-slate-200">
              <div>
                <span className="text-slate-500">Inbox directory:</span>{" "}
                <span className="font-mono">{status.inbox_dir}</span>
              </div>
              <div>
                <span className="text-slate-500">Wachtrij:</span>{" "}
                <span className="font-mono">{status.inbox_pending}</span> .eml bestanden
              </div>
            </div>
          )}

          {isConnected && (
            <div className="mt-3">
              <button
                onClick={disconnect}
                className="rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
              >
                Loskoppelen
              </button>
            </div>
          )}
        </div>
      )}

      {/* OAuth2 setup */}
      <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-[var(--kwabo-border)]">
        <h2 className="mb-1 text-base font-semibold text-[var(--kwabo-navy)]">
          ☁️ Microsoft Graph (OAuth2) setup
        </h2>
        <p className="mb-4 text-xs text-[var(--kwabo-muted)]">
          Voor Microsoft 365 mailboxen. Eerst eenmalig een Azure AD app-registration aanmaken
          (zie stappen onderaan), dan hieronder de gegevens invullen.
        </p>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="text-xs">
            <span className="mb-1 block font-medium text-slate-700">
              Directory (tenant) ID
            </span>
            <input
              type="text"
              value={tenant}
              onChange={(e) => setTenant(e.target.value)}
              placeholder="b8a4c6d2-…"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
            />
          </label>
          <label className="text-xs">
            <span className="mb-1 block font-medium text-slate-700">
              Application (client) ID
            </span>
            <input
              type="text"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="7f3c…"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
            />
          </label>
          <label className="text-xs">
            <span className="mb-1 block font-medium text-slate-700">
              Client Secret {cfg?.has_secret && <span className="text-emerald-700">(opgeslagen)</span>}
            </span>
            <input
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder={cfg?.has_secret ? "•••••••• (laat leeg om te behouden)" : "plak hier de secret-waarde"}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
            />
          </label>
        </div>

        <div className="mt-3 text-[11px] text-[var(--kwabo-muted)]">
          Redirect URI (zet dit in Azure):{" "}
          <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[10px]">
            {cfg?.redirect_uri || "http://localhost:8000/api/mailbox/oauth/callback"}
          </code>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={saveConfig}
            disabled={busy}
            className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
          >
            💾 Config opslaan
          </button>
          <button
            onClick={startOAuth}
            disabled={!canConnect}
            title={
              !canConnect
                ? "Eerst tenant_id, client_id én client_secret opslaan"
                : "Open Microsoft inlog-scherm"
            }
            className="rounded-md bg-[var(--kwabo-navy)] px-4 py-1.5 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            ☁️ Connect with Microsoft
          </button>
        </div>
      </div>

      {/* Setup instructions */}
      <details className="rounded-lg border border-[var(--kwabo-border)] bg-white p-4 text-sm">
        <summary className="cursor-pointer font-semibold text-[var(--kwabo-navy)]">
          📋 Azure AD app-registration — eenmalige setup (±5 min)
        </summary>
        <ol className="mt-3 space-y-2 pl-6 text-xs text-slate-700 list-decimal">
          <li>
            Ga naar <a className="text-[var(--kwabo-navy)] underline" href="https://portal.azure.com" target="_blank" rel="noopener noreferrer">portal.azure.com</a> → <strong>Azure Active Directory</strong> → <strong>App registrations</strong> → <strong>New registration</strong>
          </li>
          <li>Naam: <em>"Kwabo Order Intake"</em></li>
          <li>
            Supported account types: <strong>Single tenant</strong> (pilex.ai) — of Multi-tenant als je 'm ook voor Kwabo wilt gebruiken
          </li>
          <li>
            Redirect URI: type <strong>Web</strong>, URL ={" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono">
              {cfg?.redirect_uri || "http://localhost:8000/api/mailbox/oauth/callback"}
            </code>
          </li>
          <li>Klik <strong>Register</strong></li>
          <li>
            Linkermenu <strong>API permissions</strong> → <strong>Add a permission</strong> → <strong>Microsoft Graph</strong> → <strong>Delegated permissions</strong> → selecteer <code>Mail.Read</code>, <code>offline_access</code>, <code>User.Read</code> → Add
          </li>
          <li>
            Linkermenu <strong>Certificates & secrets</strong> → <strong>New client secret</strong> → geldigheid 24 maanden → kopieer de <strong>Value</strong> (niet de Secret ID!) — dit is je <em>Client Secret</em>
          </li>
          <li>
            Linkermenu <strong>Overview</strong> → kopieer <strong>Application (client) ID</strong> en <strong>Directory (tenant) ID</strong>
          </li>
          <li>Plak deze 3 waarden hierboven, klik "Config opslaan", dan "Connect with Microsoft"</li>
        </ol>
      </details>

      {/* Alternate methods */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <MethodCard
          active={status?.mode === "file_drop"}
          title="File-drop"
          icon="📂"
          description="Sleep .eml-bestanden in data/inbox en klik 'Scan' op de Queue. Werkt zonder externe credentials — handig voor tests."
          status="Werkend"
          statusClass="bg-emerald-100 text-emerald-800"
        />
        <MethodCard
          active={status?.mode === "imap"}
          title="IMAP"
          icon="📨"
          description="Klassieke IMAP-connectie via host/port/gebruikersnaam + app-password. Werkt met Gmail, oude Exchange, eigen mailservers."
          status="Nog te implementeren"
          statusClass="bg-slate-200 text-slate-700"
          disabled
        />
      </div>
    </div>
  );
}

function MethodCard({
  active,
  title,
  icon,
  description,
  status,
  statusClass,
  disabled,
}: {
  active?: boolean;
  title: string;
  icon: string;
  description: string;
  status: string;
  statusClass: string;
  disabled?: boolean;
}) {
  return (
    <div
      className={`rounded-lg bg-white p-4 ring-1 shadow-sm transition ${
        active ? "ring-[var(--kwabo-navy)] ring-2" : "ring-[var(--kwabo-border)]"
      } ${disabled ? "opacity-70" : ""}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-2xl">{icon}</span>
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${statusClass}`}
        >
          {status}
        </span>
      </div>
      <div className="mb-1 text-base font-semibold text-[var(--kwabo-navy)]">{title}</div>
      <p className="text-xs text-slate-600">{description}</p>
    </div>
  );
}
