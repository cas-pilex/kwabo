import { expect } from "@playwright/test";
import {test, resetEnv, BACKEND, login } from "./helpers";
import { promises as fs } from "fs";
import * as path from "path";

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await login(context);
});

test("forwarded email matcht originele klant (Kirchner)", async ({ page, request }) => {
  // Drop Kirchner forward into inbox_e2e (with unique hash via filename timestamp)
  const src = path.resolve(__dirname, "fixtures/kirchner-forward.eml");
  const dst = path.resolve(__dirname, "../../data/inbox_e2e/kirchner-forward-" + Date.now() + ".eml");
  await fs.copyFile(src, dst);

  const r = await request.post(`${BACKEND}/api/intake/scan`);
  expect(r.ok()).toBeTruthy();

  await page.goto("/");
  // Wait for at least 1 order in queue
  await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 15_000 });
  await page.locator("table tbody tr").first().click();

  // On detail page: body should mention Kirchner (not just a Kwabo medewerker)
  await expect(page.locator("body")).toContainText(/kirchner/i, { timeout: 15_000 });
});
