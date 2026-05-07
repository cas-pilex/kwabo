import { NextRequest, NextResponse } from "next/server";

// Diagnostic-only endpoint. Returns whatever the Vercel edge sees in
// the request: cookies, headers, and the result of asking Railway who
// the user is. Used to debug the login redirect loop without needing
// the user to share a real password — they log in normally, then
// open /api/whoami and paste what it returns.
//
// Safe to leave in production: it returns no secrets (env vars are
// excluded; tokens are masked).

const RAILWAY_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function mask(value: string | undefined): string {
  if (!value) return "<absent>";
  if (value.length <= 12) return value[0] + "…(" + value.length + ")";
  return value.slice(0, 6) + "…" + value.slice(-4) + "(" + value.length + ")";
}

export async function GET(req: NextRequest) {
  const cookieToken = req.cookies.get("kwabo_admin")?.value ?? null;

  // Try to validate the cookie against the Railway backend.
  let backend: unknown = null;
  if (cookieToken) {
    try {
      const upstream = await fetch(`${RAILWAY_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${cookieToken}` },
      });
      const body = await upstream.text();
      backend = {
        status: upstream.status,
        body: body.slice(0, 500),
      };
    } catch (e) {
      backend = { error: String(e).slice(0, 300) };
    }
  }

  return NextResponse.json({
    cookies_present: req.cookies.getAll().map((c) => c.name),
    kwabo_admin_token: mask(cookieToken ?? undefined),
    backend_me: backend,
    railway_base: RAILWAY_BASE,
    user_agent: req.headers.get("user-agent")?.slice(0, 80),
    host: req.headers.get("host"),
  });
}
