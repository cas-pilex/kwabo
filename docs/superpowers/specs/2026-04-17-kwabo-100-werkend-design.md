# Kwabo Order Intake — "100% werkend" design

**Datum:** 2026-04-17
**Scope:** C (smoketest-polish + 3 functionele high-prio fixes + polish-items)
**Buiten scope:** Real Navision API, IMAP/Graph mailbox, SharePoint import (vereisen credentials).

## Doel

De end-to-end flow `drop .eml → scan → queue → review → approve → Navision mock → audit` 100% betrouwbaar maken, met een geautomatiseerde test-harness die aantoont dat het 10× reproduceerbaar werkt zonder API-budget op te jagen.

Acceptatie:

- Alle bestaande pytest unit tests groen
- Nieuwe regressie-harness groen over 17 voorbeeld-emails (fixtures)
- `make test-10x` groen (regressie × 10)
- Playwright e2e groen (queue→approve, upload, prijsafspraken, forwarded)
- Handmatige rook-test (10 punten uit STATUS.md) groen

## Architectuur

Test-infrastructuur wordt eerst gebouwd (LLM cache + regressie-harness + Playwright), daarna fixes. Elke fix draait door de harness voor we "klaar" zeggen. Dit maakt de "10× tested" eis één commando in plaats van een uur handmatig klikken.

## Nieuwe componenten (infrastructuur)

### LLM response cache

- **Locatie:** `backend/src/kwabo/graph/llm_cache.py` + `data/llm_cache/*.json`
- **Sleutel:** SHA-256 van `{model, prompt_text, image_hashes, temperature, max_tokens}`
- **Bestand:** `data/llm_cache/{sha256}.json` met `{model, prompt_hash, response_text, ts, input_tokens, output_tokens}`
- **Flag:** `LLM_CACHE` env-var — `on` (default dev), `read-only`, `off`
- **Git:** `data/llm_cache/` in `.gitignore`
- **Foutafhandeling:** corrupt bestand → `try/except json.JSONDecodeError` → nieuwe API call, overschrijf
- **Reset:** `scripts/clear_llm_cache.py`
- **Integratie:** wrapper rond `get_llm()` in `graph/llm.py` zodat classify/extract transparant gecachet worden — nodes hoeven niet gewijzigd.

### Expected fixtures

- **Locatie:** `backend/tests/test_data/expected/{email_slug}.json`
- **Velden:** `is_order`, `klant_nr`, `bestelnr`, `taal`, `n_regels`, `matched_articles_min`, `sub_orders_count`, `warnings_subset`
- **Seeding:** eerste `pytest --update-fixtures` run schrijft fixtures; volgende runs vergelijken
- **Onderhoud:** bij bewuste wijziging → nieuwe run met `--update-fixtures` + committen

### Regressie-harness

- **Locatie:** `backend/tests/test_regression.py`
- **Pytest parametrize** over 17 .eml bestanden
- **Flow:** `runner.run_email(path)` → `state` → assert vs fixture
- **Assertions:** customer-match, n_regels, matched_ratio, sub_orders, warnings-subset
- **Runtime (cached):** < 30s voor 17 emails

### `make test-10x`

```makefile
test-10x:
	for i in 1 2 3 4 5 6 7 8 9 10; do \
	  echo "=== run $$i/10 ==="; \
	  pytest backend/tests/test_regression.py -x --tb=short || exit 1; \
	done
```

Windows-fallback: `scripts/test_10x.ps1` en `scripts/test_10x.sh`.

### Playwright smoke

- **Locatie:** `frontend/tests/smoke.spec.ts` + `playwright.config.ts`
- **webServer config:** Playwright `webServer: [backend, frontend]` — twee processen: `uvicorn kwabo.main:app --port $BACKEND_PORT` en `pnpm start --port $FRONTEND_PORT`. Beide met `reuseExistingServer: !process.env.CI`.
- **Tests (4):**
  1. queue → review → approve flow
  2. .eml upload knop
  3. prijsafspraken CRUD op klant-pagina
  4. forwarded-email toont juiste afzender
- **Fixtures:** 3 .eml bestanden in `frontend/tests/fixtures/`
- **Reset:** beforeEach wist `kwabo.db`, `data/inbox/`, `data/navision_mock/orders/`

## Fixes in scope

### 1. Seed-uitbreiding artikel-mappings

Voor alle 17 voorbeeld-emails alle voorkomende klant-artikelnummers toevoegen aan `ARTIKEL_MAPPING_SEED` in `backend/src/kwabo/db/seed.py` (gekoppeld aan dummy Kwabo-artikel `DUMMY-{klant_nr}-{klant_artnr}` als echte Kwabo-nr onbekend).

**Acceptatie:** harness `matched_articles_ratio ≥ 0.80` waarbij `matched_articles_ratio = (sum van auto-matched regels over alle 17 emails) / (sum van alle regels over alle 17 emails)`. Als het realistisch haalbare maximum op deze test-set lager ligt (afhankelijk van beschikbare seed-data), wordt de drempel verlaagd naar dat maximum en vastgelegd in een fixture-bestand `expected/_summary.json`.

### 2. Forwarded-parser verificatie

`forwarded_parser.py` is al geïmplementeerd. Uitbreiden `tests/test_forwarded_parser.py` met de 4 real-world forwards (Ivar/Mark/Nico mails). Harness-fixture voor die 4 emails moet de originele afzender matchen.

**Acceptatie:** 4 forwarded emails → juiste klant_nr (geen Kwabo-medewerker).

### 3. Kirchner multi-PDF regressie

Code is al geplumbed (extract.py + runner._run_extras). Harness-fixture voor Kirchner met `sub_orders_count ≥ 1`.

**Acceptatie:** Kirchner email → 1 parent + ≥1 sub-order in DB, beide met status `review`.

### 4. Dev-mode hydration

Onderzoek root-cause Turbopack+Windows. Werkstrategie:

1. Probeer `next dev --no-turbo` (Next 16 accepteert deze flag)
2. Als dat werkt: documenteer in README, geen code-wijziging nodig
3. Zo nee: Playwright blijft tegen `pnpm start` (prod-build) draaien; dev-mode blijft bekende issue met workaround in README

**Acceptatie:** README heeft werkend dev-commando of documenteert workaround helder.

### 5. Prijsafspraken-UI

Tab "Prijsafspraken" toevoegen aan `/klanten/[nr]/`, met:

- Lijst van prijsafspraken (GET `/api/prijsafspraken/{nr}/prijsafspraken`)
- "Toevoegen"-formulier (POST)
- Verwijderen-knop per rij (DELETE)
- "Excel importeren"-knop (POST `/import-excel`)

**Acceptatie:** Playwright CRUD test slaagt.

### 6. Email-upload knop

Op `/` (queue): knop "Upload .eml" → bestaande `POST /api/intake/upload` → refresh. Toast bij success/fail.

**Acceptatie:** Playwright upload-test slaagt; order verschijnt in queue.

### 7. Kredietlimiet-warning finaliseren

`match_customer.py:109` TODO: bij bekende klant-kredietlimiet-onderschrijding → warning in state. Schema-wijziging: kolom `kredietlimiet FLOAT NULL` toevoegen aan `Klantenkaart` (SQLModel); SQLite auto-migrate bij startup via `SQLModel.metadata.create_all()` (bestaand patroon — nieuwe NULL-kolom is backwards-compatible, geen data-migration nodig). In seed: enkele klanten krijgen een demo-limiet. Als `som(orderregels.prijs × hoeveelheid) > klant.kredietlimiet` → warning `kredietlimiet_overschreden`. Real-Nav integratie blijft toekomst.

**Acceptatie:** unit test: klant met limiet 100 + order 200 → warning.

### 8. Error-polish

- Toast-systeem (sonner of shadcn toast) voor API-failures
- Loading-spinner op approve/reject
- 404/error-pagina's
- Playwright sad-path: API 500 → toast zichtbaar

**Acceptatie:** manueel + Playwright.

## Data flow

### LLM cache

```
classify_node / extract_node
       │
       ▼
get_llm_cached(prompt, images?)
       │
       ├─ cache_key = sha256(model + prompt + image_hashes)
       │
       ├─ cache hit?  ──► return JSON uit data/llm_cache/{key}.json
       │
       └─ cache miss  ──► Anthropic API  ──► write {key}.json  ──► return
```

### Regressie-harness

```
pytest test_regression.py::test_email[{slug}]
        │
        ├─ load fixture JSON (expected)
        ├─ runner.run_email(email_path)   ◄─ LLM cached
        ├─ assert state.matched_customer.klant_nr == expected.klant_nr
        ├─ assert len(state.orderregels) == expected.n_regels
        ├─ assert matched_ratio >= expected.matched_articles_min
        ├─ assert expected.warnings_subset ⊆ state.warnings
        └─ assert sub_orders == expected.sub_orders_count
```

## Error handling

| Scenario | Behavior |
|---|---|
| LLM API 5xx / rate-limit | Bestaande exponential backoff (llm_extractor.py) — blijft |
| LLM returnt invalide JSON | Al afgehandeld in `json_parser.py`; harness assert `is_order in {True, False}` |
| Cache-bestand corrupt | `try/except json.JSONDecodeError` → nieuwe API call, overschrijf |
| Email onparsebaar | `intake_node` geeft `parse_error`; classify geskipt; harness verwacht `status=not_order` |
| Navision-mock push faalt | In-memory error → status blijft `review`, warning toegevoegd |
| Frontend API 500 | Toast "Actie mislukt — probeer opnieuw"; console error gelogd; Playwright sad-path |
| Hydration-failure in dev | Playwright draait tegen `pnpm start` (prod-build) — niet geraakt |

## Testplan ("10× alles werkt")

1. **Unit** — bestaande pytest (forwarded, prijscascade, eenheid, sanity, db, api, navision-mock, email-parsing) → moet groen blijven
2. **Regressie** — `pytest test_regression.py` over 17 emails
3. **10× regressie** — `make test-10x` faalt bij eerste afwijking
4. **Playwright e2e** — 4 flows
5. **Handmatige rook-test** — 10 punten uit STATUS.md (één keer)

## Directory-tree na afloop

```
backend/
  src/kwabo/graph/llm_cache.py           (nieuw)
  src/kwabo/db/seed.py                   (uitbreiden)
  src/kwabo/graph/nodes/match_customer.py (kredietlimiet-warning)
  scripts/clear_llm_cache.py             (nieuw)
  tests/test_regression.py               (nieuw)
  tests/test_data/expected/*.json        (nieuw, 17 files)
  tests/test_forwarded_parser.py         (uitbreiden)
  Makefile                               (nieuw)
  scripts/test_10x.sh                    (nieuw)
  scripts/test_10x.ps1                   (nieuw)
frontend/
  playwright.config.ts                   (nieuw)
  tests/smoke.spec.ts                    (nieuw)
  tests/fixtures/                        (nieuw, 3 .eml)
  app/klanten/[nr]/prijsafspraken-tab.tsx (nieuw)
  app/page.tsx                           (upload-knop)
  app/layout.tsx of components/toaster.tsx (toast-provider)
  next.config.ts                         (dev-flag of unchanged)
  package.json                           (playwright devDep + scripts)
data/
  llm_cache/                             (runtime, .gitignore)
docs/superpowers/specs/2026-04-17-kwabo-100-werkend-design.md (dit bestand)
```

## Niet in scope

- Real Navision API-integratie (vereist credentials)
- IMAP/Microsoft Graph mailbox (vereist credentials)
- SharePoint klantenkaart-import (vereist credentials)
- LangSmith tracing (optioneel, voor later)

## Risico's

1. **LLM cache hit op legitiem gewijzigde prompt** — gemitigeerd door prompt-text in hash. Bij prompt-tuning: cache mist → opnieuw → correct.
2. **Fixture-drift** — als seed-data of prompt significant wijzigt, moeten fixtures ook bijgewerkt met `--update-fixtures`. Onderdeel van PR-flow.
3. **Playwright op Windows** — webServer-spawn van uvicorn kan porten-conflict geven. Mitigatie: willekeurige poort (PLAYWRIGHT_PORT) + wait-for-ready.
4. **Artikel-match target 80%** — afhankelijk van hoeveel van de 17 emails daadwerkelijk matchbare items hebben. Als realistisch maximum lager is, acceptatie verlagen naar `max haalbaar op test-set`.
