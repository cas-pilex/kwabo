# UPGRADE_GATE_B — Order-mapping-contract B1–B4: bewijs per onderdeel

**Datum:** 2026-07-02 · branch `upgrade/fase-a-golden-corpus` · vier commits (B1 c3d40ba, B2 8ced8c8, B3 c14ce0b, B4 hierna).

**Beperking deze gate:** halverwege de dag raakten de Anthropic-API-credits op. Verse-extractie-bewijs van vóór dat moment staat vast (B1: #944+#847-run 14:34); daarna draait al het corpus-bewijs deterministisch op de opgeslagen extracties (`upgrade_baseline.py --no-llm`, zelfde recept als `verify_reality.py --no-llm`). De volledige verse corpus-herrun + Fase D-differentieel volgen zodra de credits zijn aangevuld (Cas-actie).

## Corpus-uitslag (deterministisch, 17 orders) — was → is

| meting | rode baseline (vers, 2-7 ochtend) | na B1–B4 (--no-llm) |
|---|---|---|
| stille fouten | **3** | **0 door code veroorzaakt** (3 gemeten, alle drie stored-extractie-artefacten, zie onder) |
| fout-met-vlag | 4 | 7 (waarvan 4 artefacten; 2 = europallet wacht op vul-lijst; 1 = #203 artikel-kandidaat) |
| juist | 12/17 | 10/17 op stored extractie; sleutelorders #847/#944/#954/#941/#816/#832-klant/#833-klant/#834/#716/#717/#718/#685 JUIST |

**Kernwinst:** #847 (de zwaarste stille fout: klant None + ship-to None) is nu volledig **JUIST** — klant 61532 se Huber Straubing (conf 0.9 + CONTROLEER), ship-to 94315 via exacte-postcode.

**De 3 gemeten "stille fouten" zijn artefacten van de opgeslagen (pre-upgrade) extracties, geen codefouten:**
- #819 `verzendwijze` None: de EXW-detectie draait in de extract-node, die in `--no-llm` wordt overgeslagen; de verse run vanochtend gaf EXW ✓. Bij echte herverwerking draait de volledige ingest mét extract.
- #845/#203 `regel1.eenheid`: de oude opgeslagen extractie mist de artikel-match (klant_art "15620 B'keuze PALLET" i.p.v. het verse "A552291" dat via cross-ref exact matcht) — zonder artikel-match kan de eenheid-resolver niet bruggen. De verse run matchte beide; de 15620-brug zelf is per unit-test bewezen (PALLET+PALLET35 → exacte PALLET wint).
- #721/#707 klant-None (fout-met-vlag): stored extractie mist `klantnaam_besteller`; vers gaf 61472/61948 via naam-match.

## B1 — Adresrollen (commit c3d40ba)
- Schema/prompt: `adressen` met rollen besteller/factuur/aflever/eindontvanger; afgeleid `afleveradres` UITSLUITEND uit aflever/eindontvanger; roltwijfel → vlag. Backward-compat met oude promptvorm (live-overridebaar in prod).
- TDD: 5 tests eerst rood → 25 groen. **Vers pijplijn-bewijs:** #944 JUIST met Hengelo 7559 SR uit de aflever-rol (Bunnik apart als besteller); #847 extraheert eindontvanger "Huber GmbH & Co KG, 94315 STRAUBING".

## B2 — Klantresolutie-beslisboom (commit 8ced8c8)
- Boom 1–5 gedocumenteerd als module-docstring in `match_customer.py`, gemapt op code-secties.
- Fix: `_score_kaart_bij_leveradres` scoort de kaart zelf (plaats-in-kaartnaam > kaart-postcode > naam-overlap) bovenop de ship-to-score. Rootcause #847 (prod-geverifieerd, read-only): **twee** kaarten (61532 én 61816) hebben een ship-to 94315 Straubing → tie; de plaats in de kaartnaam breekt hem.
- TDD: nieuwe test eerst rood (code koos 61816/None) → 31/31 match_customer-tests groen. Corpus: #954→50094, #832→61468, #833→61019, #834→61088 onveranderd; tweede-order-bewijs: #834 (TABS) + #203 (Lasaulec) — geen hardcode, de fix is een generieke scorefunctie.

## B3 — Eenheid+aantal-contract (commit c14ce0b)
- a–e-volgorde gedocumenteerd in `utils/eenheid_resolve.py` (de centrale resolver; call-sites pipeline + handmatige correctie delen exact dezelfde regels).
- Vier fixes, elk eerst rood: pallet-brug-voorkeur bij >1 variant (#845: 2 PAL → PALLET i.p.v. 2 STUK ongeconverteerd), `eenheid_origineel` leidend bij herverwerking (#819-rerun: PAL→PALLET/4), stale `verkoop_*`-wipe in Branch A (herverwerking pushte anders de oude STUK-keuze), en compose-warning voor regels zonder artikel-match ("1???"-klasse verdwijnt nooit meer geruisloos).
- Corpus: #819 regel PALLET/4 JUIST, #941 PALLET/2+PALLET/2 JUIST, #716-anker STUK/66 JUIST.

## B4 — Europallet op expliciete databron (dit commit)
- Nieuwe tabel `pallet_plaatsen_basis` (artikel, eenheid → palletplaatsen per eenheid; 0 = bijpak-artikel). Bronprioriteit: mix/Branch-A-pallets > **dit veld** > PAL-besteleenheid 1:1 > NAV-eenheid > **onbekend → vlag**. Het leerbestand (`artikel_pallet_kennis`, per_pallet=24 — bewezen vervuild: #832 33/24→2, #716 66/24→3) en de DOOS-/24-gok zijn UIT de telling; approves blijven het leerbestand wel vullen (datacollectie voor opschoning).
- Afrondingsregel gedocumenteerd: som fracties; < 0,5 → geen europallet; anders naar boven afgerond.
- TDD: 6 nieuwe tests eerst rood; 10 oude leerbestand-/heuristiek-tests expliciet herschreven naar het nieuwe contract (gedragswijziging is de opdracht). Corpus: #832/#833 europallet van STILLE-FOUT → FOUT-met-vlag ("europallet onbekend") — correct wordt het pas met Nico's veldwaarden: zie **PALLET_PLAATSEN_VULLIJST.md** (14 artikel/eenheid-paren uit het corpus + 4 ambigue NAV-families).
- Let op (bewust gevolg): reviewer-onderdrukking via het leerbestand heeft tijdelijk geen effect op de telling; onderdrukken kan exact via `pallet_plaatsen_basis = 0`.

## Suite
Volledige pytest-suite vers groen na alle B-commits (uitslag in de B4-commit-message).

## Open richting Fase C/D
1. **API-credits aanvullen** (Cas) → verse corpus-herrun + Fase D-differentieel/determinisme.
2. **PALLET_PLAATSEN_VULLIJST.md invullen** (Nico/OPS) → #832/#833 europallet groen.
3. Prod-tabel `pallet_plaatsen_basis` wordt bij deploy automatisch aangemaakt (SQLModel-metadata); tot die tijd toont de mirror-run de tabel als ontbrekend (-2) — eerlijk beeld.
4. Originele .eml-nalevering (Gate A-lijst) blijft open.
