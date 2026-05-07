import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set(["/login"]);

// Pass-through prefixes: never gate these. `/api/` covers our Next.js
// route handlers (login, logout proxy) which return JSON — redirecting
// a POST to /login would break the login flow entirely (which is what
// happened the first time around). Static assets and Next internals
// are also exempt.
const PASS_THROUGH_PREFIXES = [
  "/_next/",
  "/api/",
  "/favicon",
  "/kwabo-logo",
];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();
  if (PASS_THROUGH_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const token = req.cookies.get("kwabo_admin")?.value;
  if (!token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("from", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Match every route except static assets and Next.js internals. The
  // middleware itself filters /login, /api/* and asset paths above;
  // this matcher narrows the regex so we don't burn CPU on every
  // static file request.
  matcher: ["/((?!_next/static|_next/image|favicon|.*\\..*).*)"],
};
