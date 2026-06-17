import { expect } from "@playwright/test";
import { test, resetEnv, BACKEND } from "./helpers";

// FUNCTIE 7: de dedicated bron-document-banner. In mock-mode koppelt de pipeline
// het document wél, dus de skip-warning ontstaat niet vanzelf — we zaaien 'm via
// de test-only seed-order endpoint (row.warnings).

const BRON_DOC_WARNING =
  "Bron-document is NIET als inkomend document aan de NAV-order gekoppeld " +
  "(PLX_IncomingDocument niet beschikbaar in NAV 2018) — koppel het document " +
  "handmatig in Navision.";
const ANDERE_WARNING = "ARTIKEL ONZEKER regel 1: controleer het artikel.";

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await context.addCookies([
    { name: "kwabo_admin", value: "e2e", url: "http://localhost:3100" },
  ]);
});

async function seedOrderWithWarnings(
  request: import("@playwright/test").APIRequestContext,
  warnings: string[],
): Promise<number> {
  const r = await request.post(`${BACKEND}/api/testing/seed-order`, {
    data: {
      order_state: {
        email_id: "e2e-bron-doc",
        klant_match: { navision_klantnr: "10001", klantnaam: "Ferney Diabolo B.V." },
        orderregels: [{ artikelnummer_kwabo_matched: "1515155", hoeveelheid: 1 }],
      },
      email_subject: "Bestelling met bron-document",
      warnings,
    },
    headers: { "Content-Type": "application/json" },
  });
  expect(r.ok(), `seed-order should succeed (got ${r.status()})`).toBeTruthy();
  return (await r.json()).id as number;
}

test("bron-doc-warning -> dedicated banner met knop naar het paneel", async ({
  page,
  request,
}) => {
  const orderId = await seedOrderWithWarnings(request, [
    BRON_DOC_WARNING,
    ANDERE_WARNING,
  ]);

  await page.goto(`/orders/${orderId}`);

  const banner = page.getByTestId("source-doc-link-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("handmatig in Navision");
  await expect(banner.getByRole("button", { name: /bron-document/i })).toBeVisible();

  // De bron-doc-warning staat NIET dubbel in de generieke lijst...
  const generiek = page.getByTestId("order-warnings-banner");
  await expect(generiek).not.toContainText("Bron-document is NIET");
  // ...maar de overige warning wél.
  await expect(generiek).toContainText("ARTIKEL ONZEKER");

  // Het paneel waar de knop heen scrollt bestaat.
  await expect(page.locator("#incoming-document-panel")).toHaveCount(1);
});

test("geen bron-doc-warning -> geen dedicated banner", async ({ page, request }) => {
  const orderId = await seedOrderWithWarnings(request, [ANDERE_WARNING]);

  await page.goto(`/orders/${orderId}`);

  await expect(page.getByTestId("order-warnings-banner")).toBeVisible();
  await expect(page.getByTestId("source-doc-link-banner")).toHaveCount(0);
});
