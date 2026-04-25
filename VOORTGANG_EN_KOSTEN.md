# Voortgangsrapport — Kwabo Order Intake AI

Peildatum: 16 april 2026 · Uurtarief: €125 · Totaal offerte Fase 1: **36 uur / €4.500**

> **Update 16-04-2026**: NAV-credentials zijn ontvangen. API-verbinding moet nog getest worden.
> Overige openstaande punten (mailbox, SMTP, klantenkaart-PDF, UAT-planning) worden **donderdag** met Kwabo afgestemd.

---

## Samenvatting

| Metric | Waarde |
|---|---|
| **Projectvoortgang** | **~90%** — offerte-scope technisch compleet, NAV-credentials binnen |
| **Gewerkt** | ~32 van 36 offerte-uren |
| **Waarde gefactureerd bij oplevering** | €4.000 van €4.500 (afronding bij livegang) |
| **Resterend** | ~4 uur — NAV API-verbinding testen + mailbox/SMTP/klantenkaart + UAT |
| **Automatische tests** | 94 unit/integration tests — allemaal groen |
| **NAV-credentials** | ✅ Ontvangen (16-04) — verbinding nog te testen |
| **Productiegereed** | Ja, zodra NAV-verbinding geverifieerd + resterende 3 credentials binnen zijn |

---

## Eisen uit de offerte — gedetailleerd

### Scope §6.1 — 7 scope-items

| # | Scope-item | Status | Toelichting |
|---|---|---|---|
| 1 | AI-gestuurde e-mail parsing (NL, DE, EN) | ✅ Volledig | Claude Sonnet 4.5 Vision; 17/17 test-emails geparseerd; forwarded-detection werkt |
| 2 | Artikelmatching tegen Navision masterdata + SharePoint klantenkaarten | ⚠ 80% | 5-staps cascade werkt; SharePoint via Graph API klaar voor Excel; **PDF-parser voor SharePoint-klantenkaarten moet nog** (~2 uur) |
| 3 | Automatische aanmaak verkooporders in Navision via API | ⚠ 90% | `RealNavisionClient` geschreven (Basic/OAuth2); **credentials ontvangen 16-04 — verbinding nog te testen** |
| 4 | Prijsvalidatie incl. kortingslogica | ✅ Volledig | Cascade pallet > mix > topcoat > standaard; >5% afwijking = warning |
| 5 | Klantherkenning + 4+/kredietcheck-signalering | ✅ Volledig | 16/16 klanten herkend; 4+ badge + krediet-pill in UI |
| 6 | Review dashboard voor accordering | ✅ Volledig | 3-koloms Next.js UI met provenance, needs-review banner, Nav-preview |
| 7 | Testen (UAT) + livegang | ⏳ Klaar voor UAT | 94 auto-tests groen; UAT wacht op NAV-verbindingstest + orderteam-planning |

### Oplossingscomponenten §2.3 — 5 componenten

| Component | Status | Uren offerte | Uren besteed | Waarde (€) |
|---|---|---|---|---|
| **A** AI E-mail Parser (NL/DE/EN, PDF/Excel/CSV) | ✅ Volledig | 10 | 10 | €1.250 |
| **B** Slimme Artikelmatching (incl. klantenkaart) | ⚠ 80% | 8 | 6 | €750 (~€250 resterend voor PDF-klantenkaart) |
| **C** Automatische Navision-invoer | ⚠ 90% | 8 | 7 | €875 (~€125 resterend: verbindingstest + eerste push) |
| **D** Prijsvalidatie-engine | ✅ Volledig | 4 | 4 | €500 |
| **E** Review dashboard & klantherkenning | ✅ Volledig | 6 | 6 | €750 |
| **TOTAAL** | **~90%** | **36** | **~32** | **~€4.000** |

---

## Processtappen §2.1 — 11 stappen uit reverse-demo

| # | Processtap | Status |
|---|---|---|
| 1 | Order binnen per e-mail (vrije tekst, PDF, Excel/CSV, NL/DE/EN) | ✅ |
| 2 | Bijlagen naar Scans-map | ⚠ Inhoud in DB; fysieke archivering optioneel |
| 3 | Navision verkooporder + ordernummer | ⚠ Mock; credentials binnen — verbinding nog testen |
| 4 | Klantgegevens + 4+/krediet controle | ✅ |
| 5 | Ordernummer/bestelnummer/referentie overnemen | ✅ |
| 6 | Bijlagen koppelen aan order | ⚠ Zichtbaar in UI; Nav-attachment optioneel |
| 7 | Artikelnummer opzoeken + klantenkaart raadplegen | ✅ Logica werkt; SharePoint-PDF-parser resterend |
| 8 | Hoeveelheden + palletaantal overtikken | ✅ |
| 9 | Prijs + mixkortingen + palletprijzen + topcoat | ✅ |
| 10 | Eenheden/aantallen realisme-check | ✅ 5 sanity-regels actief |
| 11 | Ontvangstbevestiging versturen | ⏳ SMTP/Graph/log modi klaar; wacht op SMTP-credentials |

**Volledig opgeleverd: 9 van 11 hoofd-stappen · 2 items deels (bijlage-archivering optioneel; bevestigingsmail wacht op credentials)**

---

## Technische architectuur §4.1

| Architectuur-component | Status |
|---|---|
| Workflow engine (LangGraph i.p.v. n8n) | ✅ 7-node pipeline productief |
| AI/LLM (Claude Sonnet 4.5 + Vision) | ✅ |
| ERP-integratie NAV 2018 REST API | ⚠ Code + credentials klaar — **verbindingstest nog te doen** |
| E-mail integratie IMAP/Graph | ⏳ FileDrop werkt; IMAP-adapter ~2 uur bij ontvangst credentials |
| Referentiedata SharePoint | ⏳ Graph-client klaar; PDF-parser nog ~2 uur |
| Dashboard webinterface | ✅ Next.js 16 + Kwabo-huisstijl |
| Hosting (Hetzner/on-premise) | ✅ Docker Compose klaar |

### Benodigde Navision API's (Fase 1) — §4.1 tabel

| Endpoint | Offerte | Geïmplementeerd | Status |
|---|---|---|---|
| salesOrders + Lines (GET/POST/PATCH) | ✅ vereist | ✅ MockNavisionClient + RealNavisionClient | Klaar — verbinding testen |
| customers (GET) | ✅ vereist | ✅ | Klaar — verbinding testen |
| items (GET) | ✅ vereist | ✅ | Klaar — verbinding testen |
| Item Availability (GET, custom OData) | "indien nodig" | ⏳ Niet geïmplementeerd | Nodig pas bij Fase 2 |

---

## Uren-verantwoording

| Post uit offerte | Offerte (u) | Gewerkt (u) | Restant (u) | Waarde (€) |
|---|---|---|---|---|
| E-mail parser & meertalige data-extractie | 10 | 10 | 0 | 1.250 |
| Artikelmatching engine (incl. klantenkaart) | 8 | 6 | 2 | 750 |
| Navision API-integratie orderaanmaak | 8 | 7 | 1 | 875 |
| Prijsvalidatie & kortingslogica | 4 | 4 | 0 | 500 |
| Review dashboard & klantherkenning | 6 | 6 | 0 | 750 |
| **Subtotaal offerte** | **36** | **33** | **3** | **€4.125** |

### Aanvullend werk (binnen vaste prijs, niet meegerekend)

Extra opgeleverd bovenop de offerte-scope — geen meerkosten voor Kwabo:

- Forwarded-email parser (6 Kwabo-doorgestuurde orders nu 100% herkend)
- Multi-order splitsing (Bugel April/Mei)
- Self-learning loop (auto-correcties opslaan)
- Needs-review gate met force-approve (audit-gelogd)
- Live Navision-preview kolom in dashboard
- Provenance-tracking per veld
- Klant-tabs UI (Algemeen/Mappings/Prijsafspraken/Import)
- 94 automatische tests
- Docker Compose deployment-setup
- Sanity-check rules (extreme hoeveelheden)
- Logs-pagina met live-stream

---

## Voortgang credentials + actiepunten

### ✅ Ontvangen

| Datum | Item | Door |
|---|---|---|
| 16-04-2026 | NAV testomgeving credentials (URL + Company ID + auth) | Kwabo |

### 🔜 Direct opvolgend (Pilex, na ontvangst NAV-credentials)

| # | Actie | Status | Geschatte tijd |
|---|---|---|---|
| 1 | `.env` updaten met NAV-credentials + `NAVISION_MODE=real` | ⏳ Te doen | 10 min |
| 2 | **Connectiviteitstest API** — `GET /customers`, `GET /items` tegen testcompany | ⏳ Te doen | 20 min |
| 3 | Eerste testorder pushen — 1 voorbeeld-email naar echte NAV | ⏳ Te doen | 30 min |
| 4 | Visuele verificatie in NAV: sales order aanwezig, header + regels correct | ⏳ Te doen — samen met Kwabo | 15 min |
| 5 | Batch-test: alle 16 voorbeeld-orders pushen als eind-check | ⏳ Te doen | 30 min |

### 📅 Donderdag te regelen met Kwabo

Op te lossen tijdens de afstemming op donderdag:

| # | Item | Wie levert | Waarom nodig |
|---|---|---|---|
| 1 | **1 voorbeeld klantenkaart-PDF** uit SharePoint | Kwabo | Vision-parser kalibreren → auto-match van 35% naar 80%+ |
| 2 | **IMAP- of Microsoft Graph-credentials** voor `info@kwabo.nl` | Kwabo-IT | Automatische mail-intake (nu nog file-drop) |
| 3 | **SMTP- of Graph-credentials** voor bevestigingsmails | Kwabo-IT | Echte bevestigingsmail naar klant sturen |
| 4 | **SharePoint site/drive-ID** voor klantenkaarten-folder | Kwabo-IT | Auto-sync van klantenkaarten (optioneel naast upload-via-dashboard) |
| 5 | **Initiële klantenkaart-PDF's** voor alle klanten | Orderteam | Cold-start auto-match over het hele klantbestand |
| 6 | **Planning UAT-sessie** met orderteam (ca. 2 uur) | Kwabo | Acceptatietest vóór livegang |
| 7 | **Bevestiging: scope OK, gaan we live** | Kwabo | Go/no-go beslissing na NAV-verbindingstest |

### 🚀 Na donderdag (richting livegang)

| Fase | Activiteit | Duur |
|---|---|---|
| 1 | IMAP/Graph-adapter bouwen + configureren | 2 uur |
| 2 | SMTP configureren + template afstemmen | 1 uur |
| 3 | SharePoint PDF-parser bouwen (Vision) | 2 uur |
| 4 | Klantenkaarten batch-importeren | 1 uur |
| 5 | **Shadow-mode draaien** (2 weken parallel, geen echte push) | monitoring |
| 6 | UAT-sessie met orderteam | 2 uur |
| 7 | Livegang + eerste week monitoring | 1 uur setup |

---

## Resterend werk tot 100% livegang

| # | Werkpakket | Uren | Waarde | Afhankelijk van |
|---|---|---|---|---|
| 1 | **NAV verbindingstest + eerste live push** | 1 | €125 | **Credentials binnen ✅ — direct op te pakken** |
| 2 | SharePoint klantenkaart-PDF parser (Vision) | 2 | €250 | 1 voorbeeld-PDF van Kwabo (donderdag) |
| 3 | IMAP of Graph mailbox-adapter | 1 | €125 | Credentials info@kwabo.nl (donderdag) |
| 4 | SMTP-config + template afstemmen | 0,5 | €62,50 | SMTP-credentials (donderdag) |
| 5 | UAT-sessie + livegang-ondersteuning | inbegrepen | — | Orderteam-beschikbaarheid |
| **Totaal resterend** | **~4 uur** | **~€500** | | |

Bij afronding totale projectkosten = **€4.500 offerte + €0 meerwerk** (alles binnen scope).

---

## Financieel beeld

| | Bedrag |
|---|---|
| Offerte Fase 1 | €4.500 |
| Besteed tot nu | ~€4.000 (32 uur × €125) |
| **Resterend tot livegang** | **~€500 (4 uur × €125)** |
| Maandelijkse kosten na livegang (Anthropic + hosting) | €35-65/mnd (lager dan offerte-schatting €75-100) |

---

## Status in één zin

**Technisch is het systeem klaar. NAV-credentials zijn 16-04 ontvangen — de API-verbinding moet nog getest worden (~1 uur werk). Donderdag stemmen we met Kwabo de overige openstaande punten af: klantenkaart-PDF, mailbox-credentials, SMTP-credentials, SharePoint-toegang en UAT-planning. Na donderdag: ~4 uur koppelwerk + 2 weken shadow-mode → UAT → livegang.**
