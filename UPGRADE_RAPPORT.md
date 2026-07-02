# UPGRADE_RAPPORT — Structurele upgrade (Fase A–D)

**Datum:** 2026-07-02 · branch `upgrade/fase-a-golden-corpus` (11 commits) · alle bewijs vers gedraaid op de echte pijplijn (verse LLM-extractie, echte prod-masterdata read-only, mirror-NAV). Deelrapporten: `UPGRADE_BASELINE.md` (rode meting), `UPGRADE_DIAGNOSE.md` (oorzaken), `UPGRADE_GATE_B.md` (fixes B1–B4), `UPGRADE_GATE_C.md` (UI), `PALLET_PLAATSEN_VULLIJST.md` (Nico-actie).

## 1. Managementsamenvatting — per feedbackcategorie: was → is

| Teamklacht (4 rondes) | Was (rode baseline, pre-upgrade) | Is (na upgrade, vers gemeten) |
|---|---|---|
| **Verkeerd klantnr (agents/portalen)** | #847 resolvet niet (None); TABS-orders confident op de verkeerde vestiging; beleid verspreid over losse patches | Eén gedocumenteerde beslisboom (B2): agent/portaal → klant uit de **afleverpartij**, met kaartnaam+plaats als tiebreaker. #847 → se Huber Straubing (0.9 + CONTROLEER); alle TABS-vestigingen goed; directe e-mailklanten onveranderd 1.0 vlagvrij |
| **Besteladres i.p.v. afleveradres** | Eén adresveld zonder rol; wat de LLM koos, gold | Extractie levert adressen **mét rol** (besteller/factuur/aflever/eindontvanger, B1); ship-to gebruikt uitsluitend aflever/eindontvanger; roltwijfel → vlag. #944: Hengelo uit de aflever-rol, Bunnik apart zichtbaar als besteller |
| **Verkeerde eenheid + niet-omgerekend aantal (incl. mix)** | Lasaulec: 2 PAL → 2 STUK ongeconverteerd; logica over 5 modules met verschillende terugval; regels zonder match verdwenen stil ("1???") | Eén eenheid-contract a–e (B3): pallet-brug met deterministische voorkeur (#845/#203 → PALLET/2), herverwerking idempotent, mix-code-guard blijft (#941 → PALLET/2), #716-anker 66 STUK blijft STUK; regel zonder match → expliciete warning, nooit stil weg |
| **Onnavolgbare europallet-telling** | Vervuild leerbestand (per_pallet=24) stuurde de telling: #832 → 2 i.p.v. 1, #716 → 3 | Expliciete databron `pallet_plaatsen_basis` (B4, Nico's voorstel) > NAV-eenheid; leerbestand en /24-gok **uit** de telling; geen bron → vlag "europallet onbekend" + onderbouwing per regel in de UI |
| **"Elke ronde groen, zelfde fouten"** | Validaties op bevroren states/mocks | Golden corpus van 17 échte orders + gelabelde grondwaarheid; alle claims vers gedraaid door de echte pijplijn; strenge definitie (confident-fout-zonder-vlag = FAIL) |

**Kerngetal: stille fouten op het corpus, vers gemeten: 3 → 0.**

## 2. D1 — Differentieel (oud naast nieuw, beide vers op de echte pijplijn)

Oud = pre-upgrade code (rode baseline, 2-7 ochtend). Nieuw = na B1–B4 (2-7 middag). Zelfde bronnen, zelfde grondwaarheid, zelfde strenge judge.

| order | OUD (pre-upgrade) | NIEUW (na B1–B4) |
|---|---|---|
| #944 BAUHAUS | JUIST | JUIST |
| #954 TABS | JUIST | JUIST |
| #941 PPG | JUIST | JUIST |
| #847 Strecken | **STILLE-FOUT** (klant None gevlagd; ship-to None óngevlagd) | **JUIST** (61532 + 94315) |
| #819 afhaal | JUIST | JUIST |
| #845 Lasaulec | FOUT-met-vlag (2 PAL → STUK) | **JUIST** (PALLET/2) |
| #203 Lasaulec-2 | 2× FOUT-met-vlag | 1× FOUT-met-vlag (artikel 224681 als kandidaat gevlagd) |
| #816 Zevij | JUIST | JUIST |
| #832 TABS | **STILLE-FOUT** (europallet 2≠1) | FOUT-met-vlag ("europallet onbekend" — wacht op vullijst) |
| #833 TABS | **STILLE-FOUT** (europallet None≠1) | FOUT-met-vlag (idem) |
| #834/#716/#717/#718/#721/#707/#685 | JUIST | JUIST |

**Stille fouten: 3 → 0. Juist: 12/17 → 14/17. Crashes: 0** (één run kende 9 netwerk-crashes, na herstart alle 17 compleet).

## 3. D2 — Brede steekproef (12 niet-corpus-orders, totaal 29 vers gedraaide orders)

7 door mensen goedgekeurde (pushed) orders — hun goedgekeurde uitkomst als pseudo-grondwaarheid — plus 5 recente review-orders (beschrijvend). Uitslag: #814, #120 **JUIST vlagvrij**; #121, #516 fout-met-vlag (klant); 5 review-orders draaien schoon door (incl. #1012: mixprijzen live actief, M1PAL33-staffel correct).

**4 strenge stille-fout-tellingen, elk toegelicht:**
1. **#567 ship-to** (en klant #567/#121 gevlagd): de pseudo-GT zegt PontMeyer **Heerenveen** (61793/8447 GH) — dat is exact de fout die het team meldde en die destijds is meegekeurd. De nieuwe code kiest de vestiging op het leveradres (mét CONTROLEER-vlag); de ship-to volgt die gevlagde keuze. Geen codefout; wél bewijs dat de oude goedgekeurde data vervuild is.
2. **#537 twee regel-artikelen**: klantkeuze is gevlagd (50789 vs 50000); artikel-matching is klant-afhankelijk (kruisverwijzingen per klantnr), dus een onzekere klant geeft confident-ogende maar mogelijk verkeerde artikelen. **Aanbeveling** (open punt): bij een gevlagde klant de klant-afhankelijke artikel-matches mee laten vlaggen, of automatisch her-matchen na klantcorrectie.
3. **#522 regel-artikel** (238534 i.p.v. 12190): klant-artikelnummer is letterlijk een bestaand Kwabo-nummer → exact-match wint. De reviewer corrigeerde dit destijds handmatig; die correctie staat niet in `klantenkaart_artikelen` (leer-tabel is met 24 rijen vrijwel leeg in prod). **Data-actie**: leer-tabel vullen; de order droeg overigens wél een eenheid-vlag (niet vlagvrij gepusht).

**Geen enkele order in corpus of steekproef was tegelijk vlagvrij én fout.** Dat is de strengste zinvolle lezing van "0 stille fouten" op orderniveau; op veldniveau blijven de 3 hierboven genoemde afgeleiden + 1 data-gat staan, alle toegelicht.

## 4. D3 — Determinisme ⚠ DEELS (geblokkeerd op API-tegoed)

Run 1/3: kernset (954/944/941/847/819/845) **6/6 JUIST** — incl. #845 PALLET/2, #819 PALLET/4 + EXW, #847 61532/94315. Run 2 en 3 crashten op een opnieuw leeg Anthropic-tegoed (het aangevulde tegoed is door D1+D2+D3-run-1 ≈ 44 Vision-runs heen). **Nog te draaien na aanvulling: 2× kernset (12 runs) → 3× identiek-vergelijking staat klaar.**

## 5. D4 — Suites

- Backend-suite **vers groen: 709 passed / 17 skipped** (was 687/17 vóór de upgrade; +29 nieuwe tests, 10 bewust herschreven naar het B4-contract).
- `--regression` (17 .eml's, volle LLM): **nog niet vers gedraaid — geblokkeerd op API-tegoed** (~17 runs).
- Playwright: 13 passed incl. 7 nieuwe Fase C-specs; 7 scan-specs wachten op cache-hervulling (zelfde tegoed), 2 falen pre-existing (bewezen op ongewijzigde code).

## 6. Alleen on-site te bewijzen
- Echte NAV-push-acceptatie van de nieuwe orders (single-field PATCH-flow tegen nav2018, incl. #847's ship-to 94315 en Lasaulec PALLET-regels).
- De echte Vercel-UI met prod-data (e2e draaide tegen dev-server + seed).
- Nico's beleving van de nieuwe uitleg/volgorde — testscript hieronder.

## 7. Open punten
| # | Punt | Eigenaar |
|---|---|---|
| 1 | **API-tegoed** aanvullen (~30–40 Vision-runs) → D3 runs 2+3, --regression, Playwright-cache | Cas |
| 2 | **PALLET_PLAATSEN_VULLIJST.md** invullen (14 paren) → #832/#833 europallet groen | Nico/OPS |
| 3 | `klantenkaart_artikelen` vullen/leren (24 rijen in prod) → #522-klasse dicht | Nico/OPS + leerloop |
| 4 | Aanbeveling: klant-vlag → artikel-matches mee vlaggen of her-matchen na klantcorrectie (#537-klasse) | volgende iteratie |
| 5 | Originele .eml's naleveren (#944/#941/#816/#819/#845/#203/#954) of Supabase-creds | Cas/OPS |
| 6 | F6-prijsdata (`prijsafspraken` = 0 rijen) en F7-partnerblok (NAV-side) — ongewijzigd open | Kwabo/NAV |
| 7 | Prod-tabel `pallet_plaatsen_basis` ontstaat bij deploy; stale prod-orders herverwerken kan nu idempotent (B3) — Cas-akkoord nodig voor de prod-write | Cas |

## 8. On-site testscript (sessie met Nico, ±30 min)
1. **BAUHAUS-patroon**: stuur een testorder met afwijkend afleveradres → check adresrollen-chips (besteller grijs, aflever groen) en dat ship-to het afleveradres volgt.
2. **TABS-order**: open een verse TABS-order → klantregel toont de match-reden ("gekozen op leveradres … via ship-to van …"); wijzig de klant via de picker (zoek op plaats) → ship-to en vlaggen verversen zonder reload.
3. **Lasaulec/pallet**: order met "2 PAL" → regel toont "→ NAV: 2 × PALLET"; controleer in de NAV-preview de expliciete UoM-PATCH.
4. **Europallet**: order met gemengde regels → onderbouwing toont per regel de bron én "Niet meegeteld (pallet-plaatsen onbekend)" voor artikelen zonder waarde; vul één waarde in de vullijst en zie de telling kloppen.
5. **Werkvolgorde**: open een order met meerdere vlaggen → banner "N dingen te controleren (in volgorde)" — klant eerst; werk de lijst af en zie "✓ klaar" in de lijst verschijnen.
6. **Push**: keur één order goed en push naar NAV → verifieer regels/eenheden/europallet in NAV zelf.
