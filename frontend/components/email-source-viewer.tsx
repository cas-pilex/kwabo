"use client";

import { useState } from "react";
import { api } from "@/lib/api";

type Bijlage = { naam: string; type: string; inhoud_tekst: string };

type Source = { key: string; label: string; type: string; content: string; naam?: string };

function typeBadge(t: string): string {
  const map: Record<string, string> = {
    email: "bg-slate-200 text-slate-800",
    pdf: "bg-rose-100 text-rose-800",
    excel: "bg-emerald-100 text-emerald-800",
    csv: "bg-emerald-100 text-emerald-800",
    other: "bg-slate-100 text-slate-600",
  };
  return map[t] ?? "bg-slate-100 text-slate-600";
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) continue;
    const cols: string[] = [];
    let cur = "";
    let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"' && line[i + 1] === '"' && inQ) {
        cur += '"';
        i++;
      } else if (c === '"') {
        inQ = !inQ;
      } else if ((c === "," || c === ";") && !inQ) {
        cols.push(cur);
        cur = "";
      } else {
        cur += c;
      }
    }
    cols.push(cur);
    rows.push(cols);
  }
  return rows;
}

export function EmailSourceViewer({
  orderId,
  emailFrom,
  emailDate,
  emailBody,
  bijlagen,
}: {
  orderId: number;
  emailFrom: string | null;
  emailDate: string | null;
  emailBody: string;
  bijlagen: Bijlage[];
}) {
  const sources: Source[] = [
    { key: "email", label: "E-mail body", type: "email", content: emailBody || "(geen body)" },
    ...bijlagen.map((b, i) => ({
      key: `b-${i}`,
      label: b.naam,
      type: b.type,
      content: b.inhoud_tekst || "(geen tekst geëxtraheerd)",
      naam: b.naam,
    })),
  ];
  const [active, setActive] = useState(sources[0]?.key ?? "email");
  const [viewMode, setViewMode] = useState<"text" | "preview">("text");
  const current = sources.find((s) => s.key === active) ?? sources[0];
  const isAttachment = current && current.key !== "email";
  const fileUrl = isAttachment && current.naam
    ? api.attachmentUrl(orderId, current.naam, "inline")
    : null;
  const downloadUrl = isAttachment && current.naam
    ? api.attachmentUrl(orderId, current.naam, "attachment")
    : null;

  const canPreviewInline = current?.type === "pdf";
  const isCsv = current?.type === "csv";
  const csvRows = isCsv && current ? parseCsv(current.content) : null;

  return (
    <div className="space-y-3">
      <div className="rounded-md bg-slate-50 p-2 text-[11px] ring-1 ring-slate-200">
        <div>
          <span className="text-slate-500">Van:</span>{" "}
          <span className="font-medium text-slate-800">{emailFrom || "—"}</span>
        </div>
        <div>
          <span className="text-slate-500">Datum:</span>{" "}
          <span className="font-mono">{emailDate || "—"}</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-[var(--kwabo-border)]">
        {sources.map((s) => {
          const isActive = s.key === active;
          return (
            <button
              key={s.key}
              onClick={() => {
                setActive(s.key);
                setViewMode("text");
              }}
              className={`flex items-center gap-1.5 rounded-t px-3 py-1.5 text-[11px] font-medium transition ${
                isActive
                  ? "border border-b-white border-[var(--kwabo-border)] bg-white text-[var(--kwabo-navy)]"
                  : "text-slate-500 hover:text-[var(--kwabo-navy)]"
              }`}
              title={s.label}
            >
              <span
                className={`inline-flex rounded px-1 py-0 text-[9px] font-semibold uppercase ${typeBadge(
                  s.type,
                )}`}
              >
                {s.type}
              </span>
              <span className="max-w-[12rem] truncate">{s.label}</span>
            </button>
          );
        })}
      </div>

      {isAttachment && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1.5 ring-1 ring-slate-200">
          <div className="flex gap-1 text-[11px]">
            <button
              onClick={() => setViewMode("text")}
              className={`rounded px-2 py-0.5 ${
                viewMode === "text"
                  ? "bg-white text-[var(--kwabo-navy)] ring-1 ring-[var(--kwabo-border)]"
                  : "text-slate-600 hover:text-[var(--kwabo-navy)]"
              }`}
            >
              📄 Tekst
            </button>
            {canPreviewInline && (
              <button
                onClick={() => setViewMode("preview")}
                className={`rounded px-2 py-0.5 ${
                  viewMode === "preview"
                    ? "bg-white text-[var(--kwabo-navy)] ring-1 ring-[var(--kwabo-border)]"
                    : "text-slate-600 hover:text-[var(--kwabo-navy)]"
                }`}
              >
                🔍 PDF-preview
              </button>
            )}
          </div>
          <div className="flex gap-2 text-[11px]">
            {fileUrl && (
              <a
                href={fileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded border border-[var(--kwabo-border)] bg-white px-2 py-0.5 text-[var(--kwabo-navy)] hover:bg-slate-50"
              >
                🗗 Open in nieuw tabblad
              </a>
            )}
            {downloadUrl && (
              <a
                href={downloadUrl}
                className="rounded border border-[var(--kwabo-border)] bg-white px-2 py-0.5 text-[var(--kwabo-navy)] hover:bg-slate-50"
              >
                📥 Download
              </a>
            )}
          </div>
        </div>
      )}

      {viewMode === "preview" && canPreviewInline && fileUrl ? (
        <iframe
          src={fileUrl}
          className="h-[60vh] w-full rounded-md ring-1 ring-[var(--kwabo-border)]"
          title={current?.label}
        />
      ) : csvRows && csvRows.length > 0 ? (
        <div className="max-h-[60vh] overflow-auto rounded-md bg-white ring-1 ring-[var(--kwabo-border)]">
          <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-[11px]">
            <thead className="sticky top-0 bg-slate-50 text-[10px] font-semibold uppercase text-slate-500">
              <tr>
                {csvRows[0].map((h, i) => (
                  <th key={i} className="px-2 py-1 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--kwabo-border)]">
              {csvRows.slice(1).map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className="px-2 py-1 text-slate-800">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <pre className="max-h-[60vh] min-h-[20vh] overflow-auto whitespace-pre-wrap rounded-md bg-white p-3 text-[11px] leading-relaxed text-slate-800 ring-1 ring-[var(--kwabo-border)]">
            {current?.content?.slice(0, 40000) || ""}
          </pre>
          {current?.content && current.content.length > 40000 && (
            <div className="text-[10px] text-slate-500">
              Tekst afgekapt op 40.000 tekens (origineel {current.content.length}).
            </div>
          )}
        </>
      )}
    </div>
  );
}
