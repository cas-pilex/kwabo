# UPGRADE_DIAGNOSE — welke architectuurlaag veroorzaakt welke foutcategorie (Fase A3)

Basis: rode baseline van 2026-07-02 (`UPGRADE_BASELINE.md`, 17 orders vers door de echte pijplijn: 3 stille fouten, 4 fout-met-vlag, 12 juist). Paden onder `backend/src/kwabo/`.

## 1. Verkeerd klantnr bij agents/portalen → laag: klantresolutie + ontbrekende adresrollen

- De cascade (`graph/nodes/match_customer.py:419`) heeft de agent-gevallen deels leren kennen (shared-mailbox-disambiguatie `:295` met drempel `SHARED_MAILBOX_MIN_KLANTEN=3` `:32`), maar disambigueert uitsluitend op **ship-to-postcodes** (`_score_ship_to`) van de kandidaat-kaarten. **Baseline-bewijs #847**: afzender werkzeuge-dietrich.de staat op 5 se-Huber-kaarten; het afleveradres "se Huber GmbH & Co KG, 94315 STRAUBING" wordt geëxtraheerd maar de naam+plaats van de afleverpartij wordt niet tegen de kándidaatkaarten zelf gescoord → klant=None (kandidaten+vlag) terwijl "se Huber **Straubing**" letterlijk in het adres staat.
- TABS-orders (#954/#832/#833/#834) resolven nu wél naar de juiste vestiging (bron `leveradres_shipto`, conf 0.9) — maar áltijd met een `klant_match`-vlag: het beleid B2 ("agent → klant uit afleverpartij") bestaat de facto maar is nergens één gedocumenteerde beslisboom; elk geval is een aparte patch (K2b `:504`, vestiging-correctie `:217/:582`, postcode-bevestiging `:600-617`).
- Portalen: alleen een hardcoded set `PORTAL_DOMAINS={"zevij-necomij.com","orders.nl"}` (`:45`); het patroon "afzender ≠ afleverpartij" wordt niet generiek herkend.

## 2. Besteladres i.p.v. afleveradres → laag: extractieschema zonder adresrollen

- Het schema kent **één** adresveld: `afleveradres` (`prompts/extract_v2.txt:60`), en de prompt zegt expliciet "Afleveradres ALLEEN als drop-ship/afwijkend van factuuradres; anders null" (`:28`). Besteller-/factuuradres wordt **nooit** gestructureerd vastgelegd; de bestellende partij is alleen een naamveld `klantnaam_besteller` (`:29-33`, flat-projectie `graph/nodes/extract.py:114-123`).
- Gevolg: of het ene veld het áfleveradres of het besteladres bevat, hangt af van wat de LLM kiest. #944 gaat nu goed doordat `select_ship_to` een exacte-postcode-prioriteit heeft (`graph/nodes/select_ship_to.py:208-214`) én de LLM Hengelo koos — er is geen structurele garantie (B1).
- **Stille-fout-mechanisme (baseline #847)**: als de klant niet resolvet, wordt ship-to stil overgeslagen — `ship_to_gekozen=None` zonder eigen review-vlag (alleen `klant_match` staat gevlagd). Verwacht 94315, kreeg None = STILLE-FOUT.

## 3. Verkeerde eenheidscode + niet-omgerekend aantal → laag: UoM-logica verspreid over 5 modules

Keten: `utils/eenheid_mapping.py:22` (normalisatie, default STUK) → `utils/eenheid_resolve.py:42` (Item-UoM-resolutie; call-sites `graph/nodes/match_articles.py:256` en `api/preview.py:385`) → Branch A `graph/nodes/apply_mixprijzen.py:192` (`_verkoop_keuze:114`) → mix `_evaluate:267` → composer-terugval `integrations/navision_steps.py:102` (`_line_uom_to_emit`) + aantal-keuze `:164-169`. Elke schakel heeft eigen terugvalregels; per order dus een andere uitkomst.

- **Baseline-bewijs #845/#203 (Lasaulec)**: besteld `2.0 PAL` van 15620. De pallet-brug (`eenheid_resolve.py:66-69`) weigert zodra een artikel >1 pallet-variant heeft (`pallet_uom_code:37-39`: 15620 heeft PALLET(30) én PALLET35 → ambigu → None) → terugval STUK+vlag; Branch A zet daarna `verkoop STUK/2.0`. NAV zou **2 STUK** krijgen waar **2 PALLET (=60 stuks)** besteld is: eenheid fout én aantal niet omgerekend (gevlagd, niet stil — maar precies de gemelde categorie). #819 (23691, precies één PALLET-rij) brugt wél.
- **Vlag-lawine**: #816 krijgt 10× `orderregels[i].eenheid`-vlag en #685 8× eenheid + 8× `mix_uom:i` (mixprijzen-page niet actief in prod → élk mix-kandidaat-artikel review). Dit is de "review-last 86%"-klacht: terugval → vlag is de enige strategie, er is geen voorkeursorde (B3 a-e).
- **"1???"/non-artikelregels**: er bestaat géén concept voor toeslag-/niet-artikelregels. De composer skipt regels zonder match stil (`navision_steps.py:291-297`) en gooit alléén bij 0 matches (`:306-311`, baseline #717: compose_error, 0 operaties). Een order met 5 gematchte + 1 ongematchte regel verliest die regel geruisloos in de NAV-ops.

## 4. Onnavolgbare europallet-telling → laag: impliciete databron-prioriteit

- `utils/pallet_logic.py:120` (`_line_pallets`) probeert 6 bronnen op volgorde; het **leerbestand** `artikel_pallet_kennis` (`db/models.py:189`, `per_pallet` default **24**) staat op prioriteit 3, vóór de Item-UoM/`verkoop_eenheid`-conversie, en `HEURISTIC_PER_PALLET=24` (`:34`) vangt DOOS-gevallen.
- **Baseline-bewijs**: #832 → 33 STUK 238601 geteld als 33/24=1.375→**2** (verwacht 1; artikel heeft PALLET33); #716 → 66/24=2.75→**3**; #833 → 0.208 onder `PALLET_THRESHOLD=0.5` → **géén** europallet (verwacht 1). Twee van de drie stille fouten in de baseline zitten hier. De telling is niet uitlegbaar omdat de gekozen bron per regel verschilt; B4 (expliciet `pallet_plaatsen_basis` per artikel+eenheid, leerbestand negeren tot opgeschoond, "onbekend → vlag") adresseert precies dit.

## Dwarsverbanden / gaten die onafhankelijk van rood-groen bestaan

1. Geen adresrollen in extractie (laag 2) is de wortel onder laag 1 én de ship-to-keuze.
2. `prijsafspraken` is leeg in prod (mirror-telling 0) → F6-prijs-signaal (#816 pos9 23853-vs-238531) is data-gated inactief; geen vlag zichtbaar in de baseline.
3. Een 100%-match zonder vlag kan nog steeds fout zijn: `naam_extract` levert conf 1.0 zonder vlag na postcode-bevestiging (`match_customer.py:600-617`) — nu correct (#944/#718/#816), maar het patroon "confident-fout" wordt alleen door B1+B2 structureel afgedekt.
