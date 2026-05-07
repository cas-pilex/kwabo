"use client";

import { useState } from "react";
import { authLogin } from "@/lib/api";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authLogin(password);
      // Hard redirect so the cookie is picked up by SSR pages immediately.
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inloggen mislukt");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-lg bg-white p-8 shadow-md ring-1 ring-slate-200">
          <h1 className="text-xl font-semibold text-[var(--kwabo-navy)] mb-1">
            Kwabo Order Intake
          </h1>
          <p className="text-sm text-slate-500 mb-6">Login om verder te gaan</p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="password"
                className="block text-xs font-medium text-slate-600 mb-1"
              >
                Wachtwoord
              </label>
              <input
                id="password"
                type="password"
                autoFocus
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
              />
            </div>
            {error && (
              <p
                role="alert"
                className="text-xs text-rose-700 bg-rose-50 ring-1 ring-rose-200 rounded px-2 py-1.5"
              >
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={loading || !password}
              className="w-full rounded-md bg-[var(--kwabo-navy)] px-4 py-2 text-sm font-medium text-white transition hover:bg-[var(--kwabo-navy-500)] disabled:opacity-50"
            >
              {loading ? "Bezig..." : "Inloggen"}
            </button>
          </form>
        </div>
        <p className="mt-3 text-center text-xs text-slate-500">
          © Kwabo Techniek B.V.
        </p>
      </div>
    </div>
  );
}
