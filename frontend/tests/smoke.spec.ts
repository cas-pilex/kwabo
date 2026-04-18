import { expect } from "@playwright/test";
import { test, resetEnv, dropEml, BACKEND } from "./helpers";

test.beforeEach(async () => {
  await resetEnv();
});

test("queue toont 3 orders na scan", async ({ page, request }) => {
  await dropEml("Ferney inkooporder 4200056148.eml");
  await dropEml("Bestelling 4506782407 157.eml");
  await dropEml("Inkooporder 00176482.eml");

  const r = await request.post(`${BACKEND}/api/intake/scan`);
  expect(r.ok()).toBeTruthy();
  const body = await r.json();
  expect(body.processed?.length ?? 0).toBeGreaterThanOrEqual(3);

  await page.goto("/?filter=all");
  await expect(page.locator("table tbody tr")).toHaveCount(3, { timeout: 15_000 });
});

test("approve -> Navision push -> status pushed", async ({ page, request }) => {
  await dropEml("Ferney inkooporder 4200056148.eml");
  const r = await request.post(`${BACKEND}/api/intake/scan`);
  expect(r.ok()).toBeTruthy();
  const body = (await r.json()) as { processed: Array<{ log_id: number }> };
  const logId = body.processed?.[0]?.log_id;
  expect(logId).toBeTruthy();

  // navigeer direct naar de net gescande order
  await page.goto(`/orders/${logId}`);

  // "Goedkeuren & Push Navision" button
  const approveBtn = page.getByRole("button", { name: /goedkeur/i });

  // Als er missing-velden zijn, arm Force approve checkbox (gekoppeld aan label "Force approve")
  const enabled = await approveBtn.isEnabled().catch(() => false);
  if (!enabled) {
    const forceCheckbox = page.getByLabel(/Force approve/i);
    await forceCheckbox.check();
  }

  await expect(approveBtn).toBeEnabled({ timeout: 5_000 });
  await approveBtn.click();

  // Wait for success-message "✓ Gepusht naar Navision" OR status badge "pushed"
  await expect(page.locator('text=/pushed|Gepusht/i').first()).toBeVisible({ timeout: 20_000 });
});
