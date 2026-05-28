# Kwabo Order Intake AI — Technische audit

> Datum: 2026-05-28
> Methode: read-only inspectie van de repo op `C:\Kwabo` (commit `6441469`, branch `main`).
> Auteur: senior software-architect (Claude), in opdracht van Cas.
>
> Doel: een onbekende ontwikkelaar moet na het lezen exact begrijpen hoe het systeem
> werkt, welke onderdelen af zijn, welke half af, en waarom de huidige bugs optreden.
> Elk feit is voorzien van `bestand:regel`-bewijs. Aannames zijn expliciet gemarkeerd
> als `ONZEKER:` of `ONGEVERIFIEERD:`. Wat alleen on-site getest kan worden staat in §13.

---

## Inhoudsopgave

1. [Samenvatting & doel](#1-samenvatting--doel)
2. [Tech stack & dependencies](#2-tech-stack--dependencies)
3. [High-level architectuur](#3-high-level-architectuur)
4. [Mappenstructuur](#4-mappenstructuur)
5. [End-to-end data flow](#5-end-to-end-data-flow)
6. [Integraties (diepgaand)](#6-integraties-diepgaand)
7. [Configuratie](#7-configuratie)
8. [Hoe draait het](#8-hoe-draait-het)
9. [API / frontend surface](#9-api--frontend-surface)
10. [Implementatiestatus](#10-implementatiestatus)
11. [Tests](#11-tests)
12. [Geconstateerde probleemgebieden](#12-geconstateerde-probleemgebieden)
13. [Open vragen voor on-site test](#13-open-vragen-voor-on-site-test)
14. [Top-10 meest waarschijnlijke oorzaken van de huidige bugs](#14-top-10-meest-waarschijnlijke-oorzaken-van-de-huidige-bugs)

---

## 1. Samenvatting & doel

Wat het systeem doet: inkomende order-e-mails op `info@kwabo.nl` worden via Microsoft
Graph (OAuth2) opgehaald, door een 10-node LangGraph pipeline (Claude Sonnet 4.5 + lokale
DB-cascade + NAV-lookup) omgezet naar een gestructureerde "order-conceptstate", in een
review-dashboard (Next.js) handmatig gecontroleerd en daarna via de NAV 2018 OData V4
endpoint (Pilex test-tenant) trigger-aware (single-field POST + opvolgende PATCHes per
OnValidate-veld) als verkooporder weggeschreven.

Doelgroep:
- Eindgebruikers: backoffice Kwabo (Nico c.s.) die orders inkijken en goedkeuren.
- Beheerder: Cas, die OAuth-credentials, NAV-creds en de poll-config beheert.

Zakelijke baat: handmatig overtypen van klantorders in Navision vervalt — het systeem
levert een voorbereide order met klant/artikel/prijs-match en alle ontbrekende velden
gemarkeerd voor menselijke review.

Status op het oog (zie ook §10): het pad happy-path-mail → review → NAV-push
functioneert blijkens de testsuite en de recente commits, maar er staan een aantal
silent-failure paths en infrastructuur-aannames overeind die in productie nog niet
allemaal robuust zijn (zie §12 en §14).

---

## 2. Tech stack & dependencies

### Backend (Python)

- Python `>=3.11` (`backend/pyproject.toml:5`), Railway draait `python-3.12.7`
  (`backend/runtime.txt:1`).
- Pakketmanager: pip via `backend/requirements.txt`. `pyproject.toml` bevat geen
  dependency-block; alleen tool-config (ruff, pytest).
- Frameworks en libraries (`backend/requirements.txt:1-23`):
  - `fastapi>=0.115.0` + `uvicorn[standard]>=0.30.0`
  - `langgraph>=0.2.50` + `langchain>=0.3.0` + `langchain-anthropic>=0.3.0`
  - `anthropic>=0.40.0` (direct gebruikt door `integrations/llm_extractor.py`, naast
    de LangChain wrapper voor classify)
  - `sqlmodel>=0.0.22` + `psycopg[binary]>=3.2.0` (geen `sqlalchemy` aparte pin; loopt mee met sqlmodel)
  - `alembic>=1.13.0` (geïmporteerd maar **niet gebruikt** — er is geen `alembic.ini`
    of `migrations/`. Schema-evolutie gebeurt met `SQLModel.metadata.create_all()` +
    custom additive-migrator in `backend/src/kwabo/db/session.py:42-93`).
  - `pdfplumber>=0.11.0` (PDF tekst-extractie, met `subprocess`-fallback naar
    `pdftotext` als binary aanwezig) — zie `backend/src/kwabo/integrations/pdf_parser.py:39-50`.
  - `openpyxl>=3.1.0` (Excel-bijlage parsing in `email_client.py:181-196`).
  - `httpx>=0.27.0` (alle HTTP-calls — NAV, Graph, OAuth-exchange).
  - `pydantic-settings>=2.5.0` (envvar-config, zie §7).
  - `rapidfuzz>=3.10.0` (fuzzy artikelmatching in `match_articles.py:8`).
  - `structlog>=24.4.0` (key-value structured logging).
  - `email-validator>=2.2.0` (geen runtime-gebruik gevonden via grep; **mogelijk dood**).
  - `sse-starlette>=2.1.0` (geen runtime-gebruik gevonden; **mogelijk dood**).
  - `python-dotenv>=1.0.0`, `python-multipart>=0.0.12`.
  - Tests: `pytest>=8.3.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=5.0.0`.
  - Lint: `ruff>=0.7.0`.

### Frontend (TypeScript / React)

`frontend/package.json:15-31`:
- `next 16.2.3` (zeer recente major) + `react 19.2.4` + `react-dom 19.2.4`
  — **let op:** `frontend/AGENTS.md` waarschuwt expliciet dat dit niet de
  Next.js is die "Claude in training-data kent" en dat de API kan afwijken.
- `sonner ^2.0.7` (toast notificaties).
- Dev: `tailwindcss ^4`, `typescript ^5`, `eslint ^9 + eslint-config-next 16.2.3`,
  `@playwright/test ^1.59.1`, `@tailwindcss/postcss ^4`.

Package-manager: zowel `pnpm-lock.yaml` als `package-lock.json` aanwezig. De
README (`README.md:36-38`) instrueert `pnpm install`; `pnpm-workspace.yaml` is
ook aanwezig.

Build-script bijzonderheid: `dev` is `next dev --webpack` (niet de default
Turbopack), omdat Turbopack op Windows hydration-failures geeft — zie README
`README.md:54-64`.

### Externe services

- **LLM**: Anthropic (Claude Sonnet 4.5; `anthropic_model = "claude-sonnet-4-5"`,
  `backend/src/kwabo/config.py:14`). Twee call-paden:
  - Classify-node via LangChain wrapper (`backend/src/kwabo/graph/llm.py:11-18`)
  - Extract-node direct via `anthropic.AsyncAnthropic`
    (`backend/src/kwabo/integrations/llm_extractor.py:28-32`) — gebruikt **Vision**:
    PDF-attachments worden als `{"type":"document"}` base64 block meegestuurd.
- **NAV 2018**: OData V4 endpoint van Pilex test-tenant, PLX_* custom pages,
  Basic auth (Web Service Access Key). Configuratie via env-vars
  (`backend/src/kwabo/config.py:66-87`); client in `backend/src/kwabo/integrations/navision_nav2018.py`.
- **Microsoft Graph**: e-mailbox via OAuth2 (`backend/src/kwabo/integrations/email_client_graph.py`).
  Tokens in DB-tabel `oauth_tokens` (singleton id=1, `backend/src/kwabo/db/models.py:71-83`).
- **PostgreSQL via Supabase** (productie). DATABASE_URL via "transaction pooler"
  (port 6543), met `psycopg[binary]` driver en `prepare_threshold=None` om
  pgbouncer-incompatibiliteit met server-side prepared statements te omzeilen
  (`backend/src/kwabo/db/session.py:27-32`). Local dev: SQLite (`./kwabo.db`).
- **Railway**: backend hosting. `Procfile` en `railway.toml` definiëren
  start-command (`uvicorn kwabo.main:app --host 0.0.0.0 --port $PORT`) en
  health-check op `/api/health` (`backend/railway.toml:5`).
- **Vercel**: frontend hosting; `NEXT_PUBLIC_API_BASE` wijst naar de Railway URL.
- **Docker**: `docker-compose.yml` is aanwezig met `Dockerfile.backend` +
  `Dockerfile.frontend` voor lokale all-in-one. Volume `./data:/app/data` voor
  bestandsopslag — **alleen relevant voor docker, niet voor Railway** (zie §6.d).

---

## 3. High-level architectuur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          E-mail bron                                    │
│  EMAIL_MODE=graph   →  Microsoft Graph (info@kwabo.nl)  ← OAuth2-flow   │
│  EMAIL_MODE=file_drop → data/inbox/*.eml  (lokaal/Docker dev)           │
│  EMAIL_MODE=imap  →   NotImplementedError                               │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼  list_new()
                  ┌────────────────────────────────────┐
                  │  POST /api/intake/scan             │   ← achtergrond-poller
                  │   (intake_trigger.scan_inbox)       │     in lifespan-task
                  │   OF                                │     (interval=settings.
                  │  POST /api/intake/upload  .eml      │      mail_poll_interval_
                  │   (intake_trigger.upload_eml)        │      seconds; 0=uit)
                  └─────────────┬──────────────────────┘
                                │  per mail:
                                ▼
            _persist_source_eml()  → data/incoming_documents/by_email_id/<id>.eml
                                ▼
                      state = new_state(...)         (graph/state.py:143)
                      state["incoming_document_path"] = saved_path
                                │
                                ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │                       INGEST GRAPH (LangGraph)                     │
   │                                                                    │
   │   intake → classify ─order?─→ extract → match_customer →           │
   │              │                                                     │
   │              └─niet order→ compose (status="not_order", end)       │
   │                                                                    │
   │   → select_ship_to → match_articles → apply_mixprijzen →           │
   │     compute_europallet → validate_prices → compose_order → END     │
   │                                                                    │
   │   compose_order schrijft naar order_log met status="review"        │
   │     en bewaart de gecomponeerde NavOperation-lijst in state.       │
   └────────────────────────────────────────────────────────────────────┘
                                │
                                ▼  await _run_extras() voor multi-order PDFs
                          (sub_order_graph: skip classify/extract)
                                │
                                ▼
                       client.mark_seen(email_id)
                       (Graph: PATCH isRead=true; file_drop: shutil.move)
                                │
                                ▼
                     Order zichtbaar in /api/orders queue
                                │
                                ▼
              Reviewer opent /orders/[id] in dashboard
              ↳ E-mail body + PDF-bijlages bekijken
              ↳ Velden corrigeren via /api/orders/{id}/patch-field
                (clears state["nav_operations"] — wordt opnieuw gecomponeerd)
              ↳ Optioneel handmatig source-document uploaden
                (/api/orders/{id}/incoming-doc)
              ↳ NAV-preview tonen (/api/orders/{id}/navision-preview)
                                │
                                ▼  POST /api/orders/{id}/approve [?force=true]
                  ┌───────────────────────────────────────────┐
                  │            FINALIZE GRAPH                  │
                  │  push_navision → send_confirmation → END   │
                  │                                            │
                  │  push_navision: client.create_sales_order_ │
                  │    stepwise(operations)                    │
                  │   - Nav2018ODataClient (prod)              │
                  │   - MockNavisionClient (dev/test)          │
                  │   - ReplayNavisionClient (fixtures)        │
                  └───────────────────────────────────────────┘
                                │
                                ▼
                Bevestiging-mail (mail_mode=log/smtp/graph)
```

### LangGraph nodes (in volgorde)

Bron: `backend/src/kwabo/graph/graph.py:32-56`. Per node de input-state, het schrijven
en de zijdelingse effecten:

| # | Node | Bestand | Wat het doet | Schrijft naar state |
|---|------|---------|--------------|---------------------|
| 1 | `intake_node` | `nodes/intake.py:12-29` | Stamp + log "E-mail opgehaald" + bijlage-namen. Geen externe IO. | `stappen_log[]` |
| 2 | `classify_node` | `nodes/classify.py:21-74` | 1 LLM-call (Claude Sonnet) over body+bijlage-previews → `{is_order, reden, confidence}`. File-cached via `llm_cache`. | `is_order`, `classificatie_reden`, `classificatie_confidence` |
| 3 | `extract_node` | `nodes/extract.py:166-247` | 1 LLM-Vision-call (PDF base64 als document-block). Output is dict OF list (multi-order). Bouwt provenance-meta per veld. Post-processor herstelt Duitse `KW<NN>` weeknummers naar ISO-datum. | flat velden (`bestelnummer_klant`, `orderdatum`, `gewenste_leverdatum`, `afleveradres`, `orderregels` etc.), `_meta`, `needs_review_fields`, `extra_orders_raw` (extra orders bij multi) |
| 4 | `match_customer_node` | `nodes/match_customer.py:34-168` | Detecteert forwarded mails (origineel afzender). Cascade: DB-by-email → NAV-search-by-email → NAV-search-by-domain. Bij hit: kredietlimiet-check, 4+-check. | `klant_match`, `validatie_warnings`, `_meta.klant_match` |
| 5 | `select_ship_to_node` | `nodes/select_ship_to.py:88-172` | Leest lokale mirror `klantenkaart_ship_to`. 0 ⇒ NAV default. 1 ⇒ auto-pick. ≥2 ⇒ score op postcode/plaats/naam/straat. Ambiguous ⇒ review. | `ship_to_kandidaten`, `ship_to_gekozen` |
| 6 | `match_articles_node` | `nodes/match_articles.py:98-251` | Per regel: cascade exact → kruisverwijzing → klantenkaart → history → fuzzy (rapidfuzz WRatio drempel ≥80) → manual. Crash-counter: ≥50% NAV-fail → warning "NAV tijdelijk niet bereikbaar". Overschrijft `eenheid` met `basis_eenheid` uit lokale mirror. | `orderregels[].artikelnummer_kwabo_matched/match_methode/match_confidence`, `alle_artikelen_gematcht`, `validatie_warnings` |
| 7 | `apply_mixprijzen_node` | `nodes/apply_mixprijzen.py:178-199` | Alleen actief als klant + artikel beide `mixprijzen=true`. Kiest een mix-UoM uit `ArtikelEenheid`-rijen (1=auto, ≥2=score op residue). | `mixprijzen_actief`, per-regel `mix_uom_kandidaat`, `mix_uom_gekozen` |
| 8 | `compute_europallet_node` | `nodes/compute_europallet.py:48-62` | Roept `kwabo.utils.pallet_logic.compute_europallet(state, repo)` aan. Resultaat is een synthetisch europallet-orderregel (artnr uit `settings.europallet_artikelnr`, default 19820) of `None`. NIET toegevoegd aan `orderregels[]`. | `europallet_regel` |
| 9 | `validate_prices_node` | `nodes/validate_prices.py:15-165` | Per regel: lookup `Prijsafspraak` (cascade pallet > mix > topcoat > standaard). >5% afwijking ⇒ warning + `prijs_validated=False`. Sanity-checks (hoeveelheid >0, max PAL=100, max STUK=50000 etc.). Bouwt `_meta.orderregels[].prijs_per_eenheid` provenance. | `orderregels[].prijs_validated`, `validatie_warnings`, `alle_prijzen_valide` |
| 10 | `compose_order_node` | `nodes/compose_order.py:43-138` | Roept `compose_navision_operations(state)` aan (pure-func, geen IO). Persisteert order_log-rij (status `review` of `not_order`). Strips raw-bytes uit bijlagen vóór JSON-serialisatie. | `nav_operations`, `order_log_id`, evt. `compose_error` |

`push_navision_node` (finalize-graph, na approve) zit in `nodes/push_navision.py:106-204`:
- Geen `nav_operations` ⇒ `_mark_failed("no nav_operations on state")`.
- Anders: `client.create_sales_order_stepwise(operations)` aanroepen.
- Per-op resultaten in `state.nav_operation_results` + db (`order_state.nav_operation_results`).
- Op > 500 KB JSON: `log.warning("state_json_large")` (`push_navision.py:184`).

`send_confirmation_node` (`nodes/push_navision.py:207-252`): rendert template,
verstuurt via `mail_sender` (mode `log` of `smtp` of `graph`). Skipt als push faalde.

### State schema

Volledige `OrderState` TypedDict in `backend/src/kwabo/graph/state.py:58-140`. Totale velden:

```
Input:        email_id, email_from, email_subject, email_body, email_date,
              bijlagen[], source_path
Classify:     is_order, classificatie_reden, classificatie_confidence
Extract:      taal, bestelnummer_klant, orderdatum, gewenste_leverdatum,
              afleveradres, afleverinstructies, orderregels[], opmerkingen,
              extra_orders_raw, parent_log_id, sub_order_index
Match:        klant_match{navision_klantnr, klantnaam, match_confidence,
              match_bron, is_4plus, kredietlimiet, betalingsconditie}
              ship_to_kandidaten[], ship_to_gekozen
              mixprijzen_actief
              europallet_regel
Validation:   alle_artikelen_gematcht, alle_prijzen_valide, validatie_warnings[]
Review:       review_status, review_corrections, reviewer
              needs_review_fields[], needs_review_count
              _meta{} — per-veld provenance (value/source/confidence/needs_review)
NAV:          incoming_document_path, nav_operations[], nav_operation_results[],
              nav_autofilled{}, compose_error, navision_order_nr, navision_status
Audit:        stappen_log[], errors[]
DB:           order_log_id
```

`OrderRegel` (`state.py:17-38`) heeft 17 velden inclusief alle match-meta en
mixprijzen-UoM kandidaten. `_meta.orderregels[i]` heeft per regel een dict
{`artikelnummer_kwabo`, `artikelnummer_kwabo_matched`, `prijs_per_eenheid`, …},
elk met `{value, source, source_detail, confidence, needs_review}`.

---

## 4. Mappenstructuur

(Verzameld uit `Glob` en `ls`-output op `C:\Kwabo` en sub-dirs)

```
C:\Kwabo\
├── .git/                            (branch=main)
├── .gitignore
├── README.md                        Hoofd-README (NIET helemaal actueel — zie §10)
├── CAS_GO_LIVE_CHECKLIST.md
├── OFFERTE_STATUS.md
├── STABILISATIE_RAPPORT.md
├── STATUS.md
├── VERIFICATIE.md
├── VOORTGANG_EN_KOSTEN.md
├── VOORTGANGSRAPPORT_KWABO.md
├── docker-compose.yml               local docker (data/ als volume)
├── docker/
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
├── data/                            LOKAAL leeg (zie §6.d)
│   ├── inbox/                       0 .eml's
│   ├── processed/                   0 .eml's
│   └── navision_mock/
│       └── orders/                  0 JSONs
├── _screenshots/                    untracked (validatie-screenshots dev)
├── docs/                            (niet ingelezen, ongeverifieerd)
├── backend/
│   ├── pyproject.toml               Geen deps; alleen ruff/pytest-config
│   ├── requirements.txt             Echte dep-lijst
│   ├── runtime.txt                  "python-3.12.7" (Railway buildpack hint)
│   ├── railway.toml                 startCommand + healthcheck
│   ├── Procfile                     web: uvicorn (zelfde command)
│   ├── Makefile                     test / test-regression / test-10x targets
│   ├── kwabo.db                     LOKAAL SQLite (147 KB, 14 tables; zie §6.c)
│   ├── kwabo.log                    LOKAAL RotatingFileHandler (5 MB × 3)
│   ├── .env.example                 alle envvars met uitleg
│   ├── scripts/
│   │   ├── run_single_email.py     CLI: één .eml door pipeline
│   │   ├── run_all.py              CLI: alle 17 fixtures
│   │   ├── run_all_with_push.py    + force-approve + NAV push
│   │   ├── run_e2e_10x.py          (test_10x-runner)
│   │   ├── sync_navision_masters.py  CLI: NAV → DB mirror (zie §6.b)
│   │   ├── sync_sharepoint.py      ONGEVERIFIEERD
│   │   ├── seed_pallet_history.py
│   │   ├── verify_t12.py
│   │   ├── test_10x.sh / .ps1
│   │   └── clear_llm_cache.py
│   ├── tests/                       40+ test-files (zie §11)
│   │   ├── conftest.py
│   │   ├── test_data/emails/        17 .eml-fixtures
│   │   └── test_data/expected/
│   ├── reports/                     baseline-rapporten
│   └── src/kwabo/
│       ├── main.py                  FastAPI entry + lifespan + mail-poll
│       ├── config.py                pydantic-settings (alle env-vars)
│       ├── api/
│       │   ├── auth.py              HMAC-signed bearer-tokens (zie §6.x)
│       │   ├── orders.py            Order-CRUD + signed-URL PDF-download
│       │   ├── preview.py           navision-preview, patch-field, needs-review
│       │   ├── intake_trigger.py    POST /api/intake/{scan,upload,run-file}
│       │   ├── klanten.py           Klantenbeheer-CRUD
│       │   ├── artikelen.py        Artikel-search
│       │   ├── audit.py             Stats + audit-log
│       │   ├── mailbox.py           Graph OAuth + status
│       │   ├── admin.py             NAV master-sync via HTTP (bg-jobs)
│       │   ├── diagnostics.py       /api/diagnostics/nav probe
│       │   ├── logs.py              tail kwabo.log
│       │   ├── prijsafspraken.py
│       │   ├── schemas.py           Pydantic request/response shapes
│       │   └── testing.py           /api/testing/* (alleen als TEST_MODE=on)
│       ├── db/
│       │   ├── models.py            14 SQLModel-tabellen (zie §6.c)
│       │   ├── repository.py        per-domein repos
│       │   ├── session.py           engine + init_db + additive-migrator
│       │   └── seed.py              seed-functie voor klantenkaarten
│       ├── graph/
│       │   ├── state.py             OrderState TypedDict
│       │   ├── graph.py             3× compiled graph (ingest/finalize/sub)
│       │   ├── llm.py               ChatAnthropic singleton
│       │   ├── llm_cache.py         file-based SHA256-key cache
│       │   ├── runner.py            entry-helpers (_raw_email_to_state, run_on_eml, _run_extras)
│       │   └── nodes/              10 node-functies
│       ├── integrations/
│       │   ├── email_client.py     FileDropEmailClient + parse_eml_bytes/file
│       │   ├── email_client_graph.py GraphEmailClient (Microsoft Graph)
│       │   ├── pdf_parser.py       pdfplumber → text (subprocess-fallback)
│       │   ├── llm_extractor.py    Claude Vision PDF extract (1 call/mail)
│       │   ├── forwarded_parser.py Detect "Begin doorgestuurd…" headers
│       │   ├── navision_api.py     Protocol + MockNavisionClient + factory
│       │   ├── navision_nav2018.py NAV 2018 OData V4 (PRODUCTIE)
│       │   ├── navision_real.py    BC-flavoured client + ReplayNavisionClient
│       │   ├── navision_steps.py   compose_navision_operations (pure-func)
│       │   ├── nav_operations.py   NavOperation typed-dict + helpers
│       │   ├── nav_mock_fixtures.py MOCK_CUSTOMERS / ITEMS / SHIP_TOS etc.
│       │   ├── mail_sender.py      log / smtp / graph sender + render_confirmation
│       │   ├── document_extractor.py  (ongeverifieerd, mogelijk dood)
│       │   └── sharepoint.py        (ongeverifieerd, mogelijk dood)
│       ├── prompts/
│       │   ├── classify.txt
│       │   ├── extract.txt          (v1; mogelijk niet meer gebruikt)
│       │   └── extract_v2.txt       (huidige; door llm_extractor.py geladen)
│       ├── templates/
│       │   └── ontvangstbevestiging.txt
│       └── utils/
│           ├── logging.py
│           ├── json_parser.py       parse_json_loose: repareer LLM-truncatie
│           ├── eenheid_mapping.py   normaliseer UoM strings
│           └── pallet_logic.py      compute_europallet logic
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── playwright.config.ts
    ├── next.config.ts
    ├── middleware.ts                ONGEVERIFIEERD (vermoedelijk auth-redirect)
    ├── AGENTS.md  + CLAUDE.md       waarschuwing over Next.js 16-API
    ├── app/                         App-router pages
    │   ├── layout.tsx
    │   ├── page.tsx                 / — order queue
    │   ├── login/                   /login
    │   ├── orders/[id]/             /orders/<n> order-review (split-view)
    │   ├── klanten/                 /klanten + /klanten/<nr>
    │   ├── audit/                   /audit
    │   ├── logs/                    /logs
    │   ├── email/                   /email (Graph OAuth UI)
    │   └── api/                     proxy routes (ongeverifieerd in detail)
    ├── components/                  shared components
    │   ├── email-source-viewer.tsx  PDF iframe + Open in nieuw tabblad
    │   ├── navision-preview.tsx
    │   ├── needs-review-banner.tsx
    │   ├── order-lines-table.tsx
    │   └── …
    ├── lib/api.ts                   typed fetch-client
    ├── public/                      static
    ├── scripts/                     build-e2e.mjs
    └── tests/                       Playwright tests
```

---

## 5. End-to-end data flow

Trace van één mail → NAV-order, met `bestand:regel`-verwijzing per stap:

1. **Microsoft Graph levert nieuwe mail** (alleen als `EMAIL_MODE=graph`).
   `GraphEmailClient.list_new` (`integrations/email_client_graph.py:161-203`)
   doet `GET /me/mailFolders/inbox/messages?$filter=isRead eq false&$top=10
   &$orderby=receivedDateTime asc`, dan per item `GET /me/messages/{id}/$value`
   (raw MIME bytes). Parst via `parse_eml_bytes(raw, email_id=msg_id,
   source_path=f"graph://{msg_id}")`.

2. **Trigger**: ofwel achtergrond-poller (`main.py:60-87 _mail_poll_loop`) die
   `scan_inbox` aanroept, ofwel handmatige `POST /api/intake/scan`, ofwel
   `POST /api/intake/upload` met een `.eml`.

3. **Source-eml persisteren** (`api/intake_trigger.py:23-53 _persist_source_eml`):
   `target_dir = settings.incoming_documents_path / "by_email_id"`
   (`config.py:21,101-103` resolved-pad uit relative `../data/incoming_documents`).
   `safe_id = alfanumeriek+-+_, max 32 chars`. Schrijf `raw_eml` bytes naar
   `<target_dir>/<safe_id>.eml`. Bij OSError ⇒ `log.error("intake_source_eml_save_failed")`
   en `state["incoming_document_save_failed"]=True`. Het pad wordt teruggegeven
   en op `state["incoming_document_path"]` gezet (`intake_trigger.py:85-92` voor
   /scan en `:140-145` voor /upload).

4. **Ingest-pipeline** (`graph.py:32-56 build_ingest_graph`): zie tabel in §3.

5. **Compose pre-persist** (`compose_order_node` → `compose_navision_operations`):
   pure-func; resultaat is `list[NavOperation]` met POST/PATCH operaties die de
   trigger-aware NAV client moet uitvoeren. Wordt op `state["nav_operations"]`
   gezet en in `order_log.order_state` (JSON-kolom) gepersisteerd.

6. **mark_seen** (`intake_trigger.py:112 client.mark_seen(raw.email_id)` voor /scan).
   - file_drop: `shutil.move(inbox/...eml → processed/...eml)`
   - Graph: `PATCH /me/messages/{id}` met `{"isRead":true}`.
   `/upload` doet **geen** mark_seen (logisch: er is geen remote mailbox-item).

7. **Multi-order sub-orders** (`runner.py:36-94 _run_extras`): als `extract_node`
   een JSON-array teruggaf, draait per extra-order een `sub_order_graph`
   (skip classify+extract, alle resterende nodes). Per-sub-isolation via try/except.

8. **Review** (frontend): `app/orders/[id]/page.tsx` → `OrderReview` component.
   Reviewer ziet:
   - Linkerkolom: `EmailSourceViewer` (tabs per bijlage, tekst óf PDF-iframe via
     signed URL, "Open in nieuw tabblad", "Download").
   - Middelste kolom: extract-summary + bewerkbare velden (klant, bestelnr, datum,
     afleveradres) met `ProvenanceBadge`.
   - Rechterkolom: orderregels-tabel + ship-to picker + europallet editor + nav-preview.
   - `NavFailureBanner` bij `status="failed"`.
   - `NeedsReviewBanner` als `needs_review_fields[]` niet leeg is.
   Wijzigingen via `PATCH /api/orders/{id}/patch-field` (`api/preview.py:173-234`).
   Belangrijk: deze handler clear `state["nav_operations"] = []` (`preview.py:217`)
   zodat een volgende preview/push opnieuw `compose_navision_operations` aanroept.

9. **Approve** (`api/orders.py:317-412 approve_order`):
   - Refuseert bij `missing && !force` met HTTP 422.
   - Recompose `nav_operations` vanuit huidige state (line 352-365).
   - Sla op met `status="approved"`, dan `await finalize(state)` (finalize-graph).
   - Bij succes: `navision_order_nr` in response; bij falen: `nav_error` +
     `nav_failed_op_count`.

10. **push_navision_node** → `Nav2018ODataClient.create_sales_order_stepwise`
    (`integrations/navision_nav2018.py:466-773`):
    - Idempotency-probe: filter `External_Document_No eq '<bestelnr>'`; al
      bestaand ⇒ short-circuit met `_dedup`.
    - Per-op: skip `/incomingDocuments`-bundle (NAV 2018 PLX_IncomingDocument page
      niet geëxposeerd). Translate path BC→NAV 2018, translate body
      `camelCase→Underscore_Case`. Voor lines: voeg `Document_No`+`Document_Type='Order'`
      toe. HTTP POST/PATCH. Capture `No` voor sales-order, composite key
      `(Document_Type, Document_No, Line_No)` voor lines. Bij exception:
      `log.error("nav2018_stepwise_failure")` met volledige request/response.

11. **send_confirmation_node** (`push_navision.py:207-252`): rendert sjabloon
    en stuurt mail. Skipt als push faalde (`navision_status="failed"`).

---

## 6. Integraties (diepgaand)

### 6.a E-mail (Graph + FileDrop)

Factory: `email_client.py:226-250 get_email_client()`. Modes:

- `file_drop` ⇒ `FileDropEmailClient` (`email_client.py:202-223`):
  - Constructor maakt `inbox` en `processed` dirs (mkdir parents=True, exist_ok=True).
  - `list_new()`: `inbox.glob("*.eml")` (sorted), parst elk via `parse_eml_file`.
  - `mark_seen(email_id)`: `shutil.move(p, processed/p.name)`. **In-memory mapping
    `_path_by_id`** — die wordt op een nieuwe client-instance niet hersteld. Dit
    betekent: als de tussentijds wordt herstart na `list_new` maar vóór `mark_seen`,
    blijft het .eml in `inbox/` staan en wordt het opnieuw verwerkt.
- `graph` ⇒ `GraphEmailClient` (`email_client_graph.py:37-227`):
  - Token wordt geladen uit DB tabel `oauth_tokens` (singleton id=1).
  - `_access_token()` checkt `expires_at` (30 sec marge) en doet zo nodig refresh
    via `_refresh_token()` (POST aan `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`,
    grant=`refresh_token`). Nieuwe token wordt in DB gepersisteerd; bij DB-fail
    blijft hij in-memory en logt warning.
  - `list_new()`: 10 messages per scan (`LIST_PAGE_SIZE=10` op regel 34) — Railway
    timeout-mitigatie (per `email_client_graph.py:28-34` comment: 10 × 15 sec
    Vision-extractie ≈ 2,5 min, ruim onder de 5-min request-limit).
  - `mark_seen(id)`: PATCH `isRead=true`. Bij 403: log "App registration mist
    Mail.ReadWrite scope" en return (geen retry).
- `imap` ⇒ `NotImplementedError` (per ontwerp; zie comment regel 247-249).

OAuth-config: `oauth_config` tabel (singleton id=1, `db/models.py:56-68`) met
`tenant_id, client_id, client_secret, redirect_uri, scopes`. Geconfigureerd via
het dashboard `/email`-pagina (POST `/api/mailbox/oauth/config`,
`api/mailbox.py:197-230`). Default scopes: `offline_access Mail.ReadWrite User.Read`.

OAuth-flow (`api/mailbox.py:236-393`): `/api/mailbox/oauth/start` (admin-gated)
zet `state` token in module-level dict, redirect naar Microsoft. `/oauth/callback`
(publiek; CSRF gecheckt via state-token) wisselt `code` voor `{access_token,
refresh_token, expires_in}` en haalt `/me.mail` voor `account_email`. Persistert
in `oauth_tokens`.

**.eml-lifecycle samenvatting**:
- Bron-eml → `_persist_source_eml` → `data/incoming_documents/by_email_id/<safe_id>.eml`
- DB-rij `order_log.order_state` JSON-kolom bevat `incoming_document_path` (absoluut
  pad, op moment van schrijven).
- Bij open in dashboard: `_find_eml_path` (`api/orders.py:132-166`) zoekt 1) op
  `incoming_document_path`, 2) op `source_path` (skipt `graph://`), 3) scant
  `inbox + processed` op short-hash match.
- Als `_find_eml_path` `None` retourneert ⇒ HTTP 404 met message "Originele .eml
  niet gevonden — bestand verwijderd uit inbox/processed?" (`orders.py:514-517`).

### 6.b Navision NAV 2018 OData V4

Endpoint-shape (per `navision_nav2018.py:5-32` docstring):
- `https://<host>:1153/<service>/ODataV4`
- Per-entity URL: `<base>/PLX_SalesOrder?company=Kopie 2026 Kwabo Techniek B.V.`
  (company als querystring; **niet** via `Company('...')`-path-segment — dat geeft
  500 op deze deployment, zie regel 191-198).
- Composite key voor sales-order: `PLX_SalesOrder(Document_Type='Order',No='VO260...')`
  (`navision_nav2018.py:213-220`).
- Composite key voor lines: `PLX_SalesOrderLines(Document_Type='Order',
  Document_No='VO260...',Line_No=10000)` (`navision_nav2018.py:222-231`) — composite
  key string mag **niet** in single-quotes (NAV antwoordt 500).

Auth: Basic via Web Service Access Key (`_auth()` regel 246-247).

Field translation `_DEFAULT_FIELD_MAP` (`navision_nav2018.py:62-78`):
```
camelCase composer    →  NAV 2018 underscore
customerNumber          Sell_to_Customer_No
shipToCode              Ship_to_Code
externalDocumentNumber  External_Document_No
requestedDeliveryDate   Requested_Delivery_Date
shipmentDate            Shipment_Date
incomingDocumentNumber  Incoming_Document_Entry_No
lineType                Type
itemNumber              No
unitOfMeasureCode       Unit_of_Measure_Code
quantity                Quantity
```

Operations die NIET ondersteund worden op NAV 2018 (`navision_nav2018.py:517-559`):
- `POST /incomingDocuments`
- `PATCH /salesOrders({id}) {incomingDocumentNumber: ...}`
- `POST /incomingDocuments({id})/attachments`
Deze worden **stilzwijgend overgeslagen** met `log.warning("nav2018_incoming_doc_skipped")`.
De header + lines worden wel gepost; reviewer moet de bron-mail NAV-zijdig
handmatig attachen. **Pre-conditie voor live**: PLX_IncomingDocument page moet
NAV-zijdig geëxposeerd worden voordat deze ops mee gaan.

Idempotency-guard (`navision_nav2018.py:485-510`): vóór de loop wordt `External_
Document_No eq '<bestelnr>'` gefilterd; bestaat al ⇒ short-circuit return met
`_dedup` autofill. Best-effort: probe-failure ⇒ doorgaan met create.

Trigger-aware enforce-rules in `nav_operations._assert_op_invariants`
(`integrations/nav_operations.py`, gerefereerd uit `navision_steps.py:30-34` docstring):
- `POST /salesOrders` body = `{customerNumber: ...}` exact (1 key).
- `POST .../salesOrderLines` body = `{lineType: "Item", itemNumber: ...}` exact.
- Elke `PATCH` body bevat exact 1 niet-marker-key.
Dit dwingt de single-field PATCH-pattern af zodat NAV's OnValidate-triggers één
voor één vuren (anders bypassen multi-field POSTs de NAV-side prijsberekening,
ship-to autofill, mix-discount, etc.).

Andere NAV-clients:
- `MockNavisionClient` (`navision_api.py:62-559`): in-memory store met
  trigger-emulatie (PATCH shipToCode ⇒ autofill shipToAddress; PATCH quantity ⇒
  mix-discount voor mix-eligible items). Persist naar
  `data/navision_mock/orders/<order_nr>.json`.
- `RealNavisionClient` (BC-stijl, `navision_real.py`): bestaat maar wordt voor de
  productie-tenant niet gebruikt (mode `real` vs `nav2018`).
- `ReplayNavisionClient` (`navision_real.py`): leest vaste fixtures uit
  `tests/fixtures/navision_replay.json` — voor regressie-tests.

NAV-master-data sync (`scripts/sync_navision_masters.py` of HTTP-job
`POST /api/admin/nav-sync`, `api/admin.py:518-559`): trekt PLX_Customer, PLX_Item,
PLX_ItemReference, PLX_ShipToAddress (en wat de operator selecteert) door
`_fetch_collection_safe` → upsert in mirror-tabellen. Job draait in
`asyncio.create_task` met polling via `GET /api/admin/nav-sync/{job_id}`.
Per-100-rows: `commit() + await asyncio.sleep(0)` om `/api/health` responsive
te houden (regel 256-257).

### 6.c Database

Tabellen (uit `backend/src/kwabo/db/models.py`):

| Tabel | Doel | Velden van belang |
|-------|------|-------------------|
| `klantenkaarten` | NAV-mirror van klanten + eigen velden | nav_klantnr (unique), naam, email, email_bestelling, is_4plus, mixprijzen, kredietlimiet, betalingsconditie |
| `klant_email_aliases` | extra e-mailadressen → klant_nr | klant_nr, email, label |
| `klant_documenten` | klant-leveringsvoorwaarden e.d. (geupload) | klant_nr, filename, doc_type, text_content |
| `oauth_config` | Microsoft Graph app-registratie | singleton id=1 |
| `oauth_tokens` | Microsoft Graph access+refresh tokens | singleton id=1 |
| `klantenkaart_artikelen` | klant-art-nr → kwabo-art-nr mapping (handmatig + history) | klant_nr, klant_artikelnr, kwabo_artikelnr |
| `prijsafspraken` | per (klant, kwabo_artikelnr) prijs + korting + type (standaard/mix/pallet/topcoat) | min_hoeveelheid |
| `artikel_matching_history` | self-learning: alle succesvolle matches | match_methode, was_correctie |
| `artikelkaarten` | NAV-mirror van items | kwabo_artikelnr (PK), naam, basis_eenheid, mixprijzen |
| `artikel_eenheden` | NAV-mirror van item-UoM-tabel | (kwabo_artikelnr, eenheid_code) PK, qty_per_base, is_mix_uom |
| `klantenkaart_ship_to` | NAV-mirror van ship-to-adressen (table 222) | (klant_nr, ship_to_code) PK |
| `artikel_kruisverwijzing` | NAV item reference (table 5717) | (klant_nr, klant_artikelnr) PK → kwabo_artikelnr |
| `artikel_pallet_kennis` | self-learning europallet | (kwabo_artikelnr, eenheid) PK, pallet_required, per_pallet, confidence |
| `order_log` | hoofdtabel: 1 rij per binnenkomende mail | id, email_id, status, klant_nr, navision_order_nr, **order_state (full JSON)**, stappen_log JSON, warnings JSON |

**Schema-evolutie**: `init_db()` (`db/session.py:96-98`) doet `SQLModel.metadata.create_all`
(idempotent CREATE TABLE IF NOT EXISTS) en daarna `_apply_additive_migrations()`
(`session.py:72-93`): voor elke entry in `_ADDITIVE_MIGRATIONS` (nu alleen
`klantenkaarten.mixprijzen`) checkt het of de kolom bestaat (PRAGMA on sqlite,
information_schema elders) en doet ALTER TABLE ADD COLUMN. Geen Alembic; geen
schema-drift-detectie.

**Connection pooling**: `_build_engine` (`session.py:15-33`):
- sqlite: `check_same_thread=False`.
- postgres: `poolclass=NullPool` (pgbouncer-transactionmode pooled er al) +
  `prepare_threshold=None` (anders crashen prepared statements op pgbouncer).
- engine is **module-level** (`session.py:36`); elke node opent eigen `Session(engine)`.

**Lokale DB-stand** (read-only inspectie via `python -c "import sqlite3"`):
```
artikel_eenheden                rows=0
artikel_kruisverwijzing         rows=0
artikel_matching_history        rows=0
artikel_pallet_kennis           rows=0
artikelkaarten                  rows=0
klant_documenten                rows=0
klant_email_aliases             rows=0
klantenkaart_artikelen          rows=37
klantenkaart_ship_to            rows=0
klantenkaarten                  rows=16    laatste update: 2026-05-21 08:17:24
oauth_config                    rows=1     laatste update: 2026-05-26 20:21:54
oauth_tokens                    rows=0
order_log                       rows=0
prijsafspraken                  rows=7
```

Conclusie lokaal:
- DB is leeg behalve seed-data. **Geen orders ooit lokaal verwerkt** (`order_log=0`).
- **NAV master-sync nooit lokaal gedraaid** (artikelkaarten, artikel_eenheden,
  artikel_kruisverwijzing, klantenkaart_ship_to allemaal 0).
- **Geen lokaal Graph-token opgeslagen** (`oauth_tokens=0`) — een lokale `pnpm dev`
  + uvicorn kan dus geen echte mailbox lezen.
- Alle echte data leeft op Supabase (productie). Die heb ik in deze audit NIET
  bevraagd (read-only beperking + geen prod-credentials voorhanden in deze sessie).

### 6.d Bestandsopslag & paden

`backend/src/kwabo/config.py:18-21,89-103`:
```
inbox_dir              = "../data/inbox"
processed_dir          = "../data/processed"
navision_mock_dir      = "../data/navision_mock"
incoming_documents_dir = "../data/incoming_documents"
llm_cache_dir          = "../data/llm_cache"    (in llm_cache.py:23, env LLM_CACHE_DIR)
```

Alle vijf zijn **relatieve paden**. Bij `Path(...).resolve()` worden ze ten
opzichte van **het huidige working directory** opgelost. De CWD wisselt:

- Lokaal via README `cd backend && uvicorn ...` ⇒ CWD = `C:\Kwabo\backend\` ⇒
  `../data/incoming_documents` = `C:\Kwabo\data\incoming_documents`.
- Railway Procfile/`railway.toml` `PYTHONPATH=src uvicorn ...` ⇒ CWD = de
  *deployed root*. Volgens README (`README.md:155-157`) is **Settings → Service
  → Root Directory = `backend`**, dus de deployed root is `backend/`. Dan resolve
  `../data` naar `/data` of `/workspace/data` afhankelijk van Railway-internals.
- Docker-compose (`docker-compose.yml:7-11`) mountet `./data:/app/data` met
  containerwerkdir `/app`. Hier zou `../data` falen tenzij de container ook
  `/app/backend` als WORKDIR heeft.

`Path("../data/incoming_documents").resolve()` op Railway zal:
- `target_dir.mkdir(parents=True, exist_ok=True)` proberen — succeeds zolang
  de parent writable is (Railway containers draaien als non-root; afhankelijk
  van of `/data` of `/workspace/data` of `/tmp/...data` writable is).
- **In alle gevallen op Railway: ephemere filesystem**. Elke deploy / restart
  wist de inhoud. Een mail-eml die op dag 1 is gesaved, is bij de eerste deploy
  daarna weg. De DB-rij `order_log.order_state.incoming_document_path` blijft
  echter wijzen naar dat (nu niet meer bestaande) pad.

Geen tests dekken deze edge-case voor productie. Ik vond geen volume-mount / S3 /
Supabase-Storage handling in de codebase — alle file-IO is local-disk.

Lokale realiteit (lijst-output): `data/inbox/`, `data/processed/`,
`data/navision_mock/orders/` zijn alle leeg (0 bytes aan inhoud). `data/incoming_documents/`
en `data/llm_cache/` bestaan zelfs niet als directory (ze worden lazily aangemaakt
bij eerste gebruik).

---

## 7. Configuratie

Bron: `backend/src/kwabo/config.py` (pydantic-settings, leest `.env` en
environment variables). Aliassen via `AliasChoices` waar nodig.

| Env-var | Default | Doel |
|---------|---------|------|
| `ANTHROPIC_API_KEY` | "" | Claude API key (zonder is alles dood) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | LLM-model voor classify+extract |
| `DATABASE_URL` | `sqlite:///./kwabo.db` | local sqlite of Supabase URI |
| `NAVISION_MODE` | `mock` | `mock` / `replay` / `real` / `nav2018` |
| `EMAIL_MODE` | `file_drop` | `file_drop` / `graph` / `imap` |
| `INBOX_DIR` | `../data/inbox` | file-drop bron (relatief — zie §6.d) |
| `PROCESSED_DIR` | `../data/processed` | file-drop verplaatst-naar |
| `NAVISION_MOCK_DIR` | `../data/navision_mock` | mock-NAV write-target |
| `INCOMING_DOCUMENTS_DIR` | `../data/incoming_documents` | gesavede .eml's |
| `LANGCHAIN_TRACING_V2` | `false` | LangSmith aan/uit |
| `LANGCHAIN_PROJECT` | `kwabo-order-intake` | LangSmith project naam |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `MAIL_MODE` | `log` | `log` / `smtp` / `graph` voor bevestiging-mail |
| `LLM_CACHE_MODE` | `on` | `on` / `read-only` / `off` |
| `LLM_CACHE_DIR` | `../data/llm_cache` | sha256-keyed file cache |
| `KWABO_TEST_MODE` / `TEST_MODE` | `off` | `on` mount /api/testing/* |
| `ADMIN_PASSWORD` | "" | LEEG = auth DISABLED (dev). Productie MOET zetten |
| `JWT_SECRET` | `dev-only-change-me-in-prod` | HMAC secret voor bearer tokens |
| `JWT_TTL_HOURS` | `24` | bearer-token TTL |
| `SIGNED_URL_SECRET` | "" | HMAC voor PDF-download tokens (leeg = afgeleid van JWT_SECRET) |
| `SIGNED_URL_TTL_SECONDS` | `300` | TTL signed-URL voor bijlagen (5 min) |
| `MAIL_POLL_INTERVAL_SECONDS` | `0` | **0 = poller UIT**; ≥30 = poll-interval |
| `EUROPALLET_ARTIKELNR` | `19820` | artnr voor europallet-regel |
| `FRONTEND_URL` | `http://localhost:3000` | OAuth-callback redirect-target |
| `NAV_BASE_URL` | "" | `https://<host>:1153/<svc>/ODataV4` |
| `NAV_COMPANY` | "" | Display-name met spaties, niet quoten |
| `NAV_USERNAME` | "" | service-account |
| `NAV_PASSWORD` | "" | Web Service Access Key |
| `NAV_VERIFY_SSL` | `true` | false alleen voor staging met self-signed |
| `NAV_PAGE_SALES_ORDER` | `PLX_SalesOrder` | per-deployment overschrijfbaar |
| `NAV_PAGE_SALES_ORDER_LINES` | `PLX_SalesOrderLines` | … |
| `NAV_PAGE_CUSTOMER` | `PLX_Customer` | … |
| `NAV_PAGE_ITEM` | `PLX_Item` | … |
| `NAV_PAGE_ITEM_REFERENCE` | `PLX_ItemReference` | … |
| `NAV_PAGE_SHIP_TO` | `PLX_ShipToAddress` | … |
| `NAV_PAGE_ITEM_UOM` | `PLX_ItemUnitOfMeasure` | … |
| `KWABO_CORS_EXTRA` | "" | Extra CORS-origins comma-sep |

Tevens hardcoded in main.py `_cors_origins` (`main.py:34-50`):
- `http://localhost:3000`, `http://127.0.0.1:3000`
- `https://kwabo-pilex.vercel.app`, `https://kwabo-frontend.vercel.app`
- Plus regex `https://.*\.vercel\.app$` voor preview deployments.

Wat **hardcoded** is en geen env-var heeft (mogelijk een go-live-irritant):
- `EUROPALLET_ARTIKELNR` heeft wel env-override sinds `0088b9e` maar **wordt
  niet door alle code-paden via settings gelezen** — `EUROPALLET_ARTIKELNR = "19820"`
  staat ook in `integrations/navision_steps.py:68` (module-level constant, niet
  meer gebruikt na de fix; wel "kept for backwards-compat" per comment).
- Sanity-rules grenzen in `validate_prices.py:63-69` (PAL>100, STUK>50000,
  ROL>5000) zijn hardcoded.
- Fuzzy-threshold `>=80` voor descriptie-match in `match_articles.py:73` is hardcoded.
- LLM cache TTL: er IS geen TTL — bestanden blijven voor altijd staan.

### Lokaal vs productie

| Aspect | Lokaal (dev) | Productie (Railway) |
|--------|--------------|---------------------|
| DB | SQLite `./kwabo.db` | Supabase Postgres (pgbouncer port 6543) |
| Mailbox | `file_drop` of geen | `graph` + OAuth |
| NAV | `mock` of `replay` | `nav2018` met PLX_*-pages |
| Auth-gate | `ADMIN_PASSWORD=""` ⇒ uit (dev) | gezet, dus aan |
| Filesystem | persistent | **ephemeral** (zie §6.d) |
| Poller | uit (interval=0) | naar believen aan (env zetten) |
| LLM cache | local disk | local disk (gaat verloren bij deploy) |

---

## 8. Hoe draait het

### Processen

**Eén proces** voor backend: `uvicorn kwabo.main:app`. Het is **geen** multi-process
setup; geen aparte poll-worker. De achtergrond-poll is een `asyncio.Task` die in
`lifespan` wordt gespawned (`main.py:96-100`):
```python
poll_task = asyncio.create_task(_mail_poll_loop(interval))
```
Voorwaarden: `email_mode != "file_drop"` (`main.py:68-70 _mail_poll_loop`) EN
`mail_poll_interval_seconds >= 30` (`main.py:98`). Bij 0 (default) of 1-29:
geen taak.

Frontend: `next start` (productie) of `next dev --webpack` (dev). Single process.

### Startvolgorde

1. Backend `init_db()` (create_all + additive migraties) — `main.py:92`.
2. `seed(s)` — `main.py:93-94` (zeer beperkt; vult 16 klantenkaarten op een lege DB).
3. App routes registreren (auth gate via `Depends(require_admin)` op alle routers
   behalve `/api/health`, `/api/auth/*`, `/api/mailbox/oauth/*`,
   `/api/orders/{id}/bijlagen` — die laatste valideert via signed URL).
4. Mail-poll loop (optioneel) start na 30s initiele delay.
5. Frontend leest `NEXT_PUBLIC_API_BASE` en `NEXT_PUBLIC_SUPABASE_URL` op build-time.

### Poorten

- Backend: `$PORT` (Railway zet die) of `8000` (lokaal).
- Frontend: `3000` (`pnpm dev`) of Vercel-routing (productie).

### Afhankelijkheden

- Frontend → Backend (REST + signed URLs).
- Backend → Anthropic (HTTPS naar `api.anthropic.com`).
- Backend → Supabase (Postgres pooler op 6543).
- Backend → NAV (HTTPS naar `sf-NNNNNN.dynamicstocloud.com:1153/.../ODataV4`).
- Backend → Microsoft Graph + login.microsoftonline.com (OAuth + mail-fetch).

Geen daemons, geen Celery, geen queue, geen Redis. Alles in-process.

---

## 9. API / frontend surface

### Backend routers (per `main.py:136-173` include-volgorde)

Auth-gated tenzij anders vermeld.

**`/api/auth/*`** (`api/auth.py`)
- `POST /login` — `{password}` → `{token, expires_at}` (HMAC bearer, 24h TTL).
- `POST /logout` — no-op (client-side cookie wipe).
- `GET /me` — echo van token-claims.

**`/api/mailbox/*`** (`api/mailbox.py`)
- Public sub-router: `GET /oauth/start` (302 → Microsoft), `GET /oauth/callback`
  (302 → frontend `/email?connected=1`).
- Admin: `GET /status` (mode, connected, account_email, expires_at),
  `GET|PUT /oauth/config`, `POST /oauth/disconnect`.

**`/api/orders/*`** (`api/orders.py`)
- Public sub-router: `GET /{id}/bijlagen?naam=&disposition=&token=` — PDF/attachment
  download via signed URL (token van `bijlagen-token`).
- Admin: `GET ""` (list), `GET /{id}` (detail), `PATCH /{id}` (klant/regels/adres/opm),
  `POST /{id}/approve[?force=true]` (push naar NAV), `POST /{id}/reject`,
  `DELETE /{id}?confirm=true` (hard-delete; vereist `?confirm=true`),
  `GET /{id}/nav-debug` (volledige op-trail van push), `POST /{id}/bijlagen-token`
  (mint signed URL), `POST /{id}/incoming-doc` (upload eml/pdf/jpg als bron).

**`/api/orders/*` (preview)** (`api/preview.py`)
- `GET /{id}/navision-preview` — `{operations[], expected_post_count,
  expected_patch_count, status, missing_count}`.
- `PATCH /{id}/patch-field` — per-veld correctie + invalideer nav_operations cache.
- `GET /{id}/needs-review` — actuele list+count.

**`/api/klanten/*`** (`api/klanten.py` — niet gelezen in detail) — CRUD voor klantenkaarten + aliases + documenten.

**`/api/artikelen/*`** (`api/artikelen.py` — niet gelezen in detail) — search.

**`/api/audit/*`** (`api/audit.py` — niet gelezen in detail) — stats over order_log.

**`/api/intake/*`** (`api/intake_trigger.py`)
- `POST /scan` — leest mailbox client.list_new (10 per batch op Graph), draait
  ingest+extras per mail, return `{processed[], errors[], partial, batch_size}`.
- `POST /upload` — `.eml` file-upload, run ingest + extras, return
  `{email_id, log_id, sub_orders[]}`.
- `POST /run-file?path=...` — file path replay (alleen lokaal).

**`/api/logs/tail?lines=`** (`api/logs.py` — niet gelezen) — tail kwabo.log.

**`/api/prijsafspraken/*`** (`api/prijsafspraken.py` — niet gelezen) — CRUD.

**`/api/diagnostics/*`** (`api/diagnostics.py`)
- `GET /nav?page=…` — probe NAV connectivity (returns ok, status, url, preview).
- `GET /nav/services` — lijst beschikbare OData entity sets.
- `GET /nav/raw?path=&under_company=` — raw GET tegen NAV (debug).
- `GET /config` — non-sensitive runtime config dump (env-aanwezigheid + key-lengte).

**`/api/admin/*`** (`api/admin.py`)
- `GET /db-counts` — `{klanten, artikelen, kruisverwijzingen, ship_to_adressen}`.
- `POST /nav-sync?domains=customers,items,cross_ref,ship_to&dry_run=` — async job.
- `GET /nav-sync/{job_id}`, `GET /nav-sync` — poll/lijst.

**`/api/testing/*`** (`api/testing.py`) — alleen als `TEST_MODE=on`. Niet ingelezen.

**Root**:
- `GET /` — `{name, version}`.
- `GET /api/health` — `{status: "ok"}`.

### Frontend pages (`frontend/app/`)

- `/` — order queue (`page.tsx`, `queue-filters.tsx`).
- `/login` — admin login (zet `kwabo_admin` cookie + Authorization Bearer).
- `/orders/[id]` — split-view review (`order-review.tsx`).
  - Linkerkolom: `EmailSourceViewer` (per bijlage tab) +
    `IncomingDocumentPanel` (handmatige bron-doc upload).
  - Middenkolom: `ExtractSummary` + bewerkbare velden (klant, bestelnr, datum,
    afleveradres) + `ShipToPicker` + `MixprijzenBadge`.
  - Rechterkolom: `OrderLinesTable` + `EuropalletEditor` + `NavOperationsPreview` +
    `NavFailureBanner` + `NeedsReviewBanner`.
- `/klanten/[nr]` — klantbeheer met `afzenders-tab`, `documenten-tab`, `prijsafspraken-tab`.
- `/audit` — stats dashboard.
- `/logs` — kwabo.log tail.
- `/email` — Microsoft Graph OAuth-pagina.
- `/api/*` — Next.js route handlers (niet ingelezen in detail; vermoedelijk
  proxy + signed-URL helpers).

`middleware.ts` is aanwezig maar niet in detail ingelezen. Vermoedelijk een
auth-gate die redirects naar `/login` als geen geldige `kwabo_admin` cookie.
`ONGEVERIFIEERD`.

---

## 10. Implementatiestatus

| Onderdeel | Status | Bewijs / Toelichting |
|-----------|--------|----------------------|
| LangGraph 10-node pipeline | VOLLEDIG | `graph.py:32-56` build_ingest_graph; alle 10 node-functies aanwezig en getest |
| Sub-order graph (multi-order mails) | VOLLEDIG | `graph.py:59-82`; runner `_run_extras` met per-sub try/except (`runner.py:36-94`) |
| Finalize-graph (push + confirmation) | VOLLEDIG | `graph.py:85-92` |
| `MockNavisionClient` | VOLLEDIG | trigger-emulatie incl. ship-to-autofill en mix-discount (`navision_api.py:62-559`) |
| `Nav2018ODataClient` (PRODUCTIE) | VOLLEDIG | header+lines pad incl. composite-key URLs; **incoming-doc bundle skipt stil** (zie §6.b) — actie nodig op NAV-zijde |
| `RealNavisionClient` (BC-stijl) | HALF | bestaat maar de productie-tenant gebruikt nav2018. Voor BC zou je het moeten verifiëren; `ONGEVERIFIEERD` |
| `ReplayNavisionClient` | VOLLEDIG | t.b.v. tests |
| `FileDropEmailClient` | VOLLEDIG | klein detail: `_path_by_id` is in-memory; herstart kan tot duplicaten leiden bij file_drop (zie §12) |
| `GraphEmailClient` | VOLLEDIG | inclusief OAuth-refresh-flow; **drempel `>=30s` mail-poll interval** mag niet vergeten worden in env |
| `IMAPEmailClient` | DOOD / NOT IMPL | `email_client.py:247-249` raised `NotImplementedError` — by design placeholder |
| OAuth-flow (Microsoft) | VOLLEDIG | `api/mailbox.py:236-393`; CSRF via state-token; tokens in DB |
| Admin auth (HMAC bearer) | VOLLEDIG | `api/auth.py`; in dev (`ADMIN_PASSWORD=""`) **uit** |
| Signed-URL bijlage-download | VOLLEDIG | `api/orders.py:52-119` + frontend `email-source-viewer.tsx:82-101` |
| Trigger-aware NAV push (single-field PATCH) | VOLLEDIG | `_assert_op_invariants` + composer + executor; meerdere tests |
| Idempotency (dedup op externalDocumentNumber) | VOLLEDIG | nav2018 én mock checken beide vooraf; tests aanwezig |
| LLM file-cache | VOLLEDIG | content-addressable; SHA256 key; modes on/read-only/off |
| Frontend order-review UI | VOLLEDIG | split-view; provenance-badges; force-approve |
| Frontend `EmailSourceViewer` met PDF-iframe | VOLLEDIG | inline preview + open in nieuw tabblad |
| Self-learning artikel-history | VOLLEDIG | `repo.add_history()` na approve corrigeert + biedt fallback |
| Self-learning europallet | VOLLEDIG | `_persist_pallet_feedback` (`orders.py:616-685`) |
| NAV master-data sync (HTTP-job + CLI) | VOLLEDIG | `api/admin.py:240-451`; CLI `scripts/sync_navision_masters.py` |
| Achtergrond mail-poll | VOLLEDIG | `main.py:60-115`; **default uit (interval=0)** |
| Mail-bevestiging | HALF | `mail_sender.py` met `log`/`smtp`/`graph`. **SMTP/Graph send niet geverifieerd door mij** (`ONGEVERIFIEERD`) |
| Alembic migraties | DOOD | dep wel in requirements, geen `alembic.ini`/`migrations/`. Schema-evolutie via custom mini-migrator (`session.py:42-93`) |
| `email-validator` dep | MOGELIJK DOOD | geen runtime-gebruik gevonden via grep |
| `sse-starlette` dep | MOGELIJK DOOD | geen runtime-gebruik gevonden via grep |
| `integrations/sharepoint.py` | ONGEVERIFIEERD | bestand bestaat; script `sync_sharepoint.py` ook. Niet ingelezen. |
| `integrations/document_extractor.py` | ONGEVERIFIEERD | niet ingelezen; vermoedelijk dood (Claude Vision-pad neemt over) |
| `prompts/extract.txt` (v1) | MOGELIJK DOOD | `llm_extractor.py:23` laadt `extract_v2.txt`; geen verwijzing naar v1 gevonden |
| Test-mode endpoints | VOLLEDIG (achter `TEST_MODE=on`) | `api/testing.py` (niet ingelezen) |
| Docker-compose | VOLLEDIG (maar lokaal!) | bind-mount `data/` voor persistence; **niet relevant voor Railway** |
| README accuratesse | NIET ACCURAAT | claimt "7-node pipeline" (`README.md:6`) en `EMAIL_MODE=file_drop` als default-werkend; werkelijkheid is 10 nodes en Graph is operationeel pad |

TODO/FIXME comments (steekproef via inspectie):
- `intake_trigger.py:91-92`: marker `incoming_document_save_failed=True` wordt
  gezet, maar nergens in compose/push wordt op deze marker gereageerd. Het is dus
  observability-only.
- `navision_steps.py:65-68`: "Kept as module-level for backwards-compat" — dode constante.
- `navision_nav2018.py:454-462`: incoming-doc-ops worden actief geskipt; comment
  zegt expliciet "Either add a translation rule or skip this op in the composer."
  Acceptable as long as ops blijven skippen.

Volgens `STATUS.md` / `OFFERTE_STATUS.md` / etc. zou een uitgebreidere check
mogelijk zijn — die heb ik niet inhoudelijk doorgenomen (te lang voor deze
audit-pass). Hou er rekening mee dat README's en STATUS.md ouder zijn dan de
code.

---

## 11. Tests

40 testbestanden in `backend/tests/`. Geen testdraai uitgevoerd in deze audit
(de instructies vroegen read-only; ik wilde geen `data/` of `kwabo.db`
mutaties). De testbestanden bevatten o.a.:

- `test_pipeline_e2e.py` — full pipeline op fixture .eml's
- `test_regression.py` — 17 sample emails (zie `tests/test_data/emails/`)
- `test_navision_steps.py` — composer-rules (geüpdate na `0088b9e`)
- `test_navision_nav2018.py` — NAV 2018 client unit-tests
- `test_navision_mock.py` — mock-trigger emulatie
- `test_nav_stepwise.py` — invariant-checks
- `test_navision_dedup.py` — idempotency
- `test_navision_logging.py` — error-logging shape
- `test_match_articles_kruisverwijzing.py` / `_needs_review.py`
- `test_apply_mixprijzen.py`
- `test_pallet_logic.py`
- `test_seed_pallet_history.py`
- `test_compose_unmatched_guard.py` (compose raised ValueError bij 0 matched)
- `test_api.py` / `test_api_approve_pallet_feedback.py` / `test_api_incoming_doc.py`
  / `test_api_mailbox.py` — endpoint-tests
- `test_auth.py` — HMAC token issue/verify
- `test_orders_bijlagen.py` / `test_orders_admin_endpoints.py`
- `test_email_client_factory.py` / `test_email_parsing.py`
- `test_extract_cache.py` / `test_classify_cache.py` / `test_llm_cache.py`
- `test_forwarded_parser.py`
- `test_kredietlimiet.py`
- `test_mail_and_sanity.py`
- `test_mock_uom_trigger.py`
- `test_prijscascade.py`
- `test_admin_ship_to_sync.py`
- `test_db.py` / `test_db_nav_mirrors.py`
- `test_extract_post.py`
- `test_fase1_preventieve_fixes.py` — recent toegevoegd (commit `4ccc535`)

`conftest.py` is aanwezig (niet ingelezen). `Makefile` heeft targets `test`,
`test-regression`, `test-10x`, `cache-clear`.

De kwabo.log bevat trace van een recente pytest-run (`testserver` URLs in
`backend/kwabo.log` van `2026-05-26 22:50:04`) — vóór de huidige commits — wat
suggereert dat **de tests recent zijn uitgevoerd en (deels) groen waren**. Een
verse `make test` zou dat bevestigen. `ONGEVERIFIEERD` in deze audit.

E2E frontend-tests: `frontend/tests/` met `@playwright/test`. Niet ingelezen.

---

## 12. Geconstateerde probleemgebieden

Per gerapporteerd symptoom: root-cause hypothese met code-bewijs.

### 12.A — `{"detail":"Originele .eml niet gevonden — bestand verwijderd uit inbox/processed?"}` bij openen van gekoppeld bestand

**Bron van de error**: `api/orders.py:514-517`. Triggert wanneer `_find_eml_path`
(`api/orders.py:132-166`) `None` teruggeeft.

`_find_eml_path` zoekvolgorde:
1. `state["incoming_document_path"]` — moet bestaan op disk (`p.exists()`).
2. `state["source_path"]` — skipt als string begint met `"graph://"`; moet bestaan op disk.
3. Scan `settings.inbox_path` + `settings.processed_path` op `*.eml` en
   matcht via `_short_hash(raw)` op `email_id`.

Voor productie-mails uit Graph:
- `source_path = "graph://<msg_id>"` (`email_client_graph.py:193`). Stap 2 skipt
  altijd vanwege de prefix.
- `incoming_document_path` werd gezet door `_persist_source_eml`. **MAAR**:
  - Het pad is een absoluut pad ten tijde van schrijven (`p.resolve()`).
  - Op Railway is `data/incoming_documents/` ephemeral. Na een container-restart
    (deploy, OOM-kill, healthcheck-fail-recovery) zijn alle gesavede .eml's weg,
    terwijl `order_state.incoming_document_path` nog wijst naar `/data/incoming_documents/by_email_id/<id>.eml`.
  - Stap 3 (legacy scan op inbox+processed) faalt in Graph-mode altijd: er staan
    daar geen .eml's voor Graph-mails.

**Wat de gebruiker ziet**: voor élke mail die vóór de laatste deploy is verwerkt
en waarvan de attachment niet meer op disk staat: 404 met die misleidende
message ("verwijderd uit inbox/processed?" suggereert handmatige actie; in
werkelijkheid is het de ephemere FS).

**Andere root-cause**: ook bij een **mailbox die ooit lokaal liep en daarna naar
prod gemigreerd is** zal het pad nooit valid zijn op de andere host. De DB
houdt de absolute paden van de host waar de mail bij intake werd verwerkt.

**Recente patch `adde51b`** (`fix(pdf): _find_eml_path checks incoming_document_path first`)
heeft de lookup-volgorde gefixt zodat stap 1 vóór stap 2 komt — maar lost de
ephemere-FS root-cause niet op. Voor mails die wél recent verwerkt zijn én de
container niet herstart is, werkt het pad. Voor oude mails: nog steeds 404.

**Wat ontbreekt voor robuustheid**:
- .eml opslag in een persistente backing-store (Supabase Storage of S3-bucket)
  i.p.v. local disk.
- OF: alternative content-recovery via Graph (`GET /me/messages/{id}/$value`
  re-fetch on demand) wanneer `incoming_document_path` niet meer bestaat.

### 12.B — Geen nieuwe mails binnen om te testen (data uit begin mei)

**Root-cause-cascade**:

1. **Default `mail_poll_interval_seconds = 0`** (`config.py:53`). De achtergrond-
   poller start alléén als operator dit in Railway env op `>=30` zet. De previous
   sessie-summary bevestigt: *"User needs to set `MAIL_POLL_INTERVAL_SECONDS=300`
   in Railway env vars"* — dus dit is **nog niet gezet**. Geen poll = geen
   `/api/intake/scan` = geen nieuwe mails.
2. **Geen aparte cron** in Railway / Vercel; alles in-process. Als de uvicorn-app
   niet draait of `lifespan` niet start, gebeurt er ook niets.
3. **Graph-token kan verlopen zijn**. `oauth_tokens.refresh_token` wordt
   bewaard. `_refresh_token()` (`email_client_graph.py:97-157`) faalt als:
   - `cfg.tenant_id` of `cfg.client_id` leeg
   - `refresh_token` leeg (vereist `offline_access` scope op consent-moment)
   - Microsoft response status != 200 → `RuntimeError`.
   De previous sessie-summary bevestigt: *"User needs to re-login OAuth at /email
   for pilex@kwabo.nl (Graph token expired)"*. Dat is **een tweede vereiste
   actie** los van de poller.
4. **Lokaal**: ik kan niet de poller voor productie reproduceren want
   `EMAIL_MODE=file_drop` is default en de inbox is leeg. Een lokale `pnpm dev`
   + uvicorn zou met `EMAIL_MODE=graph` ook niet werken want `oauth_tokens` is
   leeg in de lokale DB.

**`mail_poll_skipped` event** (`main.py:69`) zou getriggerd zijn bij
`email_mode=file_drop`, maar de poller wordt zelfs niet opgestart wanneer
`interval=0` (`main.py:97-98`). Er is dus geen heartbeat-log "ik draai/niet";
operator moet aan de hand van `last_error` / `account_email` / `expires_at` in
`/api/mailbox/status` debuggen.

**Inbox-pending getal** (`api/mailbox.py:96-109`) is alleen relevant voor
`file_drop`, niet voor `graph` — voor Graph telt dit dus niet als "wachtrij".

Conclusie: drie acties nodig om mails weer te zien:
1. Railway env `MAIL_POLL_INTERVAL_SECONDS=300` (of een ander getal ≥30).
2. Microsoft Graph: re-login via dashboard `/email`-pagina (nieuwe
   refresh_token verkrijgen).
3. Bevestigen dat het Azure app-registration nog steeds `offline_access`
   geconsentd heeft (anders krijg je een access_token zonder refresh).

### 12.C — Zelfde .eml-fout bij handmatig uploaden van orders

Bij `/api/intake/upload` (`intake_trigger.py:131-158`):
- `parse_eml_bytes(content)` ⇒ `RawEmail` met `email_id = sha256(content)[:16]`,
  `source_path = None`, `raw_eml = content`.
- `_persist_source_eml(raw.raw_eml, raw.email_id)` ⇒ schrijft naar
  `data/incoming_documents/by_email_id/<email_id_hash16>.eml` en zet
  `state["incoming_document_path"]`.
- Pipeline draait.
- Geen mark_seen (geen mailbox).

Voor **een geüploade .eml** geldt **dezelfde ephemere-FS problematiek** als
12.A: na container-restart is het bestand weg. Plus:
- `source_path` is `None` (geen `graph://` prefix, maar ook geen lokaal pad).
- Stap 3 in `_find_eml_path` (scan inbox+processed) faalt — `processed/` bevat
  alleen .eml's die via file_drop verwerkt zijn (`shutil.move`); geüploade
  .eml's komen daar nooit terecht.

Een **secondaire variant** van de bug ontstaat bij handmatige uploads via
`POST /api/orders/{id}/incoming-doc` (`api/orders.py:688-757`). Die schrijft
naar `settings.incoming_documents_path / str(order_id) / safe_name` en zet
`state["incoming_document_path"]`. Hierbij is `safe_name` géén `.eml` maar
typisch een PDF — dus `_extract_attachment_bytes` (`api/orders.py:175-212`)
zou `email.message_from_bytes(raw)` proberen op een PDF en falen (de loop
vindt geen `part.get_filename()` = wanted_name).

Praktisch: als de reviewer een PDF heeft geüpload via "/incoming-doc", werkt
het PDF-iframe in de viewer via een **andere** route: niet via `_find_eml_path`
+ `_extract_attachment_bytes`, maar via Vercel SSR-side weet ik niet of er een
aparte download-helper bestaat (`api/preview.py` heeft die niet). **ONZEKER:
moet ik de frontend-route ` /api/orders/[id]/incoming-doc-download` checken om
zeker te weten dat de geüploade PDF terug-leesbaar is.**

Verder: de `incoming-doc` endpoint heeft een race tussen de eerste en de tweede
`Session(engine)` (`orders.py:699-700` vs `:739-751`). De eerste session leest
state om te valideren dat de order bestaat; de tweede schrijft het pad. Tussen
die twee kan een tweede HTTP-request gelijktijdig hetzelfde pad schrijven →
race-condition (last-write-wins). Niet kritisch.

### 12.D — Snelheid is erg traag

Geïdentificeerde knelpunten (geordend op vermoedelijke impact):

1. **`match_articles_node` doet sequentiële NAV-calls per regel**
   (`nodes/match_articles.py:105-123`). Elke regel doet 1-3 `await nav.get_item(...)`
   plus optioneel 1 `await nav.search_items(...)`. Tien orderregels ⇒ tot 60 NAV
   round-trips serieel. NAV 2018 OData call-latency in tests-runs lokaal is
   ongeverifieerd, maar productie netwerk-rondreis naar `sf-NNNNNN.dynamicstocloud.com:1153`
   per call ≈ 200-500 ms zou betekenen 12-30 sec puur voor matching. **Hoge impact**.
2. **`Nav2018ODataClient` wordt per node opnieuw geïnstantieerd**
   (`navision_api.py:574-578 get_navision_client()` retourneert een **nieuwe**
   `Nav2018ODataClient` elke call, die in z'n constructor een **nieuwe
   `httpx.AsyncClient`** opent — `navision_nav2018.py:186-189`). Geen connection-pool
   re-use over de pipeline; geen `aclose()` na gebruik in nodes (alleen in probe-
   endpoints) ⇒ **resource-leak per request** (sockets/file descriptors).
3. **`validate_prices_node` opent een TWEEDE session voor meta-update**
   (`nodes/validate_prices.py:95`). Per order dus 2 DB-connecties + per-regel
   `repo.best_match(...)` query. Niet katastrofaal (~10 ms per query op
   Postgres met index), maar onnodig.
4. **LLM Vision call** (`integrations/llm_extractor.py:131-141`): synchroon,
   `max_tokens=16000`. Een PDF-vision-extractie van Claude Sonnet 4.5 duurt
   typisch 8-25 sec. Wordt gecached (`cache_get` op SHA256 van blocks). Cache-hit
   = ms; cache-miss = veel seconden. **Hoogste impact bij eerste verwerking**.
5. **Cache invalideert bij elke kleine wijziging**: cache_key is sha256 van
   `system + json.dumps(blocks)` (`llm_extractor.py:117-123`). Elke change in
   subject, timestamp, of attachment-bytes ⇒ cache miss. Re-upload van dezelfde
   PDF onder andere naam ⇒ cache miss. Geen content-based dedup.
6. **`select_ship_to_node` opent eigen session zonder repo-arg**
   (`select_ship_to.py:105`). Verwaarloosbaar individueel maar elke node opent
   eigen connection ⇒ N connecties per order. Op pgbouncer transaction-pooler
   met `NullPool` betekent elke connect een **fresh psycopg-handshake**
   (TLS-handshake + auth) — significant trager dan pooled connections, en
   pgbouncer ziet alle verschillende prepared-statements die er niet zijn
   (`prepare_threshold=None` lost dat op qua compat maar niet qua latency).
7. **JSON-roundtrip per save**: `order_log.order_state` wordt elke push
   opnieuw `json.dumps`/`json.loads` (na `compose`, na `push_navision`, na
   `approve` — minimaal 4 keer per order). Voor grote orders (zie size_warning
   `>500KB` in `push_navision.py:184-189`) kan dit ook spitsen vertragen.
8. **NAV-master-sync block-mode**: De HTTP-job draait `await asyncio.sleep(0)`
   per 100 rijen om event loop niet te blokkeren (`api/admin.py:292-294`), maar
   de aanroeper moet polled `GET /api/admin/nav-sync/{job_id}` doen — geen WebSocket.
   Wel correct geïmplementeerd; geen blocker.
9. **PDF parsing**: `pdfplumber.extract_tables()` is bekend langzaam voor
   tabel-rijke PDFs. Per intake ≥1x per PDF. Wordt al rekening mee gehouden
   (subprocess pdftotext fallback). Verwaarloosbaar t.o.v. LLM call.
10. **Geen async voor DB-IO**: `sqlmodel` Session is sync. Elke session-call
    blokkeert de event loop. In dezelfde request-flow met awaits naar NAV/LLM
    blokken zo lang. Niet ideaal voor concurrency-throughput.

Verwachte total-roundtrip per nieuwe mail (10 regels) in productie (ruw geschat):
- intake + classify (cache hit): 0.5s
- extract (cache miss, Vision): **15-25s**
- match_customer: 1 NAV call (~0.5s)
- match_articles: 10 regels × ~3 NAV calls = **5-15s** serieel
- ship_to + mixprijzen + europallet + validate_prices: 1-2s DB
- compose_order: 0.1s
- compose_navision_operations: pure func: <50ms

**Totaal: 25-45 sec per nieuwe mail**. Bij 10 mails-per-scan-batch: ~5 min
worst-case (precies de Railway request-timeout, vandaar de wall-clock cut van
240s in `scan_inbox`, `intake_trigger.py:58,71-78`).

---

## 13. Open vragen voor on-site test

Onderstaande punten kun je alleen vanuit de productie-omgeving / NAV / Microsoft-
tenant verifiëren — vanuit deze repo-checkout niet:

1. **Supabase DB-stand**: hoeveel rijen in `order_log`, wanneer was de laatste
   `created_at`/`updated_at`, hoeveel orders status `failed`?
2. **Heeft Railway daadwerkelijk `MAIL_POLL_INTERVAL_SECONDS` gezet?** En zo
   ja, draait de poller (zoek `mail_poll_tick` in Railway-logs)?
3. **Is de huidige `oauth_tokens.expires_at` in productie nog geldig?** Zo
   niet: laat Cas opnieuw inloggen via `/email`.
4. **Bestaat `data/incoming_documents/by_email_id/<some_hash>.eml` daadwerkelijk
   in de Railway-container nu?** Een `ls /app/data/incoming_documents/by_email_id`
   (via railway run / ssh-shell) bevestigt of er .eml's persistent zijn na de
   laatste deploy.
5. **NAV-zijdige `PLX_IncomingDocument` page**: is die nu wel/niet geëxposeerd?
   Bevestigd worden via `GET /api/diagnostics/nav/services` en zoek naar
   "PLX_IncomingDocument". Zonder die page blijft 6.b's "skipped"-pad de norm.
6. **NAV-side `Permission` op PLX_ShipToAddress / PLX_ItemReference**: krijgen
   we 404s die de comment in `navision_nav2018.py:269-275` noemt? Probe per
   page via `/api/diagnostics/nav?page=PLX_ShipToAddress`.
7. **Is de NAV-master-sync gedraaid in productie?** `GET /api/admin/db-counts`
   moet niet 0 zijn voor `artikelen` en `kruisverwijzingen`. Lokaal is dat 0.
8. **Werkt de bevestigingsmail in productie?** `mail_mode=log` ⇒ alleen log.
   `mail_mode=graph` of `smtp` ⇒ daadwerkelijk versturen. Niet geverifieerd.
9. **Frontend `middleware.ts`**: wat doet het precies? Vermoedelijk auth-redirect
   maar moet ingelezen voor 100% zekerheid (vooral de cookie-name match).
10. **Frontend `/api/orders/[id]/incoming-doc-download` of `bijlagen-download`**:
    er is wel een signed-URL pad voor mail-attachments via `_extract_attachment_bytes`
    (orders.py), maar ik zag geen tweede route voor **geüploade** PDFs uit
    `/incoming-doc`. ONZEKER of die werken in de browser.
11. **Railway/Vercel concurrent processes**: zijn er meerdere uvicorn-workers
    (`gunicorn -k uvicorn.workers.UvicornWorker -w N`)? In dat geval is de
    in-process mail-poll loop **per worker actief** ⇒ ge-N-voudigt
    `/api/intake/scan` invocations. Procfile heeft geen `-w` flag, en
    railway.toml ook niet, dus standaard 1 worker — maar dit moet bevestigd
    worden in Railway-dashboard.
12. **Disk-quota / writability** op Railway voor `/data/...` of `/workspace/data/...`:
    krijgen `_persist_source_eml` of `_persist_pallet_feedback` schrijf-errors?
    Zoek `intake_source_eml_save_failed` events in Railway-logs.
13. **Daadwerkelijke LLM-cache hit-rate**: hoeveel % van mails komt cached door?
    Niet geverifieerd. Bij cache-miss = grootste kost.

---

## 14. Top-10 meest waarschijnlijke oorzaken van de huidige bugs

Gesorteerd op vermoedelijke waarschijnlijkheid van impact NU:

1. **Ephemere filesystem op Railway maakt `incoming_document_path` post-deploy
   nutteloos** (12.A + 12.C). Elke deploy/restart wipet `data/incoming_documents/`.
   Oude `order_state.incoming_document_path` wijst naar weggevallen bestand ⇒
   404 in PDF-viewer. **Bewijs**: relatief pad in config (`config.py:21`); `.gitignore`
   bevat `data/` (`ONZEKER`); geen Railway volume mount; ephemere container-FS
   is Railway-standaardgedrag. **Verifieer met**: `ls /app/data/incoming_documents/by_email_id/`
   in Railway-container van een mail die meer dan één deploy oud is.

2. **`MAIL_POLL_INTERVAL_SECONDS` is niet gezet in Railway ⇒ poller draait nooit
   ⇒ geen nieuwe mails binnen** (12.B). Default 0 = uit (`config.py:53`,
   `main.py:97-98`). Bevestigd door previous-session-todo. **Fix**: env zetten op
   bv. 300.

3. **Microsoft Graph refresh-token is verlopen / consent ingetrokken** (12.B).
   Wegens `oauth_tokens.refresh_token` ouder dan 90 dagen (Microsoft default TTL)
   of `offline_access` scope niet gegrant. `_refresh_token` ⇒ `RuntimeError` ⇒
   `scan_inbox` faalt voor élke mail. **Bewijs**: previous-session-todo bevestigt.
   **Fix**: re-login via `/email`-pagina.

4. **PDF-viewer voor geüploade `/incoming-doc` files heeft mogelijk geen
   download-pad** (12.C). De `_find_eml_path` + `_extract_attachment_bytes` is
   afgestemd op .eml-attachments; voor losse PDFs is er geen analoge route
   gevonden. Frontend gaat via `attachmentSignedUrl(orderId, naam, "inline")`
   (`email-source-viewer.tsx:91`) wat naar `/api/orders/{id}/bijlagen?...&token=`
   leidt — die call zoekt het bestand binnen de .eml, niet als losstaand bestand
   op disk. **ONZEKER, verifieer met handmatige upload-test in dashboard**.

5. **`match_articles` doet 30-60 serial NAV-calls per order** (12.D.1). Op
   productie netwerk-latency = 5-15 sec per order pure matching. Mogelijk te
   parallelliseren met `asyncio.gather` over regels, maar dat zou meerdere
   NAV-sessies parallel openen — `Nav2018ODataClient` is hier niet voor
   ontworpen (geen rate-limiter, geen retry-policy zichtbaar voor 429s).
   **Bewijs**: `nodes/match_articles.py:105` for-loop met serial await; `navision_nav2018.py:186-189`
   nieuwe httpx-client per node.

6. **NAV `incoming-doc`-bundle skipt stilzwijgend op productie** (§6.b). De
   reviewer ziet het PDF in het dashboard, maar in NAV is geen attachment aan
   de order gekoppeld. Voor sommige back-office workflows is dat een echte
   regressie t.o.v. het verwachte "alles in NAV"-model. **Bewijs**:
   `navision_nav2018.py:517-559` skip-pad met `log.warning`.

7. **`_path_by_id` in `FileDropEmailClient` overleeft geen herstart** (12). Bij
   een crash tussen `list_new()` en `mark_seen()` wordt de mail bij volgende
   scan opnieuw verwerkt ⇒ duplicaat in `order_log`. Geldt alleen voor lokaal
   / Docker file_drop pad; productie gebruikt Graph waar `mark_seen` op
   `isRead=true` rust en idempotent is.

8. **In-process mail-poll per worker ⇒ duplicate scans als Railway upschaalt
   naar N workers**. Procfile/railway.toml definieert geen worker-count, maar
   als `WEB_CONCURRENCY` of `-w` ooit gezet wordt, ploft de poller N keer
   tegelijk de mailbox. `mark_seen` is voor Graph idempotent, maar Claude
   API-quotum niet. **ONGEVERIFIEERD: hoeveel uvicorn workers draait
   Railway nu?**

9. **`compose_navision_operations` raised `ValueError` bij header-only orders
   (`navision_steps.py:262-272`) — maar dit wordt door `compose_order_node`
   gevangen en op `state["compose_error"]` gezet** (`compose_order.py:60-71`).
   Reviewer ziet status="review" met compose_error, maar de huidige
   navision-preview-status-route (`api/preview.py:153-161`) toont status
   `no_matched_articles` of `no_customer` op basis van `compose_error`. Voor
   reviewers die niet weten dat `no_matched_articles` betekent "geen regel met
   `_matched`" kan dit verwarrend zijn. Geen bug, wel UX-zwakte.

10. **Geen monitoring / alerting op silent failures**: `mail_poll_tick_failed`,
    `intake_source_eml_save_failed`, `state_json_large`, `nav2018_incoming_doc_skipped`,
    `nav2018_dedup_probe_failed`, `graph_mark_seen_forbidden`,
    `graph_token_persist_failed`, `match_single_crash` worden alleen gelogd
    (kwabo.log + Railway stdout). Geen Sentry, geen Slack-webhook, geen daily
    digest. Operator merkt pas iets bij gebruikersklacht. Belangrijk voor
    productie stabiliteit.

---

## Bijlage A — Aanbevolen verifieer-volgorde voor Cas/Nico ter plekke

Geen acties zonder bewustzijn van impact; alle items zijn read-only / monitoring.

1. `GET /api/diagnostics/config` (admin-gated): bevestig
   `email_mode=graph`, `navision_mode=nav2018`, alle `nav_*_set=true`,
   `database_url_kind=postgres`, `admin_password.set=true`,
   `jwt_secret_is_dev_default=false`.
2. `GET /api/mailbox/status`: bevestig `mode=graph`, `connected=true`,
   `account_email=...`, `expires_at` in de toekomst.
3. `GET /api/diagnostics/nav?page=PLX_SalesOrder`, herhaal voor
   `PLX_Customer`, `PLX_Item`, `PLX_ItemReference`, `PLX_ShipToAddress`,
   `PLX_IncomingDocument`. Status 200 op alle = goed; 401/404 = config-fout
   resp. permission/page-naam fout.
4. `GET /api/admin/db-counts`: counts > 0 voor klanten, artikelen,
   kruisverwijzingen.
5. Railway-logs grep `mail_poll_tick`: aanwezig met regelmaat = poller draait.
6. Railway-logs grep `intake_source_eml_save_failed` of `nav2018_stepwise_failure`:
   afwezig = goed; aanwezig = diagnose vereist.
7. In de container: `ls /app/data/incoming_documents/by_email_id/ | wc -l`
   (via Railway shell). Aantal = aantal recent verwerkte mails sinds laatste
   deploy. Vergelijk met `order_log.id` count voor dezelfde periode.
8. Per recente "failed" order: `GET /api/orders/{id}/nav-debug` en lees
   `nav_operation_results` voor exact welke op faalde.

