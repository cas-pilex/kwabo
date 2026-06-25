# FASE 0 — Rode reproductie van Nico's 3 orders door de ECHTE pijplijn

**Datum:** 23-06-2026 · **Branch:** `feat/fase2-matching` · **Scope:** read-only reproductie + diagnose, **geen** codewijziging.

## Samenvatting

De drie door Nico gemelde fouten zijn **rood gereproduceerd door de huidige, gecommitte pijplijn**
op de **echte prod-bestellingen**, met **verse LLM-extractie uit de bron-PDF** en **verse read-only
prod-masterdata** (klanten, e-mailaliassen, ship-to, artikel-eenheden, verkoop_eenheid). Geen van de
drie fouten is een extractiefout — de extractie is in alle drie correct. De fouten zitten in de
**matching-lagen** (klant-match, ship-to-keuze, eenheid/verkoop_eenheid), en ze worden gevoed door
**masterdata-feiten** die de vorige validatie nooit heeft geraakt.

| Order | prod-id | bron-bestelnr | echte uitkomst (ROOD) | laag |
|---|---|---|---|---|
| TABS #954 | 954 | 4506877460 | klant **61793 PontMeyer Heerenveen**, conf **1.0**, bron **email**, géén vlag — moet **Jongeneel Woerden (50094)** zijn | klant-match |
| BAUHAUS | 944 | 1049577521 | ship-to **3981 LB BUNNIK** — moet **7559 SR HENGELO** zijn (zit als kandidaat in de lijst) | ship-to |
| PPG #941 | 941 | XO092614 | 3 identiek-bestelde STUK-regels → **STUK / M1PAL30 / PALLET** (60 stuks → 2 pallets) | eenheid/verkoop_eenheid |

## Bronspoor & read-only-verantwoording

- **Orders gelokaliseerd** in prod `order_log` via een losse read-only engine (`create_engine(prod).connect()`,
  alleen SELECT, nooit commit) — patroon van `scripts/export_order_states.py`.
- **Bron-tier:** Supabase-storage is in deze omgeving niet geconfigureerd (geen `SUPABASE_*` in `.env`),
  dus de `.eml`-tier-1 was niet beschikbaar. Gebruikt is **tier-2: de echte bij-intake vastgelegde bron** in
  `order_log.order_state` — `email_body` (voor #954 de volledige PDF) + `bijlagen[].inhoud_tekst` (de
  deterministische pdfminer-tekstlaag van de bron-PDF). Dat is echte bron, geen reconstructie.
  - *Fidelity-kanttekening:* prod stuurde de PDF als base64 **Vision-documentblok**; de opgeslagen state
    bevat geen ruwe PDF-bytes meer (gestript), dus de reproductie voert de **tekstlaag** terug door
    `extract_from_email`. Voor deze tekst-PDF's (SAP/ORDERS.NL/Driessen) is dat inhoudelijk getrouw.
- **Pijplijn read-only t.o.v. prod:** vóór elke kwabo-import is `DATABASE_URL` overschreven naar een
  **wegwerp-sqlite**; `NAVISION_MODE=mock`. De prod-masterdata is read-only naar die sqlite gespiegeld
  (klantenkaarten 1787, klant_email_aliases **1**, ship-to 2506, artikelkaarten 3757, artikel_eenheden 12963,
  kruisverwijzing 3000, klantenkaart_artikelen 24, matching_history 24, pallet_kennis 19). Alle
  kwabo-writes (order_log van de compose-node) landden in sqlite (`log_id` 1/2/3), **niets** naar prod.
- **Verse extractie** is bewezen: classify+extract draaiden via de echte LLM op de bron-tekst en leverden
  per order de afleveradres/orderregels opnieuw af (zie hieronder). Niet de bevroren order-state hergebruikt.

> Reproductie-artefacten: `backend/_fase0/state_{941,944,954}.json` (echte bron uit prod),
> `backend/_fase0/result_{941,944,954}.json` (pijplijn-uitkomst). Wegwerp-scripts: `backend/scripts/_fase0_*.py`.

---

## Order 1 — TABS #954 (bestelnr 4506877460) → klant-match confident fout

**Bron:** `supplychain@tabsholland.nl`, PDF "Bestelling 4506877460 633".
**Verse extractie (correct):** afleveradres **Jongeneel Woerden BA659, Pijpenmakersweg 2, 3449 JE WOERDEN**.

**Rode uitkomst (volledig automatisch, identiek aan prod):**
```
klant_match = {navision_klantnr: 61793, klantnaam: "PontMeyer Heerenveen",
               match_confidence: 1.0, match_bron: "email"}   ← géén vlag, klant_kandidaten: []
ship_to_gekozen = 8447 GH (Heerenveen)
```

**Mechanisme (data-bewijs):** de afzender `supplychain@tabsholland.nl` is de **centrale inkoopmailbox
van de hele TABS-groep** (PontMeyer- én Jongeneel-vestigingen). In de klantenkaarten staat die mailbox
echter op **precies één** kaart:
```
61793  PontMeyer Heerenveen   email = "supplychain@tabsholland.nl;heerenveen@pontmeyer.nl"
```
Alle ~110 andere TABS/PontMeyer/Jongeneel-vestigingen dragen `confirmation@tabsholland.nl` (het
order**bevestigings**adres), niet supplychain@. De juiste klant draagt dat ook:
```
50094  Jongeneel Woerden BA659   email = "confirmation@tabsholland.nl;woerden@jongeneel.nl"
```
Gevolg: K1 `by_email` (exact, conf 1.0) op de inkoopmailbox levert **altijd** 61793 — ongeacht de
werkelijke leververstiging. De vestiging-correctie op het leveradres grijpt niet:
1. ze zoekt binnen de **PontMeyer-familie**, terwijl het afleveradres een **Jongeneel**-vestiging is, én
2. `plaats`/`postcode` zijn **NULL** op zowel 61793 als 50094 (customers-sync heeft City/Post_Code niet
   gevuld) — er is geen geodata om op te corrigeren.

Bijkomend: de enige `klant_email_aliases`-rij in prod is `61793 → "@pontmeyer.nl"` (fix-ronde 11-06).
Die alias is hier irrelevant (K1-email vuurt eerder) én zou een Jongeneel-order juist verder naar 61793
duwen. Het aliaspad is dus niet de redding maar een tweede pad naar dezelfde fout.

---

## Order 2 — BAUHAUS #944 (bestelnr 1049577521) → ship-to confident fout

**Bron:** `supplier@bahag.com`, ORDERS.NL/PRODUKTIVBETRIEB zip-PDF.
**Verse extractie (correct):** afleveradres **BAUHAUS Vestiging 462, Het Plein 10, 7559 SR Hengelo**.

**Rode uitkomst.** Automatisch matcht de pijplijn eerst de **demo-/seed-klant 10014** (conf 0.95, mét vlag
"DEMO-/SEED-KLANT 10014 gematcht"). In prod heeft een reviewer de klant gecorrigeerd naar **61854 Bauhaus
Nederland C.V.** Op die bevestigde klant herberekent de ship-to-node (post-correctie re-resolve, net als
in prod):
```
ship_to_gekozen = 3981 LB   (reason = "plaats_in_order_text", plaats = BUNNIK)
ship_to_kandidaten bevatten o.a.:  3981 LB BUNNIK  én  7559 SR "HENGELO OV"
```
De order gaat naar **Bunnik** terwijl het exact passende **7559 SR Hengelo** in de kandidatenlijst staat.

**Mechanisme.** `select_ship_to._decide` stap (1) "plaats in order-tekst" pakt de stad die als enige in de
ordertekst voorkomt. BAUHAUS' eigen bedrijfs-/factuuradres (Bunnik) staat in de PDF-tekst, dus **BUNNIK**
is de enige `plaats`-hit en wordt autoom gekozen — vóórdat het afleveradres (postcode 7559 SR, dat
**exact** gelijk is aan kandidaat `7559 SR`) ooit gescoord wordt. De Hengelo-kandidaat heet bovendien
`HENGELO OV`, wat niet als woordmatch op "Hengelo" telt. De heuristiek matcht zo de **factuurstad** i.p.v.
de **leverstad**, confident en zonder vlag.

---

## Order 3 — PPG #941 (bestelnr XO092614) → inconsistente eenheidscodes per regel

**Bron:** `cornedeschynkel@vanhasselverf.nl`, PDF "INKOOPORDER Driessen Verf B.V." (afleveradres Breda).
**Verse extractie (correct):** 3 regels, alle in **STUK** besteld (45 / 60 / 60).

**Rode uitkomst (prod-opgeslagen, status `pushed` → NAV VO2606419):**
| regel | kwabo-art | naam | besteld | `verkoop_uom_gekozen` | aantal |
|---|---|---|---|---|---|
| 1 | 23559 | ProGold Nonwoven 25m² | 45 STUK | **STUK** | 45 |
| 2 | 23522 | ProGold Board 50m² | 60 STUK | **M1PAL30** | 2 |
| 3 | 23523 | ProGold Board 30m² | 60 STUK | **PALLET** | 2 |

Drie nagenoeg identieke ProGold-regels, alle in STUK besteld, krijgen **drie verschillende** eenheden —
de "STUK / 1??? / M1PAL30 / PALLET" die Nico zag. Bij regel 2/3 wordt de hoeveelheid stil herschreven
(60 stuks → 2 "pallets").

**Mechanisme (data-bewijs).** Branch-A stuurt elke regel naar de `verkoop_eenheid` van zijn artikelkaart,
en die is voor de drie zusterartikelen inconsistent onderhouden:
```
23559  verkoop_eenheid = STUK
23522  verkoop_eenheid = M1PAL30     ← een MIX-UOM (artikel_eenheden.is_mix_uom = True)
23523  verkoop_eenheid = PALLET
```
`M1PAL30` is een **mix-staffelcode** die hier als gewone verkoop-eenheid op een **niet-mix-order** wordt
gezet ("1???"). Bovendien spreekt `artikel_pallet_kennis` zichzelf tegen: per_pallet = **24** voor alle
drie (confidence 0.6, dashboard 23-06), terwijl de pallet-codes 30-gebaseerd zijn (`M1PAL30`/`PALLET`
qty_per_base = 30) — dezelfde kennis-datafout als in commit `a8204c6`/Functie 4.

*Fidelity-kanttekening:* de **verse mock-NAV-run** matchte 0/3 (de tekstlaag-extractie vulde geen
`artikelnummer_kwabo`; prod matchte via Vision + live NAV op 23559/23522/23523). De `verkoop_eenheid`-codes
hierboven komen rechtstreeks uit de **echte artikelkaarten** (read-only), en de regel-uitkomst uit de
**echte prod-order-state**. De inconsistentie is dus data-gedreven en NAV2018-afhankelijk; mock kan de
artikel-match niet naspelen, maar de oorzaak (per-artikel `verkoop_eenheid`) is direct aangetoond.

---

## Diagnose — waarom ving de vorige validatie dit niet?

De eindvalidatie ("0 stille fouten, groen") draaide op **bevroren order-state** met **handgecureerde**
masterdata en **MockNAV**, en raakte exact de lagen niet waar deze drie fouten leven:

- **TABS / klant-match — het verkeerde pad getest.** `scripts/verify_funct1_klant.py` test de
  vestiging-correctie op #832/#833/#834 (allemaal **PontMeyer**) en **seedt de 4 PontMeyer-vestigingen
  met plaats+postcode** ("stand ná customers-sync", regels 42–47). De echte prod-kaarten hebben die
  velden **NULL**, en Nico's order is **Jongeneel** — geen van beide condities is ooit getest. Het
  alias/agent-mail-pad zelf (`supplychain@tabsholland.nl` → 61793) is end-to-end nergens getoetst:
  `export_order_states.py` exporteert de tabel `klant_email_aliases` niet, en geen verify-script seedt
  een alias- of agent-mail-rij. De "groene" steekproef draaide dus zonder de data die de fout veroorzaakt.

- **BAUHAUS / ship-to — bevroren state, geen verse afweging.** De N10-harness laadt de geëxporteerde
  order-state en hergebruikt de reeds-gekozen ship-to; ship-to-kandidaten van de juiste klant werden in
  `verify_funct2_shipto.py` **handmatig geseed**. De interactie "factuurstad (Bunnik) staat in de
  PDF-tekst → plaats_in_order_text wint vóór postcode-match" ontstaat alleen bij **verse extractie + de
  echte 5-kandidaten-ship-to-set**, en is in die vorm nooit gedraaid.

- **PPG / eenheid — fictieve verkoop_eenheid.** `verify_fase3.py` (r.52) en `verify_funct3_eenheid.py`
  seeden `verkoop_eenheid = "PALLET33"`/`"PALLET"` op verzonnen artikelen, terwijl prod toen leeg/STUK
  had. De **echte** inconsistentie tussen zusterartikelen (STUK vs M1PAL30 vs PALLET op 23559/23522/23523)
  en de tegenstrijdige `artikel_pallet_kennis` (per_pallet 24 vs 30) zaten niet in de testdata. Alleen
  `verify_funct4_europallet.py` raakte ooit de echte waarde en vond meteen "data-gedreven FOUT" (a8204c6)
  — maar gate'te niet op groen.

- **Scoring-rubriek.** "REVIEW = correct gedrag dat bevestiging vraagt" telt een **gevlagde** foute
  waarde niet als FAIL; alleen "stil" werd gemeten. TABS #954 is echter **niet** gevlagd (conf 1.0, géén
  kandidaten) en zou dus zelfs onder de eigen meetlat een stille fout zijn — maar het agent-mail-pad werd
  nooit met de echte data gedraaid, dus het kwam niet in de meting voor.

### De KLOOF in één alinea

De validatie toetste de **matching-logica op voorgekauwde invoer**: bevroren extractie, handgeseede
klant-/ship-to-kaarten (mét plaats/postcode die prod mist), MockNAV en fictieve `verkoop_eenheid` — en
liet de drie lagen waar de werkelijkheid binnenkomt **ongeraakt**: (1) de **echte alias-/agent-mail-data**
(`supplychain@tabsholland.nl` op één kaart, plaats/postcode NULL, `klant_email_aliases` niet geëxporteerd),
(2) de **verse extractie + echte ship-to-set** waarin de factuurstad de leverstad verslaat, en (3) de
**echte per-artikel `verkoop_eenheid`** (inconsistent + NAV2018-afhankelijk). Daardoor was "groen" een
uitspraak over de testopstelling, niet over productie — **groen ≠ werkelijkheid**.

---

## Opruimen

De reproductie gebruikte alleen-lezen prod-toegang en een wegwerp-sqlite. Tijdelijke artefacten
(`backend/_fase0/`, `backend/scripts/_fase0_*.py`) zijn niet voor commit bedoeld en kunnen weg na review.
Geen pijplijn-code gewijzigd.
