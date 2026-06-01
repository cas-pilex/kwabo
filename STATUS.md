# Status & Testrapport — Kwabo Order Intake AI

> ⚠️ De secties hieronder vanaf "De app draait" zijn van **2026-04-14** en
> beschrijven de vroege lokale mock-opzet (7 nodes, mock-Navision, demo-seed als
> model). Ze zijn historisch — de actuele productie-status staat hieronder.

## Productie-status — 2026-05-31/06-01 (uitputtende test-en-fix-campagne)

Volledige sweep van backend (alle ~62 routes), frontend (alle pagina's) en pipeline
(edge cases), met systematic-debugging + verification-before-completion. Drie échte
bugs gevonden én gefixt+gedeployd+live-geverifieerd:

- `6ab965f` — **perf/sloomheid breed**: DB-engine gebruikte `NullPool` → elke
  DB-request opende een verse Supabase-connectie (~1,3s tax). Live bewijs: elke
  DB-endpoint ~1,67s, non-DB ~0,3s, geen warmup. Client-side pool → broad sneller
  (queue 3,56→1,69s, audit-stats 3,73→1,08s, klant-detail 1,68→0,91s, mailbox 0,91s).
- `8c15c63` — **/logs + upload-knop 401**: tail-fetch/upload zonder Bearer +
  EventSource zonder header. Fix: token via header. Live: /logs toont regels,
  0 console-401's; upload-knop maakt order.
- `8cd174b` — **security (HIGH) + self-learning loop**: (a) de /logs-stream zette de
  admin-token in de EventSource-URL (lekt via logs/history) → vervangen door
  fetch()+ReadableStream met Authorization-header, stream weer Bearer-gated; (b) de
  self-learning loop werd nooit gevoed (UI stuurt geen artikel-correcties) →
  `_learn_from_approved` registreert nu klant-SKU→kwabo-mappings na elke geslaagde push.

**Bevindingen zonder bug:** alle 27 GET-endpoints 200; alle pagina's 0 console-401's;
pipeline edge cases correct — Kirchner multi-PDF spawnt sub-order (522→523), ZIP→PDF
werkt (526), Dietrich-"Lieferschein" terecht `not_order` (524, pakbon = geen order).
Enige restpunt: Engelse "FW:"-forward-sender-detectie mist (→ review, geen crash).

**Artikel-automatch ~23% = DATA, geen logica-bug**: NAV-cross-refs missen klant-SKUs;
klantenkaart/history leeg. De learning-loop is nu gefixt (`8cd174b`) en bouwt mappings
op bij elke goedkeuring — live bewezen (klant 50000: 0→2 mappings na push).

**Productie-acceptatietest (UAT, 01-06) — alle gebruikers-workflows GO:** login,
queue (filter-tabs/scan/upload), order-review (velden+klant+artikel bewerken met
herlaad-bevestigde persistentie), approve→push (VO2606403 in NAV geverifieerd),
self-learning (0→2 mappings live), bron-document, afwijzen, klantbeheer
(aliases/prijs/documenten/Excel-import: add→check→delete), audit, logs, e-mailstatus.
Geen blokkers. Restpunten (niet-blokkerend): handmatig gezette klant toont nr+conf
maar niet de naam; artikel-mappings hebben geen verwijder-endpoint.

**NAV-pushes test-Drafts (in NAV geverifieerd, door Cas te verwijderen):** VO2606400
(Dietrich), VO2606401 (TABS→PontMeyer), VO2606402 (Kirchner, auto via forward),
VO2606403 (Groenhart, via UI-edit + self-learning).

Tests: 413 passed, 17 skipped (incl. nieuwe regressietests: multi-adres-match,
artikel-search-mirror, db-pooling, logs-stream-gate, learn-from-approved).

---

## Productie-status — 2026-05-31 (5 E2E-runs live geverifieerd)

Volledige hertest in productie met 5 geïnjecteerde test-.eml's (Ferney, Dietrich,
TABS, Isero-fwd, Omtzigt). Resultaat:

- **Mailbox/poller gezond**: `state:active`, `last_poll_status:ok`, `errors:0`,
  token geldig; orders gegroeid 130→480+ sinds vorige sessie met 0 poll-errors.
- **Pijplijn**: alle 5 mails geclassificeerd als order, geëxtraheerd, artikelen +
  klant gematcht, in DB (Postgres) gepersisteerd met volledige `order_state` +
  `stappen_log`. Bron-.eml/PDF persistent in Supabase (opent in de UI).
- **2 NAV-pushes via de UI-knop** ("Goedkeuren & Push Navision"):
  - `VO2606400` — Dietrich, klant 60103, extDoc 4401054959
  - `VO2606401` — TABS→PontMeyer, klant 61793, extDoc 4506782407
  Beide read-only geverifieerd in NAV (`Kopie 2026`); 0 gefaalde operaties;
  bevestigingsmail verzonden (`send_confirmation mail_sent=True`).
- **UI-laadtijden**: queue ~4.5s, audit ~5.4s, order-detail **2.6s** (was 15s — zie fix).

### Fixes deze sessie (31 mei)
- `7b3e7b5` — **auto-match-fix**: NAV bewaart meerdere e-mailadressen in één veld
  (`a@x; b@y; c@z`); `KlantRepo.by_email` deed exact-equality en miste die →
  élke multi-adres-klant viel uit op handmatige review. Nu split-token-match,
  alleen bij ondubbelzinnige enkele klant. Live bewezen: Ferney
  `purchaseorders@ferney.nl` → 50262 auto (100%).
- `0ad2c99` — **perf-fix ("app sloom")**: `/api/artikelen/search` deed bij élke
  order-detailpagina een live NAV OData-dump van de volledige itemcatalogus
  (~15s, zonder $top). Nu bediend uit de lokale Artikelkaart-mirror (Postgres) →
  **order-detailpagina 15s → 2.6s**.

### Openstaand restpunt (geen blokkade)
- **/logs-pagina** authenticeert niet (tail-fetch zonder Bearer-header +
  EventSource kan geen headers sturen) → 401, blijft leeg. Backend-endpoint werkt
  wél (200 met token). Geïsoleerd diagnose-scherm; fix vereist frontend (+ klein
  backend voor SSE-token).

---

## Productie-status — 2026-05-30 (live geverifieerd)

Backend op Railway (`kwabo-production.up.railway.app`), frontend op Vercel
(`kwabo-pilex.vercel.app`), Postgres + Storage op Supabase. **Pipeline = 10
nodes**, `EMAIL_MODE=graph`, `NAVISION_MODE=nav2018` (live NAV 2018 OData,
company `Kopie 2026`).

### Wat live werkt (met bewijs)
- **Mailbox-intake**: Graph-poller elke 5 min, `last_poll_status: ok`,
  `errors: 0`. Mails → review-queue automatisch.
- **AI-pijplijn**: classify → extract → klant/artikelen/prijzen matchen →
  compose. NAV-mirror gevuld (1787 klanten, 3757 artikelen, 3000
  kruisverwijzingen, 2506 ship-to).
- **Bron-.eml/PDF persistent** in Supabase Storage (overleeft Railway-deploys).
- **Approve → Navision push** end-to-end bewezen: order 120 (Würth 61030) →
  `VO2606194` aangemaakt in `Kopie 2026`.

### Fixes in deze sessie (29-30 mei)
- `dc9946a` — **crash-fix**: bytes-`email_body` sloopte élke mail in
  `match_customer` (regex-op-bytes) → poison-pill loop. Nu `_plain_body` +
  `detect_forward` str-coercie. Plus poison-pill quarantine (na 3 fouten),
  error-oorzaak in `/api/mailbox/status`, en tracebacks in de logs.
- `c4e3563` — **seed-fix**: demo-klanten (10001-10016) werden in prod geseed mét
  echte order-emailadressen → matchten op niet-bestaande NAV-nummers → push
  faalde. Nu: seed alleen in dev/test; `POST /api/admin/purge-demo-seed`
  verwijderde de 16 demo-klanten uit prod (1803→1787).

### Bekende restpunten (geen blokkades)
- Review-orders verwerkt vóór `c4e3563` dragen nog het foute klantnummer in hun
  state → reviewer corrigeert handmatig vóór Approve.
- TABS/Dietrich-mails matchen mogelijk naar "review" i.p.v. automatisch (hun
  order-e-mailadres wijkt af van het adres in NAV-master) — correct gedrag.
- Tests: 397 passed, 17 skipped (skips = live-LLM regressie, vereist
  `ANTHROPIC_API_KEY`).

---

Laatste run: 2026-04-14. Alles getest op Windows 11 / Python 3.14 / Node 24 / pnpm 10.

## De app draait. Dit is hoe je erin komt:

| Onderdeel | URL | Commando |
|---|---|---|
| **Frontend** (dashboard) | http://localhost:3000 | `cd frontend && pnpm build && pnpm start` |
| Backend API | http://localhost:8000 | `cd backend && PYTHONPATH=src python -m uvicorn kwabo.main:app --port 8000` |
| API Swagger | http://localhost:8000/docs | — |

### ⚠ Belangrijk: gebruik `pnpm start` (productie-build), niet `pnpm dev`

Next.js 16 + Turbopack faalt op deze Windows-setup met HMR-websocket-fouten waardoor **client-side hydration niet start in dev mode** — knoppen doen niks, `useEffect` vuurt niet, dus de logs-pagina blijft leeg en de approve-knop reageert niet. Met `pnpm build && pnpm start` (productie) werkt ALLE interactiviteit.

## Pagina's — wat je nu kunt testen

Alle pagina's zijn live geverifieerd (HTTP 200, gehydrateerd, gescreenshot).

### 1. `/` — Order Queue
- Navy header met Kwabo-logo (in witte pil zodat het op elke achtergrond staat) + goud-accent
- 4 stat-cards: Totaal / In review / Pushed / Warnings
- Orders-tabel met navy header, confidence-pillen (groen/amber/rood), status-badges, warn-badges, Nav-ordernummer
- Klik een `#` → order-detail

### 2. `/orders/{id}` — Order Review
- **Links:** volledige e-mail body + bijlagen (uitklapbaar per PDF)
- **Rechts:** klant-selector, drop-ship adres (indien aanwezig), editable orderregels-tabel met combobox → Nav items
- **Match-badges per regel:** `exact` (groen), `history` / `klantenkaart` (sky), `fuzzy` (amber), `manual` (rood)
- **Acties:** "Goedkeuren & Push Navision" (navy) of "Afwijzen" (rose)
- **Audit trail** onderaan met alle 7 pipeline-stappen + timestamps

### 3. `/klanten` en `/klanten/{nr}`
- Tabel met alle 16 geseede klanten + zoekbare detailpagina met artikel-mappings

### 4. `/audit`
- Stat-cards (Auto-match%, Gem. confidence, Per status)
- Per order: uitklapbaar met warnings + alle stappen-log

### 5. `/logs` ⭐ (nieuw)
- Live tail van `backend/kwabo.log`
- SSE-stream (houdt verbinding open, nieuwe regels verschijnen real-time)
- Filter-inputbox (bijv. `classify`, `match_articles`, `error`)
- Kleurgecodeerd: push/approve groen, classify/extract/match sky, warnings amber, errors rose
- Live stream toggle + Clear-knop

## Wat werkt — concreet getest met live backend

### Pipeline (alle 7 nodes vuren)
Voorbeeld uit `backend/kwabo.log` na 3 emails:
```
event='intake'          bijlagen=1 email_id='4fc61a496448e786' from_='TABS Supply Chain <supplychain@tabsholland.nl>'
event='classify'        is_order=True confidence=0.98
event='extract'         bestelnr='4506782407' regels=1 taal='NL'
event='match_customer'  klant_nr='10002' bron='email' confidence=1.0
event='match_articles'  matched=1 total=1
event='compose_order'   log_id=1 regels=1
event='push_navision'   navision_order_nr='SO-8B7063A1' lines=1
event='send_confirmation' navision_order_nr='SO-8B7063A1'
```

### Batch regressie op alle 17 e-mails
```
Parsed ok: 17/17
Classified als order: 16/17 (1 = lege duplicaat)
Orders in Navision mock: 16
Klant gematcht: 12/16 (75%)
```

### Approve-flow
`POST /api/orders/1/approve` → `{"ok": true, "navision_order_nr": "SO-8B7063A1", "status": "pushed"}`
→ `data/navision_mock/orders/SO-8B7063A1.json` aangemaakt met volledige sales-order (customerNumber, externalDocumentNumber, shipToName, lines[]).

### Logs-endpoint
- `GET /api/logs/tail?lines=500` → laatste N regels
- `GET /api/logs/stream` → SSE keep-alive stream
- Bestandsrotatie: 5 MB per file, 3 backups

## Wat nog moet gebeuren

### Hoge prioriteit (functioneel)
1. **Artikel auto-match verbeteren** — nu 22% auto-gematcht. Seed-mappings in `backend/src/kwabo/db/seed.py` zijn illustratief. Oplossing: Navision-master-data export → CSV import script; self-learning loop (elke reviewer-correctie wordt opgeslagen en verbetert volgende gelijke e-mail).
2. **Forwarded-email afzenderdetectie** — 4 forwards (Ivar/Mark/Nico @ kwabo.nl) matchen nu op kunstmatige seed-adressen. Nodig: regex op forwarded-content om originele afzender te vinden.
3. **Kirchner multi-PDF** — prompt returned JSON array; eerste order wordt verwerkt, tweede (in zelfde e-mail) nog niet. Nodig: loop in `extract_node` die per element een sub-state maakt.

### Medium prioriteit (swap naar live externals)
4. **Echte Navision API** — implementeer `RealNavisionClient` in `integrations/navision_api.py` (PDF §10: Basic/OAuth2, OData /customers + /items + POST /salesOrders). Mock blijft als fallback.
5. **IMAP/Microsoft Graph intake** — implementeer `ImapEmailClient`/`GraphEmailClient` achter `EmailClient`-protocol. File-drop blijft werken voor tests.
6. **SharePoint klantenkaart-import** — script `import_klantenkaarten.py` via Microsoft Graph.

### Lage prioriteit (polish)
7. **Dev-mode hydration fix** — onderzoek Next.js 16 + Turbopack HMR-websocket op Windows. Workaround nu: `pnpm build && pnpm start`. Alternatief: downgraden naar Next 15 of turbo uitzetten met `NEXT_DISABLE_TURBOPACK=1`.
8. **Expected-JSON fixtures** per e-mail in `tests/test_data/expected/` + pytest-regressie-harness.
9. **LangSmith tracing** aanzetten voor productie-observability.
10. **Prijsafspraken** — klantenbeheer UI mist nog de prijs-tab.
11. **Email-upload UI** — nu alleen via API (`POST /api/intake/upload`) of file-drop. UI-knop "Upload .eml" zou handig zijn.

## Test-plan om het zelf na te lopen

### End-to-end smoketest (5 minuten)

```bash
# Terminal 1 — backend
cd C:/Kwabo/kwabo-order-intake/backend
rm -f kwabo.db kwabo.log                            # schone start
rm -f ../data/navision_mock/orders/*.json
PYTHONPATH=src python -m uvicorn kwabo.main:app --port 8000

# Terminal 2 — frontend (productie!)
cd C:/Kwabo/kwabo-order-intake/frontend
pnpm build && pnpm start                            # http://localhost:3000

# Terminal 3 — drop emails en scan
cp backend/tests/test_data/emails/"Ferney inkooporder 4200056148.eml" data/inbox/
cp backend/tests/test_data/emails/"Bestelling 4506782407 157.eml" data/inbox/
cp backend/tests/test_data/emails/"Inkooporder 00176482.eml" data/inbox/
curl -X POST http://localhost:8000/api/intake/scan
```

**Dan in de browser:**

1. Open http://localhost:3000 — queue toont de 3 orders met status `review`.
2. Open http://localhost:3000/logs — live-stream toont elke pipeline-stap in kleur.
3. Klik `#` op een order → review-pagina.
4. Controleer de orderregels (klant-art / Kwabo-art / match-methode/confidence).
5. Pas eventueel Kwabo-artikelnummer aan via de combobox.
6. Klik "Goedkeuren & Push Navision" → status wordt `pushed`, Nav-ordernummer verschijnt.
7. Check `data/navision_mock/orders/SO-xxx.json` voor de daadwerkelijke payload.
8. Ga naar /audit → zie volledige decision-log per order; stats-cards updaten.
9. Ga naar /klanten/10002 → zie TABS met artikel-mappings.
10. Bekijk http://localhost:8000/docs voor de hele REST-API (22 endpoints).

### Reset-commando's

```bash
# Schone DB + logs + mock-orders
rm backend/kwabo.db backend/kwabo.log
rm data/navision_mock/orders/*.json
rm data/processed/*.eml
```

## Bekende issues

| Issue | Impact | Workaround |
|---|---|---|
| `pnpm dev` hydration failure op Windows | Knoppen/logs werken niet in dev | `pnpm build && pnpm start` |
| Werkzeuge Dietrich duplicaat geclassificeerd als geen-order | Lege body + enkel bijlage | Intake-node zou body altijd met bijlage moeten combineren bij lege body; al correct in extract maar classify skipt het |
| Forwarded mails (Ivar/Mark/Nico) matchen op kunstmatige seed-adressen | Suboptimale klant-match | Forwarded-header parser (high-prio fix hierboven) |
| 22% artikel-auto-match | Veel handmatige correcties in review | Echte masterdata-import (high-prio) |

## Schermafbeeldingen

Alle pagina's zijn geverifieerd en gescreenshot. Voorbeelden staan in `/tmp/shots/prod_*.png` tijdens deze sessie. Om zelf te vergelijken: open de pagina's in de browser na bovenstaande smoketest.
