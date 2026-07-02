import { expect } from "@playwright/test";
import {test, resetEnv, login } from "./helpers";

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await login(context);
});

test("prijsafspraken CRUD op klant-detail", async ({ page }) => {
  await page.goto("/klanten/10001");

  // Tab kan ARIA-tab zijn, button-met-tekst, of direct zichtbaar. Probeer ARIA eerst.
  const tabLocator = page.getByRole("tab", { name: /prijsafspraken/i });
  const buttonLocator = page.getByRole("button", { name: /prijsafspraken/i });
  if (await tabLocator.count()) {
    await tabLocator.first().click();
  } else if (await buttonLocator.count()) {
    await buttonLocator.first().click();
  }
  // anders al direct zichtbaar

  await expect(page.locator('[data-testid="prijsafspraken-tab"]')).toBeVisible({ timeout: 10_000 });

  // Voeg toe
  const artnr = `E2E-${Date.now()}`;
  await page.locator('[data-testid="pa-artnr"]').fill(artnr);
  await page.locator('[data-testid="pa-prijs"]').fill("9.99");
  await page.locator('[data-testid="pa-add"]').click();

  await expect(page.locator(`[data-testid="pa-row-${artnr}"]`)).toBeVisible();

  // Verwijder
  await page.locator(`[data-testid="pa-del-${artnr}"]`).click();
  await expect(page.locator(`[data-testid="pa-row-${artnr}"]`)).toHaveCount(0, { timeout: 5_000 });
});
