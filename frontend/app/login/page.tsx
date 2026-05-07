// Pure HTML form submission. No JS, no fetch, no redirect race —
// the /api/auth/login route handles validation + Set-Cookie + redirect
// in one atomic HTTP response.
//
// On failure the route bounces back here with `?err=...` so we render
// an error block. We also re-render with `?err=...` on rate-limits or
// upstream issues so the user gets actionable feedback instead of a
// silent return-to-login.

type SearchParams = { err?: string; from?: string };

const ERROR_MESSAGES: Record<string, string> = {
  "1": "Ongeldig wachtwoord",
  upstream: "Backend (Railway) niet bereikbaar — probeer het zo opnieuw",
  "no-token": "Login slaagde maar er kwam geen sessie-token terug",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const errorKey = params?.err;
  const errorMessage = errorKey ? ERROR_MESSAGES[errorKey] ?? "Inloggen mislukt" : null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-lg bg-white p-8 shadow-md ring-1 ring-slate-200">
          <h1 className="text-xl font-semibold text-[var(--kwabo-navy)] mb-1">
            Kwabo Order Intake
          </h1>
          <p className="text-sm text-slate-500 mb-6">Login om verder te gaan</p>
          <form
            method="POST"
            action="/api/auth/login"
            className="space-y-4"
          >
            <div>
              <label
                htmlFor="password"
                className="block text-xs font-medium text-slate-600 mb-1"
              >
                Wachtwoord
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoFocus
                autoComplete="current-password"
                required
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--kwabo-navy)]"
              />
            </div>
            {errorMessage && (
              <p
                role="alert"
                className="text-xs text-rose-700 bg-rose-50 ring-1 ring-rose-200 rounded px-2 py-1.5"
              >
                {errorMessage}
              </p>
            )}
            <button
              type="submit"
              className="w-full rounded-md bg-[var(--kwabo-navy)] px-4 py-2 text-sm font-medium text-white transition hover:bg-[var(--kwabo-navy-500)] disabled:opacity-50"
            >
              Inloggen
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
