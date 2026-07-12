# FASE 1 — Edge-case-matrix (stap 5 / opdracht 1d)

**Status per cel is AFGELEZEN uit run 1** (`FASE1_BASELINE.md` / `fase1_run1_vers.json`:
match_bron, nrf, ops, europallet-onderbouwing), niet aangenomen.
Statussen: **GEDEKT** (≥1 corpus-order raakt de cel aantoonbaar) · **ZWAK** (alleen
tekst-reconstructie of één geval) · **FIXTURE** (gelabelde reconstructie bouwen in
Fase 2/3) · **DATAVRAAG** (hangt op prod-data of klantlabel) · **GEBLOKKEERD-NALEVERING**
(vereist echte .eml) · **SUITE** (gedekt door bestaande API-/regressietests, niet door
het batch-corpus).

## KLANT (11)

| # | Cel | Status | Bewijs uit run 1 / plan |
|---|---|---|---|
| K1 | e-mailalias-tabel (klant_email_aliases) | **FIXTURE + DATAVRAAG** | prod heeft exact 1 alias-rij; geen corpusorder loopt dit pad |
| K2 | directe NAV-e-mailmatch → conf 1.0 zonder vlag | **GEDEKT (4×)** | 716, 717, 685, 712: `bron=email conf=1.0 vlag=False` |
| K3 | domein-alias (K2b) | **FIXTURE + DATAVRAAG** | géén order liep `domein_alias` (717=email, 718=naam_extract); welk domein staat in de ene alias-rij? |
| K4 | naam-fuzzy ≥90, gap≥10 → CONTROLEER | **GEDEKT (6×)** | 941/819/845/203/721/707: `naam_extract 0.8 vlag=True` |
| K4b | naam-match → 1.0-promotie bij unieke leverpostcode (A2) | **GEDEKT (3×)** | 944/816/718: `naam_extract conf=1.0 vlag=False` — alle drie juist |
| K5 | naam-ambigu gap<10 → vlag, geen gok | **FIXTURE** | reconstructie met twee gelijkende prod-kaartnamen (bijv. "GBI Borne" vs "Probin Borne", gt_evidence) |
| K6 | agent-TABS → klant uit afleverpartij | **GEDEKT** | 954: `leveradres_shipto 0.9 vlag=True` → 50094 Jongeneel Woerden |
| K7 | agent multi-vestiging disambiguatie op leveradres | **GEDEKT (3×)** | 832→61468, 833→61019, 834→61088 (zelfde bron, drievoudig generiek-bewijs) |
| K8 | portaal (Zevij) — afzender ≠ klant | **GEDEKT (2×)** | 816 (60245), 707 (afzender support@zevij-necomij.com → GBI 61948) |
| K9 | shared mailbox → juiste partij uit familie | **GEDEKT + Vision-observatie** | 847-state → 61532; familie-.eml (ander order) → 61502+vlag; NB: postcode 94315 gedeeld door 3 klanten |
| K10 | onbekende afzender / geen kaart → kandidaten + vlag | **FIXTURE** | geen corpusgeval; screenen FW-regressie-.eml's in Fase 3-steekproef |
| K11 | demo-klant-poging → MOET vlag (nooit stil) | **FIXTURE (verplicht, opdracht)** | gelabelde fixture met demo-mailadres (10001-10016); safety-net match_customer.py:752 aantonen |

## ADRES (9)

| # | Cel | Status | Bewijs / plan |
|---|---|---|---|
| A1 | alleen besteladres → kaart/ship-to zonder gok | **GEDEKT (3×)** | 718 (postcode-exact), 721 (plaats-in-tekst), 685 (1 kandidaat) |
| A2 | bestel≠aflever → aflever wint | **GEDEKT-ZWAK** | 944 (rollen: besteller Bunnik / aflever Hengelo → 7559 SR); tekst-bron; Vision-versie na nalevering |
| A3 | drop-ship derde partij | **GEDEKT (2×)** | 845 (Polem 8531 PA), 717 (C.F. Kunststoffen 7783 DC) |
| A4 | afleveradres alleen in PDF (Vision-layout) | **GEBLOKKEERD-NALEVERING** | geen bron op schijf Vision-reproduceerbaar (herlabeling); vereist .eml's (10 storage-keys bevestigd) |
| A5 | afhaal → geen afleveradres, ship-to null | **GEDEKT-ZWAK** | 819 (tekst) |
| A6 | buitenlands adres (DE) | **GEDEKT (2×)** | 847-state (94315 Straubing) + familie-.eml via echte Vision (71083) |
| A7 | ≥2 ship-to's ambigu → `ship_to_gekozen`-vlag | **FIXTURE + DATAVRAAG** | run 1 bevat géén ambigu-geval (vlag kwam 0× voor); SELECT nodig of zo'n klant bestaat, anders gelabelde fixture |
| A8 | afleveradres zonder enige ship-to-match → geen stil terugval | **GEDEKT-met-beleidsvraag** | 707: 0 kandidaten → ship_to None, kaartadres, géén vlag — is vlagloos hier gewenst? (Gate 1-bespreekpunt) |
| A9 | handmatige klantwijziging → ship-to re-resolve | **SUITE** | api/preview.py:147-pad; gedekt door F2-tests; batch-corpus kan dit niet raken; Fase 3 herhaalt op API-niveau |

## EENHEID (9)

| # | Cel | Status | Bewijs / plan |
|---|---|---|---|
| E1 | expliciete STUK blijft STUK | **GEDEKT** | 716 STUK×66 geëmit (unitOfMeasureCode-PATCH); óók 832/833. **Kanttekening: GT-conflict A (66 vs 2×PALLET33) bepaalt of deze cel goed gedefinieerd is** |
| E2 | PAL → enige pallet-UoM van het artikel | **GEDEKT** | 819: PALLET (23691: PALLET=20 enige) + quantity 4 |
| E3 | PAL bij meerdere pallet-varianten | **GEDEKT-ZWAK** | 845/203: 15620 heeft PALLET(30) én PALLET35 → gekozen: plain PALLET, geen vlag; consistent met "60 stuks/2 PAL", maar of de keuze aantal-geverifieerd is (70 stuks/2 PAL-geval) is onbewezen → fixture voor het inconsistente geval |
| E4 | stuks = exact hele pallets → omrekening | **GEDEKT (3×)** | 941 (60→PALLET×2), 954 (→PALLET×1), 847 (930→31, 700→35) |
| E5 | mix-staffel M{X}PAL{Y} + mix-code lekt nooit | **GEDEKT-negatief / FUNCTIONEEL ROOD** | 941 (mix=false → plain PALLET ✓ geen lek); maar échte mix-klanten 685/718: n_actief=0, alles gevlagd, geen tier gekozen — staffel-randen M1/M7/M10 → gelabelde fixtures in Fase 2 |
| E6 | ongeldige besteleenheid (ROL) → terugval + vlag | **GEDEKT (3×)** | 721/707: ROL → PALLET×1 mét `orderregels[0].eenheid`-vlag; 203-pos2: manual + vlag + gevlagde skip |
| E7 | DOOS/colli-tussen-eenheid | **FIXTURE** | geen corpusgeval; 23559 heeft DOOS(30) in artikel_eenheden → fixture op echte data |
| E8 | geen eenheid in bron → default-pad | **GEDEKT-ZWAK** | 717/203-pos2 (`eenheid_origineel=None` → default STUK/manual); expliciete fixture wenselijk |
| E9 | composer emiteert gekozen UoM+aantal consistent | **GEDEKT (alle 21)** | compose-capture: per regel POST(itemNumber)+PATCH(unitOfMeasureCode)+PATCH(quantity), single-field |

## EUROPALLET (5)

| # | Cel | Status | Bewijs / plan |
|---|---|---|---|
| P1 | expliciete palletregels → som + onderbouwing | **GEDEKT (4×)** | 721/707 (verkoop_pal→1), 619 (1 + 1 regel eerlijk onbekend), 685 (7 via uom_verkoopeenheid-maten 30/60 + 6 regels onbekend→vlag); GT-labels = DATAVRAAG |
| P2 | STUK == exact 1 pallet | **GEDEKT-GEBLOKKEERD** | 832 (33×238601): None+vlag — juiste K-waarde (1) vereist pallet_plaatsen_basis (0 rijen) |
| P3 | deelpallet → afronding | **GEDEKT-GEBLOKKEERD** | 833 (5+15 STUK): None+vlag — idem |
| P4 | geen databron → vlag, géén 24-heuristiek | **GEDEKT (8×)** | 944/941/716/718/816/712/832/833: `europallet`-vlag; leerbestand (per_pallet=24, vervuild) aantoonbaar genegeerd |
| P5 | groot aantal / meerdere pallets + 3× identiek | **GEDEKT** | 685 (7); determinisme: run 2/3 byte-identiek op alle 21 records |

## OVERIG (5)

| # | Cel | Status | Bewijs / plan |
|---|---|---|---|
| O1 | afhaalorder → EXW (NL/DE) + negatief | **GEDEKT** | 819: shipmentMethodCode-PATCH aanwezig; alle 20 andere records: geen verzendwijze-op (negatief bewijs) |
| O2 | toeslag-/ongematchte regel verdwijnt nooit stil | **GEDEKT (2×)** | 203-pos2 (skip + warning + vlag), 717 (0 matches → compose_error, geen halve order) |
| O3 | artikel-prijs-signaal (23853→238531) | **GEBLOKKEERD-EERLIJK** | 816-pos9 aanwezig in corpus; prijsafspraken=0 in prod → signaal kán niet vuren; F6/7002 = GEBLOKKEERD |
| O4 | compose-status: ok / partieel / error zichtbaar | **GEDEKT** | capture nieuw in deze harness: 717=error, 203=ok-met-gevlagd-regelverlies, rest=ok |
| O5 | forwarded / non-order / multi-order-PDF / lege bijlage / ':' in naam | **GEDEKT-ZWAK + SUITE** | non-order: WD-familie-.eml → is_order=false via echte Vision ✓; forwarded/multi-PDF/colon: bestaande regressie-.eml's + suite-tests; Fase 3-steekproef dekt breder |

## Samenvatting

- **Gedekt uit run 1:** 27 van 39 cellen (waarvan 6 zwak/geblokkeerd-op-data).
- **Fixtures bouwen (Fase 2, gelabelde reconstructies op echte prod-data):**
  K1, K3, K5, K10, K11 (verplicht), A7, E3-inconsistent-geval, E5-staffelranden (M1/M7/M10), E7.
- **Geblokkeerd op nalevering (.eml):** A4 volledig; A2/A5 Vision-variant.
- **Geblokkeerd op data/labels:** P2/P3 (pallet_plaatsen_basis), O3 (7002), P1-GT-labels.
- **Beleidsvragen bij Gate 1:** A8 (0-kandidaten vlagloos?), E1/E4-definitie via
  GT-conflict A/B, E3-aantal-consistentiecheck.
