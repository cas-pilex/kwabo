import { NextRequest, NextResponse } from "next/server";

// Vercel-side login proxy. Why this exists:
// The original client-side `document.cookie = ...` after authLogin()
// raced with `window.location.href = "/"` — Next.js middleware on the
// new page-load sometimes saw the request before the cookie was
// committed, so it redirected back to /login → infinite loop.
//
// Setting the cookie via Set-Cookie header from a Vercel server
// function fixes the race: the browser commits the cookie BEFORE
// running the next navigation, atomically.
//
// The cookie is intentionally non-HttpOnly so the existing client
// fetches can still read the token from `document.cookie` and pass
// it as Authorization: Bearer to the Railway backend (which only
// accepts the Bearer header, not cookies, since it sits on a different
// origin). Trade-off accepted: short-lived (24h) HMAC token, not a
// password — XSS exposure is bounded and the token can't be promoted
// to elevated privileges (single-admin model).

const RAILWAY_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function POST(req: NextRequest) {
  let password: string;
  try {
    const body = await req.json();
    password = String(body.password ?? "");
  } catch {
    return NextResponse.json({ error: "bad-request" }, { status: 400 });
  }

  const upstream = await fetch(`${RAILWAY_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

  const data = await upstream.json().catch(() => ({}));

  if (upstream.status === 401) {
    return NextResponse.json(
      { error: "unauthorized" },
      { status: 401 },
    );
  }
  if (!upstream.ok) {
    return NextResponse.json(
      { error: "upstream-failed", status: upstream.status },
      { status: 502 },
    );
  }

  const token: string | undefined = data.token;
  const expiresAt: number | undefined = data.expires_at;
  if (!token) {
    return NextResponse.json({ error: "no-token" }, { status: 502 });
  }

  const ttlSeconds = expiresAt
    ? Math.max(60, expiresAt - Math.floor(Date.now() / 1000))
    : 86400;

  const res = NextResponse.json({ ok: true });
  // Cookie is on the Vercel domain. SameSite=Lax + Secure is the right
  // default for first-party SPAs hosted on HTTPS. NOT HttpOnly: the
  // browser SPA needs to read the value to forward it as Bearer to the
  // cross-origin Railway backend.
  res.cookies.set({
    name: "kwabo_admin",
    value: token,
    path: "/",
    maxAge: ttlSeconds,
    sameSite: "lax",
    secure: true,
    httpOnly: false,
  });
  return res;
}
