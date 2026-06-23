# VALIDATIERAPPORT RONDE 2 — verse pijplijn + differentieel

**Datum:** 23-06-2026 · **Gevalideerde code:** HEAD `9747c9b` · **Pre-fix baseline (differentieel):**
`c566bee` · **Backend:** MockNAV (operations-vorm) + ECHTE read-only prod-masterdata + ECHTE bron-PDF.

---

## 1. EINDOORDEEL

| Fix | Commit | Differentieel (oud→nieuw) | Oordeel |
|---|---|---|---|
| **A — ship-to = afleveradres** | `612e6af` (+`9747c9b`) | #944 ship-to 3981 LB Bunnik (stil) → **7559 SR Hengelo** | **PASS** |
| **B — agent/portaal via afleveradres** | `c0d4b2b` (+`9747c9b`) | TABS #954/#955/#834 → 61793 conf 1.0 **zonder vlag** (stil) → 3 **verschillende** juiste eindklanten + vlag | **PASS** |
| **C — eenheid (mix-code als verkoopeenheid)** | `3a7b2cb` | #941/#922 regel 23522 → **M1PAL30** (stil) → **STUK + review-vlag** | **PASS** |

**Differentieel-kerngetal:** OUDE code reproduceert **6 stille fouten** (4 klant/ship-to + 2 eenheid);
NIEUWE code **0**. De harness vangt dus de echte bugs → **validatie geldig**.
**Brede steekproef (23 orders, verse pijplijn):** **0 stille fouten** (nieuwe definitie).
**Systeembreed:** suite 671 passed / 17 skipped; `--regression` 17 passed; E3-invarianten 48 passed.
**Determinisme:** kernset 3× byte-identiek.

> Bewijst dat de PIJPLIJN de juiste klant/adres/eenheid/aantal PRODUCEERT en dat de harness de oude
> bugs vangt. Bewijst NIET dat NAV de push accepteert (on-site, §6) of de Vercel-UI.

---

## 2. DIFFERENTIEEL-TABEL (Blok D) — verse pijplijn, OUD `c566bee` vs NIEUW `9747c9b`

Zelfde harness (`verify_ronde2.py`), gedeelde LLM-cache (extractie-code identiek; verschil = puur de
matching-nodes). Read-only prod; wegwerp-sqlite; geseede masterdata = verse prod-export.

| order | scenario | OUD (rood) | NIEUW (groen) | stille fout? |
|---|---|---|---|---|
| **#954** | TABS supplychain@ → Jongeneel Woerden | klant **61793** conf **1.0 géén vlag**, ship-to 8447 GH | **50094** Jongeneel Woerden, conf 0.9, **vlag**, ship-to 3449 JE | OUD ja → NIEUW nee |
| **#955** | TABS → PontMeyer Alkmaar | klant **61793** conf 1.0 géén vlag | **61005** PontMeyer Alkmaar, vlag, ship-to 1821 BT | OUD ja → NIEUW nee |
| **#834** | TABS → PontMeyer Zwaag | klant **61793** conf 1.0 géén vlag | **61088** PontMeyer Zwaag, vlag, ship-to 1689 AK | OUD ja → NIEUW nee |
| **#944** | BAUHAUS → Hengelo (klant 61854) | ship-to **3981 LB Bunnik** (factuurstad uit PDF) | **7559 SR Hengelo** | OUD ja → NIEUW nee |
| **#941** r2 | PPG artikel 23522 (kaart-verkoop_eenheid = mix-code) | verkoop_uom **M1PAL30** (stil) | **STUK** + review-vlag | OUD ja → NIEUW nee |
| **#922** r1 | PPG artikel 23522 (2e order) | verkoop_uom **M1PAL30** (stil) | **STUK** + review-vlag | OUD ja → NIEUW nee |
| **#716** | Würth 1-op-1 e-mail (regressie) | 61030 conf 1.0, ship-to 5215 MK | **identiek** | nee → nee |
| **#717** | Kuipers 1-op-1 e-mail (regressie) | 61844 conf 1.0, ship-to 7783 DC | **identiek** | nee → nee |

**Anti-overfitting:** de 3 TABS-orders gingen OUD allemaal naar 61793 (de vaste fout-vestiging); NIEUW
naar **3 verschillende** eindklanten op hun eigen leveradres — niet op Woerden hardgecodeerd. BAUHAUS
#662 (zelfde portaal, ander adres) → **Groningen 9723 AW**, niet Hengelo (zie E1).

---

## 3. TRACEERBAARHEIDSMATRIX

| blok | bug (letterlijk) | fix (commit) | scenario's getest | vers bewijs (cmd → kernoutput) | backend | stille fout? | resultaat |
|---|---|---|---|---|---|---|---|
| **A** ship-to | "ship-to = besteller/factuur i.p.v. afleveradres" (#944 → Bunnik) | `612e6af`,`9747c9b` | #944→Hengelo, #662→Groningen (ander adres), #716/#717 1-adres ongewijzigd | `verify_ronde2.py` → #944 ship_to=7559 SR, #662=9723 AW | MockNAV + echte ship-to-master | nee | **PASS** |
| **B** agent/portaal | "agent-mail 100%-match zonder vlag naar één vaste vestiging" (TABS→61793) | `c0d4b2b`,`9747c9b` | #954→Woerden, #955→Alkmaar, #834→Zwaag, Zevij #915→60245; regressie #716/#717 | `verify_ronde2.py` → 0 agent/portaal-order confident-zonder-vlag | echte klant-/ship-to-data | nee | **PASS** |
| **C** eenheid/mix | "mix-staffelcode (M1PAL30) stil als verkoopeenheid; 1??? op regel" (#941) | `3a7b2cb` | #941/#922 (mix-code→STUK+vlag), #845 manueel PAL, #847 ROL→PALLET | `verify_ronde2.py --eenheid` → #941 r2 STUK + warning | echte artikelkaarten | nee | **PASS** |
| **D** differentieel | "harness moet bugs op OUD reproduceren" | n.v.t. | core+eenheid op `c566bee` | OUD 6 stille fouten → NIEUW 0 | worktree `c566bee` | — | **GELDIG** |
| **E** breed/regressie | "0 stille fouten breed; geen regressie" | alle | 23 orders + suite + --regression | 0/23 SF; 671 passed; 17 reg passed; 48 invariant | gemengd | nee | **PASS** |

---

## 4. BREDE STEEKPROEF (E1) — 23 orders, verse pijplijn, **0 stille fouten**

Confident (conf 1.0) komt **uitsluitend** voor bij 1-op-1 e-mailmatches (#716/#717/#945/#868); elke
agent/portaal-order krijgt conf 0.9 + vlag of kandidaten. Geen confident-fout-zonder-vlag.

| order | klant | bron | conf | vlag | ship-to | opmerking |
|---|---|---|---|---|---|---|
| #954 | 50094 Jongeneel Woerden | leveradres_shipto | 0.9 | ✓ | 3449 JE | feedback-order |
| #955 | 61005 PontMeyer Alkmaar | leveradres_shipto | 0.9 | ✓ | 1821 BT | TABS 2e variant |
| #834 | 61088 PontMeyer Zwaag | leveradres_shipto | 0.9 | ✓ | 1689 AK | TABS 3e variant |
| #944 | 61854 BAUHAUS | manual→ship-to | 1.0 | ✓ | 7559 SR | feedback-order |
| #662 | 61854 BAUHAUS | manual→ship-to | 1.0 | ✓ | 9723 AW | ship-to 2e variant (Groningen) |
| #915/#816 | 60245 Zevij | naam_extract | 0.8 | ✓ | 4906 CS | portaal via afleveradres |
| #716 | 61030 Würth | email | 1.0 | – | 5215 MK | regressie 1-op-1 |
| #717 | 61844 Kuipers | email | 1.0 | – | 7783 DC | regressie 1-op-1 |
| #945 | 50120 Stukbouw | email | 1.0 | – | 5482 ZA | 1-op-1 |
| #868 | 60203 | email | 1.0 | – | 6101 XK | 1-op-1 |
| #926/#897/#896/#887/#856/#832/#833/#635 | div. PontMeyer-vestigingen | leveradres_shipto | 0.9 | ✓ | per leveradres | TABS-groep, correct verspreid |
| #718 | 60892 Witzand | naam_extract | 0.8 | ✓ | 7671 JE | naam-fallback |
| #707 | 61948 GBI Borne | naam_extract | 0.8 | ✓ | None | geen ship-to-data (geen fout) |
| #721 | 61472 Van Dongen | naam_extract | 0.8 | ✓ | 3240 AG | naam-fallback |
| #847 | None | — | — | ✓ | None | niet gematcht → **gevlagd** (geen stille fout) |

**Misses/kanttekeningen (geen stille fout — alle gevlagd of data-getrouw):**
- **#847**: klant niet automatisch gematcht → review-vlag (correct, niet stil).
- **#707**: klant ok, geen ship-to-records in master → ship-to None (NAV default; geen review-trigger).
- **#819** (eenheid): artikel 23691 heeft `verkoop_eenheid=STUK` op de kaart → 4 STUK (data-getrouw;
  géén pallet-UoM in de mirror — data-observatie, geen codefout).
- **#854** (eenheid): artikel 23229 niet gematcht (manual) → eenheid niet herleidbaar; geen stille fout.

---

## 5. DETERMINISME (E2)

Kernset (#954/#944/#716/#717/#955/#834) 3× achter elkaar door de verse pijplijn → **byte-identieke**
JSON (`md5 6984c20a… ×3`, `diff` leeg). LLM-cache + gestripte timestamps → reproduceerbaar.

---

## 6. ON-SITE TESTSCRIPT (donderdag — ECHTE NAV-push, het enige echte NAV-bewijs)

Per order: keur goed in het dashboard en push; controleer in NAV2018:

| order | verwachte klant | verwacht afleveradres (ship-to) | verwachte eenheidscode + aantal | mix? |
|---|---|---|---|---|
| **#954** TABS | 50094 Jongeneel Woerden (of bevestig uit kandidaten) | 3449 JE Woerden | regel(s) zoals besteld | nee |
| **#955** TABS | 61005 PontMeyer Alkmaar | 1821 BT Alkmaar | — | nee |
| **#834** TABS | 61088 PontMeyer Zwaag | 1689 AK Zwaag | — | nee |
| **#944** BAUHAUS | 61854 Bauhaus | **7559 SR Hengelo** (NIET 3981 LB Bunnik) | STUK + aantal | nee |
| **#662** BAUHAUS | 61854 Bauhaus | **9723 AW Groningen** | — | nee |
| **#941** PPG | 61483 PPG-Driessen | 4815 PN Breda | r1 23559 **STUK** 45; r2 23522 **STUK** 60 (NIET M1PAL30); r3 23523 **PALLET** 2 | nee |
| **#922** PPG | 61483 | per order | 23522 **STUK** (NIET M1PAL30) | nee |
| **#845** Lasaulec | 61745 | Lemmer | 15620 **PAL** 2 (manuele B-keuze) | nee |

**Te bevestigen on-site:** of NAV elke `unitOfMeasureCode` (STUK/PALLET/PAL) ACCEPTEERT op de
betreffende artikelen (mock bewijst alleen de operations-vorm, niet NAV-acceptatie).

---

## 7. OPEN / GEBLOKKEERD (niet als opgelost gerapporteerd)

- **Europallet**: geparkeerd (Nico's veld-/maatvoorstel) — niet in scope van deze 3 fixes.
- **F6 prijsdata**: prijsafspraken-tabel leeg → no-op; composer prijst nooit (NAV doet dat).
- **F7 inkomend document**: NAV-partner-blok (PLX_IncomingDocument niet gepubliceerd).
- **2 business-vragen**: (a) regel "agent-mail → altijd afleveradres leidend?" (b) pallet-maten per artikel.
- **storch-ciret.com** (3 distincte rechtspersonen, gedeelde logistiek-ship-to): order routeert terecht
  naar **kandidaten + vlag** (geen gok), géén stille fout — bewust review.
- **23691/STUK-vs-pallet** en de europallet-/kennis-datafout: data-kant (NAV-artikelkaart), niet codefout.

---

## 8. EERLIJKHEIDSPARAGRAAF

Deze ronde bewijst, met **verse extractie uit de echte bron** + **verse read-only prod-masterdata** +
een **differentieel** dat de oude bugs op `c566bee` als FAIL reproduceert en op `9747c9b` als PASS:
dat de **pijplijn** de juiste **klant**, **afleveradres/ship-to**, **eenheidscode** en **aantal**
PRODUCEERT, en dat de harness de werkelijkheid meet (geen reproductie-op-oud = ongeldig — die is er wél).
Het bewijst **NIET**: (1) dat NAV2018 de gepushte codes daadwerkelijk **accepteert** — dat is on-site
(§6), want MockNAV valideert alleen de operations-vorm, niet NAV's eigen UoM-/prijs-OnValidate; (2) de
echte **Vercel-UI**; (3) de artikel-match van PPG end-to-end onder mock (Vision/live-NAV-afhankelijk —
de eenheid-fix is bewezen op de **echte prod-matched regels + echte kaarten**, niet op een verse
offline-artikel-match).

---

### Reproductie
```
cd backend
python scripts/verify_ronde2.py            # E1 brede steekproef → _ronde2/vol.json (0 stille fouten)
python scripts/verify_ronde2.py --core     # kernset (determinisme/diff)
python scripts/verify_ronde2.py --eenheid  # Blok C → _ronde2/eenheid.json
# differentieel: git worktree add ../kwabo-prefix c566bee; kopieer .env+harness; LLM_CACHE_DIR gedeeld
```
Guard (read-only): `DATABASE_URL=sqlite` vóór elke kwabo-import; prod alleen via losse
`create_engine(PROD).connect()`-SELECT (nooit commit); `seed()` no-op op niet-sqlite (`db/seed.py`).
