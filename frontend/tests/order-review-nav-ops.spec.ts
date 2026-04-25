import { expect } from "@playwright/test";
import { test, resetEnv, dropEml, BACKEND } from "./helpers";

test.beforeEach(async () => {
  await resetEnv();
});

/**
 * Seed an order via the file-drop pipeline and return its log_id.
 *
 * The fixture `Ferney inkooporder 4200056148.eml` reliably produces an
 * order in `review` status — we only need the row to exist; we patch the
 * T11-specific state slots (ship_to_kandidaten, mixprijzen_actief,
 * europallet_regel) directly via the PATCH-field endpoint.
 */
async function waitForBackend(
  request: import("@playwright/test").APIRequestContext,
): Promise<void> {
  const deadline = Date.now() + 30_000;
  let lastErr: unknown;
  while (Date.now() < deadline) {
    try {
      const r = await request.get(`${BACKEND}/docs`);
      if (r.ok()) return;
    } catch (e) {
      lastErr = e;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`backend never came up: ${String(lastErr)}`);
}

async function seedOrder(request: import("@playwright/test").APIRequestContext): Promise<number> {
  await waitForBackend(request);
  await dropEml("Ferney inkooporder 4200056148.eml");
  const r = await request.post(`${BACKEND}/api/intake/scan`);
  expect(r.ok()).toBeTruthy();
  const body = (await r.json()) as { processed: Array<{ log_id: number }> };
  const logId = body.processed?.[0]?.log_id;
  expect(logId, "scan should produce at least one order").toBeTruthy();
  return logId!;
}

async function patchField(
  request: import("@playwright/test").APIRequestContext,
  orderId: number,
  path: string,
  value: unknown,
) {
  const r = await request.patch(
    `${BACKEND}/api/orders/${orderId}/patch-field`,
    {
      data: { path, value, reviewer: "e2e" },
      headers: { "Content-Type": "application/json" },
    },
  );
  expect(r.ok(), `PATCH ${path} should succeed (got ${r.status()})`).toBeTruthy();
}

/**
 * Clear the cached nav_operations slot on an order. The preview endpoint
 * prefers `state["nav_operations"]` when present (filled by compose_order
 * during the pipeline run); after our T11-specific PATCHes we want it to
 * recompose on the fly so the seed values are reflected.
 */
async function clearNavOpsCache(
  request: import("@playwright/test").APIRequestContext,
  orderId: number,
) {
  await patchField(request, orderId, "nav_operations", []);
}

test("ship-to picker: multiple candidates -> select -> preview updates", async ({
  page,
  request,
}) => {
  const orderId = await seedOrder(request);

  // Seed two ship-to candidates so the picker renders.
  await patchField(request, orderId, "ship_to_kandidaten", [
    {
      klant_nr: "10001",
      ship_to_code: "ALPHA",
      naam: "Alpha BV",
      straat: "Hoofdstraat 1",
      postcode: "1011AA",
      plaats: "Amsterdam",
      land: "NL",
      is_default: true,
    },
    {
      klant_nr: "10001",
      ship_to_code: "BETA",
      naam: "Beta BV",
      straat: "Marktplein 2",
      postcode: "3011AB",
      plaats: "Rotterdam",
      land: "NL",
      is_default: false,
    },
  ]);
  await patchField(request, orderId, "ship_to_gekozen", null);
  await clearNavOpsCache(request, orderId);

  await page.goto(`/orders/${orderId}`);

  const picker = page.getByTestId("ship-to-picker");
  await expect(picker).toBeVisible();

  const select = page.getByTestId("ship-to-select");
  await expect(select).toBeVisible();
  await select.selectOption("BETA");

  // After selection the preview should refresh to include a shipToCode op.
  // The picker fires PATCH ship_to_gekozen, the parent bumps refreshKey,
  // the NavOperationsPreview re-fetches.
  await expect(
    page
      .getByTestId("nav-operations-preview")
      .locator("text=/Ship-to Code BETA/i"),
  ).toBeVisible({ timeout: 10_000 });
});

test("mixprijzen badge: visible when mixprijzen_actief", async ({
  page,
  request,
}) => {
  const orderId = await seedOrder(request);

  // Read state to find any regel index.
  const detail = await request
    .get(`${BACKEND}/api/orders/${orderId}`)
    .then((r) => r.json());
  const regels = detail.order_state.orderregels || [];
  expect(regels.length, "fixture should produce >=1 regel").toBeGreaterThan(0);

  await patchField(request, orderId, "mixprijzen_actief", true);
  await patchField(request, orderId, "orderregels[0].mix_uom_kandidaat", [
    "STUK",
    "DOOS",
  ]);
  await patchField(request, orderId, "orderregels[0].mix_uom_gekozen", null);

  await page.goto(`/orders/${orderId}`);

  await expect(page.getByTestId("mix-badges-row")).toBeVisible();
  await expect(page.getByTestId("mix-badge-0")).toBeVisible();
  await expect(page.getByTestId("mix-badge-0")).toContainText(/Mix-UOM kiezen|Mix:/);
});

test("europallet editor: add then verwijderen removes pallet from preview", async ({
  page,
  request,
}) => {
  const orderId = await seedOrder(request);

  // Start with a europallet so we can verify removal end-to-end.
  await patchField(request, orderId, "europallet_regel", {
    kwabo_artikelnr: "19820",
    hoeveelheid: 2,
    eenheid: "STUK",
  });
  await clearNavOpsCache(request, orderId);

  await page.goto(`/orders/${orderId}`);

  const editor = page.getByTestId("europallet-editor");
  await expect(editor).toBeVisible();

  // Preview should mention the europallet line.
  await expect(
    page
      .getByTestId("nav-operations-preview")
      .locator("text=/Europallet|19820/i")
      .first(),
  ).toBeVisible({ timeout: 10_000 });

  // Click Verwijderen — editor collapses to "+ Voeg europallet toe".
  await page.getByTestId("europallet-remove").click();
  await expect(page.getByTestId("europallet-add")).toBeVisible({ timeout: 10_000 });

  // Preview no longer shows an Europallet op.
  await expect(
    page.getByTestId("nav-operations-preview").locator("text=/Europallet/i"),
  ).toHaveCount(0, { timeout: 10_000 });
});
