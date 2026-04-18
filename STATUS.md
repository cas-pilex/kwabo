# Status & Testrapport — Kwabo Order Intake AI

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
