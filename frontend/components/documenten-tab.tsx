"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Doc = {
  id: number;
  filename: string;
  doc_type: string;
  mime_type: string | null;
  size_bytes: number;
  created_at: string;
  text_preview: string;
};

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function typeBadge(t: string): string {
  const map: Record<string, string> = {
    pdf: "bg-rose-100 text-rose-800 ring-rose-200",
    docx: "bg-sky-100 text-sky-800 ring-sky-200",
    excel: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    csv: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    txt: "bg-slate-200 text-slate-800 ring-slate-300",
    other: "bg-slate-100 text-slate-600 ring-slate-200",
  };
  return map[t] ?? map.other;
}

export function DocumentenTab({ klantNr }: { klantNr: string }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [uploading, setUploading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [fullText, setFullText] = useState<Record<number, string>>({});
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      setDocs(await api.listDocuments(klantNr));
    } catch (e) {
      toast.error(`Laden mislukt: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  useEffect(() => {
    load();
  }, [klantNr]);

  async function doUpload(files: FileList | File[]) {
    const list = Array.from(files);
    if (list.length === 0) return;
    setUploading(true);
    try {
      for (const f of list) {
        await api.uploadDocument(klantNr, f);
        toast.success(`Geüpload: ${f.name}`);
      }
      await load();
    } catch (e) {
      toast.error(`Upload mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setUploading(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Dit document verwijderen?")) return;
    try {
      await api.deleteDocument(klantNr, id);
      toast.success("Verwijderd");
      setExpanded(null);
      await load();
    } catch (e) {
      toast.error(`Verwijderen mislukt: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function toggleExpand(id: number) {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!fullText[id]) {
      try {
        const d = await api.getDocument(klantNr, id);
        setFullText((prev) => ({ ...prev, [id]: d.text_content }));
      } catch (e) {
        toast.error(`Laden mislukt: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  }

  return (
    <div className="space-y-4 text-sm">
      <p className="text-[var(--kwabo-muted)]">
        Upload klantkaart-documenten (PDF, Word, Excel, CSV, TXT). De tekst wordt automatisch
        geëxtraheerd en bewaard als referentie bij de klant — handig voor matching-context en
        handmatige controles.
      </p>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files?.length) {
            doUpload(e.dataTransfer.files);
          }
        }}
        onClick={() => fileRef.current?.click()}
        className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-sm transition cursor-pointer ${
          dragOver
            ? "border-[var(--kwabo-navy)] bg-slate-50"
            : "border-slate-300 bg-white hover:border-[var(--kwabo-navy)]"
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.docx,.xlsx,.xls,.csv,.txt"
          onChange={(e) => {
            if (e.target.files?.length) doUpload(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="text-base font-medium text-[var(--kwabo-navy)]">
          {uploading ? "⏳ Uploaden…" : "📎 Sleep bestanden hier of klik om te kiezen"}
        </div>
        <div className="text-xs text-[var(--kwabo-muted)]">
          PDF · Word · Excel · CSV · TXT — meerdere tegelijk is OK
        </div>
      </div>

      {/* Document list */}
      <div className="overflow-hidden rounded-md border border-[var(--kwabo-border)] bg-white">
        <table className="min-w-full divide-y divide-[var(--kwabo-border)] text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-[var(--kwabo-muted)]">
            <tr>
              <th className="px-3 py-1.5 text-left">Bestand</th>
              <th className="px-3 py-1.5 text-left">Type</th>
              <th className="px-3 py-1.5 text-right">Grootte</th>
              <th className="px-3 py-1.5 text-left">Geüpload</th>
              <th className="px-3 py-1.5 text-right"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--kwabo-border)]">
            {docs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-[var(--kwabo-muted)]">
                  Nog geen documenten geüpload.
                </td>
              </tr>
            )}
            {docs.map((d) => {
              const isOpen = expanded === d.id;
              return (
                <Fragment key={d.id}>
                  <tr
                    className={`cursor-pointer transition hover:bg-slate-50 ${
                      isOpen ? "bg-slate-50" : ""
                    }`}
                    onClick={() => toggleExpand(d.id)}
                  >
                    <td className="px-3 py-1.5 font-medium text-slate-800">{d.filename}</td>
                    <td className="px-3 py-1.5">
                      <span
                        className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ${typeBadge(d.doc_type)}`}
                      >
                        {d.doc_type}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-slate-500">
                      {fmtSize(d.size_bytes)}
                    </td>
                    <td className="px-3 py-1.5 text-xs text-slate-500">
                      {new Date(d.created_at).toLocaleString("nl-NL")}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          remove(d.id);
                        }}
                        className="text-xs text-rose-700 hover:underline"
                      >
                        Verwijder
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-slate-50/50">
                      <td colSpan={5} className="px-3 py-2">
                        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
                          Geëxtraheerde tekst
                        </div>
                        <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-white p-2 text-[11px] leading-relaxed text-slate-800 ring-1 ring-[var(--kwabo-border)]">
                          {fullText[d.id] ?? d.text_preview ?? "(geen tekst)"}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
