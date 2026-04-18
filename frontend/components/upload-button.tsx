"use client";
import { useState, useRef } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export function UploadButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  async function handle(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
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
      onDone?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
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
        className="px-4 py-2 rounded-md bg-[#0b2545] text-white hover:bg-[#13345e] disabled:opacity-50 transition"
      >
        {busy ? "Bezig…" : "Upload .eml"}
      </button>
      {error && <span className="text-rose-600 text-sm">{error}</span>}
    </div>
  );
}
