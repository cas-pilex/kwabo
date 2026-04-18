// Build de frontend met NEXT_PUBLIC_API_BASE gericht op de e2e backend.
// Cross-platform vervanging voor `NEXT_PUBLIC_API_BASE=... next build`.
import { spawnSync } from "node:child_process";

const backendPort = process.env.BACKEND_PORT ?? "8100";
const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? `http://localhost:${backendPort}`;

const res = spawnSync("next", ["build"], {
  stdio: "inherit",
  shell: true,
  env: { ...process.env, NEXT_PUBLIC_API_BASE: apiBase },
});

process.exit(res.status ?? 1);
