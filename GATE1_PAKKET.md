# GATE 1 — beslispakket Fase 1 (her-diagnose, 10-07-2026)

**Code-anker:** main `cd190a6` (schoon; niets onder `backend/src/kwabo/` aangeraakt).
**Kerngetal (run 1, vers, geauditeerde judge): 0 stille fouten · 3 fout-met-vlag
(alle drie data-gated) · 14 juist · 4 observaties · 0 crashes — op het TEKST-pad.**
Het Vision-pad is voor de feedback-orders nog onbewezen (zie blokkade 1).

> Naamgeving: de bestanden `FASE1_*.md` van 10-07 horen bij DEZE her-diagnose;
> het oudere `FASE1_VALIDATIE.md` (09-06) is van een eerdere ronde en staat hier los van.

## 1. Deliverables (GO-criteria 1-5, alle vers geverifieerd)

| # | Criterium | Bewijs |
|---|---|---|
| 1 | Baseline letterlijk per order, run-metadata, replays zonder onverklaarde delta | `FASE1_BASELINE.md` (volledige per-order-JSON; run 2/3 byte-identiek; run 4 tweede verse trekking: alleen cosmetische extract-variantie, geen oordeel-kanteling); ruwe data `backend/_upgrade/fase1/fase1_run{1,1a,2,3,4}*.json` |
| 2 | Judge-audit compleet | `FASE1_JUDGE_AUDIT.md`: vlag-vocabulaire-tabel, 6 gaten elk eerst ROOD aangetoond en gedicht (`tests/test_fase1_judge.py`, 16 tests), UI-zichtbaarheid gecheckt, judge-wijzigingen alleen mild-makend; run 1-oordeel identiek onder oude én nieuwe judge |
| 3 | GT-audit 100% herkomst | `FASE1_GT_AUDIT.md`: elk niet-null veld K/M/B/D/O met citaat of geplakte SELECT (`_upgrade/fase1/gt_evidence.json`); geen veld "onbekende herkomst" |
| 4 | Diagnose per categorie met bestand:regel + standgehouden-tabel | `FASE1_DIAGNOSE.md`: pre-fix (2-7) → nu; geen enkele fix geregressed; meta-diagnose (vlag-lawine 20/21 + vlag-vernietiging bij patch-field) |
| 5 | Matrix alle cellen gestatust | `FASE1_MATRIX.md`: 39 cellen — 27 gedekt (6 zwak/geblokkeerd), 9 fixtures gepland, rest expliciet geblokkeerd/datavraag |
| 6 | Suite groen | vers gedraaid 10-07: **728 passed** (incl. de 16 judge-zelftests) |

## 2. Read-only-verklaring (GO-criterium 7)

Gedraaide scripts, alle met het bewezen guard-patroon (prod-URL apart gelezen →
`DATABASE_URL` overschreven naar wegwerp-sqlite VÓÓR elke kwabo-import → prod
uitsluitend via losse `SELECT`-connecties, nul `commit()`):
`fase1_preflight.py` · `fase1_corpus_probe.py` · `fase1_gt_evidence.py` ·
`fase1_baseline.py` (smoke 2×, run 1a, run 1, run 2, run 3, run 4) · `fase1_report.py`
(puur lokaal) · 2 inline read-only SELECT-probes (storage-keys) · pytest (sqlite).
NAV: uitsluitend `NAVISION_MODE=mirror` (push erft van mock). De verboden-lijst
(`run_all*.py`, `run_e2e_10x.py`, `verify_t12.py`, `seed_pallet_history.py`,
`sync_navision_masters.py`, `backfill_*`) is niet aangeraakt.
Gewijzigde bestanden: alleen `tests/corpus/manifest.json` (eerlijke herlabeling),
nieuwe `scripts/fase1_*.py`, `tests/test_fase1_judge.py` en de FASE1-rapporten.

## 3. Wat de her-diagnose aan het licht bracht (samenvatting)

1. **De eerdere fixes houden stand op verse extractie (tekst-pad):** 847-ship-to nu
   juist; agent-orders resolven naar de afleverpartij mét vlag; geen mix-code-lek;
   geen PAL→STUK-terugval; europallet gokt nooit meer.
2. **Maar de Fase A/D-validatie raakte het Vision-pad nooit** (0 van 17 orders; de
   "state_met_pdf"-labels waren onjuist — PDF-bytes lossy in email_body) én ook
   #847's "echte .eml's" bleken familie-orders. Vision-bewijs = geblokkeerd op
   eml-nalevering (lijst hieronder).
3. **De drie resterende gevlagde fouten zijn data-gaten, geen code-gaten:**
   #203-artikel (geen kruisverwijzing), #832/#833-europallet
   (`pallet_plaatsen_basis` = 0 rijen; leerbestand vervuild per_pallet=24, genegeerd).
4. **Meta-verklaring "vier rondes groen, klant rood":** (a) vlag-lawine — 20/21
   corpus-records dragen ≥1 vlag (816: 11, 685: 17) → reviewer-blindheid;
   (b) **vlag-vernietiging**: `PATCH /patch-field` herschrijft `needs_review_fields`
   uit `_meta`, waardoor de vlaggen `ship_to_gekozen`/`europallet`/
   `verkoop_eenheid:{pos}`/`mix_uom:{pos}` verdwijnen uit banner én approve-gate
   zodra de reviewer één willekeurig veld bewerkt (preview.py:401-402). Fase 2-kern.
5. **Mix-laag is functioneel dood bij echte mix-klanten** (685/718: n_actief=0,
   louter vlaggen, geen tier-keuze) — veilig maar onwerkbaar; Fase 2-kern (2c).
6. `adres_rollen` is geen OrderState-channel en wordt na extract gedropt (rollen
   overleven alleen in `_meta`) — Fase 2-kandidaat voor persistentie/UI.

## 4. Beslislijst (GO-criterium 6) — jouw input gevraagd

**GT-herlabelvragen (volledige onderbouwing in FASE1_GT_AUDIT.md):**
- **A. #716:** 66 STUK laten staan of herlabelen naar 2×PALLET33? (opdracht-tekst wil
  omrekening; huidige GT + eerder F3-anker zegt STUK; beide varianten zijn €1.386 en
  expliciet — het is een notatie-beleidskeuze die 2c bepaalt)
- **B. #847 (spiegelbeeld):** PALLET 31/35 laten staan of STUK 930/700
  ("STUK-blijft-STUK")? Consistent beleid met A nodig.
- **C. #941 ship-to:** `4814 RR` bevestigen (extract zei 4815 PN; die bestaat niet
  als ship-to — 4814 RR is de enige Breda-optie).
- **F. 15620:** palletmaat 30 bevestigen (plain PALLET=30 bestaat naast PALLET35).
- **G.** Vestigingsnummers formeel bevestigen: 954→50094, 832→61468, 833→61019,
  834→61088 (eis is klant-bevestigd; nummers zijn masterdata-afgeleid).
- **H.** #717/#685: juiste artikelnummers aanleveren, of accepteren dat deze orders
  alleen op vlag-gedrag beoordeeld worden.
- **Beleidsvragen:** A8 (0 ship-to-kandidaten: vlagloos kaartadres OK?);
  E3 (pallet-variant-keuze aantal-consistentie-check gewenst?).

**Data-acties (deblokkeren de K-targets):**
- **D/E. Europallet:** `pallet_plaatsen_basis` vullen (0 rijen) —
  `PALLET_PLAATSEN_VULLIJST.md`, NAV-voorkeursroute (07f3fe5). Tot dan blijft
  europallet voor STUK-regels eerlijk "onbekend → vlag" (GEBLOKKEERD-VEILIG).
- **I. F6-prijs-signaal:** GEBLOKKEERD op 7002-data (prijsafspraken=0) — blijft zo
  gerapporteerd.

**Eml-nalevering (Supabase Storage, alle keys bevestigd aanwezig in prod-order_log;
nodig voor Vision-bewijs A4/A2/A5 en volle-getrouwheid-validatie):**
```
944  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-cc1934a0e9cdbc50.eml
954  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-301d41c3304d704e.eml
941  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-601883a5898dc145.eml
847  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-bb914bf6762d393c.eml
819  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-6db60d3c7ee0a630.eml
845  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-89fdb6766cfe1efc.eml
203  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h.eml
816  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-6ec968f7f9eb69ee.eml
832  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-10bd54eb46948cc1.eml
833  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-52314dbe1f5d2ddc.eml
834  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-3baaefb95d6baca7.eml
716  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-b1624d47c28f4416.eml
619  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-3a0c62a4f2cde9e4.eml
712  by_email_id/AAMkADk1ZTMzY2QxLWU0YzctNGVmMC1h-95f08a34f622d5cc.eml
```
Benodigd: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (read-only download volstaat),
of een mailbox-export. De .eml's landen dan in `tests/corpus/sources/` en de bronnen
upgraden automatisch naar het Vision-pad (`_try_pdf_bytes`/run_on_eml).

**Labels observatie-orders:** #619 en #712 draaien mee zonder GT; volledige output
staat in FASE1_BASELINE.md — labelvoorstellen kunnen daaruit worden bevestigd.

## 5. Voorstel Fase 2-zwaartepunten (pas ná jouw akkoord + beslissingen A/B)

1. Contract 2c (één eenheid+aantal-resolver) — inclusief werkende mix-tier-keuze en
   het A/B-notatiebeleid; diff-bewijs dat de ≥10 verspreide paden verdwijnen.
2. Vlag-persistentie: patch-field mag node-vlaggen niet vernietigen; vlaggen krijgen
   UI-anker (mix_uom/europallet-chips + inline regelmarkering).
3. Vlag-volumebeleid (816's 10× terechte-maar-luidruchtige ROL-vlaggen).
4. `adres_rollen` als state-channel + UI "adres per rol".
5. Matrix-fixtures K1/K3/K5/K10/K11/A7/E3/E5/E7 (gelabelde reconstructies).

**STOP.** Er wordt niets gebouwd tot Gate 1-akkoord + beantwoorde beslislijst.
