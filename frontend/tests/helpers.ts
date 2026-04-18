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

export async function resetEnv() {
  await rmrf(INBOX);   await fs.mkdir(INBOX, { recursive: true });
  await rmrf(PROCESSED); await fs.mkdir(PROCESSED, { recursive: true });
  await rmrf(NAV_MOCK); await fs.mkdir(NAV_MOCK, { recursive: true });
  await rmrf(DB);
}

export async function dropEml(name: string) {
  await fs.copyFile(path.join(FIX, name), path.join(INBOX, name));
}

export const BACKEND = `http://localhost:${process.env.BACKEND_PORT ?? 8100}`;

export const test = base.extend({});
