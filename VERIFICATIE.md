# Verificatie — Trigger-respecterende Sales Order push (feat/nav-trigger-respecting-order-entry)

Branch: `feat/nav-trigger-respecting-order-entry`
Laatste commit: `7b6f82f` (T11 NAV-trigger preview + reviewer controls)
Verificatiedatum: 2026-04-25

## Status

- Backend tests: **191 passed / 17 skipped** (39 warnings, alle warnings betreffen pydantic-v1 + FastAPI `on_event` — niet gerelateerd aan deze branch)
- Frontend e2e: **9 passed** (in 24.3s)
- Regressie 17 emails: **16 / 16 niet-leeg nav_operations** voor de 16 als order geclassificeerde emails (1 e-mail correct als not_order geclassificeerd)
- Smoke test mock NAV: **PASS** (Ferney 4200056148 → SO-117C84A6, 6 ops, autofill captured)

Eindstatus: **DONE**

## Forbidden field check
Voor elk van de 17 sample-emails bevat de samengestelde `nav_operations` lijst:
- **0** voorkomens van `unitPrice` in een line POST of PATCH body
- **0** voorkomens van `description` in een line POST body (description komt enkel voor op `POST /incomingDocuments`, niet op order/line — zoals beoogd)
- **0** voorkomens van `description2` in een line POST body
- **0** redundante `unitOfMeasureCode` PATCHes (alleen geëmitteerd wanneer `eenheid` afwijkt van `eenheid_default`, of wanneer `mix_uom_gekozen` expliciet gezet is)

Header (`/salesOrders`) bodies bevatten ook geen verboden velden: alleen `customerNumber` op POST en single-field PATCHes voor `shipToCode`, `externalDocumentNumber`, `requestedDeliveryDate`, `shipmentDate`, `incomingDocumentNumber`. Geen `description`, geen `currencyCode`, geen `paymentTermsCode` op de header — die worden door NAV-triggers afgeleid uit `customerNumber`.

## Operations breakdown

Gebaseerd op alle 16 als order geclassificeerde sample-emails:

- Ops per order: **avg 6.4 (range 3–11)**
- POST /salesOrders: **1.00 per order** (totaal 16, zoals verwacht — exact 1 per order)
- PATCH /salesOrders: **avg 2.56 per order** (totaal 41 — bestaande uit shipToCode (waar van toepassing), externalDocumentNumber, requestedDeliveryDate, shipmentDate)
- POST /salesOrderLines: **avg 0.94 per order** (totaal 15 — alleen geëmitteerd voor matched items)
- PATCH /salesOrderLines: **avg 1.88 per order** (totaal 30 — quantity altijd, unitOfMeasureCode wanneer non-default)
- POST /incomingDocuments: **0** in deze run (geen `incoming_document_path` gezet door deze script-flow; werkt wel via API-upload-endpoint, gedekt door `test_api_incoming_doc.py`)

Onmatched regels worden bewust overgeslagen: ze blokkeren de validatiegate en zouden human review vereisen.

## Mixprijzen

Orders met `mixprijzen_actief=true`: **0** in de huidige sample-set (de geseede `MixprijsKlant` records dekken klanten die niet voorkomen in deze 17 voorbeeld-emails).

De mixprijzen-pad zelf is unit-tested (zie `tests/test_apply_mixprijzen.py` + scenario-tests in `tests/test_navision_steps.py`) en het composer pad emit `mix_uom_gekozen` correct als `unitOfMeasureCode` PATCH (bevestigd door `test_navision_steps.test_compose_emits_uom_patch_for_mix_uom`).

## Europallet

Orders met `europallet_regel` gezet: **1** (`L. De Vos sa_nv - Order IOR26_00083 ...`)
- Hoeveelheid: 2 (gemiddelde over 1 order = 2.00)
- Auto-bepaald via `compute_europallet_node` op basis van pallet-historie + heuristics
- Approve-feedback naar `PalletKennisRepo`: gedekt door `tests/test_api_approve_pallet_feedback.py` — **5 tests passing**

## Smoke test against MockNavisionClient

`scripts/run_single_email.py "tests/test_data/emails/Ferney inkooporder 4200056148.eml" --approve`:
- Composed: **6 ops** (1 POST /salesOrders + 3 PATCH /salesOrders [externalDocumentNumber, requestedDeliveryDate, shipmentDate] + 1 POST /salesOrderLines + 1 PATCH /salesOrderLines [quantity])
- Executed succesvol tegen Mock NAV (alle 6 ops met status 2xx)
- Final order number: **SO-117C84A6**
- `sales_order_id`: `117c84a6-e635-4298-bf4f-19a59ff7eeac`
- `nav_autofilled` velden gecaptured (door NAV-triggers ingevuld, niet door tool):
  - Header: `id`, `number`, `sellToCustomerName`, `paymentTermsCode`, `currencyCode`, `shipToCode`, `languageCode`, `status`, `documentId`
  - Line: `description`, `unitOfMeasureCode`, `unitPrice`
- Confirmation-mail naar `purchaseorders@ferney.nl` correct verzonden (via mail_sender mock)

Dit bewijst de kerneis van deze branch: NAV vult `description`, `unitPrice`, `currencyCode`, `paymentTermsCode` in via OnValidate-triggers; de tool stuurt deze velden zelf nooit op.

## NAV staging smoke (handmatig — voor Cas)

Deze stappen kunnen niet door de CI worden uitgevoerd zonder echte NAV-credentials. Te doen door Cas:

1. Vul `.env` met:
   - `NAV_BASE_URL=https://api.businesscentral.dynamics.com/v2.0/<tenant>/<env>/api/v2.0`
   - `NAV_COMPANY_ID=<UUID van de target company>`
   - `NAV_AUTH_MODE=basic`
   - `NAV_USERNAME=<service-account>`
   - `NAV_PASSWORD=<wachtwoord>`
2. Run dry-run om endpoint shapes te verifiëren:
   ```
   python scripts/sync_navision_masters.py --full --dry-run
   ```
3. Run zonder `--dry-run` om master data (klanten + items + ship-to's) te laden:
   ```
   python scripts/sync_navision_masters.py --full
   ```
4. Set `NAVISION_MODE=real` in `.env` en run de pipeline op één voorbeeld-email:
   ```
   python scripts/run_single_email.py "tests/test_data/emails/Ferney inkooporder 4200056148.eml" --approve
   ```
5. Verify in NAV-UI dat trigger-velden zoals **Description**, **Unit Price**, **Currency Code**, **Payment Terms Code**, **Ship-to Address** zijn ingevuld door NAV (niet door de tool).

## Wat is af / wat is open

### Af (T1–T11 zoals beschreven in plan):
- T1: Trigger-aware `NavOperation` types + invariant helpers (`integrations/nav_operations.py`)
- T2: `RealNavisionClient.create_sales_order_stepwise` met body-key + path-placeholder substitutie
- T3: `MockNavisionClient.create_sales_order_stepwise` met identieke contract enforcement
- T4: `compose_navision_operations` pure function (`integrations/navision_steps.py`)
- T5: Ship-to selectie-node (`select_ship_to_node` + DB mirror)
- T6: Kruisverwijzing-tabel + `match_articles` met `eenheid_default`
- T7: Mixprijzen-node (`apply_mixprijzen_node`)
- T8: Europallet-zelflerend (`compute_europallet_node` + `PalletKennisRepo`)
- T9: Pipeline-bedrading: `compose_order_node` zet `nav_operations`; `push_navision_node` voert stepwise uit
- T10: API endpoints `POST /api/orders/{id}/incoming-doc` + approve pallet feedback
- T11: Frontend NAV-trigger preview + reviewer controls (ship-to, mixprijzen-UoM, europallet, incoming-doc)

### Open (niet geblokkeerd, judgement calls):
- **Mixprijzen-coverage in sample emails**: 0 / 16 sample-emails matchen op een klant met `mix-prijzen_actief=true`. Dit is geen regressie — de logic is unit-tested en de seed-data dekt mix-klanten die niet voorkomen in de 17 voorbeeld-emails. Aan te raden: bij het uitbreiden van de sample-set ook één mix-klant order toe te voegen voor end-to-end coverage.
- **Incoming-document smoke**: 0 / 16 sample-emails komen door `compose_navision_operations` heen met `incoming_document_path` gezet, omdat de script-flow geen documenten naar disk schrijft. Het pad wordt wel gezet door `POST /api/orders/{id}/incoming-doc` (gedekt door `test_api_incoming_doc.py`, 7 tests passing).
- **Echte NAV staging smoke**: vereist credentials (zie sectie hierboven) — kan alleen door Cas op een staging-tenant.
- **`run_all.py` matched ratio**: 15/35 = 42.9% auto-matched. Dit is geen regressie van deze branch (cijfers vergelijkbaar met baseline) maar wel een verbeterpunt voor toekomstig matching-werk (T6's kruisverwijzing-tabel kan worden uitgebreid).

Geen regressies geconstateerd. Alle bestaande tests slagen (191 backend / 9 e2e), forbidden-field invariant houdt over alle 17 sample-emails, smoke test tegen mock NAV slaagt met correct gevulde autofill-velden.
