import { NextResponse } from "next/server";

export async function POST() {
  const res = NextResponse.json({ ok: true });
  // Wipe the same cookie. Same attributes as in /login so the browser
  // recognises it as the cookie to overwrite.
  res.cookies.set({
    name: "kwabo_admin",
    value: "",
    path: "/",
    maxAge: 0,
    sameSite: "lax",
    secure: true,
    httpOnly: false,
  });
  return res;
}
