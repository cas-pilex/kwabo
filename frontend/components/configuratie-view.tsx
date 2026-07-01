"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  api,
  type PipelineStep,
  type PromptOut,
  type PromptVersionOut,
  type SettingOut,
} from "@/lib/api";

type Tab = "prompts" | "settings" | "pipeline";

export function ConfiguratieView() {
  const [tab, setTab] = useState<Tab>("prompts");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">
          Configuratie
        </h1>
        <p className="text-sm text-[var(--kwabo-muted)]">
          Bekijk en verscherp de AI-prompts en -instellingen. Wijzigingen werken direct bij de
          volgende (her-)verwerking — geen redeploy nodig.
        </p>
      </div>

      <nav className="flex gap-1 border-b border-[var(--kwabo-border)]">
        <TabButton active={tab === "prompts"} onClick={() => setTab("prompts")}>
          AI-prompts
        </TabButton>
        <TabButton active={tab === "settings"} onClick={() => setTab("settings")}>
          AI-instellingen
        </TabButton>
        <TabButton active={tab === "pipeline"} onClick={() => setTab("pipeline")}>
          Pipeline-overzicht
        </TabButton>
      </nav>

      {tab === "prompts" && <PromptsTab />}
      {tab === "settings" && <SettingsTab />}
      {tab === "pipeline" && <PipelineTab />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px rounded-t-md border-b-2 px-4 py-2 text-sm font-medium ${
        active
          ? "border-[var(--kwabo-navy)] text-[var(--kwabo-navy)]"
          : "border-transparent text-[var(--kwabo-muted)] hover:text-[var(--kwabo-navy)]"
      }`}
    >
      {children}
    </button>
  );
}

// ---------- AI-prompts ----------

function PromptsTab() {
  const [prompts, setPrompts] = useState<PromptOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setPrompts(await api.getPrompts());
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <div className="text-sm text-[var(--kwabo-muted)]">Laden…</div>;
  if (err) return <div className="text-sm text-rose-600">{err}</div>;

  return (
    <div className="space-y-6">
      {prompts.map((p) => (
        <PromptEditor key={p.key} prompt={p} onChanged={load} />
      ))}
    </div>
  );
}

function PromptEditor({ prompt, onChanged }: { prompt: PromptOut; onChanged: () => void }) {
  const [content, setContent] = useState(prompt.content);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [versions, setVersions] = useState<PromptVersionOut[]>([]);

  // Sync het tekstveld wanneer de bovenliggende lijst herlaadt (bv. na reset/rollback).
  useEffect(() => {
    setContent(prompt.content);
  }, [prompt.content]);

  const dirty = content !== prompt.content;

  async function save() {
    if (!content.trim()) {
      toast.error("Prompt mag niet leeg zijn");
      return;
    }
    setBusy(true);
    try {
      await api.savePrompt(prompt.key, { content, note: note || null });
      toast.success(`Prompt "${prompt.label}" opgeslagen`);
      setNote("");
      onChanged();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    try {
      await api.resetPrompt(prompt.key);
      toast.success("Hersteld naar standaard");
      onChanged();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleHistory() {
    const next = !showHistory;
    setShowHistory(next);
    if (next) {
      try {
        setVersions(await api.getPromptVersions(prompt.key));
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function rollback(versionId: number) {
    setBusy(true);
    try {
      await api.rollbackPrompt(prompt.key, versionId);
      toast.success(`Teruggerold naar versie ${versionId}`);
      setShowHistory(false);
      onChanged();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-[var(--kwabo-border)] bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-medium text-[var(--kwabo-navy)]">
            {prompt.label}
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-[var(--kwabo-muted)]">
              {prompt.key}
            </code>
            {prompt.is_overridden ? (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                aangepast
              </span>
            ) : (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--kwabo-muted)]">
                standaard
              </span>
            )}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-[var(--kwabo-muted)]">{prompt.beschrijving}</p>
        </div>
        <button
          onClick={toggleHistory}
          className="shrink-0 text-xs text-[var(--kwabo-navy)] hover:underline"
        >
          {showHistory ? "Verberg historie" : "Versiehistorie"}
        </button>
      </div>

      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        spellCheck={false}
        rows={Math.min(24, Math.max(8, content.split("\n").length + 1))}
        className="mt-3 w-full rounded border border-[var(--kwabo-border)] p-3 font-mono text-xs leading-relaxed focus:border-[var(--kwabo-navy-500)] focus:outline-none focus:ring-1 focus:ring-[var(--kwabo-navy-500)]"
      />

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="flex flex-1 flex-col">
          <span className="text-[10px] uppercase text-[var(--kwabo-muted)]">Notitie (optioneel)</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="bijv. 'strengere afwijzing offertes'"
            className="rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm"
          />
        </label>
        <button
          onClick={save}
          disabled={busy || !dirty}
          className="rounded-md bg-[var(--kwabo-navy)] px-3 py-1.5 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Bezig…" : "Opslaan"}
        </button>
        <button
          onClick={reset}
          disabled={busy || !prompt.is_overridden}
          className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Herstel naar standaard
        </button>
      </div>
      {dirty && (
        <p className="mt-2 text-xs text-amber-700">
          Niet-opgeslagen wijzigingen. Klik Opslaan om ze te activeren.
        </p>
      )}

      {showHistory && (
        <div className="mt-4 rounded border border-[var(--kwabo-border)] bg-slate-50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase text-[var(--kwabo-muted)]">
            Versiehistorie
          </h3>
          {versions.length === 0 ? (
            <p className="text-sm text-[var(--kwabo-muted)]">
              Nog geen opgeslagen versies (prompt draait op het standaardbestand).
            </p>
          ) : (
            <ul className="divide-y divide-[var(--kwabo-border)]">
              {versions.map((v) => (
                <li key={v.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <span className="font-mono text-xs text-[var(--kwabo-muted)]">
                      v{v.id} · {v.source}
                    </span>
                    {v.is_active && (
                      <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-700">
                        actief
                      </span>
                    )}
                    <div className="truncate text-xs text-[var(--kwabo-muted)]">
                      {new Date(v.created_at).toLocaleString("nl-NL")}
                      {v.note ? ` — ${v.note}` : ""}
                    </div>
                  </div>
                  <button
                    onClick={() => rollback(v.id)}
                    disabled={busy || v.is_active}
                    className="shrink-0 text-xs text-[var(--kwabo-navy)] hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Terugrollen
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

// ---------- AI-instellingen ----------

function SettingsTab() {
  const [settings, setSettings] = useState<SettingOut[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const rows = await api.getConfigSettings();
      setSettings(rows);
      setValues(Object.fromEntries(rows.map((r) => [r.key, r.value])));
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setBusy(true);
    try {
      const rows = await api.saveConfigSettings(values);
      setSettings(rows);
      setValues(Object.fromEntries(rows.map((r) => [r.key, r.value])));
      toast.success("Instellingen opgeslagen");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="text-sm text-[var(--kwabo-muted)]">Laden…</div>;
  if (err) return <div className="text-sm text-rose-600">{err}</div>;

  return (
    <div className="max-w-2xl space-y-4">
      {settings.map((s) => (
        <div
          key={s.key}
          className="rounded-lg border border-[var(--kwabo-border)] bg-white p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <label className="text-sm font-medium text-[var(--kwabo-navy)]">{s.label}</label>
            {s.is_overridden && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                aangepast
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-[var(--kwabo-muted)]">{s.beschrijving}</p>
          <div className="mt-2">
            {s.type === "bool" ? (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(values[s.key])}
                  onChange={(e) => setValues((v) => ({ ...v, [s.key]: e.target.checked }))}
                />
                <span>{values[s.key] ? "Aan" : "Uit"}</span>
              </label>
            ) : s.type === "number" ? (
              <input
                type="number"
                step="0.1"
                value={String(values[s.key] ?? "")}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [s.key]: parseFloat(e.target.value) }))
                }
                className="w-40 rounded border border-[var(--kwabo-border)] px-2 py-1 text-sm"
              />
            ) : (
              <input
                type="text"
                value={String(values[s.key] ?? "")}
                onChange={(e) => setValues((v) => ({ ...v, [s.key]: e.target.value }))}
                className="w-full rounded border border-[var(--kwabo-border)] px-2 py-1 font-mono text-sm"
              />
            )}
          </div>
          <p className="mt-1 text-[10px] text-[var(--kwabo-muted)]">
            Standaard: <code>{String(s.default)}</code>
          </p>
        </div>
      ))}
      <button
        onClick={save}
        disabled={busy}
        className="rounded-md bg-[var(--kwabo-navy)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--kwabo-navy-500)] disabled:opacity-40"
      >
        {busy ? "Bezig…" : "Instellingen opslaan"}
      </button>
    </div>
  );
}

// ---------- Pipeline-overzicht ----------

function PipelineTab() {
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const d = await api.getPipelineSteps();
        setSteps(d.steps);
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="text-sm text-[var(--kwabo-muted)]">Laden…</div>;
  if (err) return <div className="text-sm text-rose-600">{err}</div>;

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--kwabo-muted)]">
        De volledige verwerkingsketen, in volgorde. Alleen de{" "}
        <span className="font-medium text-[var(--kwabo-navy)]">AI</span>-stappen hebben een
        bewerkbare prompt; de rest is deterministische code.
      </p>
      <ol className="space-y-2">
        {steps.map((s, i) => (
          <li
            key={s.key}
            className="rounded-lg border border-[var(--kwabo-border)] bg-white p-4"
          >
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-[var(--kwabo-muted)]">
                {i + 1}
              </span>
              <h3 className="text-sm font-medium text-[var(--kwabo-navy)]">{s.label}</h3>
              {s.type === "llm-prompt" ? (
                <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-sky-700">
                  AI-prompt
                </span>
              ) : (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--kwabo-muted)]">
                  deterministisch
                </span>
              )}
            </div>
            <p className="mt-1.5 text-sm text-[var(--kwabo-muted)]">{s.beschrijving}</p>
            <dl className="mt-2 grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
              <div>
                <dt className="inline font-semibold text-[var(--kwabo-navy)]">Input: </dt>
                <dd className="inline text-[var(--kwabo-muted)]">{s.input}</dd>
              </div>
              <div>
                <dt className="inline font-semibold text-[var(--kwabo-navy)]">Output: </dt>
                <dd className="inline text-[var(--kwabo-muted)]">{s.output}</dd>
              </div>
            </dl>
            <p className="mt-1 font-mono text-[10px] text-[var(--kwabo-muted)]">{s.bron}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
