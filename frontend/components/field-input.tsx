"use client";

import { forwardRef, useEffect, useRef, useState } from "react";
import type { FieldMeta } from "@/lib/api";
import { ProvenanceBadge } from "./provenance-badge";

type Props = {
  label: string;
  path: string;                   // JSON-path used as DOM id for scrollIntoView from banner
  value: string | number | null | undefined;
  meta?: FieldMeta;
  onChange: (newVal: string | number | null) => void;   // debounced PATCH happens in parent
  type?: "text" | "number" | "date";
  placeholder?: string;
  width?: string;                 // tailwind width class
  list?: string;                  // datalist id for combobox
  disabled?: boolean;
  monospace?: boolean;
};

export const FieldInput = forwardRef<HTMLInputElement, Props>(function FieldInput(
  { label, path, value, meta, onChange, type = "text", placeholder, width = "w-full", list, disabled, monospace },
  ref,
) {
  const [local, setLocal] = useState<string>(value == null ? "" : String(value));
  const tRef = useRef<number | null>(null);

  useEffect(() => {
    setLocal(value == null ? "" : String(value));
  }, [value]);

  function commit(next: string) {
    if (tRef.current) window.clearTimeout(tRef.current);
    tRef.current = window.setTimeout(() => {
      if (next === "") onChange(null);
      else if (type === "number") {
        const n = Number(next);
        onChange(isNaN(n) ? null : n);
      } else {
        onChange(next);
      }
    }, 400);
  }

  const isMissing = meta?.needs_review || (value == null || value === "");
  const ringCls = isMissing
    ? "border-rose-300 bg-rose-50/40 focus:ring-rose-500"
    : "border-slate-300 focus:ring-[var(--kwabo-navy)]";
  const inputCls = `${width} rounded-md border ${ringCls} px-2 py-1 text-sm focus:outline-none focus:ring-2 ${monospace ? "font-mono text-xs" : ""}`;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-medium text-[var(--kwabo-muted)]" htmlFor={path}>
          {label}
        </label>
        <ProvenanceBadge meta={meta} size="xs" />
      </div>
      <input
        ref={ref}
        id={path}
        type={type}
        list={list}
        disabled={disabled}
        value={local}
        placeholder={placeholder ?? (isMissing ? "Vul aan…" : "")}
        onChange={(e) => {
          setLocal(e.target.value);
          commit(e.target.value);
        }}
        className={inputCls}
      />
    </div>
  );
});
