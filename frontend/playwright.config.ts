import { defineConfig } from "@playwright/test";

const FRONTEND_PORT = Number(process.env.FRONTEND_PORT ?? 3100);
const BACKEND_PORT = Number(process.env.BACKEND_PORT ?? 8100);

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  fullyParallel: false, // file-drop + shared DB — moet sequentieel
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `python -m uvicorn kwabo.main:app --port ${BACKEND_PORT}`,
      cwd: "../backend",
      url: `http://localhost:${BACKEND_PORT}/docs`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: {
        PYTHONPATH: "src",
        DATABASE_URL: "sqlite:///./kwabo-e2e.db",
        NAVISION_MODE: "mock",
        EMAIL_MODE: "file_drop",
        INBOX_DIR: "../data/inbox_e2e",
        PROCESSED_DIR: "../data/processed_e2e",
        NAVISION_MOCK_DIR: "../data/navision_mock_e2e",
        LLM_CACHE_MODE: "on",
        LLM_CACHE_DIR: "../data/llm_cache",
        KWABO_CORS_EXTRA: `http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}`,
      },
    },
    {
      command: `pnpm start --port ${FRONTEND_PORT}`,
      cwd: ".",
      url: `http://localhost:${FRONTEND_PORT}`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_BASE: `http://localhost:${BACKEND_PORT}` },
    },
  ],
});
