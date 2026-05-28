"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Props = {
  orderId: number;
  incomingPath: string | null | undefined;
  onChanged?: () => void;
};

function basename(p: string): string {
  // Handles both windows + posix paths.
  const norm = p.replace(/\\/g, "/");
  const parts = norm.split("/").filter(Boolean);
  return parts[parts.length - 1] || p;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function IncomingDocumentPanel({
  orderId,
  incomingPath,
  onChanged,
}: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<{ saved_path: string; file_size: number } | null>(
    incomingPath ? { saved_path: incomingPath, file_size: 0 } : null,
  );

  async function handle(files: FileList | null) {
    if (!files || files.length === 0) return;
    const file = files[0];
    setBusy(true);
    try {
      const r = await api.uploadIncomingDoc(orderId, file);
      setInfo({ saved_path: r.saved_path, file_size: r.file_size });
      toast.success(`Bron-document geüpload (${fmtSize(r.file_size)})`);
      onChanged?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Upload mislukt: ${msg}`);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  // "Open"/"Download" minten een signed URL per klik. De URL leeft 5 min;
  // re-minten bij volgende klik is goedkoper dan een stale-URL bug.
  async function openIncomingDoc(disposition: "inline" | "attachment") {
    try {
      const url = await api.incomingDocSignedUrl(orderId, disposition);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Openen mislukt: ${msg}`);
    }
  }

  return (
    <div
      data-testid="incoming-doc-panel"
      className="rounded-md border border-[var(--kwabo-border)] bg-slate-50 p-2"
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--kwabo-muted)]">
          Bron-document
        </span>
        {info?.saved_path ? (
          <span
            className="ml-auto truncate text-[11px] text-slate-600"
            title={info.saved_path}
          >
            📎 {basename(info.saved_path)}
            {info.file_size > 0 && (
              <span className="ml-1 text-slate-400">· {fmtSize(info.file_size)}</span>
            )}
          </span>
        ) : (
          <span className="ml-auto text-[11px] italic text-slate-400">
            (geen bestand)
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          ref={ref}
          type="file"
          accept=".pdf,.eml,image/*"
          data-testid="incoming-doc-input"
          onChange={(e) => handle(e.target.files)}
          className="sr-only"
        />
        <button
          onClick={() => ref.current?.click()}
          disabled={busy}
          data-testid="incoming-doc-upload-btn"
          className="rounded-md border border-[var(--kwabo-border)] bg-white px-2 py-1 text-xs hover:bg-slate-100 disabled:opacity-50"
        >
          {busy ? "Bezig…" : info?.saved_path ? "Vervang…" : "Kies bestand…"}
        </button>
        {info?.saved_path && (
          <>
            <button
              onClick={() => openIncomingDoc("inline")}
              data-testid="incoming-doc-open-btn"
              className="rounded-md border border-[var(--kwabo-border)] bg-white px-2 py-1 text-xs hover:bg-slate-100"
              title="Open in nieuw tabblad"
            >
              🗗 Open
            </button>
            <button
              onClick={() => openIncomingDoc("attachment")}
              data-testid="incoming-doc-download-btn"
              className="rounded-md border border-[var(--kwabo-border)] bg-white px-2 py-1 text-xs hover:bg-slate-100"
              title="Download bestand"
            >
              📥 Download
            </button>
          </>
        )}
        <span className="text-[10px] text-slate-500">
          .pdf, .eml of afbeelding
        </span>
      </div>
    </div>
  );
}

export default IncomingDocumentPanel;
