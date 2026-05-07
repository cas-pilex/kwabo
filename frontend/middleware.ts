import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set(["/login"]);

// Static assets, the favicon, and Next.js internals never need auth.
const PASS_THROUGH_PREFIXES = ["/_next/", "/favicon", "/kwabo-logo"];

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
  // middleware itself filters /login and asset paths above; this matcher
  // narrows the regex so we don't burn CPU on every static file request.
  matcher: ["/((?!_next/static|_next/image|favicon|.*\\..*).*)"],
};
