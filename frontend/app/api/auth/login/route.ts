import { NextRequest, NextResponse } from "next/server";

// Vercel-side login route. Accepts BOTH:
//   - JSON body  (legacy fetch path; keeps test/curl simple)
//   - form-encoded body (HTML form posts; most robust path because
//     the cookie + redirect are a single atomic HTTP response — no
//     JS redirect race after the fetch resolves)
//
// The HTML form path is what the /login page now uses. It returns
// 303 See Other with Set-Cookie, so the browser commits the cookie
// and follows the redirect in one go. Middleware on the next page
// load sees the cookie deterministically. Earlier attempts using
// `document.cookie` and JS redirect raced against navigation in some
// browsers and produced the loop.

const RAILWAY_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";


async function readPassword(req: NextRequest): Promise<{
  password: string;
  isForm: boolean;
} | null> {
  const ct = (req.headers.get("content-type") || "").toLowerCase();
  if (ct.startsWith("application/json")) {
    try {
      const body = await req.json();
      return { password: String(body.password ?? ""), isForm: false };
    } catch {
      return null;
    }
  }
  // Default: form-encoded or multipart. NextRequest.formData handles both.
  try {
    const form = await req.formData();
    const value = form.get("password");
    return { password: String(value ?? ""), isForm: true };
  } catch {
    return null;
  }
}

function setAuthCookie(res: NextResponse, token: string, ttlSeconds: number) {
  // Cookie on Vercel domain. SameSite=Lax + Secure is right for a
  // first-party SPA on HTTPS. NOT HttpOnly: the browser SPA needs to
  // read the value to forward as Authorization: Bearer to Railway
  // (different origin). Trade-off accepted: short-lived token, single
  // admin model, XSS exposure is bounded.
  res.cookies.set({
    name: "kwabo_admin",
    value: token,
    path: "/",
    maxAge: ttlSeconds,
    sameSite: "lax",
    secure: true,
    httpOnly: false,
  });
}


export async function POST(req: NextRequest) {
  const parsed = await readPassword(req);
  if (!parsed) {
    return NextResponse.json({ error: "bad-request" }, { status: 400 });
  }
  const { password, isForm } = parsed;

  const upstream = await fetch(`${RAILWAY_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

  const data = await upstream.json().catch(() => ({}));

  if (upstream.status === 401) {
    if (isForm) {
      // Bounce back to login with a flag so the page renders an error.
      const url = new URL("/login?err=1", req.url);
      return NextResponse.redirect(url, 303);
    }
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!upstream.ok) {
    if (isForm) {
      const url = new URL("/login?err=upstream", req.url);
      return NextResponse.redirect(url, 303);
    }
    return NextResponse.json(
      { error: "upstream-failed", status: upstream.status },
      { status: 502 },
    );
  }

  const token: string | undefined = data.token;
  const expiresAt: number | undefined = data.expires_at;
  if (!token) {
    if (isForm) {
      const url = new URL("/login?err=no-token", req.url);
      return NextResponse.redirect(url, 303);
    }
    return NextResponse.json({ error: "no-token" }, { status: 502 });
  }

  const ttlSeconds = expiresAt
    ? Math.max(60, expiresAt - Math.floor(Date.now() / 1000))
    : 86400;

  if (isForm) {
    // 303 + Set-Cookie in one response. Browser commits the cookie and
    // follows the redirect — no JS, no race.
    const url = new URL("/", req.url);
    const res = NextResponse.redirect(url, 303);
    setAuthCookie(res, token, ttlSeconds);
    return res;
  }

  const res = NextResponse.json({ ok: true });
  setAuthCookie(res, token, ttlSeconds);
  return res;
}
