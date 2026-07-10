# FASE 1 — GT-audit (stap 2b): herkomst van elk grondwaarheid-label

**Datum:** 10-07-2026 · **Bron:** `backend/tests/corpus/ground_truth.json` (17 orders) ·
**Bewijs:** read-only prod-SELECT's in `backend/_upgrade/fase1/gt_evidence.json`
(script `backend/scripts/fase1_gt_evidence.py`, guard-patroon, 0 writes) + citaten uit
repo-docs en de 4e-ronde-opdrachttekst. Geen enkel beoordeeld veld houdt "onbekende
herkomst"; open velden zijn expliciet O-geklasseerd met een labelvraag.

## Herkomstklassen

- **K** = klant/team-feedback-citaat — **K(opdr)** = 4e-ronde-opdrachttekst (leidend),
  **K(man)** = manifest-/rapportfeedback (corpus-annotatie).
- **M** = masterdata-afgeleid; SELECT-bewijs geplakt (gt_evidence.json).
- **B** = beleid-afgeleid (bijv. agent→afleverpartij); blijft staan, wordt bij Gate 1
  expliciet ter bevestiging voorgelegd.
- **D** = direct uit het brondocument/extract (niet betwist).
- **O** = open → labelvraag Nico/OPS.

## M-bewijs — kernuitkomsten (alle read-only, 10-07)

| claim | SELECT-uitkomst | verdict |
|---|---|---|
| klantnummers 61854/61483/61969/61745/60245/61030/61844/60892/61472/61948/60203/61532(+60103)/50094-familie | alle namen→nummers bevestigd in `klantenkaarten` | ✅ |
| 941 is GEEN mix-klant | `mixprijzen=false` voor 61483 | ✅ |
| 718/685 zijn mix-klanten | `mixprijzen=true` voor 60892/60203 | ✅ |
| PontMeyer-vestigingen 61468 Zoetermeer / 61019 Heemstede / 61088 Zwaag | bevestigd (1 rij elk) | ✅ |
| ship-to's 944 `7559 SR` HENGELO (61854) · 954 `3449 JE` WOERDEN (50094) · 845 `8531 PA` LEMMER · 816 `4906 CS` · 716 `5215 MK` · 717 `7783 DC` | alle bevestigd | ✅ |
| 941 ship-to: bestaat `4815 PN`? | **nee** — alleen `4814 RR` BREDA bestaat voor 61483 | GT `4814 RR` = enige kandidaat; extract-adres `4815 PN` bestaat niet als ship-to (vraag C blijft t.a.v. juistheid) |
| 847 ship-to `94315` | bestaat bij 61532 — én bij **61595 en 61816** (3 klanten delen postcode 94315!) | ✅ + disambiguatie-observatie |
| 847 aantallen: 23730 PALLET qty_per_base, 23733 idem | 23730 PALLET=30 (930/30=**31** ✓), 23733 PALLET=20 (700/20=**35** ✓) | ✅ GT-aantallen exact masterdata-consistent |
| 819: 23691 pallet=20 | 23691: PALLET=20, STUK=1 | ✅ (opdracht-citaat bevestigd) |
| 15620 pallet-maten (vraag F) | 11 UoM-rijen, o.a. `M10PAL30`/`M15PAL30`(mix-codes, 30/pallet); volledige lijst in gt_evidence.json | maat 30 dominant; F blijft bevestigingsvraag |
| 238601 PALLET33 (t.b.v. #716-conflict) | 44 UoM-rijen, o.a. `EXW PAL33`=33, `EXW PAL35`=35 | PAL33-familie bestaat |
| verkoop_eenheid prod (europallet-route) | 15620/229231/23522/… = **STUK** | route "NAV-verkoopeenheid→palletmaat" levert niets; F4-vullijst-route bevestigd nodig |
| `pallet_plaatsen_basis` | **0 rijen** (tabel bestaat sinds PR #6-deploy) | europallet-K-targets mechanisch onhaalbaar tot OPS vult |
| leerbestand vervuild (opdracht 4) | `artikel_pallet_kennis`: per_pallet=**24** voor 238601, 229231, … (bevestigd_door='dashboard') | ✅ vervuiling bevestigd; negeren is terecht |
| klant-specifieke kruisverwijzingen 941 (`804600→23559` e.d.) en 83x (`K700100070→…`) | **bestaan NIET** in prod-`artikel_kruisverwijzing` (0 rijen); wel generieke rijen bij ándere klanten (bijv. 60282: `23559→23559`) | artikel-GT blijft geldig als DOEL, maar het match-pad is data-gated → verklaring in diagnose |

## Per-order-classificatie

Compact per order; de volledige veld-tabellen met citaten staan hieronder in de bijlage
van dit document verwerkt per opmerking. Klassen per veld:

| order | klant_nr | adres/ship-to | regels (eenheid/aantal/artikel) | europallet | bijzonderheden |
|---|---|---|---|---|---|
| 944 | M (61854 ✅) | **K(opdr)** "Bunnik 3981 LB i.p.v. Hengelo 7559 SR" + M | D/D/M | — | sterkste K-anker adresrollen |
| 954 | naam **K(opdr)** ("moet Jongeneel Woerden"), nummer **M** (50094 ✅; nooit mens-gepusht — HERVERIFICATIE r78: record bleef op 61793 in review) | M (3449 JE ✅) | artikel M | — | vraag G |
| 941 | M (61483 ✅, mix=false ✅) | ship-to **M+O**: 4814 RR = enige bestaande; extract zei 4815 PN | r1 D; r2/r3 eenheid **K(opdr)** ("mix en PALLET door elkaar") + aantal M (60/30=2) | **O** (expliciete OPS-vraag) | vraag C+E |
| 847 | **K(opdr)** ("i.p.v. se Huber 61532" ✅) | **K(opdr)** ("#847: 31303" = de fout; 94315 ✅ — let op: 3 klanten delen 94315) | eenheid **O/conflict** (GT=PALLET 31/35 ↔ scenario-eis "STUK-blijft-STUK #847"); aantallen M ✅ | — | vraag B; bron heeft GEEN extra STUK-regels (alleen pos 10/20 + systeem-pos 21) |
| 819 | M (61969 ✅) | B+D (afhaal→null) | eenheid **K(opdr)** ("PAL → stille STUK-terugval (#819, 23691 pallet=20)" ✅) | — | verzendwijze EXW = **B** (F5, eerder Cas-bevestigd) |
| 845 | M (61745 ✅) | M (8531 PA Polem ✅) | eenheid M **let op** maat 30-vs-35 (vraag F) | — | drop-ship-anker |
| 203 | M (61745) | — | idem 15620; pos2 eenheid bewust null = **B** (B3-beleid ROL) | — | generiek-bewijs Lasaulec |
| 816 | M (60245 ✅) | M (4906 CS ✅) | M/D; pos9 = F6-signaal (**GEBLOKKEERD** op 7002-data, opdracht 5) | — | vraag I |
| 832 | **B+M** (61468 ✅; K dekt alleen de disambiguatie-EIS) | D + B (ship_to null=kaartadres) | artikel M | **K(opdr)** "832: 2 i.p.v. 1" — mechanisch geblokkeerd (ppb=0, leerbestand=24) | vraag D+G |
| 833 | **B+M** (61019 ✅) | idem | D/D/M | **K(opdr)** "833: 0 i.p.v. 1" — idem geblokkeerd | vraag D+G |
| 834 | **B+M** (61088 ✅) | idem | artikel M | — | vraag G |
| 716 | M (61030 ✅) | M (5215 MK ✅) | **O/conflict**: GT=STUK 66 ↔ opdracht 3 "niet omgerekend (Würth 66 i.p.v. 2xPALLET33)" | — | **vraag A (kernconflict)** |
| 717 | M (61844 ✅) | M (7783 DC ✅) | **O**: regel-GT bewust leeg (stored 18390 gevlagd) | — | vraag H |
| 718 | M (60892 ✅ mix) | — | artikel M+**K(opdr)** ("Kwabo-nr-als-klantnr") | — | — |
| 721 | M (61472 ✅) | — | eenheid null = **B** (B3: ROL geen item-UoM; opdracht 5 "ROL→400") | — | — |
| 707 | **B+M** (61948 ✅; portaal→afleverpartij) | — | artikel M+K(opdr) | — | — |
| 685 | M (60203 ✅ mix) | M (6101 XK) | **O**: regel-GT bewust leeg | — | vraag H |

## Herlabel-/labelvragen voor Gate 1 (beslislijst)

**A. #716 — STUK 66 vs 2×PALLET33 (kernconflict; chronologische flip-flop).**
EINDVALIDATIERAPPORT (11-06, N7): "NAV kreeg 66 i.p.v. 2×PALLET33" (€45.738 i.p.v.
€1.386) → verwachtte 2×PALLET33. F4-plan (18-06): "PALLET33 was een artefact van fictieve
testdata; prod verkoop_eenheid=STUK". UPGRADE (02-07): "#716-anker: 66 STUK blijft STUK".
Opdracht (4e ronde, leidend): "niet omgerekend (**Würth 66 i.v.p. 2xPALLET33**)" → wil
omrekening. Nuance: 66 STUK en 2×PALLET33 zijn hoeveelheid-equivalent (2×33=66; beide
€1.386; beide sturen een expliciete eenheid en voorkomen de €45k-bug) — het conflict is
notatie, geen geld. **Vraag: STUK 66 of PALLET33 2?** Masterdata: 238601 heeft
`EXW PAL33`-familie (33/stuks per pallet) — een "PALLET33"-notatie is masterdata-mogelijk.

**B. #847 — spiegelbeeld van A.** GT codeert PALLET 31/35 (pipeline-omrekening uit
930/700 STUK, origineel ROL); de scenario-eis zegt "STUK-blijft-STUK (#847, geen valse
omrekening)". Bron-state bevat GEEN andere STUK-regels (herlabel-, geen
uitbreidingsvraag). **Vraag: PALLET 31/35 of STUK 930/700?** Let op de spanning met A:
zoals de opdracht nu leest wil hij #716 wél omrekenen en #847 niet — als het beleid
"stuks-die-exact-hele-pallets-zijn → pallet-notatie" is, zou #847 óók PALLET moeten
zijn (930=31×30 ✓, 700=35×20 ✓). Consistente beleidsuitspraak nodig.

**C. #941 ship-to.** Extract-afleveradres = Driessen Breda `4815 PN`; GT = `4814 RR`.
SELECT: `4815 PN` bestaat NIET als ship-to; `4814 RR` BREDA is de enige. GT is dus
"best beschikbare masterdata-keuze". **Vraag: bevestig 4814 RR** (of: moet er een
nieuwe ship-to 4815 PN in NAV komen?).

**D. #832/#833 europallet=1** — K-target staat vast (opdracht 4), maar mechanisch
geblokkeerd: `pallet_plaatsen_basis`=0 rijen en leerbestand per_pallet=24 (vervuild,
terecht genegeerd). **Actie: vullijst invullen** (PALLET_PLAATSEN_VULLIJST.md;
voorkeursroute NAV verkoop_eenheid→pallet-code, commit 07f3fe5). Tot die tijd is de
enige eerlijke uitkomst: europallet=onbekend→VLAG (geen gok) —
GEBLOKKEERD-VEILIG-AFGEHANDELD, niet "opgelost".

**E. #941 europallet_aantal=null** — expliciete OPS-labelvraag (23559/23522/23523).

**F. #845/#203 — 15620 pallet-maat 30 vs 35** — bevestig 30 (mix-codes M10PAL30/M15PAL30
suggereren 30/pallet; volledige UoM-lijst in gt_evidence.json).

**G. Agent-vestigingsnummers 954→50094, 832→61468, 833→61019, 834→61088** — de EIS
(klant uit afleverpartij) is K(opdr); de nummers zijn masterdata-afgeleid en bij 954
nooit mens-bevestigd (record bleef in review op 61793). SELECT's bevestigen dat de
nummers de juiste vestigingen zijn. **Vraag: formeel bevestigen.**

**H. #717/#685 — lege regel-GT** — correcte artikelen onbekend (stored matches waren
gevlagd/fuzzy). **Vraag: Kwabo levert de juiste artikelnummers** (of accepteert dat
regel-uitkomsten van deze orders alleen op vlag-gedrag beoordeeld worden).

**I. #816 pos9 — F6-prijs-signaal (23853 vs klantprijs 238531)** — data-gated
(prijsafspraken=0 in prod); GEBLOKKEERD op 7002-data per opdracht 5. Vlag-gedrag is het
enige toetsbare.

## Structurele observaties uit het bewijs (voer voor 1c-diagnose)

1. **Kruisverwijzing-sparsity**: de klant-specifieke mappings die de artikel-GT zou
   "verklaren" (941: 804600→23559; 83x: K7001…→…) bestaan niet in prod. Artikel-matching
   moet dus via klantenkaart/history/fuzzy/exact-Kwabo-nr — verklaart de lage automatch
   en maakt de artikel-GT tot een DOEL-label, niet een reproduceerbaarheid-garantie.
2. **Postcode 94315 gedeeld door 3 klanten** (61532, 61595, 61816) — postcode-alleen
   is onvoldoende voor klant/ship-to-disambiguatie in DE; naam+plaats nodig.
3. **Europallet-datalaag**: alle drie de bronnen op volgorde van prioriteit:
   `pallet_plaatsen_basis` leeg (0), `verkoop_eenheid` = STUK (geen palletmaat),
   leerbestand vervuild (24, genegeerd) → de deterministische europallet kán in prod
   momenteel alleen "onbekend→vlag" of via mix/Branch-A-regels tellen.
4. **`AFHAAL`/`EXW …`/`FCA …` bestaan als Item-UoM-codes** (bijv. 23522 `AFHAAL`=30,
   `FCA PAL20`=20) — het UoM-landschap is veel rijker dan STUK/PALLET/mix; relevant
   voor het eenheid-contract (2c) en de matrix-cellen E2/E3/E7.
