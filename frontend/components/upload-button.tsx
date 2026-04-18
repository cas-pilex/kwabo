"use client";
import { useState, useRef } from "react";
import { toast } from "sonner";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export function UploadButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  async function handle(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch(`${API}/api/intake/upload`, { method: "POST", body: fd });
        if (!r.ok) {
          let msg = `HTTP ${r.status}`;
          try {
            const j = await r.json();
            msg = j.detail || msg;
          } catch {}
          throw new Error(`${f.name}: ${msg}`);
        }
      }
      toast.success(`${files.length} bestand(en) geüpload`);
      onDone?.();
    } catch (e: unknown) {
      toast.error(`Upload mislukt: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div className="flex items-center gap-3">
      <input
        ref={ref}
        type="file"
        accept=".eml"
        multiple
        onChange={(e) => handle(e.target.files)}
        className="sr-only"
        data-testid="eml-upload-input"
      />
      <button
        onClick={() => ref.current?.click()}
        disabled={busy}
        data-testid="eml-upload-button"
        className="px-4 py-2 rounded-md bg-[#0b2545] text-white hover:bg-[#13345e] disabled:opacity-50 transition inline-flex items-center gap-2"
      >
        {busy && (
          <svg
            className="animate-spin h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
            <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
        )}
        {busy ? "Bezig…" : "Upload .eml"}
      </button>
    </div>
  );
}
