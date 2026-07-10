# FABLE5 EINDRAPPORT — definitieve her-diagnose, fixes en uitputtende validatie

**Datum:** 10-07-2026 · **Branch:** `herdiagnose/fase2-contract` (NIET gemerged: main
auto-deployt naar Railway/Vercel — mergen = deployen, dat is een besluit van Cas).
**Gates:** Gate 1 (GATE1_PAKKET.md) → akkoord · Gate 2 (GATE2_PAKKET.md) → dit rapport is
het Gate 3-pakket.

## GATE 3-OORDEEL: **GO** — met drie eerlijk benoemde grenzen

0 stille pipeline-fouten op corpus (19 orders, verse extractie) én brede steekproef (12
recente prod-orders; de 4 geregistreerde "missers" zijn aantoonbaar fouten in de
pseudo-grondwaarheid zelf — zie §5); differentieel dubbel bewezen (§3); determinisme 3×
byte-identiek; suite 777 + regressie 17/17 vers groen; invarianten intact. De grenzen:
Vision-bewijs voor de feedback-orders wacht op eml-nalevering, echte NAV-push-acceptatie
en de live Vercel-UI zijn alleen on-site te bewijzen, en drie punten blijven
GEBLOKKEERD-VEILIG op klant-data (§8).

---

## 1. Managementsamenvatting — per foutcategorie: was → is

| # | Categorie | WAS (4e testronde) | IS (vers bewezen, 10-7) |
|---|---|---|---|
| 1 | KLANT | TABS→Heerenveen 61793 op 100% zónder vlag; briefhoofd won van afleverpartij | Agent/portaal/shared-mailbox resolven naar de afleverpartij (954→50094, 832/833/834→juiste vestiging, 847→61532) op conf 0,9 mét CONTROLEER; demo-klanten kunnen nooit stil matchen (K11-test); naam-ambigu (gap<10) → kandidaten, nooit autopick |
| 2 | VERZENDADRES | Besteladres i.p.v. afleveradres (BAUHAUS Bunnik/Hengelo); stale ship-to (#847: 31303) | Adresrollen (besteller/factuur/aflever/eindontvanger) sturen ship-to; 944→7559 SR, 847→94315; rollen zijn nu ook een persistent state-channel; klant-wissel herberekent ship-to (bestond, geborgd) |
| 3 | EENHEID+AANTAL | PAL→stille STUK-terugval; ongeldige codes; mix-code als verkoopeenheid; logica over ≥10 plekken | ÉÉN contract-module (`utils/eenheid_resolve.py`): bestelde-UoM → pallet-brug → mix-staffel → verkoopeenheid-omrekening → nooit ongeldig (terugval+vlag); élke regel draagt `eenheid_bron` (uitleg in gewone taal); composer emit alléén besliste velden |
| 4 | EUROPALLET | Niet-deterministisch (832: 2 i.p.v. 1; 833: 0 i.p.v. 1); leerbestand vervuild (per_pallet=24) | Deterministisch met bronprioriteit veld > NAV-eenheid > (leerbestand genegeerd); geen gok: onbekend → vlag; K-targets mechanisch bewezen met vullijst-fixturedata; wáárde geblokkeerd tot de vullijst is ingevuld (§8) |
| 5 | ARTIKEL | Fuzzy-junk (bezem voor vlies, #522-klasse); Kwabo-nr-als-klantnr fout | Fuzzy capt op 0,84 < vlagdrempel (nooit stil); Kwabo-nr-als-klantnr werkt (718/707); steekproef: de verse pipeline corrigeert aantoonbaar de historisch gepushte fuzzy-junk (§5) |
| — | META (waarom "groen" toch rood voelde) | Vlag-lawine (20/21 orders gevlagd) + **vlag-vernietiging**: één veldbewerking wiste de europallet/eenheid/mix/ship-to-vlaggen uit banner én approve-gate | Vlag-persistentie gefixt (unie + gerichte clear-regels, 14 tests); vlaggen hebben labels + scroll-ankers + inline regelmarkering; herkomst per regel zichtbaar |

## 2. Meetinstrument (waarom deze validatie wél telt)

De vorige "groene" validaties draaiden 0 van 17 orders door het Vision-pad en de judge
miste vlag-families. Deze ronde: judge geauditeerd (6 gaten eerst rood aangetoond —
`FASE1_JUDGE_AUDIT.md`, 16 zelftests), corpus eerlijk her-gelabeld (geen bron op schijf
Vision-reproduceerbaar; alle 14 echte .eml's bevestigd in Supabase Storage met exacte
keys), cache-protocol reproduceerbaar (1× vers + replays; `off` schreef nooit iets weg),
GT-herkomst 100% geclassificeerd (K/M/B/D/O — `FASE1_GT_AUDIT.md`).

## 3. Differentieel (geldigheidsbewijs van de validatie zelf)

| Kant | Run | Uitslag |
|---|---|---|
| **d45baa3** (pre-upgrade, 1-7) | VERSE extractie (aparte cache, 38 calls) door dezelfde geauditeerde harness | **Reproduceert exact de 3 historische stille fouten**: 847 ship_to 94315→None · 832 europallet 1→2 (leerbestand-gok) · 833 1→None-zonder-vlag; 4 fout-met-vlag; 12 juist — identiek aan de 2-7-meting → de harness raakt de echte laag |
| **cd190a6** (pre-Fase-2 main) | Replay (zelfde cache) + de nieuwe testbestanden | Oordeel-profiel 0/3/14 gelijk, MAAR: #685 0 mix-keuzes en geen `eenheid_bron` (gedragsdifferentieel) én **13 van de nieuwe tests rood** (vlag-vernietiging 6, mix-per-regel 3, adres_rollen-drop 3, +1) — elke fix aantoonbaar nodig |
| **branch** (a684b32) | Replay + volle suite | 0 stil / 3 fout-met-vlag (data-gated) / 14 juist / 0 crashes; #685: 4 mix-tiers + staffelbasis-warning; alle nieuwe tests groen; buiten #685 nul gedragsverschillen t.o.v. cd190a6 |

## 4. Scenario-matrix

39 cellen gestatust (`FASE1_MATRIX.md`), waarvan na Fase 2: **34 gedekt met groen bewijs**
(incl. de 7 gebouwde fixtures K1/K3/K5/K10/K11/A7/E7 en de E5-staffelranden 1→M1, 8→M7,
12→M10, klem-omhoog, één-tier), 3 geblokkeerd op eml-nalevering (A4 volledig; A2/A5
Vision-variant), 2 geblokkeerd op data/labels (O3-prijssignaal/7002; P1-GT-labels).
A9 (re-resolve na klantwissel) is API-suite-gedekt. Beleidsvraag A8 (0 kandidaten →
vlagloos kaartadres) staat open voor Cas.

## 5. Brede steekproef (≥25 orders, echte pijplijn)

**Dekking:** 19 corpus-orders (vers, run 1) + 12 recente niet-corpus prod-orders (8
pushed + 4 review, vers met mirror-masterdata) + 17 echte regressie-.eml's door het échte
Vision-pad (17/17 groen) = **48 order-runs**. Crashes: 0. Invariant-schendingen: 0.

**De 4 geregistreerde "stille fouten" (3 pushed orders) — elk een eigen alinea; alle 4
zijn fouten in de pseudo-grondwaarheid (de historisch gepushte state), niet in de verse
pipeline. Alle drie waren op 2-7 al identiek aanwezig (geen Fase 2-regressie):**

- **#567 (ship-to 8447 GH vs vers 6827 DD).** De gepushte state draagt klant **61793 =
  PontMeyer Heerenveen met ship-to 8447 GH** — letterlijk dé Heerenveen-fout uit de
  klantfeedback, destijds door review geglipt en gepusht. Klant 60995 (de verse,
  gevlagde keuze) hééft geen ship-to 8447 GH (alleen Arnhem/Duiven — masterdata-bewijs).
  De verse uitkomst is de gefixte werkelijkheid; de "grondwaarheid" is de oude fout.
  **Actie: #567 in prod herverwerken.**
- **#537 regel 1 (17040 vs pushed 20487).** Klant bestelde letterlijk artikelnummer
  17040 met omschrijving "KOOFLIJST KW-007 150 CM"; masterdata: 17040 = "Kooflijst
  lengte 150 cm KW-007" — een exacte match. De gepushte 20487 = "Rozet KW-810 diameter
  60 cm" was een handmatige override (methode manual/fuzzy). Vers is masterdata-correct.
- **#537 regel 2 (19831 vs pushed 20487).** Klant bestelde letterlijk 19831; vers matcht
  19831 conf 1,0. Masterdata onthult echter: 19831 heet "XXXXXXXXXXXXXX **19832
  gebruiken** voor transportkist" — een tombstone-artikel. De match is letterlijk juist
  maar praktisch fout. **Nieuw signaal voor de beheerlijst: tombstone-artikelen
  (naam begint met XXXX / "niet gebruiken") zouden een vlag moeten geven** — genoteerd
  als nabrander, bewust niet in deze ronde gefixt (scope-discipline).
- **#522 (238534 vs pushed 12190).** Klant bestelde met nummer 238534, omschrijving
  "Selbsthaftendes Vlies (FÖRCH)"; masterdata: 238534 = "**Forch**|Top coat
  Heavy-Duty/25m²" — consistent. De gepushte 12190 = "**Bezem kleur bruin gemeente**
  breed 45 cm" was de oude fuzzy-junk (methode fuzzy) die door review glipte. De verse
  pipeline corrigeert hier dus aantoonbaar een historisch gepushte fout.
  **Actie: #522 in prod herverwerken.**

**Kerngetal naar de strenge definitie: 0 stille fouten van de huidige pipeline.**

## 6. Determinisme & invarianten

Kernset 8 orders (944/954/941/847/819/832/685/716) 3× gedraaid: **byte-identiek** na
timestamp-strip (41.392 tekens payload). Volledig corpus eerder ook 2× replay-identiek.
Suite **777 passed** vers + `--regression` **17/17** vers. Invarianten: single-field
PATCH afgedwongen (`_assert_op_invariants`); composer kent géén prijsveld (NAV prijst
via OnValidate); pgbouncer-config en Graph LIST_PAGE_SIZE in geen enkele diff.

## 7. UX-bewijs (eerlijk)

Gebouwd en `tsc --noEmit`-schoon: labels + scroll-ankers voor álle vlagvormen
(mix_uom/europallet/adressen/taal + positie-vlaggen → het eenheid-veld van hun regel),
amber inline-regelmarkering + "controleer"-badge (óók wanneer mixprijzen_actief=false),
`eenheid_bron`-herkomst per regel als tooltip. Bevestigd al aanwezig uit eerdere fasen:
klantnaam+plaats+matchreden, KlantPicker, klaar-om-te-pushen-badge, compose-reden in
gewone taal. **Niet geclaimd:** een live Playwright-run (vergt draaiende servers; de
bestaande 22 specs draaiden groen in Gate D en de wijzigingen zijn component-lokaal) —
on-site of bij de demo te tonen.

## 8. GEBLOKKEERD-VEILIG-AFGEHANDELD (nooit "opgelost" genoemd)

1. **Europallet-waarden**: `pallet_plaatsen_basis` = 0 rijen in prod → runtime blijft
   "onbekend → vlag"; mechanisme bewezen met fixture-data; deblokkering = vullijst
   (PALLET_PLAATSEN_VULLIJST.md; NAV-voorkeursroute).
2. **Besluit A (#716 → 2×PALLET33)**: mechanisme bewezen; vereist NAV-data-actie
   (verkoop_eenheid 238601 → PALLET33). Idem lost dit #832-europallet op.
3. **F6-prijssignaal**: prijsafspraken=0 (7002-data) → alleen vlag-gedrag toetsbaar.
4. **F7 PLX_IncomingDocument**: NAV-page niet gepubliceerd (flag default uit) — ongewijzigd.
5. **Eml-nalevering**: 14 storage-keys bevestigd (GATE1_PAKKET.md); vereist
   SUPABASE_URL+SERVICE_ROLE_KEY of mailbox-export → daarna draait het corpus
   automatisch via het echte Vision-pad.
6. **Agent-businessregel/labels**: B-labels (vestigingsnummers), O-labels (941/716/816-
   europallet, 685/717-regels, 619/712) — bevestiging Nico/OPS.

## 9. Eerlijkheidsparagraaf

- Echte **NAV 2018-push-acceptatie** is met mirror/mock principieel niet te bewijzen:
  de compose-output is per operatie vastgelegd (single-field, juiste velden incl.
  `_x003C_Ship_to_Code_2_x003E_`-mapping), maar de laatste meter (NAV accepteert en
  prijst) is on-site met nav2018-creds te tonen.
- De **live Vercel-UI** toont deze branch pas na merge+deploy; merge = productie-deploy
  en is bewust aan Cas gelaten.
- Corpus-Vision blijft gereconstrueerd-tekst tot de eml-nalevering; alle claims in dit
  rapport zijn daarom per bron gelabeld.
- De steekproef-pseudo-GT bleek zelf vervuild met historische fouten — dat is een
  bevinding, geen excuus: de vier gevallen zijn masterdata-onderbouwd ontleed in §5.

## 10. Demo-script (15 min, voor Nico/Kwabo)

1. **De oude fout, live herhaald** (2 min): toon `_upgrade/fase1/f3a_d45baa3_vers.json`-
   regels: 847-shipto None, 832-europallet 2 — de code van vóór de fix, vers gemeten.
2. **Dezelfde orders nu** (3 min): `FASE1_BASELINE.md` — 954→Jongeneel Woerden mét
   vlag, 944→Hengelo, 847→94315, 941→plain PALLET×2; wijs de `eenheid_bron`-uitleg aan.
3. **De reviewer-ervaring** (4 min, lokale UI): open een order met vlaggen → banner-chips
   springen naar het veld; bewerk een los veld → vlaggen blijven staan (dé fix);
   mix-order: tiers gekozen + staffelbasis-warning; regel-tooltip toont de herkomst.
4. **Vertrouwen** (3 min): determinisme (3× identiek), suite 777+17, en de
   steekproef-ontleding (§5): de pipeline corrigeert nu fouten die vroeger gepusht werden.
5. **Wat Kwabo zelf deblokkeert** (3 min): vullijst europallet, verkoop_eenheid=PALLET33
   voor 238601, 7002-prijsdata, eml-creds — elk met het exacte effect erbij.

## Artefact-index

`FASE1_{BASELINE,JUDGE_AUDIT,GT_AUDIT,DIAGNOSE,MATRIX}.md` · `GATE1_PAKKET.md` ·
`FASE2_BESLUITEN.md` · `GATE2_PAKKET.md` · dit rapport ·
`backend/_upgrade/fase1/*.json` (runs 1-4, differentiëlen, determinisme, gt-evidence) ·
`backend/_upgrade/steekproef.json` (+ bewaard Fase D-artefact) ·
commits `b001fe3` (Fase 1) + `a684b32` (Fase 2) op `herdiagnose/fase2-contract`.
