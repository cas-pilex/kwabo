"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

export default function LogsPage() {
  const [lines, setLines] = useState<string[]>([]);
  const [live, setLive] = useState(true);
  const [filter, setFilter] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  // Initial tail fetch
  useEffect(() => {
    console.log("[logs] useEffect init fetch");
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/api/logs/tail?lines=500`);
        const d = await r.json();
        console.log("[logs] got", d?.lines?.length, "lines");
        setLines(d.lines || []);
      } catch (e) {
        console.error("[logs] fetch err", e);
        setLines([`[frontend] kan niet verbinden met ${API_BASE}`]);
      }
    })();
  }, []);

  // SSE stream
  useEffect(() => {
    if (!live) {
      esRef.current?.close();
      esRef.current = null;
      return;
    }
    const es = new EventSource(`${API_BASE}/api/logs/stream`);
    esRef.current = es;
    es.onmessage = (ev) => {
      if (!ev.data || ev.data.startsWith(":")) return;
      setLines((prev) => [...prev.slice(-1999), ev.data]);
    };
    es.onerror = () => {
      es.close();
      esRef.current = null;
    };
    return () => es.close();
  }, [live]);

  // Auto-scroll
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines]);

  const visible = filter
    ? lines.filter((l) => l.toLowerCase().includes(filter.toLowerCase()))
    : lines;

  function colorClass(line: string): string {
    if (/\bERROR\b|level='error'/.test(line)) return "text-rose-300";
    if (/\bWARN\b|level='warn'/.test(line)) return "text-amber-200";
    if (/push_navision|approve/i.test(line)) return "text-emerald-300";
    if (/classify|extract|match_|validate/.test(line)) return "text-sky-300";
    return "text-slate-200";
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--kwabo-navy)]">Logs</h1>
        <p className="text-sm text-[var(--kwabo-muted)]">
          Live structured log van de Python-backend (tail op <code>backend/kwabo.log</code>).
        </p>
      </div>

      <div className="flex items-center gap-3">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter (bijv. classify, match_articles, error)"
          className="w-96 rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-sm focus:border-[var(--kwabo-navy-500)] focus:outline-none focus:ring-1 focus:ring-[var(--kwabo-navy-500)]"
        />
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
          <span>Live stream</span>
        </label>
        <button
          onClick={() => setLines([])}
          className="rounded-md border border-[var(--kwabo-border)] bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
        >
          Clear
        </button>
        <span className="ml-auto text-xs text-[var(--kwabo-muted)]">
          {visible.length} regels{filter && ` (gefilterd uit ${lines.length})`}
        </span>
      </div>

      <div
        ref={logRef}
        className="h-[calc(100vh-280px)] overflow-auto rounded-lg bg-[var(--kwabo-navy)] p-3 font-mono text-[11px] leading-relaxed shadow-inner"
      >
        {visible.length === 0 && (
          <div className="text-slate-400">(geen regels — trigger een intake via POST /api/intake/scan)</div>
        )}
        {visible.map((l, i) => (
          <div key={i} className={colorClass(l)}>
            {l}
          </div>
        ))}
      </div>
    </div>
  );
}
