# Kwabo Order Intake AI

AI-gestuurd systeem dat inkomende order-e-mails op `info@kwabo.nl` automatisch verwerkt tot conceptverkooporders in Microsoft Dynamics NAV 2018. Zie `../kwabo_technische_beschrijving.md.pdf` voor de volledige specificatie.

## Status (huidige implementatie)

- ✅ **Python backend:** LangGraph-pipeline van 7 nodes (intake → classify → extract → match_customer → match_articles → validate_prices → compose_order) + finalize (push_navision → send_confirmation)
- ✅ **LLM-extractie:** Claude Sonnet 4.5 met prompt voor NL/DE/EN orders; robuuste JSON-parser die truncatie repareert
- ✅ **Mock Navision:** in-memory met persist naar `data/navision_mock/orders/*.json`
- ✅ **File-drop mailbox:** `.eml` bestanden in `data/inbox/` → `POST /api/intake/scan`
- ✅ **SQLite DB:** klantenkaarten, artikelmappings, prijsafspraken, matching history, order_log
- ✅ **FastAPI REST:** `/api/orders`, `/api/klanten`, `/api/artikelen`, `/api/audit`, `/api/intake`
- ✅ **Next.js 16 dashboard:** queue, order-review met inline artikel-correctie, klantenbeheer, audit log met stats
- ✅ **Self-learning:** dashboard-correcties worden opgeslagen in `artikel_matching_history` en `klantenkaart_artikelen` — volgende gelijke e-mail wordt automatisch gematcht

### Baseline regressie op 17 voorbeeld-emails

| Metric | Resultaat |
|---|---|
| Emails geparseerd | 17/17 |
| Als order geclassificeerd | 16/17 (1 = lege duplicaat Werkzeuge Dietrich, correct afgewezen) |
| Klant gematcht | 12/16 (75%) |
| Sales orders in Navision mock | 16/17 (94%) |
| Artikel auto-match | ~22% (lage baseline omdat seed mappings slechts voorbeelden dekken) |

Artikel-match-rate verbetert structureel naarmate de dashboard-reviewer correcties opslaat (self-learning loop).

## Quickstart

### Eenmalig

```bash
cd backend
pip install -r requirements.txt           # of: uv sync
cp .env.example .env                      # vul ANTHROPIC_API_KEY in
cd ../frontend
pnpm install
```

### Backend draaien

```bash
cd backend
PYTHONPATH=src python -m uvicorn kwabo.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
```

### Frontend draaien

```bash
cd frontend
pnpm dev                                  # http://localhost:3000 (of 3001)
```

### Dev-mode op Windows

`pnpm dev` draait met `next dev --webpack`. Next.js 16 gebruikt standaard Turbopack, maar op Windows 11 geeft dat hydration-failures waardoor `useEffect` niet vuurt en knoppen dood blijven. Met de webpack-dev-server werkt alle interactiviteit (HMR, React state, event handlers) direct.

Alternatieven:

- `pnpm dev:turbo` — stock `next dev` met Turbopack (experimenteel op Windows; werkt wel op macOS/Linux).
- `pnpm build && pnpm start` — productie-build, 100% reproducible (dit is wat Playwright ook gebruikt).

Upstream te volgen: https://github.com/vercel/next.js/issues (zoek naar "turbopack windows hydration").

### Verwerkings­flow testen

```bash
# 1) single email
cd backend
python scripts/run_single_email.py "tests/test_data/emails/Ferney inkooporder 4200056148.eml" --approve

# 2) batch alle 17 — resultatenrapport
python scripts/run_all.py

# 3) via API: drop emails in data/inbox/ en scan
curl -X POST http://localhost:8000/api/intake/scan
```

## Repository layout

```
kwabo-order-intake/
├── backend/
│   ├── src/kwabo/
│   │   ├── config.py              Settings (pydantic-settings)
│   │   ├── main.py                FastAPI app
│   │   ├── api/                   orders, klanten, artikelen, audit, intake_trigger
│   │   ├── db/                    SQLModel schema + repository + seed
│   │   ├── graph/
│   │   │   ├── state.py           OrderState TypedDict
│   │   │   ├── graph.py           StateGraph build
│   │   │   ├── llm.py             Anthropic Claude
│   │   │   ├── runner.py          convenience runner
│   │   │   └── nodes/             intake, classify, extract, match_customer, match_articles, validate_prices, compose_order, push_navision
│   │   ├── prompts/               classify.txt, extract.txt
│   │   ├── integrations/          pdf_parser, email_client (FileDrop), navision_api (Mock)
│   │   └── utils/                 eenheid_mapping, json_parser, logging
│   ├── scripts/                   run_single_email.py, run_all.py
│   └── tests/test_data/emails/    17 voorbeeld .eml bestanden
├── frontend/
│   ├── app/
│   │   ├── page.tsx               Order queue
│   │   ├── orders/[id]/           Order review (split-view + inline correcties)
│   │   ├── klanten/[nr]/          Klantenbeheer + artikelmappings
│   │   └── audit/                 Audit log + stats
│   └── lib/api.ts                 Typed API client
└── data/
    ├── inbox/                     Drop .eml hier voor scan
    ├── processed/                 Verwerkte .eml bestanden
    └── navision_mock/orders/      Mock ERP orders als JSON
```

## Go-live: koppelen aan echte mailbox + NAV

Volledige variabelenlijst staat in `backend/.env.example`. Korte versie:

**Echte NAV 2018 (OData v2)** — `RealNavisionClient` is af. Zet:
- `NAVISION_MODE=real`
- `NAV_BASE_URL`, `NAV_COMPANY_ID`
- `NAV_AUTH_MODE=basic` met `NAV_USERNAME` + `NAV_PASSWORD` (Web Service Access Key) **of**
  `NAV_AUTH_MODE=oauth` met `NAV_TENANT_ID`, `NAV_CLIENT_ID`, `NAV_CLIENT_SECRET`, `NAV_SCOPE`
- Optioneel `NAV_VERIFY_SSL=false` voor self-signed staging

Daarna eenmalig `python backend/scripts/sync_navision_masters.py --full` om klanten/items/ship-tos/UoMs/cross-refs uit NAV op te halen. Vervolgens incrementeel met `--delta`.

**Microsoft Graph mailbox** — plumbing (OAuth-flow + token-opslag) staat klaar; de fetch-implementatie is een stub die met een duidelijke melding faalt tot deze is ingevuld. Zet:
- `EMAIL_MODE=graph`
- Doorloop OAuth via dashboard → `/api/mailbox/oauth/start`

**File-drop fallback** (huidige standaard, geen wijziging vereist):
- `EMAIL_MODE=file_drop` + drop `.eml` files in `data/inbox/`

**IMAP** — niet geïmplementeerd. `EMAIL_MODE=imap` geeft een duidelijke `NotImplementedError` zodat configuratiefouten zichtbaar zijn.

Bij elke NAV-error tijdens go-live worden request body, response body+status, error type en op-context gestructureerd gelogd (`event=nav_stepwise_failure`) zodat post-mortem mogelijk is.

## Cloud deploy: Supabase + Railway + Vercel

| Component | Hosting | Hoe gekoppeld |
|---|---|---|
| Postgres database | Supabase | `DATABASE_URL` (transaction pooler URI, port 6543) |
| FastAPI backend | Railway | reads `DATABASE_URL` + `ANTHROPIC_API_KEY` + NAV/Graph creds uit Railway env |
| Next.js frontend | Vercel | `NEXT_PUBLIC_API_BASE_URL` wijst naar Railway-URL |

### 1. Supabase (eenmalig)

1. Pak de **Transaction pooler** connection string uit Supabase Dashboard → Project Settings → Database → Connection string → URI tab.
2. Zet hem als `DATABASE_URL` in Railway én lokaal in `.env`. Het pad gebruikt `postgresql+psycopg://...:6543/postgres`.
3. Schema bootstrappen: één keer een script draaien dat `init_db()` aanroept tegen de Supabase URL — bv. `PYTHONPATH=src python -c "from kwabo.db.session import init_db; init_db()"`. Dit is idempotent (re-run = no-op).
4. Master-data sync: `python backend/scripts/sync_navision_masters.py --full` (vereist NAV-creds; vult klanten/items/ship-tos/UOMs/kruisverwijzingen).

### 2. Railway (backend)

1. Connect GitHub repo `cas-pilex/kwabo`, selecteer `backend/` als root.
2. Build command: `pip install -r requirements.txt`. Start command: `PYTHONPATH=src uvicorn kwabo.main:app --host 0.0.0.0 --port $PORT`.
3. Env vars: kopiëer alle uncommented regels uit `backend/.env.example`, vul echte waarden. Belangrijk:
   - `DATABASE_URL` (Supabase pooler URI)
   - `ANTHROPIC_API_KEY`
   - `NAVISION_MODE=real` + alle `NAV_*` creds wanneer je echte NAV koppelt
   - `EMAIL_MODE=graph` + `GRAPH_*` wanneer je echte mailbox koppelt
4. Bij eerste deploy: zet `EMAIL_MODE=file_drop` en `NAVISION_MODE=mock` om de boel in mock-mode te smoke-testen, daarna omschakelen.

### 3. Vercel (frontend)

1. Connect GitHub repo, selecteer `frontend/` als root, framework = Next.js (auto-detected).
2. Env vars:
   - `NEXT_PUBLIC_API_BASE_URL=https://<je-railway-app>.up.railway.app`
   - Optioneel `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` als de frontend ooit direct met Supabase praat (nu niet, gaat via backend).

### Secrets — nooit committen

`.env` staat in `.gitignore`. Productie-secrets horen alleen in Railway/Vercel env-UI of in Supabase Vault. Service-role key van Supabase **nooit** in frontend env zetten — die bypasst Row Level Security.

## Volgende stappen om naar 100% werkende orders te komen

1. **Artikel-match verbeteren:** seed mapping aanvullen op basis van echte Kwabo-masterdata (Nav items export) zodat exact/klantenkaart-matches slagen i.p.v. fuzzy → 80%+ auto-match.
2. **Echte Navision credentials** toevoegen en `RealNavisionClient` implementeren; item-search geeft dan live hits i.p.v. mock.
3. **Prompt-tuning:** extract-prompt iteratief verfijnen per klant-format (TABS/PontMeyer speciaal; Kirchner multi-order array).
4. **Forwarded-email afzenderdetectie:** nu vallen 4 forwards (Ivar/Mark/Nico @ kwabo.nl) naar "klant niet gevonden" — regex op forwarded-content toevoegen.
5. **Tests uitbreiden:** per-email JSON fixtures in `tests/test_data/expected/` en `pytest` regressie-harness.
6. **LangSmith tracing** aanzetten (`LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`) voor productie-observability.
