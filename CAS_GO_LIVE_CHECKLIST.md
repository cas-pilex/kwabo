# Go-live checklist — wat alleen Cas nog kan invullen

Alles in de codebase wat zonder echte credentials gefixt kon worden, is gefixt:
de NAV-trigger-aware push-laag is af, alle 27 NAV-tests passen, de FastAPI
deprecation-warnings zijn weg, de stale email-stub-tests zijn aangepast op
het huidige (geïmplementeerde) gedrag, en de unescaped HTML-entities in het
dashboard zijn opgelost. Status van de codebase is daarmee: 215/215 tests
passen (de 17 skipped zijn integratie-tests die expliciet credentials
verwachten).

Wat hieronder staat zijn de stappen die alleen jij kan doen, omdat ze
externe systeemtoegang of fysieke configuratie vereisen.

## 1. Microsoft Graph mailbox aansluiten

**Doel:** orders die binnenkomen op `info@kwabo.nl` worden automatisch
opgehaald in plaats van handmatig via file-drop.

1. **Azure AD app-registratie** (eenmalig, ±5 min):
   - portal.azure.com → Azure Active Directory → App registrations → New
   - Naam: `Kwabo Order Intake`
   - Account types: Single tenant
   - Redirect URI (Web): `http://localhost:8000/api/mailbox/oauth/callback`
     (later vervangen door je productie-URL)
2. **API permissions** (delegated, Microsoft Graph):
   - `Mail.ReadWrite`
   - `User.Read`
   - `offline_access`
   - Klik **Grant admin consent**
3. **Client secret** aanmaken → kopieer de **Value** (niet de Secret ID)
4. **Tenant ID + Client ID** kopiëren uit Overview-pagina
5. In het dashboard: open `/email`, plak de drie waarden, klik
   **Config opslaan** en daarna **Connect with Microsoft**
6. In `.env`: zet `EMAIL_MODE=graph`

Het dashboard heeft een complete UI-walkthrough hiervoor (`/email` route),
inclusief screenshots.

## 2. Echte NAV 2018 koppelen

**Doel:** de orders worden in de echte NAV 2018 OData-API aangemaakt in
plaats van in de in-memory mock. De stepwise NAV-client is af + getest;
alleen credentials ontbreken.

In `backend/.env`:

```
NAVISION_MODE=real
NAV_BASE_URL=https://<jouw-nav-host>:7048/<NAV-instance>/api/v2.0
NAV_COMPANY_ID=<company-guid-uit-nav>
NAV_AUTH_MODE=basic            # of: oauth
# bij basic:
NAV_USERNAME=<web-service-user>
NAV_PASSWORD=<web-service-key>
# bij oauth (Azure AD-fronted NAV):
NAV_TENANT_ID=...
NAV_CLIENT_ID=...
NAV_CLIENT_SECRET=...
NAV_SCOPE=https://api.businesscentral.dynamics.com/.default
NAV_VERIFY_SSL=true            # false ALLEEN bij self-signed staging
```

### Web Service Access Key in NAV ophalen

1. NAV 2018 → user kaart van de service-user → Web Service Access Key →
   "Generate" → kopieer de waarde
2. Geef die user de juiste permissies (P/G voor Sales Header, Sales Line,
   Item, Customer, Item Reference, Incoming Document, Attachment)

## 3. Master-data sync draaien (eenmalig + daarna delta)

Zodra NAV-creds staan:

```bash
cd kwabo-order-intake/backend
PYTHONPATH=src python scripts/sync_navision_masters.py --full
```

Dit haalt klanten, items, ship-to-adressen, UoMs en kruisverwijzingen uit
NAV en zet ze in de SQLite-mirror. Daarna delta:

```bash
PYTHONPATH=src python scripts/sync_navision_masters.py        # default = --delta
```

Roep dit dagelijks aan via een scheduler (Task Scheduler / cron).

## 4. Eén staging-push als acceptatietest

Vóór je productie aanzet:

1. Zet `NAVISION_MODE=real` met **staging**-creds (niet productie)
2. Drop één test-`.eml` in `data/inbox/`
3. Backend draaien: `PYTHONPATH=src uvicorn kwabo.main:app --port 8000`
4. Trigger scan: `curl -X POST http://localhost:8000/api/intake/scan`
5. Open dashboard → review de order → klik **Goedkeuren**
6. **Verifieer in NAV staging:**
   - Sales Header is aangemaakt met klantgegevens (sellToCustomerName,
     paymentTermsCode, currencyCode) door de OnValidate van customerNumber
   - Sales Line bevat unitPrice (niet €0,00) en — bij mix-klant + mix-artikel
     met mix-UoM — de mix-staffel-prijs (Codeunit moet zijn afgevuurd)
   - Externe documentnr, requestedDeliveryDate, shipmentDate kloppen
   - Bij mix-flow: ziet het Unit Price-veld op de regel een prijs <
     standaardprijs zodra de mix-quantity-PATCH is gestuurd? Zo ja: Codeunit
     vuurt zoals verwacht.
   - Incoming Document is aangemaakt + bestand gekoppeld

Als alle 6 punten kloppen op staging → veilig om productie aan te zetten.

## 5. Vercel + Railway (optioneel, voor cloud-hosting)

Niet vereist als je alles op één Windows-server draait, maar als je
multi-user / always-on wil:

- **Supabase** Postgres: zet `DATABASE_URL` op de transaction pooler URI
  (poort 6543), draai eenmalig `init_db()` tegen die URL
- **Railway** voor de FastAPI-backend: root `backend`, env vars uit `.env`
- **Vercel** voor de Next.js dashboard: root `frontend`,
  `NEXT_PUBLIC_API_BASE` wijzen naar Railway-URL
- **CORS:** zet `KWABO_CORS_EXTRA=https://<je-vercel-domain>` in Railway

## Snel-controle vóór go-live

```bash
# Backend tests groen?
cd kwabo-order-intake/backend
python -m pytest -q
# Verwacht: 215 passed, 17 skipped (geen failures)

# Frontend build slaagt?
cd ../frontend
pnpm build
# Verwacht: ✓ Compiled successfully
```

## Wat al af is

- ✅ NAV trigger-aware stepwise client (single-field PATCH per veld)
- ✅ 10-stappen-flow uit de feedback gemapt op code (header → ship-to → external doc → datums → regels → UoM → quantity → europallet → incoming document → attachment)
- ✅ Mix-prijzen flow (klantflag × artikelflag × mix-UoM check)
- ✅ Idempotency-guard op externalDocumentNumber (re-push faalt niet)
- ✅ Audit trail: per-PATCH autofill diff bewaard voor post-mortem
- ✅ 27 dedicated NAV-trigger tests groen
- ✅ End-to-end testen op 17 voorbeeld-emails: 12 worden compleet doorgepushed naar mock NAV met 0 errors
- ✅ FastAPI lifespan-migratie (geen deprecation warnings meer)
- ✅ Stale email-client tests bijgewerkt naar huidig (werkend) gedrag
- ✅ Frontend build slaagt; resterende lint-errors zijn React 19 strict
  advisories (geen runtime impact)
