# FASE 1 — Judge-audit (stap 2a): het meetinstrument zelf geverifieerd

**Datum:** 10-07-2026 · **Code-anker:** main `cd190a6` (schoon) · **Principe:** rood-vóór-groen
geldt ook voor de judge — elk gedicht gat is eerst als falende test aangetoond
(`backend/tests/test_fase1_judge.py`, 16 tests, groen).

## Waarom deze audit

De Fase A-judge (`backend/scripts/upgrade_baseline.py:221-294`) bepaalde wat als
JUIST / FOUT-met-vlag / STILLE-FOUT telde. Een judge die vlaggen mist die de pipeline
wél zet, produceert valse stille fouten (ruis); een judge die vlaggen meetelt die de
reviewer nooit ziet, verbergt echte stille fouten. Beide richtingen zijn gecontroleerd.
De geauditeerde judge staat in `backend/scripts/fase1_judge.py` (pure module, gestart
als letterlijke kopie van de Fase A-judge; wijzigingen uitsluitend na een rode test).

## 1. Volledig vlag-vocabulaire (schrijvers in backend/src/kwabo/)

Er zijn TWEE bronnen van `needs_review_fields`-paden die NIET hetzelfde vocabulaire
produceren:

**(A) Node-schrijvers** (ingest; wat de baseline-judge leest):

| Key-patroon | Niveau | Schrijver | Conditie |
|---|---|---|---|
| `taal`, `bestelnummer_klant`, `orderdatum`, `afleverinstructies` | order | extract.py:111 | LLM-veldmeta needs_review |
| `afleveradres` | order | extract.py:148/160/162 | rol-twijfel LLM / veldmeta |
| `orderregels[{i}].artikelnummer_kwabo` / `.hoeveelheid` / `.eenheid` | regel, 0-based | extract.py:188 | LLM-veldmeta needs_review |
| `klant_match` | order | match_customer.py:789 | geen match / conf<1.0 / demo-klant (:785) |
| `orderregels[{i}].artikelnummer_kwabo_matched` | regel, 0-based | match_articles.py:330-332; validate_prices.py:227-229 | niet gematcht / conf<0.85 / prijs-verdacht |
| `orderregels[{idx}].eenheid` | regel, 0-based | match_articles.py:338-340 | resolve_line_uom gaf eenheid-vlag |
| `orderregels[{i}].prijs_per_eenheid` | regel, 0-based | validate_prices.py:233-235 | prijs invalide / ontbrekend-met-afspraak |
| `ship_to_gekozen` | order | select_ship_to.py:246 | ≥2 kandidaten, ambigu |
| `verkoop_eenheid:{pos}` | regel, **1-based** | apply_mixprijzen.py:293-295, 387-389 | Branch-A-warning |
| `mix_uom:{pos}` | regel, **1-based** | apply_mixprijzen.py:366-368 | mix ambigu / geen tier |
| `europallet` | order | compute_europallet.py:66-67 | regel(s) zonder pallet-databron |

Gefilterd (nooit vlag): `gewenste_leverdatum`, `opmerkingen`, `klantnaam_besteller`
(extract.py:213-216). `verzendwijze`: geen enkele schrijver (meta needs_review=False,
extract.py:277).

**(B) Meta-herleiding** `api/preview.py:108-120` (`_all_needs_review_paths`), gebruikt
door `GET /needs-review` én — cruciaal — door `PATCH /patch-field`, die
`needs_review_fields` ermee OVERSCHRIJFT (preview.py:401-402).

## 2. Judge-gaten (gevonden → gedicht, elk eerst ROOD)

| # | Gat in Fase A-judge | Bewijs | Fix in fase1_judge.py | Test |
|---|---|---|---|---|
| 1 | `mix_uom:{pos}` niet herkend als eenheid-vlag → gevlagde mix-fout telde als STILLE-FOUT | upgrade_baseline.py:274 vs apply_mixprijzen.py:366 | eenheid-vlag = verkoop_eenheid:{pos} ∨ mix_uom:{pos} ∨ orderregels[i].eenheid | test_mix_uom_vlag_telt_als_eenheid_vlag |
| 2 | `regel.aantal` altijd gevlagd=False, ook onder eenheid-vlag; bestaande `orderregels[i].hoeveelheid`-vlag was verweesd | upgrade_baseline.py:283 | aantal deelt de eenheid-vlag van dezelfde positie (eenheid+aantal = één beslissing, resolve_line_uom) + herkent hoeveelheid-vlag | test_aantal_fout_onder_eenheidsvlag_is_review |
| 3 | `afleveradres_postcode` keek alleen naar `ship_to_gekozen`; extract-vlaggen `afleveradres`/`adressen` genegeerd | upgrade_baseline.py:247 vs extract.py:148/160/162 | adres-vlag = ship_to_gekozen ∨ afleveradres ∨ adressen | test_afleveradres_vlag_uit_extract_telt_voor_postcode |
| 4 | compose-status/NAV-ops/regelverlies niet vastgelegd noch beoordeeld ('1???'-klasse onzichtbaar voor de meting) | summarize (upgrade_baseline.py:184-218) | summarize legt vast: compose-status (ok/leeg/error), ops (op/path/body_keys/optional), regels_zonder_match, regelverlies_gevlagd | test_summarize_bevat_compose_status_en_regelverlies e.a. |
| 5 | adres-per-rol niet vastgelegd; `adres_rollen` is bovendien géén OrderState-channel en wordt door LangGraph na extract GEDROPT | state.py (OrderState: key ontbreekt); extract.py:163 | summarize leest de rollen uit `_meta['adressen'].value` (enige plek waar ze overleven) | test_summarize_adres_rollen_uit_meta_fallback |

| 6 | **Eigen harnas-fout, gevonden in run 1a**: de `eml_ondersteunend`-.eml's van #847 werden tegen de GT van order 847 gejudged, maar het zijn FAMILIE-orders (bestelnr 4401054959 met leveradres 71083, resp. een non-order met is_order=false volgens test_data/expected) → 5 valse "stille fouten" | `_upgrade/fase1/fase1_run1a_vers_gtpairing_bug.json` (bewaard) vs test_data/expected/*Dietrich*.json | eml_ondersteunend draait als Vision-observatie ZONDER GT-koppeling (fase1_baseline.py); manifest-847 geannoteerd + 847 alsnog op de eml-naleveringslijst | gecorrigeerde run 1 = replay van dezelfde verse extracties (cache 41→41) |

Bewust ONGEWIJZIGD (gedocumenteerde strengheid):
- `verzendwijze` blijft vlagloos-streng: er bestaat geen verzendwijze-vlag in de
  pipeline, dus elke fout is per definitie stil (test_verzendwijze_fout_blijft_altijd_stil).
- De strenge kern (confident-fout zonder vlag = STILLE-FOUT) zat al goed en is met
  test_confident_foute_klant_zonder_vlag_is_stille_fout vastgeklikt.
- Judge-patronen zonder producerende schrijver (dode detectie): geen gevonden.

## 3. UI-zichtbaarheid van vlaggen (voorwaarde voor "vlag telt")

De strenge definitie eist een vlag die de reviewer ZIET. Feiten:

- Elke nrf-key wordt een chip in de takenlijst-banner (needs-review-banner.tsx:83-97)
  → alle judge-getelde vlaggen zijn in beginsel zichtbaar. MAAR:
  - `mix_uom:{pos}`, `europallet`, `adressen`, `taal` renderen als RAUWE padstring
    zonder klik-sprong (pretty(), needs-review-banner.tsx:28-36);
  - `verkoop_eenheid:{pos}` heeft een net label maar geen scroll-anchor;
  - inline regelmarkering (rij rood / veld-ring) hangt aan `regelsMeta`, NIET aan
    needs_review_fields → `verkoop_eenheid:{pos}`/`mix_uom:{pos}` geven géén inline
    markering (order-lines-table.tsx:126/189, field-input.tsx:45-48);
  - mix-badges renderen alleen bij `mixprijzen_actief=true`; zijn álle mix-regels
    ambigu (n_actief=0, apply_mixprijzen.py:392) dan is de `mix_uom`-vlag alleen een
    rauwe chip.
- **Product-bevinding (Fase 2-kandidaat, hier alleen gediagnosticeerd):**
  `PATCH /patch-field` herschrijft `needs_review_fields` uit `_meta`
  (preview.py:401-402). `ship_to_gekozen` (node-pad), `europallet`,
  `verkoop_eenheid:{pos}` en `mix_uom:{pos}` bestaan NIET in `_meta` met
  needs_review → deze vlaggen VERDWIJNEN uit banner én approve-gate
  (order-review.tsx:169/233) zodra de reviewer één willekeurig ander veld bewerkt —
  ongeacht of ze zijn opgelost. Dit is een vlag-vernietigingsmechanisme in prod.

**Judge-consequentie:** de baseline draait pipeline-only (geen patches), dus voor de
meting tellen node-vlaggen als zichtbaar (chip bestaat). De verdwijn-bug en de rauwe
chips staan als aparte diagnose-items in FASE1_DIAGNOSE.md.

## 4. Effect van de judge-wijzigingen op de vergelijking met 2-7

De 1c-vergelijkingstabel (pre-fix 2-7 → nu) rapporteert BEIDE judge-oordelen (oud én
geauditeerd) per order, zodat "fix hield stand" nooit een artefact van de
judge-wijziging is. Richting van elke wijziging: gaten 1-3 maken de judge MILDER
(minder valse stille fouten), nooit strenger; gat 4/5 zijn pure vastlegging. De
strenge kern is onveranderd.

## 5. Zelftest

`backend/tests/test_fase1_judge.py` — 16 tests, elk gat eerst rood aangetoond op de
letterlijke Fase A-kopie, daarna groen na de fix. Draait mee in de suite (geen
kwabo-imports, geen DB, geen env-bijwerkingen).
