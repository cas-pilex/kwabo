import { expect } from "@playwright/test";
import {test, resetEnv, login } from "./helpers";
import { promises as fs } from "fs";
import * as path from "path";

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await login(context);
});

test("upload van ongeldig bestand toont toast-error", async ({ page }) => {
  await page.goto("/");

  // Schrijf tijdelijk een niet-.eml bestand (backend wijst dit af met HTTP 400)
  const badFile = path.resolve(__dirname, "fixtures/bad-not-eml.txt");
  await fs.writeFile(badFile, "dit is geen email");

  try {
    // setInputFiles negeert het accept=".eml" attribuut en kan ook .txt selecteren
    await page.locator('[data-testid="eml-upload-input"]').setInputFiles(badFile);

    // Sonner rendert toasts als <li data-sonner-toast>
    await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({
      timeout: 10_000,
    });
  } finally {
    await fs.rm(badFile, { force: true });
  }
});
