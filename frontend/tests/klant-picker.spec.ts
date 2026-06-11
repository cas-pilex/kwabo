import { expect } from "@playwright/test";
import { promises as fs } from "fs";
import * as path from "path";
import { test, resetEnv, BACKEND } from "./helpers";

/**
 * K3.3 (Fase 2): KlantPicker — als de naam-fallback meerdere kandidaten
 * vond (klant_kandidaten), toont het klant-blok een picker. Een keuze
 * patcht klant_match en de review-status ververst direct (geen reload).
 *
 * Seeding: echte GBI Borne-order #707 (zevij-portaal, klant ongematcht)
 * met de echte kandidaten die de naam-fallback voor 'GBI Borne' vindt.
 */

const STATES = path.resolve(__dirname, "../../backend/tests/test_data/states");

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await context.addCookies([
    { name: "kwabo_admin", value: "e2e", url: "http://localhost:3100" },
  ]);
});

async function seedGbiBorneMetKandidaten(
  request: import("@playwright/test").APIRequestContext,
): Promise<number> {
  const files = await fs.readdir(STATES);
  const file = files.find((f) => f.startsWith("order_707"));
  expect(file, "fixture order_707* moet bestaan").toBeTruthy();
  const env = JSON.parse(await fs.readFile(path.join(STATES, file!), "utf-8"));
  const state = env.order_state;
  // Wat match_customer's naam-fallback voor 'GBI Borne' aan kandidaten geeft
  // (echte klantnummers; in de e2e-DB staan alleen demo-kaarten, dus de
  // naam-verrijking blijft leeg — de test assert op het klantnr).
  state.klant_kandidaten = [
    { navision_klantnr: "61948", klantnaam: "GBI Borne", score: 100, bron: "naam_extract" },
    { navision_klantnr: "60704", klantnaam: "Probin Borne", score: 76.2, bron: "naam_extract" },
  ];
  const r = await request.post(`${BACKEND}/api/testing/seed-order`, {
    data: {
      order_state: state,
      email_from: env.email_from,
      email_subject: env.email_subject,
      status: "review",
    },
  });
  expect(r.ok(), `seed-order should succeed (got ${r.status()})`).toBeTruthy();
  const { id } = (await r.json()) as { id: number };
  return id;
}

test("klant-kandidaat kiezen: klantnr ingevuld + badge weg zonder reload", async ({
  page,
  request,
}) => {
  const orderId = await seedGbiBorneMetKandidaten(request);

  await page.goto(`/orders/${orderId}`);

  // Picker zichtbaar met beide kandidaten; klant nog ONTBREEKT.
  const picker = page.getByTestId("klant-picker");
  await expect(picker).toBeVisible();
  const klantVeld = page.locator('label[for="klant_match"]').locator("xpath=..");
  await expect(klantVeld.getByText("ONTBREEKT")).toBeVisible();

  const select = page.getByTestId("klant-select");
  await expect(select).toBeVisible();
  await select.selectOption("61948");

  await page.waitForResponse(
    (r) => r.url().includes("/patch-field") && r.ok(),
  );

  // Zonder reload: klantnr staat in het veld, badge weg, picker weg.
  await expect(page.locator("#klant_match")).toHaveValue("61948", {
    timeout: 10_000,
  });
  await expect(klantVeld.getByText("ONTBREEKT")).toHaveCount(0);
  await expect(page.getByTestId("klant-picker")).toHaveCount(0);
});
