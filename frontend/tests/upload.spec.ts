import { expect } from "@playwright/test";
import {test, resetEnv, login } from "./helpers";
import { promises as fs } from "fs";
import * as path from "path";

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await login(context);
});

test("upload .eml verschijnt in queue", async ({ page }) => {
  await page.goto("/?filter=all");

  // Tel alleen echte orderregels (de empty-state <tr> heeft geen order-link).
  const orderRows = page.locator('table tbody tr:has(a[href^="/orders/"])');
  const before = await orderRows.count();

  // Lees fixture en prepend een unieke header zodat email_id (hash van de bytes)
  // anders is dan eventuele eerdere runs in dezelfde backend-sessie. Zo tellen we
  // met zekerheid een NIEUWE row, ook wanneer resetEnv de gelockte SQLite-file
  // op Windows niet kan verwijderen.
  const fixture = path.resolve(
    __dirname,
    "fixtures/Ferney inkooporder 4200056148.eml",
  );
  const original = await fs.readFile(fixture);
  const unique = Buffer.concat([
    Buffer.from(`X-Kwabo-Test-Run: ${Date.now()}-${Math.random()}\r\n`),
    original,
  ]);

  await page.locator('[data-testid="eml-upload-input"]').setInputFiles({
    name: "ferney-upload.eml",
    mimeType: "message/rfc822",
    buffer: unique,
  });

  // Na succesvolle upload triggert onDone() window.location.reload().
  // Wachten tot de nieuwe rij verschijnt.
  await expect(orderRows).toHaveCount(before + 1, { timeout: 30_000 });
});
