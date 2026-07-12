# GATE 2 — bewijs Fase 2 (structurele fixes op de her-diagnose, 10-07-2026)

**Branch:** `herdiagnose/fase2-contract` (main auto-deployt — er is bewust NIET naar main
gemerged). **Suite vers: 777 passed** (was 728 bij Gate 1; +49 nieuwe tests, alle
test-first waar het nieuw gedrag betrof). **Corpus-herrun (echte data, replay):
0 stille fouten · 3 fout-met-vlag (data-gated) · 14 juist · 0 crashes** — identiek
oordeel-profiel aan de Fase 1-baseline, plus de bedoelde verbeteringen hieronder.

## Wat er gebouwd is (elk onderdeel: rood aangetoond → fix → groen + generiek bewijs)

### F2.1 — Vlag-persistentie (de meta-oorzaak-fix)
`PATCH /patch-field` vernietigde de meta-loze node-vlaggen (`ship_to_gekozen`,
`europallet`, `verkoop_eenheid:{pos}`, `mix_uom:{pos}`) bij élke veldbewerking —
uit banner én approve-gate (preview.py:401-402). Nu: `_herleid_needs_review` = unie
van meta-herleiding + meta-loze node-vlaggen; alleen de bewerking die een vlag
adresseert lost hem op; meta blijft de baas waar meta bestaat (opgeloste velden
herflaggen nooit).
**Bewijs:** `tests/test_patch_field_vlag_persistentie.py` — 6 cases eerst ROOD
(vlaggen weg), daarna 14/14 groen over 4 vlagfamilies × overleven/gericht-oplossen/
meta-wint, incl. klant-wissel-reresolve en bevestig-zelfde-klant. Alle 29 bestaande
patch-field-tests blijven groen.

### F2.2 — Mix-tier-keuze werkt (ambiguïteit is een regel-eigenschap)
Eén onresolveerbare regel zette de order-brede `ambiguous` en vergiftigde álle
regels (Veris #685: 8 regels → 0 keuzes, 8 vlaggen). Nu: per-regel-ambiguïteit;
staffelbasis telt de resolveerbare regels; versmalde basis wordt EXPLICIET gemeld
(warning met uitgesloten posities).
**Bewijs:** `tests/test_apply_mixprijzen_per_regel.py` — 3 cases eerst ROOD, daarna
9/9 groen incl. de E5-staffelranden (totaal 1→M1, 8→M7, 12→M10, onder-laagste→klem,
één-tier). **Echte data:** #685-replay: 4 tiers gekozen (M5PAL30×5, M5PAL60×2,
M8PAL45×1, M33PAL33×1) + 4 eerlijk gevlagd + warning "staffelbasis M9 … regels
1, 4, 5, 7 vallen erbuiten"; #941 (negatief: geen mix-klant) onveranderd plain
PALLET×2; #718 tweede mix-klant blijft correct gevlagd.

### F2.3 — Eenheid+aantal-contract in ÉÉN module (opdracht 2c)
Alle beslislogica (resolve/pallet-brug/Branch-A/verkoop-keuze/plain-pallet-
equivalent/base-omrekening/mix-tier-parsing) geconsolideerd in
`kwabo/utils/eenheid_resolve.py`; `apply_mixprijzen.py` houdt alleen de
ORDER-context (staffelbasis) en kromp ~230 regels; `api/preview.py` importeert
niet langer uit een graph-node. NIEUW: `regel["eenheid_bron"]` — herkomst van
élke eenheid-keuze in gewone taal ("pallet-brug: …", "verkoopeenheid-omrekening:
60 STUK = 1 × PALLET (60 per PALLET)", "mix-staffel M7PAL30: … tier M7 bij
staffelbasis M9").
**Bewijs:** `tests/test_fase2_eenheid_contract.py` (13 tests; bron-gedrag eerst
ROOD) + consolidatie-borging als test (oude paden bestaan niet meer in de node;
api importeert het contract) + git-diff (-230 regels beslislogica uit de node).
Alle 66 bestaande eenheid/mix/Branch-A/compose-tests groen. **Echte data:**
volledige corpus-replay — buiten #685 (bedoelde F2.2-doorwerking: 4 extra
UoM-PATCHes, europallet 7→9 met mix-bron-onderbouwing) NUL gedragsverschillen.

### F2.4 — adres_rollen is nu een OrderState-channel
LangGraph dropte de B1-rollen-dict na extract (geen channel) → onzichtbaar voor
persistentie/UI. Nu gedeclareerd (state.py) en automatisch gepersisteerd.
**Bewijs:** `tests/test_state_adres_rollen_channel.py` — 3 tests eerst ROOD
(letterlijk het drop-gedrag), daarna groen.

### F2.5 — UX: elke vlag heeft een label, een anker en regel-context
Banner-chips: nette labels voor `mix_uom:{pos}`/`europallet`/`adressen`/`taal` +
anker-mapping (positie-vlaggen → het eenheid-veld van hun regel; europallet/
afleveradres → nieuwe blok-id's). Regels met een eenheid/mix-vlag krijgen een
amber rij-markering + "controleer"-badge, óók wanneer `mixprijzen_actief=false`
(het gat waar de mix-vlag onzichtbaar was). `eenheid_bron` is per regel zichtbaar
(tooltip op de eenheid-cel en de badge). Compose-reden in gewone taal bestond al
(NavOperationsPreview: no_matched_articles/compose_error + reason) — geverifieerd,
niet herbouwd; idem klaar-badge, klant-matchreden (C1) en KlantPicker (Fase C).
**Bewijs:** `npx tsc --noEmit` schoon. EERLIJK: een live Playwright-run vergt
draaiende servers en volgt in Fase 3/on-site; de wijzigingen zijn klein en
component-lokaal.

### F2.6 — Europallet-K-targets mechanisch bewezen (waarde blijft GEBLOKKEERD)
`tests/test_fase2_europallet_p2_p3.py`: met vullijst-fixturedata levert het
mechanisme exact de K-targets (#832: 33×(1/33)=1; #833: (5+15)×(1/33)=0,61→1)
incl. de afrondgrens (0,45→0; 0,50→1) en P5 (2,6→3). Prod-tabel blijft leeg →
runtime blijft eerlijk "onbekend→vlag"; deblokkering = vullijst (Nico/OPS).

### F2.7 — Matrix-fixtures (alle 7 cellen groen, 0 xfail)
`tests/test_fase2_matrix_fixtures.py`: K11 (demo-klant → geforceerde vlag +
waarschuwing, VERPLICHT), K5 (naam-gap 2,5 < 10 → geen autopick, kandidaten +
vlag), K1 (e-mailalias-pad), K3 (domein-alias 0.9 + vlag), K10 (onbekende
afzender → nooit autopick), A7 (2 gelijkwaardige ship-to's → None + vlag), E7
(DOOS geldig zonder vlag; COLLI → terugval + vlag).
Observatie (geen bug): een alias-match is in de provenance niet te
onderscheiden van een direct kaart-e-mailveld (bron 'email', conf 1.0) —
traceerbaarheidswens, genoteerd.

## Besluitenlog (FASE2_BESLUITEN.md) — ter bevestiging
- **A (#716):** 2×PALLET33 = NAV-data-actie (verkoop_eenheid 238601 → PALLET33,
  Kwabo's eigen voorkeursroute); mechanisme bewezen met fixture-data
  (test_branch_a_besluit_A_66_stuk_wordt_2_pallet33); GT blijft STUK×66 tot de
  NAV-actie; extra karakterisering: op de huidige NAV-UoM's ('EXW PAL33' als
  tweede hele kandidaat) blijft 66 terecht STUK.
- **B (#847):** PALLET 31/35 blijft (exact + masterdata-uniek); "geen valse
  omrekening" generiek geborgd (816 blijft STUK, bewezen).
- **C/F/G:** 4814 RR · 15620-maat 30 · vestigingsnummers — masterdata-gestaafd.
- **D/E/H/I:** GEBLOKKEERD zoals gerapporteerd (vullijst / 7002 / regel-GT-labels).

## Invarianten-check
Single-field PATCH ongewijzigd afgedwongen (`nav_operations.py:_assert_op_invariants`,
compose-capture toont uitsluitend 1-veld-PATCHes); composer kent geen prijsveld
(alleen NAV prijst); pgbouncer niet aangeraakt; LIST_PAGE_SIZE niet aangeraakt;
prod uitsluitend read-only benaderd; geen commit op main.

## Rest naar Fase 3
Differentieel (pre-fix cd190a6 ↔ branch), brede steekproef ≥25 orders, 8×3
determinisme, suite + --regression, Playwright/on-site-UX-bewijs, FABLE5_EINDRAPPORT.md.
