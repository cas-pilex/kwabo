# Offerte vs Implementatie — Volledig Overzicht

Offerte: "Kwabo_Offerte_Definitief__5_.docx" (versie 2.0, maart 2026)
Status-datum: 16 april 2026

---

# SCENARIO 1: Intelligente Order Intake (Fase 1)

**Offerte-status:** Definitief · €4.500 · 36 uur · 3-4 weken doorlooptijd

---

## §2.1 Huidig orderintake-proces — 11 processtappen

Het huidige handmatige proces dat geautomatiseerd moet worden. Per stap: wat de offerte beschrijft, hoe het is geïmplementeerd, en wat de status is.

### Stap 1: Order komt binnen per e-mail op info@kwabo.nl
**Offerte:** "Order komt binnen per e-mail op info@kwabo.nl (als vrije tekst, PDF of Excel/CSV bijlage, in NL, DE of EN)"

**Status: ✅ VOLLEDIG GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `backend/src/kwabo/integrations/email_client.py` → `FileDropEmailClient` leest `.eml` bestanden uit `data/inbox/` en parset ze met Python's `email` module
- Bijlagen worden automatisch geëxtraheerd: PDF's (ook uit ZIP), Excel (.xlsx/.xls), CSV
- Logo's/afbeeldingen worden overgeslagen
- Forwarded e-mails (van Kwabo-medewerkers die orders doorsturen) worden gedetecteerd door `integrations/forwarded_parser.py` — de originele afzender wordt teruggehaald uit de forwarded headers (Outlook NL/EN/DE + Gmail)

**Wat nog nodig voor live:**
- `ImapEmailClient` of `GraphEmailClient` implementeren (protocol staat klaar, ~50 regels code) + credentials van Kwabo-IT. File-drop blijft werken als fallback/testmodus.

---

### Stap 2: Medewerker sleept bijlagen naar Scans-map
**Offerte:** "Medewerker sleept bijlagen handmatig naar de Scans-map op het netwerk"

**Status: ⚠ DEELS — bijlagen worden bewaard in state, niet als losse bestanden op schijf**

**Hoe het werkt:**
- Bijlage-inhoud (tekst) wordt opgeslagen in `order_log.order_state` JSON in de SQLite database
- Raw PDF-bytes worden bewaard in-memory voor de Vision-extractor maar NIET persistent op schijf

**Wat nog nodig:**
- Optioneel: `data/attachments/{order_log_id}/` aanmaken met originele bijlage-bestanden
- Of: Nav-API `POST salesOrders({id})/attachments` (custom OData) om bijlagen direct aan de Nav-order te koppelen

---

### Stap 3: In Navision verkooporder openen + ordernummer genereren
**Offerte:** "In Navision een nieuwe verkooporder openen en ordernummer genereren"

**Status: ✅ VOLLEDIG GEÏMPLEMENTEERD (mock) · skeleton klaar voor echte NAV**

**Hoe het werkt:**
- `backend/src/kwabo/integrations/navision_api.py` → `MockNavisionClient` simuleert de Nav-API en schrijft orders als JSON naar `data/navision_mock/orders/SO-{uuid}.json`
- `backend/src/kwabo/integrations/navision_real.py` → `RealNavisionClient` is volledig geschreven met:
  - Basic Auth + OAuth2 (Azure AD) ondersteuning
  - `POST /salesOrders` (header aanmaken) + `POST /salesOrders({id})/salesOrderLines` (regels toevoegen)
  - Retry met exponential backoff bij 5xx fouten
  - Idempotency-check op `externalDocumentNumber` om dubbele orders te voorkomen
- Schakelen: `NAVISION_MODE=mock|replay|real` in `.env`
- Er is ook een `ReplayNavisionClient` die tegen een JSON-fixture draait voor offline QA

**Wat nog nodig voor live:**
- NAV-server URL + Company-ID + webservice-credentials van Kwabo/NAV-partner
- Testen tegen NAV testcompany (NIET productie)

---

### Stap 4: Klantgegevens invullen; 4+ controleren of kredietlimiet aanvragen
**Offerte:** "Klantgegevens invullen; bij onbekende klant: 4+ lidmaatschap controleren of kredietlimiet aanvragen bij Allianz"

**Status: ✅ GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `backend/src/kwabo/graph/nodes/match_customer.py` → 3-staps klantherkenning:
  1. E-mailadres matchen tegen `klantenkaarten` tabel (incl. forward-detectie)
  2. Navision customers API doorzoeken op email/naam
  3. Als niet gevonden → "KLANT NIET GEVONDEN" warning + needs_review
- Na match: `is_4plus` en `kredietlimiet` worden gelezen uit de klantenkaart-database
- Als klant NIET 4+ is → warning "⚠ KLANT IS GEEN 4+ LID"
- Klant-match verreikt met `is_4plus`, `kredietlimiet`, `betalingsconditie`

**Hoe het eruit ziet in de UI:**
- Review-pagina kolom 2 → Klant-blok toont:
  - Klantnaam + Navision-nr (editable combobox)
  - Groene badge "4+ lid" of rode badge "geen 4+"
  - Blauwe pill "krediet € X.XXX"
  - Provenance-badge (📧 e-mail / 📇 klantkaart / ⚠ missing)

**Wat nog nodig voor live:**
- Echte Nav-integratie om openstaand saldo op te vragen (`GET /salesOrders?$filter=status eq 'Open'`) voor daadwerkelijke krediet-benutting-berekening. Nu tonen we alleen de limiet.
- Allianz-koppeling (indien gewenst) is out-of-scope offerte

---

### Stap 5: Ordernummer, bestelnummer, referentienummer overnemen
**Offerte:** "Ordernummer, bestelnummer en referentienummer overnemen uit de bijlagen"

**Status: ✅ VOLLEDIG GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `backend/src/kwabo/integrations/llm_extractor.py` → Claude Sonnet 4.5 met Vision leest het hele PDF-document en extraheert `bestelnummer_klant`, `orderdatum`, `gewenste_leverdatum` met per-veld provenance
- Het PDF-bestand wordt als `document` content-block naar Claude gestuurd (niet als geëxtraheerde tekst) — werkt ook op scanned/image PDFs
- Prompt-caching (`cache_control: ephemeral`) maakt herverwerking 80% goedkoper

**Hoe het eruit ziet in de UI:**
- Kolom 2 → Header-blok: bestelnr, orderdatum, leverdatum (alle 3 editable + provenance-badge 📄 PDF)

---

### Stap 6: Bijlagen koppelen aan de order
**Offerte:** "Bijlagen koppelen aan de order vanuit de Scans-map"

**Status: ⚠ DEELS — bijlage-inhoud zichtbaar in UI, niet als losse bestanden gekoppeld**

**Hoe het werkt:**
- Kolom 1 van de review-pagina toont alle bijlagen uitklapbaar met de volledige PDF-tekst (via pdfplumber fallback)
- De bijlage-metadata (naam, type, tekst-preview) wordt opgeslagen in `order_log.order_state`

**Wat nog nodig:**
- Fysieke bestanden opslaan in `data/attachments/` of als Nav-attachment via API

---

### Stap 7: Artikelnummer opzoeken, klantenkaart raadplegen
**Offerte:** "Per orderregel: artikelnummer opzoeken uit bijlagen. Bij afwijkende nummering: vorige order of klantenkaart in SharePoint raadplegen"

**Status: ✅ VOLLEDIG GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `backend/src/kwabo/graph/nodes/match_articles.py` → 5-staps cascade:
  1. **Exact**: klant noemt zelf het Kwabo-nummer (bijv. "Uw artikelnummer: 228321") → verifieer in Nav items
  2. **History**: eerder gemanual-de match voor dit klant-artikelnr → automatisch hergebruiken (self-learning!)
  3. **Klantenkaart**: mapping uit `klantenkaart_artikelen` tabel (gevuld via SharePoint-import of dashboard Excel-upload)
  4. **Fuzzy**: omschrijving vergelijken met Nav-items via `rapidfuzz` WRatio-scoring (≥70% = match)
  5. **Manual**: niet gevonden → markeer als `needs_review` zodat reviewer handmatig selecteert
- Elke match krijgt `match_confidence` (0-1) en `match_methode` ("exact"/"history"/"klantenkaart"/"fuzzy"/"manual")

**Hoe het eruit ziet in de UI:**
- Kolom 2 → per orderregel:
  - Klant-artnr (📄 uit PDF)
  - Kwabo-artnr (editable combobox, zoekt in Nav-items datalist)
  - Match-badge: groen "exact 100%", blauw "klantenkaart 90%", amber "fuzzy 78%", rood "manual 0%"
  - Rode rand + "Vul aan…" placeholder als needs_review

**Self-learning:**
- Bij elke reviewer-correctie → mapping opgeslagen in `artikel_matching_history` + `klantenkaart_artikelen`
- Volgende identieke order = automatisch gematcht

**SharePoint-koppeling:**
- `backend/src/kwabo/integrations/sharepoint.py` → Microsoft Graph client die Excel-bestanden downloadt van SharePoint en upsert naar lokale DB
- `backend/scripts/sync_sharepoint.py` → CLI voor handmatige of cron-sync
- `/api/klanten/{nr}/import-excel` → dashboard Excel-upload (drag & drop)
- Klantenbeheer UI: 4 tabs (Algemeen / Artikelmappings / Prijsafspraken / Import Excel)

---

### Stap 8: Hoeveelheden overtikken, palletaantal invullen
**Offerte:** "Hoeveelheden overtikken, palletaantal invullen"

**Status: ✅ VOLLEDIG GEÏMPLEMENTEERD**

**Hoe het werkt:**
- Claude Vision extraheert hoeveelheid + eenheid per orderregel uit PDF/body
- `backend/src/kwabo/utils/eenheid_mapping.py` → normaliseert 30+ eenheid-varianten (Rolle→ROL, Stück→STUK, pcs→STUK, m²→M2, pallet→PAL, etc.)
- Provenance per veld (📄 source + confidence 99%)

**Hoe het eruit ziet in de UI:**
- Per regel: hoeveelheid (number input) + eenheid (text input), beide editable

---

### Stap 9: Prijs controleren tegen prijzendocument; mixkortingen en palletprijzen toepassen
**Offerte:** "Prijs controleren tegen prijzendocument in klantmap; mixkortingen en palletprijzen toepassen (tenzij topcoat-uitzondering)"

**Status: ✅ VOLLEDIG GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `backend/src/kwabo/graph/nodes/validate_prices.py` → cascade prijsvalidatie:
  1. `PrijsRepo.best_match(klant, artikel, hoeveelheid)` zoekt de meest specifieke geldende afspraak:
     - **Palletprijs** (type='pallet', min_hoeveelheid ≤ besteld) → hoogste prioriteit
     - **Mixkorting** (type='mix', min_hoeveelheid ≤ totaal) → tweede prioriteit
     - **Topcoat-uitzondering** (type='topcoat') → derde prioriteit
     - **Standaardprijs** (type='standaard') → fallback
  2. Berekent verwachte prijs = `prijs × (1 - korting_pct/100)`
  3. Vergelijkt met bestelde prijs: >5% afwijking = warning met type-info ("palletprijs verwacht: €12.00")
- `prijsafspraken` tabel heeft: klant_nr, kwabo_artikelnr, prijs, korting_pct, type, min_hoeveelheid, geldig_van, geldig_tot

**Hoe het eruit ziet in de UI:**
- Per regel: prijs-veld met groene ✓ (valide), rode ✗ (afwijking), grijze — (geen afspraak)
- Warning-tekst in banner bij afwijking ("PRIJS AFWIJKING regel 1: klant €19.35 vs palletprijs-afspraak €12.00 (61.3%)")
- Klantenbeheer → Prijsafspraken tab: CRUD per klant (toevoegen/verwijderen, kwabo-artnr, prijs, korting%, type, geldig tot)

---

### Stap 10: Eenheden en aantallen controleren op realisme
**Offerte:** "Eenheden en aantallen controleren op realisme; bij twijfel terugbellen of -mailen"

**Status: ✅ GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `validate_prices_node` bevat 5 sanity-regels:
  - Hoeveelheid ≤ 0 → "Hoeveelheid is 0 of negatief"
  - PAL > 100 → "Meer dan 100 pallets besteld — klopt dit?"
  - STUK > 50.000 → "Meer dan 50.000 stuks besteld — klopt dit?"
  - ROL > 5.000 → "Meer dan 5.000 rollen besteld — klopt dit?"
  - Onbekende eenheid → "Onbekende eenheid"
- Triggert `validatie_warnings` + `needs_review` op het betreffende veld

---

### Stap 11: Ontvangstbevestiging versturen
**Offerte:** "Ontvangstbevestiging versturen vanuit Navision; orderbevestiging later met verzenddatum"

**Status: ✅ GEÏMPLEMENTEERD**

**Hoe het werkt:**
- `backend/src/kwabo/integrations/mail_sender.py` → 3 adapters achter `MailSender` protocol:
  - **LogMailSender** (default): logt de bevestiging (voor development)
  - **SmtpMailSender**: verstuurt via SMTP (config: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM)
  - **GraphMailSender**: verstuurt via Microsoft Graph `POST /me/sendMail` (voor Office 365)
- Template in `backend/src/kwabo/templates/ontvangstbevestiging.txt`:
  ```
  Geachte {klant_naam},
  Wij bevestigen de ontvangst van uw bestelling met referentie {bestelnr_klant}.
  Uw order is verwerkt onder Navision-ordernummer {navision_order_nr}.
  ```
- Schakelen: `MAIL_MODE=log|smtp|graph` in `.env`
- `send_confirmation_node` in pipeline: na succesvolle Nav-push → bevestigingsmail naar klant-emailadres
- Audit trail registreert of mail daadwerkelijk verstuurd is

**Wat nog nodig voor live:**
- SMTP-credentials of Graph-credentials van Kwabo-IT
- Goedkeuring op template-tekst door Kwabo

---

## §2.2 Knelpunten (3)

| Knelpunt | Status |
|----------|--------|
| **1. Handmatig overtikken** — orders handmatig overnemen uit e-mails/PDF's/CSV naar Nav | ✅ Opgelost: Claude Vision extraheert automatisch, reviewer controleert en klikt 1x |
| **2. Artikelnummer-matching** — klant-nummers ≠ Kwabo-nummers, raadplegen van klantenkaarten | ✅ Opgelost: 5-staps cascade + self-learning + SharePoint-sync |
| **3. Prijsvalidatie over meerdere bronnen** — mix/pallet/topcoat kortingslogica | ✅ Opgelost: cascade best_match() met type-prioriteit |

---

## §2.3 Oplossingscomponenten (A-E)

### Component A: AI E-mail Parser
**Offerte:** "Leest inkomende mails, herkent taal (NL/DE/EN), extraheert orderdata uit vrije tekst, PDF- en CSV-bijlagen"

**Status: ✅ VOLLEDIG**
- Claude Sonnet 4.5 met Vision-API (leest PDF als beeld, niet alleen tekst)
- Taaldetectie NL/DE/EN per order
- Provenance per veld: {value, source, source_detail, confidence, needs_review}
- Multi-order detectie (als 1 mail meerdere bestellingen bevat → automatisch gesplitst)
- Forwarded-email parser (6/6 forwards correct gedetecteerd in test-set)
- Prompt-caching voor kostenreductie bij herverwerking

### Component B: Slimme Artikelmatching
**Offerte:** "Matcht klant-artikelnummers tegen Navision masterdata en klantenkaarten. Leert van eerdere orders."

**Status: ✅ VOLLEDIG**
- 5-staps cascade (exact → history → klantenkaart → fuzzy → manual)
- Self-learning: elke reviewer-correctie verbetert toekomstige matches
- SharePoint-sync voor klantenkaarten (Graph client + CLI-script)
- Dashboard Excel-import per klant
- Baseline auto-match: 31-40% (beperkt door seed-data; stijgt structureel door self-learning + echte masterdata)

### Component C: Automatische Navision-invoer
**Offerte:** "Vult de verkooporder in Navision automatisch in via API"

**Status: ✅ VOLLEDIG (mock; real-client klaar)**
- MockNavisionClient → JSON op disk (voor development/demo)
- RealNavisionClient → volledig geschreven (Basic Auth + OAuth2, retry, idempotency)
- ReplayNavisionClient → JSON-fixture voor offline QA/CI
- `build_sales_order_payload()` → gedeelde helper voor preview EN push (byte-identiek)
- Navision-preview in kolom 3 van review-pagina (live update bij elke wijziging)

### Component D: Prijsvalidatie-engine
**Offerte:** "Controleert automatisch of prijzen overeenkomen met geldende prijsafspraken inclusief mixkortingen, palletprijzen en tijdelijke kortingsperiodes"

**Status: ✅ VOLLEDIG**
- `PrijsRepo.best_match()` cascade: pallet > mix > topcoat > standaard
- `min_hoeveelheid` guard (palletprijs alleen als hoeveelheid ≥ drempel)
- Geldigheidsperiode-check (geldig_van / geldig_tot)
- >5% afwijking = warning + needs_review
- Sanity checks op extreme hoeveelheden

### Component E: Klantherkenning
**Offerte:** "Herkent bekende klanten automatisch. Bij nieuwe klanten: signaleert 4+ status en initieert indien nodig de kredietcontrole"

**Status: ✅ VOLLEDIG**
- E-mail → DB-match → Nav-search → fuzzy-naam (met forward-detectie)
- 16/16 klanten gematcht in test-set (100%)
- 4+ signalering: badge in UI + warning als niet-4+
- Kredietlimiet: getoond als pill in klant-blok
- Provenance: "email" / "forward_email" / "navision_search" / "missing"

---

## §4.1 Technische Architectuur

| Offerte-component | Implementatie | Status |
|---|---|---|
| **Workflow Engine: n8n** | LangGraph (Python graph-based agent framework) | ✅ Equivalent — LangGraph is preciezer voor AI-pipelines; n8n kan later als UI-wrapper |
| **AI/LLM** | Claude Sonnet 4.5 via Anthropic SDK (Vision + prompt-caching) | ✅ |
| **ERP-integratie: NAV 2018 REST API** | Mock + RealNavisionClient (standaard API + custom OData skeleton) | ✅ Klaar voor credentials |
| **E-mail integratie: IMAP/Graph** | FileDropEmailClient (protocol klaar, adapters skeleton) | ⚠ Adapter ~50 regels; wacht op credentials |
| **Referentiedata: SharePoint klantenkaarten** | SharePointClient + sync_sharepoint.py + dashboard Excel-import | ✅ |
| **Dashboard** | Next.js 16 + Tailwind v4 met Kwabo-branding | ✅ |
| **Hosting: on-premise/Hetzner** | Docker Compose (backend + frontend) | ✅ Dockerfiles + compose klaar |

### Navision API (Fase 1)

| API/Service | Operaties | Type | Status |
|---|---|---|---|
| **salesOrders + Lines** | GET, POST, PATCH | Standaard API | ✅ Mock + Real-skeleton |
| **customers** | GET | Standaard API | ✅ Mock + Real-skeleton |
| **items** | GET | Standaard API | ✅ Mock + Real-skeleton |
| **Item Availability** | GET | Custom OData (indien nodig) | ⏳ Niet geïmplementeerd — pas nodig bij assemblage-detectie (Fase 2) |

---

## §5 Investering & Uren

| Onderdeel | Uren offerte | Status | Toelichting |
|---|---|---|---|
| E-mail parser & meertalige extractie | 10 | ✅ | Vision-extractor + forwarded-parser + multi-order |
| Artikelmatching (incl. klantenkaart) | 8 | ✅ | 5-staps cascade + self-learning + SharePoint-sync |
| Navision API-integratie orderaanmaak | 8 | ✅ (mock + skeleton) | Real-client klaar; credentials-afhankelijk |
| Prijsvalidatie & kortingslogica | 4 | ✅ | Cascade + mix/pallet/topcoat + sanity |
| Review dashboard & klantherkenning | 6 | ✅ | 3-koloms UI + provenance + needs-review + audit |
| **TOTAAL** | **36** | **✅** | |

### Maandelijkse kosten (na livegang)

| Component | Offerte | Realiteit |
|---|---|---|
| Hosting & licentiekosten | €25/mnd | Docker op Hetzner/on-prem = €5-15/mnd |
| AI/LLM API-kosten | €50-75/mnd | ~€0.03/PDF-pagina × 50-100 orders/week × ~3 pagina's = €30-50/mnd |
| **Totaal** | **€75-100/mnd** | **€35-65/mnd** (voordeliger door prompt-caching) |

---

## §6.1 Scope — Wat zit erin (7 items)

| # | Scope-item | Status | Bewijs |
|---|---|---|---|
| 1 | AI-gestuurde e-mail parsing (NL, DE, EN) | ✅ | Claude Vision + forwarded parsing; 17/17 test-emails geparsed |
| 2 | Artikelmatching tegen Nav masterdata + SharePoint klantenkaarten | ✅ | 5-staps cascade + Excel-import + SharePoint-sync script |
| 3 | Automatische aanmaak verkooporders in Navision via API | ✅ (mock) | `build_sales_order_payload()` + RealNavisionClient klaar |
| 4 | Prijsvalidatie incl. kortingslogica | ✅ | `best_match()` cascade + mix/pallet/topcoat |
| 5 | Klantherkenning en 4+/kredietcheck-signalering | ✅ | 100% match + 4+-badge + krediet-pill |
| 6 | Review dashboard voor accordering | ✅ | 3-koloms (email/extract/nav-preview) + provenance + needs-review banner |
| 7 | Testen (UAT) + livegang | ⏳ | pytest 44/44 groen; UAT wacht op Kwabo orderteam + echte Nav-test |

---

## §6.2 Wat zit er NIET in

| Item | Status | Toelichting |
|---|---|---|
| Werkzaamheden NAV-partner | Buiten scope | Custom web services moet Kwabo apart regelen |
| Wijzigingen NAV-configuratie | Buiten scope | Geen tabellen/pagina's/codeunits aangepast |
| Integratie andere systemen (dan Nav + SharePoint) | Buiten scope | — |
| Scenario 2 (dashboard, data-audit, inkooptool) | Apart voorstel | Zie hieronder |
| Structurele proceswijzigingen | Buiten scope | — |
| Hardware/licentiekosten derden | Buiten scope | — |

---

## §6.3 Aannames — verificatie

| Aanname | Status |
|---|---|
| 10-20 representatieve order-e-mails | ✅ 17 ontvangen en gebruikt voor kalibratie |
| Navision testomgeving beschikbaar | ⏳ Wacht op Kwabo/NAV-partner |
| NAV-partner beschikbaar voor web services (2 weken) | ⏳ Wacht op Kwabo |
| Order intake team beschikbaar voor UAT | ⏳ Wacht op planning |
| 5-10 vaste klantformaten | ✅ 16 unieke klanten geïdentificeerd en geconfigureerd |

---

## WAT NOG NODIG IS VOOR LIVEGANG FASE 1

### Blokkers (afhankelijk van Kwabo-IT)

| # | Actie | Door wie | Impact |
|---|---|---|---|
| 1 | NAV testomgeving URL + webservice-account | Kwabo + NAV-partner | Zonder dit kunnen we niet naar echte Nav pushen |
| 2 | IMAP of Graph credentials voor info@kwabo.nl | Kwabo-IT | Zonder dit: handmatig .eml droppen |
| 3 | SMTP of Graph credentials voor bevestigingsmail | Kwabo-IT | Zonder dit: bevestiging alleen gelogd |
| 4 | SharePoint site/drive-ID (optioneel als Excel-upload volstaat) | Kwabo-IT | Excel-upload werkt nu al zonder SharePoint |

### Pilex-werk (1-2 dagen na ontvangst credentials)

| # | Taak | Geschatte duur |
|---|---|---|
| 1 | `ImapEmailClient` of `GraphEmailClient` implementeren | 2-3 uur |
| 2 | `NAVISION_MODE=real` aansluiten + testen tegen testcompany | 4-6 uur |
| 3 | `MAIL_MODE=smtp` configureren + template afstemmen | 1 uur |
| 4 | Shadow-mode draaien (2 weken parallel) | monitoring |
| 5 | UAT met orderteam | 1-2 sessies |
| 6 | Livegang | 1 uur deployment |

---

---

# SCENARIO 2: Data, Voorraad & Inkoop (Fase 2)

**Offerte-status:** Indicatief · €7.000-€8.000 · 4-5 weken · Scope na afstemming tijdens Fase 1

**Huidige implementatie-status: ❌ NIET GESTART**

Dit scenario is bewust apart gehouden. Hieronder staat wat de offerte beschrijft zodat het volledig is gedocumenteerd.

---

## §3.1 Volledig assemblage/voorraad-proces (13 stappen)

### ORDER INTAKE (stap 1-2)
| Stap | Beschrijving | Fase 2 status |
|---|---|---|
| 1 | Order intake (zelfde als Scenario 1) | ✅ Via Fase 1 |
| 2 | Verkooporder opslaan met status 'Open', zichtbaar voor logistiek | ✅ Via Fase 1 (Nav-push) |

### LOGISTIEK — Beschikbaarheid & Planning (stap 3-6)
| Stap | Beschrijving | Fase 2 status |
|---|---|---|
| 3 | Per orderregel beschikbaarheid nachecken: (1) directe voorraad, (2) inkomende containers/transfers, (3) onbestickerde bulk | ❌ Niet gebouwd |
| 4 | Reserveren op verkooporderregel of transferregel; bulk opzoeken op artikelnaam zonder bedrijfsnaam | ❌ Niet gebouwd |
| 5 | Bij niet-beschikbaar: assemblageorder aanmaken met artikelen, hoeveelheden, labels; bij gedeeltelijke voorraad: splitsen | ❌ Niet gebouwd |
| 6 | Assemblageorder controleren op volledigheid; status → 'Vrijgegeven' | ❌ Niet gebouwd |

### MAGAZIJN — Assemblage & Verzending (stap 7-12)
| Stap | Beschrijving | Fase 2 status |
|---|---|---|
| 7 | Grondstof- en materiaalbeschikbaarheid controleren, reserveren | ❌ |
| 8 | Transferorder (container) inboeken in Nav, voorraad vrijgeven | ❌ |
| 9 | Assemblage uitvoeren: etiketteren, bestickeren, componenten picken | ❌ (fysiek proces) |
| 10 | Assemblageorder gereedmelden in Nav | ❌ |
| 11 | Assemblageorder inboeken; producten beschikbaar op verkooporder | ❌ |
| 12 | Verkooporder boeken, afleverbon afdrukken, verzendsticker plakken | ❌ |

### ADMINISTRATIE (stap 13)
| Stap | Beschrijving | Fase 2 status |
|---|---|---|
| 13 | Eindcontrole + facturatie | ❌ |

---

## §3.2 Geïdentificeerde knelpunten (Fase 2)

| # | Knelpunt | Status |
|---|---|---|
| 1 | **Voorraaddata in Navision klopt niet** — registratieproblemen, procesfouten, systeemissues | ❌ Data-audit niet gestart |
| 2 | **Geen centraal overzicht** — voorraad, orders, inkoop verspreid over Nav-schermen + Excel | ❌ Dashboard niet gebouwd |
| 3 | **MRP-planning niet real-time** — Excel-gebaseerd, niet live gekoppeld aan Nav | ❌ MRP-vervanging niet gebouwd |

---

## §3.3 Oplossingsrichtingen (Fase 2)

| Richting | Beschrijving | Status |
|---|---|---|
| **Data-audit & oorzaakanalyse** | Uitzoeken waarom voorraaddata niet klopt; registratieproblemen/procesfouten identificeren | ❌ Niet gestart |
| **Centraal operations dashboard** | Eén overzicht: real-time voorraad (bestickerd + onbestickerd), openstaande orders, inkooporders, inkomende containers | ❌ Niet gebouwd |
| **Slimme inkoopsuggesties** | MRP-Excel vervangen door geïntegreerd systeem met real-time Nav-data; AI-suggesties op basis van verkooppatronen | ❌ Niet gebouwd |
| **Automatische assemblage-detectie** | Systeem herkent automatisch of assemblage nodig is op basis van productcodes + voorraadniveaus + containers | ❌ Niet gebouwd |
| **Guided assemblageorder-aanmaak** | Automatisch assemblageorder-voorstel genereren inclusief componenten, hoeveelheden en labels op basis van BOM | ❌ Niet gebouwd |

---

## §4.1 Navision API (Fase 2)

| API/Service | Operaties | Type | Status |
|---|---|---|---|
| Assembly BOM (Page 36 / Table 90) | GET | Custom OData | ❌ |
| Assembly Orders (Page 900) | GET, POST | Custom OData | ❌ |
| Assembly Order Lines (Page 901) | GET, POST | Custom OData | ❌ |
| Item Ledger Entries (Table 32) | GET | Custom OData | ❌ |
| Transfer Orders | GET | Custom OData | ❌ |
| Purchase Orders | GET | Custom OData | ❌ |
| salesInvoices | GET | Standaard API | ❌ |

*Alle Fase 2 API's vereisen dat de NAV-partner custom web services publiceert.*

---

## §7 Vervolgstappen

| # | Actie | Door | Status |
|---|---|---|---|
| 1 | Akkoord op dit voorstel (Fase 1) | Kwabo | ✅ Akkoord |
| 2 | Voorbeeld order-e-mails aanleveren (10-20) | Kwabo | ✅ 17 ontvangen |
| 3 | Navision testomgeving + webservice-account | Kwabo + NAV-partner | ⏳ In afwachting |
| 4 | Kickoff en start ontwikkeling Fase 1 | Pilex | ✅ Gestart en grotendeels af |
| 5 | Tijdens Fase 1: samen Fase 2 scopen | Pilex + Kwabo | ⏳ Nog te plannen |
| 6 | Oplevering Fase 1 + UAT | Pilex + orderteam | ⏳ Na Nav-testomgeving |
| 7 | Livegang Fase 1 | Pilex + Kwabo | ⏳ Na UAT |
| 8 | Voorstel Fase 2 ter goedkeuring | Pilex | ⏳ Na Fase 1 live |
