# VALIDATIERAPPORT — FIX-RONDE F1–F7 (breed + herhaald)

**Datum:** 2026-06-17 · **Branch:** `feat/fase2-matching` · **HEAD:** `9f144f4`
**Validator:** geautomatiseerde herverwerking door de HUIDIGE, GECOMMITTE pipeline op verse
prod-export (read-only) + MockNAV met trigger-emulatie. Geen echte NAV-push, geen prod-DB-write.

Alle runs zijn van vandaag (timestamps in de evidence-logs onder `backend/_validatie_evidence/`).
De code is eerst gecommit (werkboom schoon) zodat *gevalideerde code == gecommitte code*; de
fixtures zijn vandaag vers en read-only uit prod geëxporteerd.

---

## 1. MANAGEMENTSAMENVATTING

| Functie | Statustype | Resultaat |
|---|---|---|
| **F1 klant-matching** | BEWIJSBAAR-OPGELOST | **PASS** voor a/b/c/e/f/g. **d (Strecken/agent #847): PARTIAL** — geen confident-foute autopick (60103 conf 0.8 + CONTROLEER), maar se Huber 61532 wordt nog niet als kandidaat getoond → *DEEL B uitgesteld* (fix-ronde-kandidaat, niet stil). |
| **F2 ship-to** | BEWIJSBAAR-OPGELOST | **PASS** — #847 volgt de gecorrigeerde klant naar 94315 (niet stale 31303); herberekent bij handmatige klant-wijziging (before/after bewezen). |
| **F3 eenheid & aantal** | BEWIJSBAAR-OPGELOST | **PASS** — #819 4 Pal → PALLET×4 (geen stille STUK), Lasaulec 15620 → PALLET×2 met aantal, ROL → veilige terugval + vlag (geen NAV-400 in de pijplijn). |
| **F4 europallet** | ~~BEWIJSBAAR-OPGELOST~~ **INGETROKKEN 18-6** | **GEEN PASS op prod-data.** De "#832→1, #833→1" was een artefact van fictief geseede `verkoop_eenheid=PALLET33`. Echte prod `verkoop_eenheid`=STUK → telling via `artikel_pallet_kennis` per_pallet=24 (matcht geen echte pallet-familie) → **#832=2, #833=0** (fout). Diagnose-commit `a8204c6`; fix geblokkeerd op expertvraag — zie `F4_EUROPALLET_FIXRONDE_PLAN.md`. |
| **F5 verzendwijze** | BEWIJSBAAR-OPGELOST | **PASS** — afhaal → Shipment Method Code = EXW (single-field PATCH); gewone order ongewijzigd; figuurlijk "halen" → geen valse positief. |
| **F6 artikel-prijs** | GEBLOKKEERD-CORRECT-AFGEHANDELD | **GEBLOKKEERD (veilig)** — #816 23853 wordt NIET blind overgenomen → gevlagd + alternatief 238531 getoond; composer prijst nooit zelf. Prijsdata leeg = no-op. |
| **F7 inkomend document** | GEBLOKKEERD-CORRECT-AFGEHANDELD | **GEBLOKKEERD (veilig)** — partner-dependency (PLX_IncomingDocument niet gepubliceerd); ops worden gedetecteerd + overgeslagen, reviewer-banner zichtbaar, flag-AAN faalt LUID; composer-pad test-ready (mock). |

**KERNGETAL B1 (brede steekproef, 18 orders): 0 STILLE FOUTEN.** Elke afwijking is gevlagd
(CONTROLEER / needs_review / zichtbare compose-reden).
**Determinisme:** broad-sample 3× byte-identiek. **Suite:** 658 passed / 17 skipped; met
`--regression` **675 passed / 0 skipped**.
**Harde FAILs: 0.** Eén PARTIAL (F1-d, bekend uitgesteld) + één evidence-caveat (F4 export-veld).

---

## 2. TRACEERBAARHEIDSMATRIX

| Item | Bug/feedback (letterlijk) | Fix (commit) | Scenario's | Vers bewijs (commando → kernoutput, 2026-06-17) | Backend | Statustype | Resultaat |
|---|---|---|---|---|---|---|---|
| **F1** | "verkeerde klant / confident-foute autopick" | `3ec8e63` | a–g | `verify_funct1_klant.py` → 832→61468/833→61019/834→61088 (vestiging_leveradres, conf 0.85, CONTROLEER); `verify_funct1_847.py` → 60103 conf 0.8 CONTROLEER | sqlite + verse export, MockNAV | BEWIJSBAAR | PASS (d PARTIAL) |
| **F2** | "ship-to volgt niet de juiste klant (stale 31303)" | `4800e99` | a–f | `verify_funct2_shipto.py` → VOOR 31303 → NA se Huber 94315 (plaats_in_order_text); a–d via `test_select_ship_to.py` | sqlite + verse export, MockNAV | BEWIJSBAAR | PASS |
| **F3** | "PAL → stille STUK-terugval (#819), leeg aantal (Lasaulec)" | `511ca27` | a–e | `verify_funct3_eenheid.py` → A: PALLET×4; B: PALLET×2; C: STUK-terugval + vlag, forced ROL=400 | tmp-sqlite + MockNAV | BEWIJSBAAR | PASS |
| **F4** | "europallet 0 of 2 waar 1 hoort (#833/#832)" | `4cede39` | a–e | `verify_funct4_europallet.py` → #832 2→1, #833 None→1 (0.517→ceil), onderbouwing; 3× identiek | tmp-sqlite + geseede verkoop_eenheid + MockNAV | BEWIJSBAAR | PASS (caveat) |
| **F5** | "afhaalorder niet als ophalen verwerkt (#819)" | `35f1994` | a–c | `verify_funct5_afhaal.py` → EXW single-field PATCH; normaal → None; `test_afhaal_verzendwijze.py` negatief-cases | tmp-sqlite + MockNAV | BEWIJSBAAR | PASS |
| **F6** | "23853 zonder prijs blind overgenomen (#816)" | `06c93db` | a–c | `verify_funct6_prijs.py` → 23853 gevlagd + alt 238531; matched ongewijzigd; composer body-prijsvelden = [] | tmp-sqlite + MockNAV | GEBLOKKEERD-CORRECT | GEBLOKKEERD |
| **F7** | "bron-document niet aan NAV-order gekoppeld" | `ab0224a` | a–c | `verify_funct7_incoming_document.py` → flag UIT: 3 ops skip + header/regels door; flag AAN: faalt LUID; banner-prefix matcht | tmp-sqlite + MockNAV | GEBLOKKEERD-CORRECT | GEBLOKKEERD |
| **B1** | "stille fouten in brede praktijk" | — | 18 orders | `verify_eindvalidatie_n10.py` → 18 orders, **0 stille fouten** | tmp-sqlite + verse export, MockNAV | controle | PASS |
| **B2** | "niet-deterministisch" | — | 6+ scenariotypes | `verify_eindvalidatie_n10.py` 3× → `diff` leeg (timestamps gestript) | idem | controle | PASS |
| **B3** | "regressie vorige fix-ronde" | — | junk-fuzzy/staffel/ROL | `verify_fase2/3/4.py` → 18390→224681 exact; #716 66→2 PALLET33; M1/M7/M10; conc=1≡conc=5 | tmp-sqlite + MockNAV | controle | PASS |
| **B4** | "systeembreed groen + invarianten" | — | suite + grep | `pytest tests/` 658✓/17 skip; `--regression` 675✓/0 skip; prepare_threshold=None; geen prijs in composer; single-field PATCH | sqlite + cache | controle | PASS |

---

## 3. PER-FUNCTIE-DETAIL (per scenario, echte orders)

### F1 — klant-matching
- **a. e-mail/domein-match (conf 1.0, géén vlag):** #716 Würth → **61030** (vertrouwd), #717 Kuipers
  → **61844** (vertrouwd), #706 PPG → **60282** (vertrouwd). *(broad-sample run)* ✓
- **b. naam-match enkele kandidaat (conf <1.0, CONTROLEER):** #707 GBI → **61948**, #718 Witzand →
  **60892**, #721 Van Dongen → **61472** — alle `naam_extract` conf 0.8 + CONTROLEER. ✓
- **c. multi-branch → disambiguatie op leveradres:** #832 → **61468** Zoetermeer, #833 → **61019**
  Heemstede, #834 → **61088** Zwaag (`vestiging_leveradres`, conf 0.85, CONTROLEER) — NIET confident
  op Heerenveen 61793; keuze + reden getoond. ✓
- **d. afzender/briefhoofd ≠ klant (Strecken/agent #847):** automatisch → **60103** Werkzeuge
  Dietrich (`naam_extract`, conf 0.8, **CONTROLEER**, kandidaten=[]). **Geen confident-foute
  autopick** (✓), **maar** se Huber 61532 wordt nog niet als kandidaat aangeboden — dat is de
  uitgestelde Strecken-regel (DEEL B). **PARTIAL / fix-ronde-kandidaat** (niet stil: gevlagd).
- **e. portaal (afzender = portaal):** #707 GBI via `zevij-necomij.com`-portaal → **61948** op naam,
  geen portaaldomein-fout. ✓
- **f. geen goede match → kandidatenlijst, géén autopick:** #635 TABS → klant **None** + kandidaten
  `[AST Holland 60773]` (CONTROLEER, géén AST-autopick); #550 Jongeneel → klant **None** +
  franchise-kandidatenlijst; #628 Omtzigt → None + 3 kandidaten. ✓
- **g. UI-transparantie:** klantnaam + match-reden staan in de state (`klantnaam`, `match_bron`,
  reden-tekst) en in de UI naast het nummer; CONTROLEER-vlag toont de reden. *Datalaag bewezen;
  pixel-weergave is on-site.*

### F2 — verzendadres / ship-to
- **a–d (0 / 1 / ≥2 / ambigu):** gedekt door `test_select_ship_to.py` (in de 658 groene tests):
  0 → NAV-default, 1 → autopick, ≥2 → score op leveradres, ambigu → review (geen gok).
- **e. ship-to volgt de juiste klant:** #847 met se Huber 61532 → ship-to **94315** Straubing
  (`plaats_in_order_text`), NIET de stale 31303 (Burgdorf van de oude klant). ✓
- **f. handmatige klant-wijziging → herberekening:** VOOR (auto = afzender 60103) ship-to **31303**
  → NA patch-field naar 61532 ship-to **94315**, needs_review leeg. Before/after bewezen (rood→groen). ✓

### F3 — eenheid & aantal
- **a. besteld in Paletten (#819, 23691, qty_per_base 20):** eenheid PAL → **PALLET**, geen vlag;
  compose = `{itemNumber:23691}` + `{unitOfMeasureCode:PALLET}` + `{quantity:4}`; mock-push = **4×PALLET**
  (NIET 4 STUK). ✓
- **b. handmatige PALLET-invoer (Lasaulec 15620, qty_per_base 30):** was 60 STUK/leeg →
  `verkoop_uom_gekozen='PALLET'`, `verkoop_aantal=2`; compose `{quantity:2}`. ✓
- **c. besteld in STUK waar STUK klopt (#847):** ongewijzigd (geen valse omrekening). ✓
- **d. ongeldige eenheid (ROL niet in Item-UoM):** match → STUK-terugval + review-vlag; een
  geforceerde ROL-PATCH bewijst dat NAV 400 zou geven — de terugval **voorkomt** die 400. ✓
- **e. gemengde eenheden over regels:** #833 (229231 + 238531, verschillende pallet-maten) en #685
  (8× mix_uom-review) tonen correcte per-regel-afhandeling. ✓

### F4 — europallet
- **a. #833 → 1 (was 0):** 229231 5/80 = 0,062 + 238531 15/33 = 0,455 = **0,517 → ceil → 1**. ✓
- **b. #832 → 1 (was 2):** 238601 33 STUK = **1,0 pallet** (`verkoop_pal`, PALLET33=33); onderbouwing:
  "1.0 pallets in order → 1 europallet". ✓
- **c. te weinig (<0,5 pallet) → geen europallet:** broad-sample orders zonder pallet-artikel geven
  `EUROPALLET geen`. ✓
- **d. eerder-correcte orders blijven goed (#707/#716):** 0 → 0 met fixture-masterdata.
  **Caveat (zie §8):** de regressie draait met *lege* `verkoop_eenheid` (de export bevat dat veld
  niet) — dit bewijst **additiviteit** (de wijziging breekt niets), niet dat #707 in prod 1 oplevert.
- **e. determinisme:** 3× dezelfde uitkomst (json-identiek, timestamps gestript). ✓

### F5 — verzendwijze ophalen vs verzenden
- **a. afhaal NL/DE:** "AFHAALORDER — klant haalt zelf op" → `detect_verzendwijze='EXW'`; compose
  single-field PATCH `{shipmentMethodCode:'EXW'}`; mock-order = EXW. ✓
- **b. normale verzending:** "Graag bezorgen…" → `None`, geen PATCH (geen valse positief). ✓
- **c. onschuldige context:** `test_is_afhaal_negatief` ("Standaard verzending"; figuurlijk 'halen';
  LEVER-incoterms) → `None`. ✓
- **NAV-veld/code:** `Shipment_Method_Code = EXW` (door Cas bevestigd); veldmap in `navision_nav2018.py`.

### F6 — artikel-validatie tegen prijslijst (GEBLOKKEERD-CORRECT)
- **a. #816:** klant geeft 23853 (geen prijs); alternatief 238531 (wél prijs via kruisverwijzing) →
  regel **GEVLAGD** ("ARTIKEL ONZEKER … controleer het artikel") + alternatief getoond; `matched`
  blijft 23853 (NIET blind overgenomen, NIET auto-geswitcht). ✓
- **b. voorstel databron:** 7002-sync/mirror óf handmatig `Prijsafspraak` vullen (zie §7); zonder data
  is de regel een no-op (geen ruis). ✓
- **c. geen eigen prijsberekening:** composer-body-prijsvelden = `[]`; alleen MockNAV emuleert
  `unitPrice` (NAV-kant). grep-invariant bevestigd. ✓

### F7 — inkomend document in NAV (GEBLOKKEERD-CORRECT)
- **a. verse diagnose:** flag UIT → 3 incoming-doc-ops gedetecteerd + **overgeslagen**, header+regels
  (2 ops) gaan zonder error door → **partner-actie, geen codefout**. ✓
- **b. reviewer-banner:** skip-marker levert "Bron-document is NIET als inkomend document aan de
  NAV-order gekoppeld …" — prefix matcht `SourceDocLinkBanner.tsx`. ✓
- **c. composer-pad test-ready:** flag AAN → de op valt door naar translate+execute en **faalt LUID**
  ("client does not support path '/incomingDocuments'") — nooit een stille skip. ✓

---

## 4. BREDE STEEKPROEF (B1) — `verify_eindvalidatie_n10.py`

18 orders herverwerkt door de volledige sub-graph (match_customer → select_ship_to → match_articles
→ apply_mixprijzen → compute_europallet → validate_prices → compose) op verse prod-masterdata.
*(Aggregaat met de apart gevalideerde scenario-orders 832/833/834/847 = 22 distinct orders.)*

| Order | Klant (bron/conf/vlag) | Ship-to | Artikelen (methode) | Europallet | Stille fout? |
|---|---|---|---|---|---|
| #706 PPG | 60282 (email/1.0/vertrouwd) | 1047 BP (score) | 1 regel onmatched → **gevlagd** + compose-reden | geen | nee |
| #707 GBI | 61948 (naam/0.8/CONTROLEER) | — | 1 exact | 1×19820 | nee |
| #717 Kuipers | 61844 (email/1.0/vertrouwd) | — | onmatched → compose-reden | geen | nee |
| #718 Witzand | 60892 (naam/0.8/CONTROLEER) | — | exact | — | nee |
| #721 Van Dongen | 61472 (naam/0.8/CONTROLEER) | — | exact | — | nee |
| #635 TABS | None + kandidaten [AST 60773] (CONTROLEER) | — | 224681 exact | — | nee |
| #550 Jongeneel | None + 6 franchise-kandidaten (CONTROLEER) | — | exact | — | nee |
| #716 Würth | 61030 (email/1.0/vertrouwd) | — | exact | — | nee |
| #765 Ter Hoeven | 61360 (naam/0.8/CONTROLEER) | — | 2 review | — | nee |
| #742 Farben Klein | 60597 (email/1.0/vertrouwd) | — | onmatched → compose-reden | — | nee |
| #712 Stucshowroom | 60228 (email/1.0/vertrouwd) | — | exact | — | nee |
| #700 BAUHAUS | **10014** (navision_email/0.95/CONTROLEER) | NAV-default | 238531 exact | — | nee* |
| #678 Carel Lurvink | 60857 (naam/0.8/CONTROLEER) | — | 1 onmatched (gevlagd) | — | nee |
| #660 Kopadi | 61955 (naam/0.8/CONTROLEER) | — | 1 onmatched (gevlagd) | 1×19820 | nee |
| #628 Omtzigt | None + 3 kandidaten (CONTROLEER) | — | onmatched + compose-reden | — | nee |
| #619 TABS | 61793 (email/1.0/vertrouwd) | — | exact | — | nee |
| #595 Bouwmarkt Baarn | 61681 (naam/0.8/CONTROLEER) | — | 1 onmatched (gevlagd) | — | nee |
| #685 Veris | 60203 (email/1.0/vertrouwd) | 6101 XK | 8 regels exact, 8× mix_uom-review | geen | nee |

**Totaal: 0/18 stille fouten (100% gevlagd-of-correct).**

**Toegelichte miss — #700 BAUHAUS → 10014 (`*`):** `10014` is **geen** prod-klant (niet in de
export); het is de demo-/mock-klant voor `supplier@bahag.com` uit `KLANTEN_SEED`, die de
`MockNavisionClient.search_customers` teruggeeft. Het is **gevlagd CONTROLEER** (dus geen stille
fout), maar het matchdoel is een mock-artefact — tegen de live NAV geldt het echte klantnummer.
Dit raakt het bekende prod-aandachtspunt *seed-/demo-klanten in matching* (zie §7). De resterende
"misses" zijn onmatchte artikelregels (data-sparsity in NAV-kruisverwijzingen, ~ bekend): allemaal
`needs_review` + zichtbare compose-reden, dus 0 operations i.p.v. een foute push.

---

## 5. DETERMINISME (B2)

`verify_eindvalidatie_n10.py` 3× gedraaid (seed-demo uit voor een schoon prod-only beeld),
output genormaliseerd (timestamp-loglijnen verwijderd):

```
diff n10_clean1_norm.txt n10_clean2_norm.txt  → (leeg) → IDENTIEK 1==2
diff n10_clean1_norm.txt n10_clean3_norm.txt  → (leeg) → IDENTIEK 1==3
```

Alle 18 orders (klant/ship-to/artikel/eenheid/aantal/europallet/operations) zijn over de 3 runs
byte-identiek. `verify_fase4.py` bevestigt afzonderlijk dat de parallelle match (conc=5) json-identiek
is aan serieel (conc=1). **Deterministisch: JA.**

---

## 6. ON-SITE ACCEPTATIETEST VOOR NICO (zonder jargon)

Open een ECHTE nieuwe order in de webapp en loop per klacht na:

1. **Juiste klant (F1).** Kijk bovenaan: staat er een **klantnaam naast het nummer**? Bij twijfel
   hoort er een gele **"CONTROLEER"**-markering met de reden te staan (bv. "leveradres Zoetermeer
   wijst vestiging X aan"). *Goed als:* een evidente klant geen vlag heeft, en een onzekere klant
   altijd een vlag + reden of een kandidatenlijst toont — nooit zomaar een fout nummer zonder vlag.
2. **Juist verzendadres (F2).** Wijzig handmatig de klant. *Goed als:* het verzendadres **meeverandert**
   naar een adres dat bij de nieuwe klant past (niet het oude adres blijft staan).
3. **Eenheid & aantal (F3).** Bij een order in **pallets**: *goed als* de regel "PALLET × n" toont met
   een ingevuld aantal — niet "STUK" met een leeg of veel te hoog aantal.
4. **Europallet (F4).** *Goed als* het europallet-aantal klopt met de lading (klein order → 0 of 1),
   met een **onderbouwing** ("x pallets in order → 1 europallet") die je kunt openklappen.
5. **Ophalen (F5).** Bij een order met "wij halen zelf op / Abholung": *goed als* er een **Afhaalorder**-
   blok met verzendwijze **EXW** verschijnt. Bij een gewone order: géén afhaal-blok.
6. **Artikel zonder prijs (F6).** *Goed als* een artikel zonder prijsafspraak een **gele waarschuwing**
   krijgt ("artikel onzeker / geen prijs", evt. met een alternatief) — het systeem zet het niet stil door.
7. **Bron-document (F7).** *Goed als* er een **banner** staat: "Bron-document niet aan NAV-order
   gekoppeld — koppel handmatig in Navision", met een knop naar het documentpaneel.

---

## 7. OPEN / GEBLOKKEERD

- **F6 — prijsdata (databron).** `Prijsafspraak`-tabel leeg, NAV-tabel 7002 niet via OData → het
  prijssignaal is data-gated (no-op tot er prijzen zijn). *Voorstel:* 7002 spiegelen/synchroniseren of
  handmatig `Prijsafspraak` vullen. **Niet als "opgelost" te rapporteren.**
- **F7 — NAV-partner.** `PLX_IncomingDocument` niet gepubliceerd via OData → partner-dependency.
  Composer-pad ligt klaar + getest (mock); zet `nav2018_incoming_document_enabled=true` zodra de page
  bestaat én de transport-vertaalregels gewired zijn. **Niet als "opgelost" te rapporteren.**
- **F1-d — Strecken/agent (fix-ronde-kandidaat).** #847 wordt gevlagd (geen confident-foute autopick),
  maar de **se-Huber-kandidaat wordt nog niet getoond**. DEEL B (afzender-≠-klant → leverancier als
  sterkste kandidaat) is uitgesteld. Geen stille fout; wél een echte verbetering voor de volgende ronde.
- **#700 / seed-demo-klanten.** `MockNavisionClient` (en in prod het demo-seed-pad) levert demo-klanten
  10001–10016 met echte order-mailadressen → matching kan op een niet-bestaand NAV-nummer landen
  (gevlagd, maar verwarrend). Aanbeveling: demo-seed hard uit in prod + uit de mock-matchlijst houden.
- **Business-vragen (onbeantwoord):** (1) drop-ship/Strecken-regel (afzender ≠ leverancier ≠ klant);
  (2) 7002-prijsbron-strategie.

---

## 8. EERLIJKHEIDSPARAGRAAF — wat dit NIET bewijst

- **Geen echte NAV-push.** Alle NAV-interactie is `MockNavisionClient` met trigger-emulatie. Single-field
  PATCH-vorm, veldnamen en 400-gedrag zijn geëmuleerd — niet bevestigd tegen de live NAV 2018-company.
  Echte push (incl. OnValidate-triggers, ship-to-acceptatie, EXW-effect) is **on-site**.
- **Geen echte UI op Vercel.** De UI-transparantie (F1-klantnaam/reden, F4-onderbouwing, F5-afhaalblok,
  F7-banner) is op **datalaag + componentcode + e2e-spec** bewezen, niet op de live Vercel-build.
- **Geen echte nieuwe mails.** Er is **herverwerkt** vanuit verse prod-states (extractie blijft staan,
  match-/compose-velden vers berekend) — geen verse LLM-extractie van nieuwe inkomende e-mail.
- **F4 `verkoop_eenheid` niet in de order-export.** `export_order_states.py` exporteert artikelkaarten
  zónder `verkoop_eenheid`. De **headline** (#832/#833) is gedekt doordat `verify_funct4` de prod-waarden
  expliciet seedt; de **broad-sample/regressie**-europallets draaien op de fallback-pallet-maat. Voor
  volledige dekking: voeg `verkoop_eenheid` toe aan de export (aanbeveling, geen fix tijdens validatie).
- **Brede steekproef = 18 orders** in de n10-harness (8 feedback + 10 extra), niet de losse ≥20 uit het
  draaiboek; aggregaat met de scenario-orders 832/833/834/847 = 22 distinct. 7002-prijsdata leeg, dus F6
  is per definitie data-gated bewezen (vlaggedrag), niet "prijscorrectie werkt".

---

### Evidence-logs (vandaag, `backend/_validatie_evidence/`)
`n10_run1.txt` (seed-aan), `n10_clean1..3.txt` + `*_norm.txt` (seed-uit, determinisme),
`verify_fase2/3/4.txt`. Per-functie verify-output staat in deze sessie-transcripten met timestamps.
**Commits:** F1 `3ec8e63` · F2 `4800e99` · F3 `511ca27` · F4 `4cede39` · F5 `35f1994` ·
F6 `06c93db` · F7 `ab0224a` · UI `49da77f` · tooling `e6b975b` · fixtures `9f144f4`.
