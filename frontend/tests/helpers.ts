import { test as base } from "@playwright/test";
import { promises as fs } from "fs";
import * as path from "path";

const INBOX = path.resolve(__dirname, "../../data/inbox_e2e");
const PROCESSED = path.resolve(__dirname, "../../data/processed_e2e");
const NAV_MOCK = path.resolve(__dirname, "../../data/navision_mock_e2e/orders");
const DB = path.resolve(__dirname, "../../backend/kwabo-e2e.db");
const FIX = path.resolve(__dirname, "fixtures");

async function rmrf(p: string) {
  try { await fs.rm(p, { recursive: true, force: true }); } catch {}
}

export const BACKEND = `http://localhost:${process.env.BACKEND_PORT ?? 8100}`;

export async function resetEnv() {
  // Filesystem: inbox + processed + navision mock
  await rmrf(INBOX);   await fs.mkdir(INBOX, { recursive: true });
  await rmrf(PROCESSED); await fs.mkdir(PROCESSED, { recursive: true });
  await rmrf(NAV_MOCK); await fs.mkdir(NAV_MOCK, { recursive: true });
  // DB: via backend endpoint (avoids Windows SQLite file-lock issue)
  try {
    const r = await fetch(`${BACKEND}/api/testing/reset`, { method: "POST" });
    if (!r.ok) {
      // Endpoint may not be mounted on first call (backend still starting); swallow
      console.warn(`reset endpoint returned HTTP ${r.status}`);
    }
  } catch (e) {
    // Backend may not be ready yet on very first run — tolerable
    console.warn("reset endpoint unreachable:", e);
  }
  // Also drop the SQLite file if possible (best-effort for fully-clean runs)
  await rmrf(DB);
}

export async function dropEml(name: string) {
  await fs.copyFile(path.join(FIX, name), path.join(INBOX, name));
}

export const test = base.extend({});

// Auth (31-05): het dashboard zit achter het kwabo_admin-cookie; de e2e-backend
// draait zonder ADMIN_PASSWORD dus elke waarde volstaat. Specs van vóór de
// auth-introductie misten dit en strandden op de /login-redirect (lege tabel).
export async function login(context: import("@playwright/test").BrowserContext) {
  await context.addCookies([
    { name: "kwabo_admin", value: "e2e", url: `http://localhost:${process.env.FRONTEND_PORT ?? 3100}` },
  ]);
}
