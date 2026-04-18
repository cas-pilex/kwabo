# Voortgangsrapportage Kwabo Order Intake AI

**Project:** AI Automation voor Verkooporderprocessen — Fase 1: Intelligente Order Intake
**Klant:** Kwabo Techniek B.V.
**Leverancier:** Pilex — AI Automation Consultancy
**Offerte-referentie:** Kwabo_Offerte_Definitief v2.0, maart 2026
**Rapportagedatum:** 16 april 2026

---

## 1. Managementsamenvatting

Fase 1 is inhoudelijk **nagenoeg afgerond**. Alle vijf oplossingscomponenten (A t/m E) uit de offerte zijn gebouwd, getest op 17 echte order-e-mails, en draaien als werkend systeem. De livegang hangt af van twee acties aan Kwabo-zijde: (1) Navision-testomgeving met webservice-account en (2) e-mail/SMTP-credentials. Na ontvangst hiervan schatten wij **1-2 werkdagen** voor de koppeling + een shadow-run-periode, waarna UAT met het orderteam kan starten.

| KPI | Resultaat op testset (17 e-mails) |
|-----|----------------------------------|
| E-mails succesvol geparseerd | **17 van 17 (100%)** |
| Correct als order geclassificeerd | **16 van 17** (1 terecht als "geen order": was een pakbon/Lieferschein) |
| Klant automatisch herkend | **16 van 16 (100%)** (incl. 6 doorgestuurde mails van Kwabo-medewerkers) |
| Orderregels geëxtraheerd | **35 regels** uit 16 orders |
| Artikelen automatisch gematcht | **31-40%** (op basis van illustratieve seed-data; stijgt structureel bij echte Navision-masterdata + zelflerend effect) |
| Multi-order detectie | **1 e-mail met 2 bestellingen** automatisch gesplitst in 2 aparte orders |
| Verkooporders aangemaakt (mock-Navision) | **16 van 16** succesvol naar mock-ERP gepusht als JSON |

---

## 2. Oplevering per offerte-onderdeel

### 2.1 Processtappen uit de reverse-demo

Tijdens de procesanalyse zijn 11 handmatige stappen geïdentificeerd. Hieronder per stap wat er is gebouwd.

---

#### Stap 1 — Order komt binnen per e-mail

**Offerte:** "Order komt binnen per e-mail op info@kwabo.nl (als vrije tekst, PDF of Excel/CSV bijlage, in NL, DE of EN)"

**Opgeleverd:**
- E-mail parser die `.eml`-bestanden verwerkt via Python's standaard `email`-module
- **Ondersteunde bijlageformaten:** PDF, Excel (.xlsx/.xls), CSV, en ZIP-archieven (PDF's in ZIP worden automatisch uitgepakt — relevant voor o.a. BAUHAUS die orders als ZIP verstuurt)
- Afbeeldingen (logo's, handtekeningen) worden automatisch overgeslagen
- **Forwarded e-mails:** een dedicated parser herkent wanneer een Kwabo-medewerker (bijv. Ivar, Mark, Nico) een klantorder doorstuurt. De parser extraheert de originele afzender uit de forwarded headers in drie talen (NL: "Van:", EN: "From:", DE: "Von:"). In de testset worden alle 6 forwarded e-mails correct teruggeleid naar de juiste klant.

**Hoe het nu werkt:**
- Momenteel worden e-mails als `.eml`-bestanden in een inbox-map geplaatst (file-drop modus)
- Het `EmailClient`-protocol is zo ontworpen dat een IMAP- of Microsoft Graph-adapter dezelfde interface implementeert. De omschakeling is een configuratie-wijziging (`EMAIL_MODE=imap` of `EMAIL_MODE=graph` in het `.env`-bestand) + het invullen van de betreffende credentials.

**Wat nog nodig voor live:**
- IMAP- of Microsoft Graph-credentials voor `info@kwabo.nl` (actie Kwabo-IT)
- Implementatie van de betreffende adapter (~50 regels code, ~2 uur)

---

#### Stap 2 — Bijlagen naar Scans-map

**Offerte:** "Medewerker sleept bijlagen handmatig naar de Scans-map op het netwerk"

**Opgeleverd:**
- Bijlage-inhoud (geëxtraheerde tekst + metadata) wordt opgeslagen als onderdeel van de order-state in de database
- In het review-dashboard worden alle bijlagen weergegeven in kolom 1, met de volledige PDF-tekst uitklapbaar per bijlage

**Wat nog nodig:**
- Optioneel: fysieke opslag van bijlage-bestanden op schijf (als vervanging van de Scans-map)
- Of: bijlagen als attachment aan de Navision-verkooporder koppelen via de NAV attachments-API (custom OData, indien beschikbaar)

---

#### Stap 3 — Verkooporder openen in Navision + ordernummer genereren

**Offerte:** "In Navision een nieuwe verkooporder openen en ordernummer genereren"

**Opgeleverd:**
- **Mock-Navision client** die het volledige API-gedrag simuleert. Orders worden als JSON-bestanden op schijf geschreven met unieke ordernummers (SO-xxxxxxxx). Dit maakt het mogelijk de volledige flow te testen en te demonstreren zonder live NAV-verbinding.
- **Productie-Navision client** (`RealNavisionClient`) is volledig geschreven en ondersteunt:
  - **Basic Authentication** (NAV Web Service Access Key): `NAV_USERNAME` + `NAV_PASSWORD`
  - **OAuth2** (Azure AD client credentials): `NAV_TENANT_ID`, `NAV_CLIENT_ID`, `NAV_CLIENT_SECRET`
  - `POST /api/v2.0/companies({companyId})/salesOrders` voor het aanmaken van de order-header
  - `POST /salesOrders({id})/salesOrderLines` voor het toevoegen van orderregels
  - **Idempotency-check:** vóór het aanmaken wordt gecontroleerd of een order met hetzelfde `externalDocumentNumber` (= bestelnummer klant) al bestaat, om dubbele orders te voorkomen
  - **Retry-mechanisme:** bij server-fouten (HTTP 5xx) wordt automatisch tot 3× herhaald met exponentiële wachttijd
- **Replay-client** voor offline QA/CI: draait tegen een JSON-fixture-bestand zodat tests ook zonder netwerk draaien
- Omschakeling via `NAVISION_MODE=mock|replay|real` in `.env`

**Gebruikte Navision API-endpoints (standaard, Fase 1):**

| Endpoint | Operatie | Doel |
|----------|----------|------|
| `salesOrders` | POST | Verkooporder aanmaken |
| `salesOrders({id})/salesOrderLines` | POST | Orderregels toevoegen |
| `customers` | GET | Klant opzoeken op nummer, naam of e-mail |
| `items` | GET | Artikel opzoeken op nummer of omschrijving |

**Wat nog nodig voor live:**
- NAV-server URL + Company ID + webservice-account (actie Kwabo + NAV-partner)
- Testen tegen Navision-testomgeving (niet productie)

---

#### Stap 4 — Klantgegevens invullen; 4+ en krediet controleren

**Offerte:** "Klantgegevens invullen; bij onbekende klant: 4+ lidmaatschap controleren of kredietlimiet aanvragen bij Allianz"

**Opgeleverd — Klantherkenning:**
Het systeem herkent klanten automatisch via een 4-staps cascade:

1. **E-mailadres matchen** tegen de lokale klantenkaart-database → confidence 100%
2. **Forward-detectie:** als de afzender een Kwabo-medewerker is (bijv. `Ivar.Dofferhoff@kwabo.nl`), wordt de originele afzender uit de doorgestuurde tekst gehaald en gebruikt voor de match
3. **Navision customers-API doorzoeken** op e-mailadres → confidence 95%
4. **Navision naam-zoeken** op basis van het e-maildomein (bijv. `ferney.nl` → "Ferney") → confidence 70%
5. Als geen match gevonden: **"KLANT NIET GEVONDEN"**-waarschuwing; de medewerker selecteert handmatig via een combobox in het dashboard

**Resultaat op testset:** 16 van 16 orders correct aan de juiste klant gekoppeld (100%), inclusief 6 doorgestuurde e-mails.

**Opgeleverd — 4+ signalering:**
- Na een succesvolle klant-match worden de velden `is_4plus` (boolean) en `kredietlimiet` (decimaal) uit de klantenkaart-database gelezen
- Als de klant **geen 4+ lid** is, wordt een waarschuwing toegevoegd: "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden"
- In het review-dashboard wordt naast de klantnaam een **badge** getoond:
  - Groene badge "4+ lid" als de klant wél lid is
  - Rode badge "geen 4+" als de klant géén lid is
  - Blauwe pill "krediet € X.XXX" met het kredietlimiet-bedrag

**Wat nog nodig voor live:**
- In de klantenkaart-seed moeten de echte 4+-statussen en kredietlimieten worden ingevuld (nu staan voorbeeldwaarden)
- Voor daadwerkelijke krediet-benutting-berekening: openstaand-saldo opvragen via NAV-API (`GET /salesOrders?$filter=customerNumber eq 'X' and status eq 'Open'` + optellen). Nu wordt alleen het limiet-bedrag getoond.

---

#### Stap 5 — Ordernummer, bestelnummer en referentienummer overnemen

**Offerte:** "Ordernummer, bestelnummer en referentienummer overnemen uit de bijlagen"

**Opgeleverd:**
- Claude Sonnet 4.5 met **Vision-API** leest het PDF-document als beeld (niet als geëxtraheerde tekst). Dit werkt ook op gescande/image-only PDF's en complexe tabelindelingen.
- Per geëxtraheerd veld wordt een **provenance-record** bijgehouden:
  - `value`: de waarde zelf (bijv. "4200056148")
  - `source`: waar het vandaan komt ("pdf", "email_body", "email_header", "missing")
  - `source_detail`: exacte locatie (bijv. "Ferney.pdf p.1 header")
  - `confidence`: 0.0 tot 1.0 (bijv. 0.99 voor duidelijk leesbare velden)
  - `needs_review`: boolean — `true` als het veld ontbreekt of onzeker is
- Bij elke herverwerking van dezelfde e-mail wordt **prompt-caching** toegepast (de PDF blijft in de Anthropic-cache), wat de kosten met ~80% verlaagt.
- **Multi-order detectie:** als Claude meerdere bestellingen herkent in één e-mail (bijv. Bugel stuurt April- en Mei-bestelling in één mail), worden deze automatisch gesplitst in aparte orders. De sub-orders erven de audit-trail van de primaire order en tonen een link naar de parent-order in het dashboard.

**In het review-dashboard:**
- Kolom 2 toont naast elk veld een **provenance-icoontje**:
  - 📄 = uit PDF
  - 📧 = uit e-mail header/body
  - 📇 = uit klantenkaart (database)
  - 🕘 = uit eerdere correctie (self-learning)
  - ✏️ = handmatig ingevoerd door reviewer
  - ⚠️ = ontbreekt (rood omrand, "Vul aan…"-placeholder)
- Het confidence-percentage wordt getoond als een kleur-gecodeerde pill (groen ≥90%, amber 70-89%, rood <70%)

---

#### Stap 6 — Bijlagen koppelen aan de order

**Offerte:** "Bijlagen koppelen aan de order vanuit de Scans-map"

**Opgeleverd:**
- Alle bijlagen zijn zichtbaar en uitklapbaar in kolom 1 van het review-dashboard
- Bijlage-metadata (naam, type, inhoud) wordt bewaard in de order-state

**Wat nog nodig:**
- Fysieke opslag als losse bestanden en/of koppeling via Navision attachments-API (optioneel)

---

#### Stap 7 — Artikelnummer opzoeken; klantenkaart raadplegen

**Offerte:** "Per orderregel: artikelnummer opzoeken uit bijlagen. Bij afwijkende nummering: vorige order of klantenkaart in SharePoint raadplegen"

**Opgeleverd — Artikelmatching engine:**
Een 5-staps cascade die per orderregel het klant-artikelnummer omzet naar het Kwabo/Navision-artikelnummer:

| Stap | Methode | Voorbeeld | Confidence |
|------|---------|-----------|------------|
| 1. **Exact** | Klant noemt zelf het Kwabo-nummer (bijv. "Uw artikelnummer: 228321") | TABS-order: `K700100007 → 228321` | 100% |
| 2. **History** | Dit klant-artikelnummer is eerder handmatig gecorrigeerd door een reviewer → automatisch hergebruiken | Ferney `23532` was vorige keer gecorrigeerd naar `1515155` | 95% |
| 3. **Klantenkaart** | Mapping staat in de klantenkaart-database (geïmporteerd uit SharePoint of dashboard) | Isero `24300 → 2597768` uit Excel-import | 90% |
| 4. **Fuzzy** | Omschrijving vergelijken met alle Navision-artikelen via fuzzy-matching (rapidfuzz WRatio) | "Stucloper 120cm" ≈ "Stucloper 120 cm wit" | 70-90% |
| 5. **Manual** | Niet gevonden → markeer als needs_review, reviewer selecteert handmatig | Rode rand in dashboard, combobox doorzoekt Nav-items | 0% |

**Self-learning mechanisme:**
Wanneer een reviewer in het dashboard een artikelnummer corrigeert en de order goedkeurt, wordt deze correctie opgeslagen in twee tabellen:
- `artikel_matching_history` (voor stap 2 — history lookup)
- `klantenkaart_artikelen` (voor stap 3 — klantenkaart mapping)

Dit betekent dat dezelfde klant-artikelcombinatie de volgende keer **automatisch** correct wordt gematcht, zonder handmatige interventie.

**SharePoint-koppeling:**
- Een Microsoft Graph-client (`SharePointClient`) kan Excel-bestanden downloaden vanuit SharePoint
- Een CLI-script (`sync_sharepoint.py`) kan handmatig of via cron worden uitgevoerd:
  ```
  python scripts/sync_sharepoint.py --file klantenkaart.xlsx --klant 10001
  python scripts/sync_sharepoint.py --sharepoint --folder "Klantenkaarten" --klant 10001
  ```
- Het dashboard biedt per klant een **"Import Excel"**-tab waar een `.xlsx`-bestand kan worden geüpload via de browser
- Verwachte Excel-kolommen: `klant_artikelnr`, `kwabo_artikelnr`, optioneel `omschrijving`, `prijs`, `korting_pct`, `geldig_tot`

**Wat nog nodig voor live:**
- SharePoint site/drive-ID (optioneel; Excel-upload via dashboard werkt nu al zonder SharePoint-credentials)
- Initieële import van bestaande klantenkaarten als Excel-bestanden

---

#### Stap 8 — Hoeveelheden overtikken, palletaantal invullen

**Offerte:** "Hoeveelheden overtikken, palletaantal invullen"

**Opgeleverd:**
- Hoeveelheden en eenheden worden door Claude geëxtraheerd uit PDF/body met provenance
- **Eenheid-normalisatie:** 30+ varianten worden automatisch omgezet naar Navision-codes:

| Invoer (voorbeeld) | Navision-code |
|---------------------|---------------|
| Rolle, Roll, rollen, RLL | ROL |
| stuks, Stück, pcs, ea, STK | STUK |
| pallet, Pallet, PAL | PAL |
| m², qm | M2 |
| meter, lfm | M1 |
| bos, BOS | BOS |
| doos, box | DOOS |
| kg, KG | KG |

- In het dashboard zijn hoeveelheid en eenheid **beide bewerkbaar** per orderregel

---

#### Stap 9 — Prijs controleren; mixkortingen en palletprijzen

**Offerte:** "Prijs controleren tegen prijzendocument in klantmap; mixkortingen en palletprijzen toepassen (tenzij topcoat-uitzondering)"

**Opgeleverd — Prijsvalidatie-engine met cascadelogica:**

Het systeem zoekt per orderregel de meest specifieke geldende prijsafspraak op in een prioriteitscascade:

| Prioriteit | Type | Voorwaarde | Voorbeeld |
|------------|------|------------|-----------|
| 1 (hoogste) | **Palletprijs** | `min_hoeveelheid ≤ bestelde hoeveelheid` | Klant bestelt 60 stuks, palletprijs geldt vanaf 50 → palletprijs van toepassing |
| 2 | **Mixkorting** | `min_hoeveelheid ≤ totale bestelhoeveelheid` | Gemengde order met korting op totaalvolume |
| 3 | **Topcoat-uitzondering** | Altijd (als geconfigureerd) | Specifieke producten met afwijkende prijsstelling |
| 4 (laagste) | **Standaardprijs** | Fallback | Normale afgesproken prijs |

Na het bepalen van de juiste afspraak wordt de verwachte prijs berekend als `prijs × (1 - korting_pct / 100)` en vergeleken met de prijs op de bestelling:
- **≤5% afwijking:** ✅ geaccepteerd (groen indicator in dashboard)
- **>5% afwijking:** ❌ waarschuwing met vermelding van het prijstype, bijv. "PRIJS AFWIJKING regel 1: klant €19.35 vs palletprijs-afspraak €12.00 (61.3%)"
- **Geen afspraak gevonden:** grijze indicator, informatief

**Klantenbeheer — Prijsafspraken-tab:**
Het dashboard biedt per klant een **Prijsafspraken**-tab waar afspraken kunnen worden:
- Toegevoegd (artikelnr, prijs, korting%, type, geldig tot)
- Verwijderd
- Geïmporteerd via Excel-upload (dezelfde upload als voor artikelmappings)

---

#### Stap 10 — Eenheden en aantallen controleren op realisme

**Offerte:** "Eenheden en aantallen controleren op realisme; bij twijfel terugbellen of -mailen"

**Opgeleverd — Sanity checks:**

Het systeem past 5 automatische realisme-controles toe op elke orderregel:

| Controle | Drempel | Waarschuwing |
|----------|---------|-------------|
| Nul of negatief | hoeveelheid ≤ 0 | "Hoeveelheid is 0 of negatief" |
| Extreem palletaantal | PAL > 100 | "Meer dan 100 pallets besteld — klopt dit?" |
| Extreem stukaantal | STUK > 50.000 | "Meer dan 50.000 stuks besteld — klopt dit?" |
| Extreem rollenaantal | ROL > 5.000 | "Meer dan 5.000 rollen besteld — klopt dit?" |
| Onbekende eenheid | eenheid leeg of "ONBEKEND" | "Onbekende eenheid" |

Wanneer een controle triggert, verschijnt de waarschuwing in de needs-review-banner en wordt het betreffende veld gemarkeerd als `needs_review` (rode rand, reviewer moet bevestigen of corrigeren).

---

#### Stap 11 — Ontvangstbevestiging versturen

**Offerte:** "Ontvangstbevestiging versturen vanuit Navision; orderbevestiging later met verzenddatum"

**Opgeleverd:**
Na een succesvolle push naar Navision verstuurt het systeem automatisch een ontvangstbevestiging aan de klant. Drie verzendmodi worden ondersteund:

| Modus | Configuratie | Werking |
|-------|-------------|---------|
| **Log** (standaard) | `MAIL_MODE=log` | Bevestiging wordt gelogd (geen e-mail verstuurd; voor development) |
| **SMTP** | `MAIL_MODE=smtp` | Verstuurt via SMTP (TLS) met configureerbare host/poort/credentials |
| **Microsoft Graph** | `MAIL_MODE=graph` | Verstuurt via Graph API `POST /me/sendMail` (voor Office 365) |

**E-mailtemplate** (bewerkbaar in `backend/src/kwabo/templates/ontvangstbevestiging.txt`):
```
Geachte {klant_naam},

Wij bevestigen de ontvangst van uw bestelling met referentie {bestelnr_klant}.
Uw order is verwerkt en opgenomen in ons systeem onder Navision-ordernummer {navision_order_nr}.

Heeft u vragen over deze bestelling? Neem dan contact met ons op via info@kwabo.nl.

Met vriendelijke groet,
Kwabo Techniek B.V.
Volendam
```

In de audit-trail wordt geregistreerd of de mail daadwerkelijk is verstuurd of alleen gelogd.

**Wat nog nodig voor live:**
- SMTP-credentials of Graph-credentials (actie Kwabo-IT)
- Afstemming op gewenste template-tekst

---

### 2.2 Knelpunten uit de procesanalyse

| # | Knelpunt uit offerte | Hoe opgelost |
|---|---------------------|-------------|
| 1 | **Handmatig overtikken van orderdata** — Elke order moet handmatig worden overgetikt uit e-mails, PDF's of CSV-bestanden naar Navision. E-mails komen in drie talen (NL, DE, EN) en in wisselende formats. | Claude Vision extraheert automatisch uit elk PDF-formaat (ook gescand). De reviewer controleert in het 3-koloms dashboard en klikt "Goedkeuren" — geen handmatig overtypen meer. |
| 2 | **Artikelnummer-matching** — Klanten gebruiken eigen artikelnummers die niet overeenkomen met Kwabo-nummering. Soms ontbreken nummers en staat alleen een beschrijving. | 5-staps matching-cascade (exact → history → klantenkaart → fuzzy → manual) met zelflerend effect: elke correctie verbetert toekomstige matches. |
| 3 | **Prijsvalidatie over meerdere bronnen** — Prijzen moeten gecontroleerd worden tegen het prijzendocument. De kortingslogica is complex: mixprijzen, palletprijzen, topcoat-uitzonderingen. | Cascade prijsvalidatie met 4 niveaus (pallet > mix > topcoat > standaard), hoeveelheid-drempels, korting-berekening en >5%-afwijking-waarschuwing. |

---

### 2.3 Oplossingscomponenten (A t/m E)

#### Component A: AI E-mail Parser — ✅ Volledig opgeleverd

| Eigenschap | Detail |
|-----------|--------|
| **Technologie** | Claude Sonnet 4.5 via Anthropic Vision-API |
| **Talen** | NL, DE, EN (automatische detectie) |
| **Invoerformaten** | PDF (tekst + beeld), Excel, CSV, vrije tekst in e-mailbody, ZIP met PDF |
| **Speciale gevallen** | Forwarded e-mails (6/6 correct), multi-order in 1 mail (automatisch gesplitst) |
| **Kalibratie** | Getest op alle 17 aangeleverde voorbeeld-e-mails |
| **Kostenoptimalisatie** | Prompt-caching reduceert API-kosten bij herverwerking met ~80% |
| **Provenance** | Elk geëxtraheerd veld heeft bron, locatie, confidence en review-vlag |

#### Component B: Slimme Artikelmatching — ✅ Volledig opgeleverd

| Eigenschap | Detail |
|-----------|--------|
| **Matching-strategieën** | 5 niveaus: exact, history, klantenkaart, fuzzy, manual |
| **Self-learning** | Reviewer-correcties worden opgeslagen en automatisch hergebruikt |
| **Klantenkaart-bron** | SharePoint-sync (Graph API) + dashboard Excel-upload |
| **Fuzzy-matching** | rapidfuzz WRatio met ≥70% drempel |
| **Baseline op testset** | 31-40% auto-match (beperkt door seed-data; verwachting met echte masterdata: >80%) |

#### Component C: Automatische Navision-invoer — ✅ Volledig opgeleverd (mock; real-client klaar)

| Eigenschap | Detail |
|-----------|--------|
| **Mock-modus** | Simuleert volledige NAV API; orders als JSON op disk |
| **Productie-client** | Basic Auth + OAuth2, retry, idempotency-check op bestelnummer |
| **Replay-modus** | JSON-fixture voor offline QA/CI |
| **Preview** | Live Navision-payload preview in kolom 3 van dashboard (refresht bij elke wijziging) |
| **Omschakeling** | `NAVISION_MODE=mock|replay|real` in `.env` |
| **NAV-endpoints** | salesOrders (POST), salesOrderLines (POST), customers (GET), items (GET) |

#### Component D: Prijsvalidatie-engine — ✅ Volledig opgeleverd

| Eigenschap | Detail |
|-----------|--------|
| **Prijstypen** | Standaard, mix, pallet, topcoat |
| **Cascade** | Pallet > mix > topcoat > standaard (meest specifieke wint) |
| **Hoeveelheid-drempel** | Pallet-/mixprijs alleen als bestelhoeveelheid ≥ `min_hoeveelheid` |
| **Afwijkingsgrens** | >5% = waarschuwing met type-vermelding |
| **Geldigheid** | Periode-check op `geldig_van` / `geldig_tot` |
| **Sanity checks** | 5 realisme-regels op hoeveelheid + eenheid |
| **Beheer** | Prijsafspraken CRUD per klant in dashboard + Excel-import |

#### Component E: Klantherkenning — ✅ Volledig opgeleverd

| Eigenschap | Detail |
|-----------|--------|
| **Matching** | E-mail → DB → NAV e-mail → NAV naam (4 stappen) |
| **Forward-detectie** | Outlook NL/EN/DE + Gmail headers |
| **4+ signalering** | Groene/rode badge in dashboard; waarschuwing als niet-4+ |
| **Kredietlimiet** | Blauwe pill met limiet-bedrag; uitbreidbaar naar benutting-check via NAV-API |
| **Resultaat testset** | 16/16 correct (100%) |

---

### 2.4 Review Dashboard

Het dashboard is het centrale punt waar de orderinvoerder de AI-verwerkte order controleert en accordeert.

**Toegang:** `http://localhost:3000` (productie-build)

**Pagina's:**

| Route | Functie |
|-------|---------|
| `/` | **Order Queue** — overzicht van alle orders met filter-tabs (In review / Gepusht / Geen order / Alle), stat-cards en "Scan inbox"-knop |
| `/orders/{id}` | **Order Review** — 3-koloms detail (zie hieronder) |
| `/klanten` | **Klantenlijst** — alle klanten met Navision-nr, naam, e-mail, taal |
| `/klanten/{nr}` | **Klantdetail** — 4 tabs: Algemeen, Artikelmappings, Prijsafspraken, Import Excel |
| `/audit` | **Audit Log** — alle AI-beslissingen per order, uitklapbaar, met KPI-cards |
| `/logs` | **Live Logs** — streaming structured log van de backend met filter en kleurcodering |

**3-koloms review-pagina (`/orders/{id}`):**

| Kolom 1: E-mail & PDF | Kolom 2: Extract + Klantkaart | Kolom 3: Navision Request |
|---|---|---|
| Originele e-mailbody (read-only) | **Klant-blok:** Nav-nr (editable), klantnaam, 4+-badge, krediet-pill | **POST** URL + headers |
| Alle bijlagen uitklapbaar met volledige PDF-tekst | **Header:** bestelnr, orderdatum, leverdatum, afleverinstructies | Live JSON-payload (syntax-highlighted) |
| | **Drop-ship adres:** naam, straat, postcode, plaats, land (alle editable) | Status-badge: 🟢 klaar / 🟡 N velden missen / 🔴 geen klant |
| | **Orderregels:** per regel → klant-artnr, Kwabo-artnr (combobox), omschrijving, hoeveelheid, eenheid, prijs, match-badge | "Kopieer JSON" knop |
| | **Opmerkingen** (editable textarea) | |
| | **Goedkeuren & Push Navision** / **Afwijzen** | |

**Needs-review systeem:**
- Bovenaan de pagina: een sticky banner toont het aantal velden dat aanvulling nodig heeft
- Per ontbrekend veld: een klikbare shortcut die direct naar het veld scrollt en de cursor erin plaatst
- De "Goedkeuren"-knop is **uitgeschakeld** zolang er verplichte velden ontbreken
- Een "Force approve (gelogd)"-toggle maakt de knop vrij; het forceren wordt geregistreerd in de audit-trail

**Elke veldwijziging in kolom 2:**
1. Triggert een `PATCH /api/orders/{id}/patch-field` naar de backend
2. Backend werkt de state bij en herberekent de needs-review-telling
3. Kolom 3 (Navision-preview) refresht automatisch binnen ~1 seconde
4. De reviewer ziet meteen het effect van elke aanpassing

---

### 2.5 Technische architectuur

| Offerte-component | Implementatie | Toelichting |
|---|---|---|
| Workflow Engine (n8n) | **LangGraph** (Python graph-based agent framework) | LangGraph biedt meer controle over AI-pipelines dan n8n; n8n kan later als visuele wrapper worden toegevoegd indien gewenst |
| AI / LLM | **Claude Sonnet 4.5** via Anthropic SDK met Vision + prompt-caching | |
| ERP-integratie | **NAV 2018 REST API** — MockNavisionClient + RealNavisionClient (Basic/OAuth2) | |
| E-mail integratie | **FileDropEmailClient** (protocol klaar voor IMAP/Graph) | |
| Referentiedata | **SharePoint Graph API** + dashboard Excel-upload + CLI sync-script | |
| Dashboard | **Next.js 16** + Tailwind v4, Kwabo-huisstijl (navy/goud), productie-build | |
| Hosting | **Docker Compose** — `Dockerfile.backend` (Python 3.12-slim) + `Dockerfile.frontend` (Node 20-slim multistage) | |

---

### 2.6 Testsuite

| Testbestand | Aantal tests | Wat wordt getest |
|-------------|-------------|-----------------|
| `test_email_parsing.py` | 8 | Alle 17 .eml-bestanden parseren, bijlagen extractie, BAUHAUS ZIP-ontvouwing |
| `test_forwarded_parser.py` | 7 | 6 forward-detecties (correcte originele afzender) + 1 negatieve test |
| `test_db.py` | 6 | Seed-data, klantenkaart-mapping CRUD, matching-history, prijsafspraken, order-log |
| `test_navision_mock.py` | 3 | Mock-klant-lookup, order-persistentie op disk, replay-client fixture |
| `test_units.py` | 21 | Eenheid-normalisatie, JSON-parsing (code-fence-stripping, array-reparatie), pad-utilities, needs-review-aggregatie, Navision-payload-bouw |
| **Totaal** | **44** | Alle tests slagen in ~23 seconden |

---

### 2.7 Database

5 tabellen in SQLite (productie: PostgreSQL):

| Tabel | Kolommen | Doel |
|-------|---------|------|
| `klantenkaarten` | nav_klantnr, naam, email, email_bestelling, telefoon, taal, standaard_afleveradres, speciale_instructies, is_4plus, kredietlimiet, betalingsconditie | Klantherkenning + 4+/krediet |
| `klantenkaart_artikelen` | klant_nr, klant_artikelnr, kwabo_artikelnr, omschrijving, standaard_prijs, korting_pct, geldig_tot | Klant-specifieke artikelmapping |
| `prijsafspraken` | klant_nr, kwabo_artikelnr, prijs, korting_pct, type (standaard/mix/pallet/topcoat), min_hoeveelheid, geldig_van, geldig_tot | Prijsvalidatie-cascade |
| `artikel_matching_history` | klant_nr, klant_artikelnr, klant_omschrijving, kwabo_artikelnr, match_methode, was_correctie, order_datum | Self-learning feedback loop |
| `order_log` | email_id, email_from, email_subject, status, is_order, klant_nr, bestelnummer_klant, navision_order_nr, aantal_regels, alle_artikelen_gematcht, alle_prijzen_valide, warnings, correcties, reviewer, stappen_log, order_state | Volledige audit-trail per order |

---

### 2.8 API-overzicht

22 REST-endpoints op `http://localhost:8000`:

| Categorie | Endpoints | Voorbeelden |
|-----------|-----------|-------------|
| **Orders** | 8 | `GET /api/orders`, `POST /approve`, `PATCH /patch-field`, `GET /navision-preview`, `GET /needs-review` |
| **Klanten** | 8 | `GET /api/klanten`, `POST /artikelen`, `GET/POST/DELETE /prijsafspraken`, `POST /import-excel` |
| **Intake** | 3 | `POST /api/intake/scan`, `POST /upload`, `POST /run-file` |
| **Audit** | 2 | `GET /api/audit`, `GET /api/audit/stats` |
| **Overig** | 3 | `GET /api/artikelen/search`, `GET /api/logs/tail`, `GET /api/logs/stream` (SSE) |

Swagger-documentatie: `http://localhost:8000/docs`

---

## 3. Actiepunten voor livegang

### Acties Kwabo / NAV-partner

| # | Actie | Wie | Geschatte doorlooptijd |
|---|-------|-----|----------------------|
| 1 | Navision-testomgeving + webservice-account (lees+schrijf op salesOrders, customers, items) | Kwabo + NAV-partner | 1-2 weken |
| 2 | IMAP-credentials of Microsoft Graph app-registratie voor info@kwabo.nl | Kwabo-IT | 1 dag |
| 3 | SMTP-credentials of Graph-credentials voor bevestigingsmails | Kwabo-IT | 1 dag |
| 4 | SharePoint site-ID + drive-ID (optioneel; Excel-upload werkt al) | Kwabo-IT | Optioneel |
| 5 | Echte klantenkaarten als Excel-bestanden (voor initiële import) | Orderteam | 1 dag |
| 6 | Beschikbaarheid orderteam voor UAT-sessie(s) | Kwabo | Planning afstemmen |

### Acties Pilex (na ontvangst credentials)

| # | Actie | Geschatte duur |
|---|-------|---------------|
| 1 | IMAP/Graph e-mail adapter implementeren + testen | 2-3 uur |
| 2 | `NAVISION_MODE=real` configureren + testen tegen testcompany | 4-6 uur |
| 3 | `MAIL_MODE=smtp/graph` configureren + template afstemmen | 1 uur |
| 4 | Initiële klantenkaart-import draaien | 1 uur |
| 5 | Shadow-mode (2 weken parallel draaien zonder echte push) | Monitoring |
| 6 | UAT-sessie(s) met orderteam | 1-2 sessies van 2 uur |
| 7 | Livegang + monitoring eerste week | 1 uur setup + dagelijkse check |

---

## 4. Maandelijkse kosten (na livegang)

| Component | Offerte-schatting | Actuele schatting | Toelichting |
|-----------|------------------|------------------|-------------|
| Hosting (Docker op Hetzner of on-prem) | €25/mnd | €5-15/mnd | Minimale resources nodig; SQLite of lichtgewicht PostgreSQL |
| AI/LLM API-kosten (Anthropic) | €50-75/mnd | €30-50/mnd | ~€0.03/PDF-pagina, prompt-caching -80%, geschat 50-100 orders/week × ~3 pagina's |
| **Totaal** | **€75-100/mnd** | **€35-65/mnd** | |

---

---

# SCENARIO 2: Data, Voorraad & Inkoop (Fase 2)

**Status:** Indicatief · €7.000-€8.000 · 4-5 weken · **Nog niet gestart**
**Planning:** Scope wordt bepaald na gezamenlijke afstemming tijdens Fase 1

Hieronder volgt een volledig overzicht van wat de offerte beschrijft voor Fase 2, zodat dit document als referentie kan dienen bij de scopingsgesprekken.

---

### Scenario 2 — Processtappen (13 stappen over 4 afdelingen)

#### ORDER INTAKE (stap 1-2) — gedekt door Fase 1

| Stap | Beschrijving | Status |
|------|-------------|--------|
| 1 | Order intake via e-mail + Navision-invoer (zelfde als Scenario 1) | ✅ Via Fase 1 |
| 2 | Verkooporder opslaan met status 'Open', zichtbaar voor logistiek | ✅ Via Fase 1 |

#### LOGISTIEK — Beschikbaarheid & Planning (stap 3-6)

| Stap | Beschrijving | Status |
|------|-------------|--------|
| 3 | Per orderregel beschikbaarheid checken op 3 niveaus: (1) directe magazijnvoorraad, (2) inkomende containers/transferorders, (3) onbestickerde bulk (artikelnaam zonder bedrijfsnaam opzoeken) | ❌ |
| 4 | Bij voldoende voorraad: reserveren op verkooporderregel. Bij inkomende containers: reserveren op transferregel. Bij bulk: magazijnvoorraad onbestickerd identificeren. | ❌ |
| 5 | Bij niet-beschikbaar: assemblageorder aanmaken met artikelen, hoeveelheden, labels. Bij gedeeltelijke voorraad: splitsen. | ❌ |
| 6 | Assemblageorder controleren op volledigheid (regels, labels, eenheden, palletaantallen). Na akkoord: status → 'Vrijgegeven', doorsturen naar magazijn. | ❌ |

#### MAGAZIJN — Assemblage & Verzending (stap 7-12)

| Stap | Beschrijving | Status |
|------|-------------|--------|
| 7 | Grondstof-/materiaalbeschikbaarheid controleren in Navision. Benodigde voorraad reserveren. | ❌ |
| 8 | Transferorder (container) inboeken in Navision. Vrijgekomen voorraad reserveren op assemblageorder. | ❌ |
| 9 | Assemblage uitvoeren: onbestickerde producten etiketteren en bestickeren conform assemblageorder. Componenten picken en samenvoegen. | ❌ (fysiek proces) |
| 10 | Assemblageorder gereedmelden in Navision. Status → 'Gereed'. | ❌ |
| 11 | Assemblageorder inboeken. Geassembleerde producten komen automatisch beschikbaar op verkooporder. | ❌ |
| 12 | Verkooporder boeken, afleverbon afdrukken, verzendsticker + etiket plakken. Order is verzendklaar. | ❌ |

#### ADMINISTRATIE (stap 13)

| Stap | Beschrijving | Status |
|------|-------------|--------|
| 13 | Eindcontrole op geboekte verkooporder + facturatie richting klant | ❌ |

---

### Scenario 2 — Knelpunten

| # | Knelpunt | Toelichting |
|---|---------|-------------|
| 1 | **Voorraaddata in Navision klopt niet** | Informatie over voorraadniveaus en assemblagecomponenten wijkt af van werkelijkheid in magazijn. Oorzaken onduidelijk (registratieproblemen, procesfouten, systeemissues). |
| 2 | **Geen centraal overzicht** | Verkoopcijfers, voorraadniveaus, inkooporders en transferorders zitten verspreid over meerdere Navision-schermen en een losse Excel. Geen single source of truth. |
| 3 | **MRP-planning niet real-time** | MRP-planning in Excel is gebaseerd op Navision-data maar niet live gekoppeld. Logistiek werkt met momentopnames die verouderd kunnen zijn. |

---

### Scenario 2 — Oplossingsrichtingen

| Richting | Beschrijving |
|---------|-------------|
| **Data-audit & oorzaakanalyse** | Eerst uitzoeken waarom de voorraaddata in Navision niet klopt. Registratieproblemen, procesfouten of systeemissues identificeren en oplossen aan de bron. |
| **Centraal operations dashboard** | Eén overzicht met real-time voorraadniveaus (bestickerd + onbestickerd), openstaande orders, inkooporders en inkomende containers. Alle datapunten op één plek. |
| **Slimme inkoopsuggesties** | Vervanging van de MRP-Excel door een geïntegreerd systeem met real-time Navision-data. AI-gestuurde suggesties op basis van verkooppatronen: bij consistente klanten bestickerd inkopen, bij overige slim omgaan met bulk. |
| **Automatische assemblage-detectie** | Het systeem herkent bij binnenkomst van een order automatisch of assemblage nodig is op basis van productcodes, voorraadniveaus en inkomende containers in Navision. Logistiek hoeft niet meer handmatig per regel te checken. |
| **Guided assemblageorder-aanmaak** | Wanneer assemblage nodig is, genereert het systeem automatisch een compleet assemblageorder-voorstel inclusief alle benodigde componenten, hoeveelheden en labels op basis van de BOM in Navision. De logistiekmedewerker controleert en accordeert. |

---

### Scenario 2 — Benodigde Navision API's

| API / Service | Operaties | Type | Toelichting |
|--------------|-----------|------|-------------|
| Assembly BOM (Page 36 / Table 90) | GET | Custom OData | Stuklijsten opvragen voor assemblage-voorstel |
| Assembly Orders (Page 900) | GET, POST | Custom OData | Assemblageorders aanmaken en opvragen |
| Assembly Order Lines (Page 901) | GET, POST | Custom OData | Regels toevoegen aan assemblageorders |
| Item Ledger Entries (Table 32) | GET | Custom OData | Historische voorraadmutaties voor data-audit |
| Transfer Orders | GET | Custom OData | Inkomende containers/transfers opvragen |
| Purchase Orders | GET | Custom OData | Openstaande inkooporders opvragen |
| salesInvoices | GET | Standaard API | Facturatiegegevens voor operations dashboard |

*Al deze API's vereisen dat de NAV-partner custom web services publiceert. Dit moet apart worden afgestemd en bekostigd bij de NAV-partner.*

---

### Scenario 2 — Investering

| Omschrijving | Bedrag |
|-------------|--------|
| Fase 2: Centraal dashboard, data-audit, real-time voorraadkoppeling, inkoopsuggesties | €7.000 - €8.000 (indicatief) |

*De definitieve scope en prijs worden vastgesteld na afstemming tijdens Fase 1. Pilex legt hiervoor een apart voorstel voor ter goedkeuring. Kwabo zit nergens aan vast voor Fase 2 bij akkoord op het huidige voorstel.*
