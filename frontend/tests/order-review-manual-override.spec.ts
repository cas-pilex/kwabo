import { expect } from "@playwright/test";
import { promises as fs } from "fs";
import * as path from "path";
import { test, resetEnv, BACKEND } from "./helpers";

/**
 * M1 (Fase 2): een handmatige override moet de rode review-status DIRECT
 * wissen, zonder handmatige pagina-reload.
 *
 * Faalgeval Van Dongen (prod #721): reviewer vulde het klantnr in, de
 * NAV-operaties kregen de juiste waarde, maar de ONTBREEKT-badge en het
 * "niet gematcht"-pilletje bleven staan. Oorzaak: patch() ververst alleen
 * `missing` + previewKey; alle badges renderen uit initialState dat nooit
 * opnieuw van de server wordt gehaald.
 *
 * Seeding: échte order-states uit backend/tests/test_data/states/ via het
 * test-mode endpoint /api/testing/seed-order (geen LLM nodig).
 */

const STATES = path.resolve(__dirname, "../../backend/tests/test_data/states");

test.beforeEach(async ({ context }) => {
  await resetEnv();
  // De middleware checkt alleen het BESTAAN van het kwabo_admin-cookie;
  // validatie gebeurt backend-side en de e2e-backend draait zonder
  // ADMIN_PASSWORD (require_admin is dan open).
  await context.addCookies([
    { name: "kwabo_admin", value: "e2e", url: "http://localhost:3100" },
  ]);
});

async function seedFromState(
  request: import("@playwright/test").APIRequestContext,
  prefix: string,
): Promise<number> {
  const files = await fs.readdir(STATES);
  const file = files.find((f) => f.startsWith(prefix));
  expect(file, `fixture ${prefix}* moet bestaan — draai export_order_states.py`).toBeTruthy();
  const env = JSON.parse(await fs.readFile(path.join(STATES, file!), "utf-8"));
  const r = await request.post(`${BACKEND}/api/testing/seed-order`, {
    data: {
      order_state: env.order_state,
      email_from: env.email_from,
      email_subject: env.email_subject,
      status: "review",
    },
  });
  expect(r.ok(), `seed-order should succeed (got ${r.status()})`).toBeTruthy();
  const { id } = (await r.json()) as { id: number };
  return id;
}

async function patchField(
  request: import("@playwright/test").APIRequestContext,
  orderId: number,
  path_: string,
  value: unknown,
) {
  const r = await request.patch(
    `${BACKEND}/api/orders/${orderId}/patch-field`,
    {
      data: { path: path_, value, reviewer: "e2e" },
      headers: { "Content-Type": "application/json" },
    },
  );
  expect(r.ok(), `PATCH ${path_} should succeed (got ${r.status()})`).toBeTruthy();
}

test("klantnr handmatig invullen: naam + badge verversen zonder reload", async ({
  page,
  request,
}) => {
  // Echte Witzand-order #718: klant kwam ongematcht binnen.
  const orderId = await seedFromState(request, "order_718");

  await page.goto(`/orders/${orderId}`);

  // Rode uitgangssituatie: geen klantnaam, ONTBREEKT-badge bij het veld.
  await expect(page.locator("#klant_match")).toBeVisible();
  await expect(page.getByTestId("klant-naam")).toHaveCount(0);
  const klantVeld = page.locator('label[for="klant_match"]').locator("xpath=..");
  await expect(klantVeld.getByText("ONTBREEKT")).toBeVisible();

  // Handmatige override via de UI (debounced PATCH na 400ms). 10001 is de
  // demo-seed-klant zodat de naam-verrijking iets te tonen heeft.
  await page.locator("#klant_match").fill("10001");
  await page.waitForResponse(
    (r) => r.url().includes("/patch-field") && r.ok(),
  );

  // ZONDER reload: de klantnaam verschijnt (kan alleen via een verse
  // server-render) en de ONTBREEKT-badge is weg.
  await expect(page.getByTestId("klant-naam")).toHaveText(
    "Ferney Diabolo B.V.",
    { timeout: 10_000 },
  );
  await expect(klantVeld.getByText("ONTBREEKT")).toHaveCount(0);
});

test("kwabo-artnr handmatig invullen: 'niet gematcht'-pil verdwijnt zonder reload", async ({
  page,
  request,
}) => {
  // Echte Van Dongen-order #721 — maak de regel eerst weer ongematcht,
  // zoals hij oorspronkelijk binnenkwam.
  const orderId = await seedFromState(request, "order_721");
  await patchField(request, orderId, "orderregels[0].artikelnummer_kwabo_matched", "");

  await page.goto(`/orders/${orderId}`);

  // exact: true — anders matcht dit ook de samenvattingsregel
  // "Niet gematcht: N regel(s)" (getByText is case-insensitief).
  const pil = page.getByText("niet gematcht", { exact: true });
  await expect(pil.first()).toBeVisible();

  // Rij openklappen en het Kwabo-artnr handmatig invullen (de échte fix
  // die de reviewer destijds deed: 228321). Retry tegen de hydration-race:
  // een klik vóór React de handlers koppelt is een no-op.
  const input = page.locator('[id="orderregels[0].artikelnummer_kwabo_matched"]');
  await expect(async () => {
    await page.getByRole("button", { name: "Alles open" }).click();
    await expect(input).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
  await input.fill("228321");
  await page.waitForResponse(
    (r) => r.url().includes("/patch-field") && r.ok(),
  );

  // ZONDER reload: pil weg.
  await expect(page.getByText("niet gematcht", { exact: true })).toHaveCount(0, {
    timeout: 10_000,
  });
});
