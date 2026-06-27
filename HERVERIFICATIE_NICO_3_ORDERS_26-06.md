# Herverificatie Nico's 3 orders — 26 juni 2026

> Methode: **read-only**. Rauwe `.eml` (mét PDF) opgehaald uit Supabase Storage →
> door de ECHTE pijplijn gedraaid (`verify_reality.py --eml`, **Vision-extractie**,
> `NAVISION_MODE=mirror` tegen read-only gespiegelde prod-masterdata) op zowel de
> huidige code als de baseline vóór de fixes. Geen bevroren state, geen mock voor matching.
> Prod-backend = `kwabo-production.up.railway.app`, draait `63fa5fe` (GET /api/version).

## Aanleiding
Gemeld dat 3 orders nog faalden in prod: BAUHAUS ship-to = besteladres; TABS #954 →
PontMeyer 61793 op 100% zonder vlag; PPG #941 mix-eenheden fout ("1???"). Eerdere
"het werkt"-claims waren afgewezen → eis: bewijs op de echte pijplijn óf fix de root cause,
plus een differentieel dat aantoont dat de meting de echte laag raakt.

## Kernuitkomst
**Alle drie de orders zijn al correct op de gedeployede code** (`63fa5fe`). De door Nico
geziene "rode" waarden zijn **stale `order_log`-records van vóór de fix-deploy** — geen
live falen. Geen codefix nodig. Bewezen met verse bron-Vision-output + een differentieel
dat de oude bugs reproduceert.

## Rood/groen — Vision-vs-Vision differentieel (zelfde .eml, alleen de code verschilt)

| Order | Baseline `1d75b4e` (vóór fixes) = ROOD | Huidige main `63fa5fe` = GROEN |
|---|---|---|
| **#954 TABS** (supplychain@tabsholland.nl) | klant **61793** PontMeyer · conf **1.0** · bron `email` · **géén vlag** · ship-to 8447 GH | klant **50094** Jongeneel Woerden · conf **0.9** · bron `leveradres_shipto` · **gevlagd** · ship-to **3449 JE** |
| **#944 BAUHAUS** | ship-to **3981 LB BUNNIK** (besteladres) · reason `plaats_in_order_text` | ship-to **7559 SR HENGELO** · reason `afleveradres_postcode_exact` (Vision leest "Vestiging 462") |
| **#941 PPG** | regel2 (art 23522, 60 STUK) → uom **M1PAL30** | regel1 STUK 45 · regel2/3 **PALLET aantal 2** (60→2 omgerekend) · géén "1???" |

Het differentieel reproduceert met **identieke Vision-bytes** de exacte gemelde fouten op de
baseline → de harness raakt de echte extractie-/aliaslaag (dat was de kloof waardoor
eerdere mock/frozen-validatie ten onrechte groen was).

## Waarom Nico nog "rood" zag (bewijs)
Read-only query op prod `order_log` — de records die in de UI staan:

| Order | Aangemaakt | Gepushte (stale) waarde | = baseline-bug? |
|---|---|---|---|
| #954 | 2026-06-23 08:08 | klant 61793 · bron email · conf 1.0 · géén vlag · ship-to 8447 GH | ✅ |
| #944 | 2026-06-22 15:09 | ship-to 3981 LB Bunnik · géén vlag | ✅ |
| #941 | 2026-06-22 13:01 | regel2 verkoop_uom M1PAL30 | ✅ |

De fixes kwamen op main in `63fa5fe` (**25 juni**) — ná het verwerken van deze orders.
Prod draait die fix nu (GET /api/version → 63fa5fe), maar de 3 orders zijn nooit herverwerkt.

## #941 — bedoelde eenheid (uit Nico's eerdere feedback)
`VALIDATIERAPPORT_RONDE2.md` defect C: de bug was *"mix-staffelcode (M1PAL30) stil als
verkoopeenheid; 1??? op regel"*; bedoelde uitkomst (regel 116): *"r2 23522 **PALLET 2**;
r3 23523 **PALLET 2** (NIET M1PAL30)"*. De huidige code levert exact dat; de "1???" was de
oude M1PAL30 op de stale record.

## Generiek-bewijs (geen hardcode)
Zelfde logica, andere orders, huidige code (Vision):

| Order | Resultaat | Bewijst |
|---|---|---|
| #834 TABS | klant **61088** PontMeyer Zwaag · 0.9 · gevlagd · ship-to 1689 AK | ander eindklant dan #954 |
| #955 TABS | klant **61005** PontMeyer Alkmaar · 0.9 · gevlagd · ship-to 1821 BT | wéér ander eindklant |
| #662 BAUHAUS | ship-to **9723 AW Groningen** · `afleveradres_postcode_exact` | ander adres dan #944 |

Dezelfde agent-mailbox lost op naar drie verschillende juiste eindklanten op afleveradres.

## Verificatie
- 3 order-regressietests: **11/11 groen** (`test_match_customer_shared_mailbox`,
  `test_select_ship_to_postcode_priority`, `test_branch_a_mixcode_sales_unit`).
- Volledige backend-suite: **678 passed, 17 skipped, 0 failed**.
- Werkelijkheid-harness na GT-correctie: **0 stille fouten, 3/3 juist**.

## Correctie ground_truth (gegrond in VALIDATIERAPPORT_RONDE2.md, niet in eigen output)
`_reality/ground_truth.json` was vervuild met de oude buggy waarden. Gecorrigeerd:
944 ship-to → 7559 SR; 941 regel2 → PALLET; 954 toegevoegd (50094 / 3449 JE).

## Status van de 3 records in prod (read-only gecheckt) + besluit 27-06

| Order | Dashboard-status | In NAV? | Besluit (Cas, 27-06) |
|---|---|---|---|
| **#941 PPG** | `pushed` | **NAV-order `VO2606419`** met foute eenheid M1PAL30 (vóór-deploy gepusht) | **Laten staan** — bekende vóór-deploy-afwijking; correctie in Navision niet uitgevoerd |
| **#944 BAUHAUS** | `pushed` | **NAV-order `VO2606418`** met foute ship-to 3981 LB Bunnik (vóór-deploy gepusht) | **Laten staan** — idem |
| **#954 TABS** | `review` (niet gepusht) | n.v.t. — staat nog op oude klant 61793 | **Laten staan** — geen reprocess/re-resolve uitgevoerd |

**Belangrijk:** #944 en #941 zijn al naar Navision gepusht (VO2606418 / VO2606419) mét de oude
foute waarden; het dashboard toont dus correct wat destijds is verstuurd. Een dashboard-
herverwerking lost de NAV-order niet op — dat zou een NAV-zijdige correctie vergen. Per besluit
27-06 blijven alle drie ongewijzigd; ze zijn een **bekende, gedocumenteerde vóór-deploy-afwijking**.

**De code is correct en live** (`63fa5fe` op main + Railway + Vercel): élke *nieuwe* binnenkomende
order wordt correct afgehandeld (bewezen met #834→Zwaag, #955→Alkmaar, #662→Groningen). Er is
geen codefix nodig en geen nieuwe code uit deze ronde.

## Reproduceren
```
# rauwe .eml read-only uit Supabase Storage (keys staan in order_state.incoming_document_storage_key)
# daarna, vanuit backend/ met systeem-Python + venv site-packages op PYTHONPATH:
py -3 scripts/verify_reality.py --eml <map-met-954/944/941.eml>
# differentieel: git worktree add <pad> 1d75b4e ; kopieer verify_reality.py + navision_mirror.py
#   + mirror-branch in navision_api._build_navision_client ; draai dezelfde --eml
# suite (Windows): py -3 -c "import os; os.environ['ADMIN_PASSWORD']=''; import pytest; pytest.main(['-q'])"
```
