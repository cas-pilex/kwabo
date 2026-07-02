import { expect } from "@playwright/test";
import { test, resetEnv, BACKEND } from "./helpers";

/**
 * Fase C (structurele upgrade) — Nico's werk in één oogopslag:
 *  C1a  match-reden permanent zichtbaar bij de klant-keuze
 *  C1b  eenheid-omrekening per regel ("→ NAV: 2 × PALLET")
 *  C1c  europallet-onderbouwing incl. NIET-meegetelde regels (onbekend)
 *  C1   adresrollen-chips (besteller ≠ aflever zichtbaar)
 *  C2b  kandidaten-picker met zoekveld
 *  C2d/C3b  vlaggen als geordende takenlijst ("N dingen te controleren")
 *  C3a  "✓ klaar"-badge in de orderlijst bij 0 vlaggen
 */

test.beforeEach(async ({ context }) => {
  await resetEnv();
  await context.addCookies([
    { name: "kwabo_admin", value: "e2e", url: "http://localhost:3100" },
  ]);
});

/** Synthetische maar realistische state (TABS-agent-patroon, #954/#845-mix). */
function rijkeState() {
  return {
    email_id: "e2e-fase-c",
    email_from: "TABS Supply Chain <supplychain@tabsholland.nl>",
    email_subject: "Bestelling 4506877460 633",
    email_body: "",
    bijlagen: [],
    is_order: true,
    classificatie_confidence: 0.98,
    taal: "NL",
    bestelnummer_klant: "4506877460",
    klantnaam_besteller: "TABS Holland B.V.",
    klant_match: {
      navision_klantnr: "50094",
      klantnaam: "Jongeneel Woerden BA659",
      plaats: "WOERDEN",
      match_confidence: 0.9,
      match_bron: "leveradres_shipto",
      match_uitleg:
        "gedeelde mailbox — gekozen op leveradres 3449 JE WOERDEN via ship-to van 'Jongeneel Woerden BA659'",
    },
    adres_rollen: {
      besteller: { naam: "TABS Holland B.V.", postcode: "1500 GA", plaats: "Zaandam", land: "NL" },
      aflever: { naam: "Jongeneel Woerden BA659", postcode: "3449 JE", plaats: "WOERDEN", land: "NL" },
    },
    afleveradres: { naam: "Jongeneel Woerden BA659", straat: "Pijpenmakersweg 2", postcode: "3449 JE", plaats: "WOERDEN", land: "NL" },
    ship_to_gekozen: "3449 JE",
    orderregels: [
      {
        positie: 1,
        artikelnummer_klant: "228321",
        artikelnummer_kwabo: null,
        artikelnummer_kwabo_matched: "228321",
        omschrijving: "Stucloper 30 stuks",
        hoeveelheid: 30,
        eenheid: "STUK",
        eenheid_origineel: "STUK",
        verkoop_uom_gekozen: "PALLET",
        verkoop_aantal: 1,
        prijs_per_eenheid: null,
        prijs_validated: null,
        ean_code: null,
        leverdatum_regel: null,
        opmerkingen: null,
        match_methode: "exact_klantnr",
        match_confidence: 1.0,
      },
      {
        positie: 2,
        artikelnummer_klant: "MYST-1",
        artikelnummer_kwabo: null,
        artikelnummer_kwabo_matched: "88888",
        omschrijving: "Mysterie-artikel zonder palletdata",
        hoeveelheid: 10,
        eenheid: "STUK",
        eenheid_origineel: "STUK",
        prijs_per_eenheid: null,
        prijs_validated: null,
        ean_code: null,
        leverdatum_regel: null,
        opmerkingen: null,
        match_methode: "exact",
        match_confidence: 1.0,
      },
    ],
    europallet_regel: { kwabo_artikelnr: "19820", artikelnummer_kwabo: "19820", hoeveelheid: 1, eenheid: "STUK", positie: 3 },
    _meta: {
      klant_match: { value: "50094", source: "auto", confidence: 0.9, needs_review: true },
      europallet: {
        regels: [
          { artikelnr: "228321", qty: 30, eenheid: "STUK", bron: "uom_familie", pallet_maat: 30, pallets: 1 },
        ],
        totaal_pallets: 1,
        europallet_aantal: 1,
        uitleg: "1.0 pallets in order → 1 europallet (afgerond naar boven).",
        onbekend: [{ artikelnr: "88888", qty: 10, eenheid: "STUK" }],
      },
    },
    // Bewust in "verkeerde" volgorde: de banner moet klant eerst tonen.
    needs_review_fields: ["orderregels[0].eenheid", "europallet", "klant_match"],
    validatie_warnings: [],
    stappen_log: [],
  };
}

async function seed(
  request: import("@playwright/test").APIRequestContext,
  state: Record<string, unknown>,
): Promise<number> {
  const r = await request.post(`${BACKEND}/api/testing/seed-order`, {
    data: { order_state: state, status: "review" },
  });
  expect(r.ok(), `seed-order should succeed (got ${r.status()})`).toBeTruthy();
  const { id } = (await r.json()) as { id: number };
  return id;
}

test("C1a: match-reden staat permanent bij de klant (niet alleen in de bevestig-knop)", async ({ page, request }) => {
  const id = await seed(request, rijkeState());
  await page.goto(`/orders/${id}`);
  const reden = page.getByTestId("klant-match-reden");
  await expect(reden).toBeVisible();
  await expect(reden).toContainText("leveradres 3449 JE WOERDEN");
});

test("C1b: regel toont de NAV-omrekening (30 STUK → 1 × PALLET)", async ({ page, request }) => {
  const id = await seed(request, rijkeState());
  await page.goto(`/orders/${id}`);
  const badge = page.getByTestId("regel-nav-eenheid-1");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("1 × PALLET");
});

test("C1c: europallet-onderbouwing toont ook wat NIET meegeteld is", async ({ page, request }) => {
  const id = await seed(request, rijkeState());
  await page.goto(`/orders/${id}`);
  await expect(page.getByTestId("europallet-onderbouwing")).toBeVisible();
  const onbekend = page.getByTestId("europallet-onbekend");
  await expect(onbekend).toBeVisible();
  await expect(onbekend).toContainText("88888");
});

test("C1: adresrollen-chips maken besteller vs aflever zichtbaar", async ({ page, request }) => {
  const id = await seed(request, rijkeState());
  await page.goto(`/orders/${id}`);
  const rollen = page.getByTestId("adres-rollen");
  await expect(rollen).toBeVisible();
  // NB: de rol-labels zijn visueel uppercase via CSS; de DOM-tekst is lowercase.
  await expect(rollen).toContainText("besteller");
  await expect(rollen).toContainText("TABS Holland B.V.");
  await expect(rollen).toContainText("aflever");
  await expect(rollen).toContainText("WOERDEN");
});

test("C2d/C3b: vlaggen als geordende takenlijst — klant eerst", async ({ page, request }) => {
  const id = await seed(request, rijkeState());
  await page.goto(`/orders/${id}`);
  const lijst = page.getByTestId("review-takenlijst");
  await expect(lijst).toContainText("3 dingen te controleren");
  const knoppen = lijst.locator("button");
  // Seed-volgorde was [regel-eenheid, europallet, klant] — de banner sorteert.
  await expect(knoppen.nth(0)).toContainText("Klant");
  await expect(knoppen.nth(1)).toContainText("eenheid");
  await expect(knoppen.nth(2)).toContainText("europallet");
});

test("C2b: klant-kandidaten zijn doorzoekbaar", async ({ page, request }) => {
  const state = rijkeState();
  // Geen match, wél veel kandidaten -> picker met zoekveld.
  state.klant_match = undefined as never;
  (state as Record<string, unknown>).klant_kandidaten = [
    { navision_klantnr: "61468", klantnaam: "Pontmeyer Zoetermeer", plaats: "ZOETERMEER", score: 8, bron: "gedeelde_mailbox" },
    { navision_klantnr: "61019", klantnaam: "PontMeyer Heemstede", plaats: "HEEMSTEDE", score: 8, bron: "gedeelde_mailbox" },
    { navision_klantnr: "50094", klantnaam: "Jongeneel Woerden BA659", plaats: "WOERDEN", score: 10, bron: "gedeelde_mailbox" },
  ];
  state._meta = { ...(state._meta as Record<string, unknown>), klant_match: { value: null, source: "missing", confidence: 0, needs_review: true } } as never;
  const id = await seed(request, state);
  await page.goto(`/orders/${id}`);

  await expect(page.getByTestId("klant-picker")).toBeVisible();
  await expect(page.getByTestId("klant-select").locator("option")).toHaveCount(4); // 3 + placeholder
  await page.getByTestId("klant-zoek").fill("woerden");
  await expect(page.getByTestId("klant-select").locator("option")).toHaveCount(2); // 1 + placeholder
  await expect(page.getByTestId("klant-select")).toContainText("Jongeneel Woerden");
});

test("C3a: order zonder vlaggen krijgt '✓ klaar'-badge in de lijst", async ({ page, request }) => {
  const state = rijkeState();
  state.needs_review_fields = [];
  delete (state._meta as Record<string, unknown>).klant_match;
  const id = await seed(request, state);
  await page.goto(`/`);
  const badge = page.getByTestId(`klaar-badge-${id}`);
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("klaar");
});
