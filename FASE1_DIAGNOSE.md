# FASE 1 — Laag-diagnose (stap 4 / opdracht 1c)

**Meetbasis:** `FASE1_BASELINE.md` run 1 (vers, main `cd190a6`, geauditeerde judge,
mirror-prod-masterdata) + replays run 2/3 (byte-identiek) + tweede verse trekking run 4
(alleen cosmetische extract-variantie, geen oordeel-kanteling).
**Totaal run 1: 0 stille fouten · 3 fout-met-vlag · 14 juist · 4 observaties · 0 crashes.**
Dit oordeel geldt onder de OUDE én de geauditeerde judge (de drie niet-juiste velden
dragen vlaggen die beide judges herkennen: `klant_match`, `europallet`,
`artikelnummer_kwabo_matched`).

**Epistemische grens (eerlijkheid):** dit is het TEKST-pad. Geen enkele corpus-bron op
schijf is Vision-reproduceerbaar (PDF-bytes lossy in email_body — zie
`manifest.json:_fase1_herlabeling_10_7`). Vision is alleen end-to-end geraakt via twee
familie-.eml's (observatie, correcte classificatie incl. non-order-afwijzing). Volledig
Vision-bewijs voor de feedback-orders vereist eml-nalevering (alle 10 storage-keys
bevestigd in prod, incl. #847 `…-bb914bf6762d393c.eml`).

---

## Standgehouden-tabel: pre-fix (2-7, `UPGRADE_BASELINE.md`) → nu (run 1)

| Toetssteen | Pre-fix (d45baa3, oude judge) | Nu (cd190a6, geauditeerde judge) | Verdict |
|---|---|---|---|
| #847 ship-to | **STILLE-FOUT** (94315 → None) | JUIST (94315; klant 61532 via leveradres_shipto 0.9 + vlag) | **standgehouden** (B2-kaartscore + select_ship_to) |
| #832 europallet | **STILLE-FOUT** (2 i.p.v. 1, via leerbestand-24-gok) | FOUT-met-vlag (None + `europallet`-vlag; geen gok) | **fix hield stand** (gok weg); wáárde geblokkeerd op OPS-data |
| #833 europallet | **STILLE-FOUT** (None zonder vlag) | FOUT-met-vlag (None + vlag) | idem |
| #944 besteladres vs afleveradres | (pre-fix casus: Bunnik gekozen) | JUIST: rollen-extractie kiest Hengelo 7559 SR; ship-to exact | **standgehouden** (B1-rollen, tekst-pad) |
| #954/#832/#833/#834 agent → afleverpartij | 61793-Heerenveen-klasse | 50094/61468/61019/61088 via `leveradres_shipto` 0.9 + CONTROLEER | **standgehouden** (B2); nummers = GT-vraag G |
| #941 mix-code als verkoopeenheid | M1PAL30-lek | plain PALLET×2 (klant mix=false) | **standgehouden** (`_plain_pallet_equiv`-guard) |
| #819 PAL → STUK-terugval | STUK 4-klasse | PALLET 4 (23691 PALLET=20) + verzendwijze EXW | **standgehouden** (F3/F5) |
| #716 66 STUK | — | STUK×66 expliciet geëmit | juist per HUIDIGE GT; **GT-conflict A open** (opdracht wil 2×PALLET33) |
| #203 regel 2 (224681, ROL) | — | ongematcht + vlag + skip-warning (regelverlies gevlagd) | fail-loud; **nooit gefixt** qua match (data-gat) |

Geen enkele geteste eerdere fix is **geregressed**.

---

## Categorie 1 — KLANT (agent/alias vs afleverpartij)

**Meting:** alle 5 agent-/portaal-/shared-mailbox-orders (954, 832, 833, 834, 847-state)
resolven naar de afleverpartij met bron `leveradres_shipto`, conf 0.9, mét vlag. Geen
enkele 100%-zonder-vlag-fout meer.
**Laag:** `match_customer.py:504-514` (shared-mailbox eerst) → `:346`
(`_disambiguate_shared_mailbox`) → `:242` (`_correct_vestiging_op_leveradres`, over élke
match) → `:785-789` (vlagregel). Portaal: `PORTAL_DOMAINS:70`. A2-promotie naar 1.0 bij
unieke leverpostcode: `:654-671` (zichtbaar bij 944/816/718: `naam_extract` conf 1.0
zonder vlag — en alle drie juist).
**Restrisico's:**
- `seed_demo_data=True` (config.py:75): demo-klanten 10001-10016 dragen echte
  mailadressen; safety-net (`:752-762`) forceert CONTROLEER maar het pad bestaat —
  matrix-cel K11 test dit expliciet.
- Postcode `94315` gedeeld door 3 klanten (61532/61595/61816, gt_evidence) — de
  DE-disambiguatie leunt op naam+plaats; cel K9 dekt dit maar een tweede DE-shared-order
  is gewenst.
- Structureel: élke agent-order blijft permanent 0.9 + CONTROLEER → juiste uitkomst maar
  vaste review-last (zie meta-diagnose).

## Categorie 2 — VERZENDADRES

**Meting:** 944 → Hengelo 7559 SR (rollen: besteller Bunnik / aflever Hengelo, beide in
`_meta.adressen` vastgelegd); 847-state → 94315; 845 → drop-ship Polem 8531 PA; 819 →
afhaal, ship-to null; ambigu-pad: 707 → 0 kandidaten, geen ship-to, geen gok.
**Laag:** `extract_v2.txt:28-36` + `extract.py:124-163` (rollen; eindontvanger > aflever;
besteller nooit) → `select_ship_to.py:_decide:160` (postcode-prio :208; ambigu →
None+review :240-248) → re-resolve bij klantwijziging `api/preview.py:147`.
**Restrisico's:**
- **`adres_rollen` is géén OrderState-channel** (state.py) → LangGraph dropt het na
  extract; rollen overleven alleen in `_meta['adressen'].value`. Persistentie/UI kunnen
  "adres per rol" dus niet tonen; herverwerking uit opgeslagen states verliest de
  rollen-provenance. Fase 2-kandidaat (channel + UI).
- Vision-extractie van adressen (bijv. "Vestiging 462" uit PDF-layout) is op dit corpus
  niet reproduceerbaar bewezen — eml-nalevering vereist.
- A9 (re-resolve na handmatige klantwijziging) is API-pad, niet batch-toetsbaar — aparte
  test in Fase 2/3-matrix.

## Categorie 3 — EENHEID + AANTAL

**Meting:** geen ongeldige code richting NAV in run 1: ROL-bestellingen brugden naar
PALLET (721/707 exact_klantnr → PALLET×1; 816 → PALLET×n of STUK×n via klantenkaart) of
werden gevlagd + veilig overgeslagen (203-pos2 manual, met warning én
`artikelnummer_kwabo_matched`-vlag). Geen "1???": composer skipt uitsluitend mét warning
(compose_order.py:74-86) of weigert compleet (717: `compose_error` — zie hieronder).
**Laag (nog steeds ≥10 plekken; de opdracht-2c-consolidatie blijft nodig):**
`eenheid_mapping.py` · `extract.py:194` · `eenheid_resolve.py:53` ·
`match_articles.py:233-264` · `apply_mixprijzen.py` (`_branch_a:192`,
`_verkoop_keuze:114`, `_plain_pallet_equiv:156`, staffels :311-375) · `mixcode.py` ·
`pallet_logic.py` · `navision_steps.py:102/133` · `preview.py:366-399` ·
`validate_prices.py:124-140`.
**Restrisico's:**
- **Mix-laag levert bij echte mix-klanten niets dan vlaggen**: 685 (Veris, mix=true):
  8 regels → n_actief=0, 8× `mix_uom:{pos}`-vlag + 8× eenheid-vlag, verkoop-UoM=None;
  718 idem (1 regel). Uitkomst is veilig (niets fout naar NAV; emit valt terug op
  geldige `eenheid`) maar functioneel kiest de mix-staffel nooit — combineer met de
  UI-bevinding dat mix-badges alleen renderen bij `mixprijzen_actief=true` en de
  `mix_uom`-chip rauw is: de reviewer krijgt een vlag-muur zonder handvat. Kern-item
  voor 2c.
- 816: **10/10 regels eenheid-gevlagd** (ROL besteld) terwijl de gekozen UoM's juist
  zijn → valse review-last.
- `regelverlies` bij 0 matches: 717 → `compose_error`
  ("Cannot compose … all unmatched", navision_steps.py:308) — fail-loud en gevlagd,
  maar het order-record oogt in de overzichtstabel "JUIST" omdat de GT-regels leeg zijn;
  push is onmogelijk. UX/status-communicatie = Fase 2.
- GT-conflicten A (#716 STUK-66 vs 2×PALLET33) en B (#847 PALLET-31/35 vs
  STUK-blijft-STUK) bepalen het 2c-beleid "stuks-die-exact-hele-pallets-zijn" —
  beslissing nodig bij Gate 1 vóór er iets gebouwd wordt.

## Categorie 4 — EUROPALLET

**Meting:** geen enkele gok meer, en de onderbouwing is per regel expliciet
(bron + palletmaat + telling). 721/707: 1 hele pallet via Branch-A (`verkoop_pal`) → 1;
619: 1 (+1 regel eerlijk "onbekend" → vlag); 685: **deels** — 2 regels tellen via
`uom_verkoopeenheid` (maten 30 en 60) tot 7 europallets, 6 regels staan in de
`onbekend`-lijst → vlag. Waar géén databron bestaat (STUK-regels): `europallet`-vlag,
waarde None (o.a. 944, 941, 716, 718, 832, 833, 816, 712).
**Laag:** `pallet_logic.py:122` (`_line_pallets`, bronprioriteit) + `:199`
(`europallet_breakdown`) + `compute_europallet.py:60-78` (vlag).
**Status van de drie databronnen (gt_evidence, read-only 10-7):**
`pallet_plaatsen_basis` = **0 rijen** (tabel bestaat sinds PR #6-deploy) ·
`artikelkaarten.verkoop_eenheid` = STUK voor de corpus-artikelen (geen palletmaat) ·
`artikel_pallet_kennis` = vervuild (per_pallet=24, 'dashboard') en terecht genegeerd.
**Conclusie: GEBLOKKEERD-VEILIG-AFGEHANDELD.** De K-targets (#832=1, #833=1) zijn pas
haalbaar als de vullijst (PALLET_PLAATSEN_VULLIJST.md; NAV-voorkeursroute 07f3fe5) is
ingevuld. Tot die tijd is "onbekend → vlag" de enige eerlijke uitkomst; elke andere
uitkomst zou een nieuwe gok zijn.

## Categorie 5 — ARTIKEL

**Meting:** 40/41 corpus-regels gematcht (methoden: exact, exact_klantnr, klantenkaart);
1 ongematcht (203-pos2) → vlag + veilige skip; 717 (18390-casus) → ongematcht + vlag +
compose-weigering. Fuzzy-junk: niet waargenomen; fuzzy capt op 0.84 < vlagdrempel 0.85
(`match_articles.py:143/306`), dus fuzzy is per constructie nooit stil.
**Laag:** `match_articles.py:_match_single` (cascade), `validate_prices.py:211-229`
(prijs-signaal).
**Restrisico's:** kruisverwijzing-sparsity bevestigd (klant-specifieke mappings voor
941/83x bestaan niet in prod; matching leunt op exact-Kwabo-nr/klantenkaart) →
automatch-plafond is een DATA-kwestie, geen bug. F6-prijs-signaal (816-pos9) is
data-gated (prijsafspraken=0) — GEBLOKKEERD op 7002-data, alleen vlag-gedrag toetsbaar.

## Categorie 6 — HARNESS-KLOOF (meta-oorzaak; nieuw bewijs uit deze fase)

1. **Fase A/D raakte het Vision-pad nooit**: alle 17 orders draaiden als tekst
   (extractie_mode in `_upgrade/d1_nieuw_vers.json`); de "state_met_pdf"-labels waren
   onjuist (PDF lossy in email_body; `_try_pdf_bytes` keek in bijlagen). De eerdere
   "differentieel 3→0"-claim geldt dus alleen voor het tekst-pad.
2. **Eigen run 1a-fout**: familie-.eml's tegen 847-GT gejudged → 5 valse stille fouten;
   gevonden via test_data/expected, gefixt (observatie zonder GT), origineel bewaard
   (`fase1_run1a_vers_gtpairing_bug.json`). Les: GT-koppeling is zelf een foutbron.
3. **Judge-gaten 1-6**: zie FASE1_JUDGE_AUDIT.md (mix_uom/aantal/afleveradres/compose/
   rollen/eml-pairing) — elk eerst rood aangetoond.
4. **Artefact-hygiëne**: `_upgrade/baseline.json` (pre-fix meetdata) was overschreven
   door een 1-order-run; de gecommitte MD is de enige volledige pre-fix-bron.

## META-DIAGNOSE — waarom "vier rondes groen" en toch klant-rood (hypothese met bewijs)

Twee mechanismen die samen verklaren dat gevlagde waarheid als stille fout bij de klant
aankomt:

1. **Vlag-lawine → reviewer-blindheid.** Run 1: **20/21 records dragen ≥1 vlag**;
   uitschieters 816 (11 vlaggen, allemaal terecht qua uitkomst) en 685 (17). Als álles
   CONTROLEER is, is niets het.
2. **Vlag-vernietiging bij bewerking (prod-mechanisme).** `PATCH /patch-field`
   herschrijft `needs_review_fields` uit `_meta` (preview.py:401-402); de vlaggen
   `ship_to_gekozen` (node-pad), `europallet`, `verkoop_eenheid:{pos}` en
   `mix_uom:{pos}` bestaan dáár niet → één willekeurige veldbewerking wist ze uit
   banner én approve-gate. Een reviewer die íéts aanpast, ziet de europallet-/eenheid-
   vlag daarna nooit meer — de order oogt "klaar om te pushen".

Beide zijn Fase 2-kernpunten (contract 2b/2c/2d + UX): vlaggen persistent maken over
patches heen, en de vlag-volumeknop (terechte-maar-luidruchtige vlaggen zoals 816's
10× ROL-eenheid) beleid geven.
