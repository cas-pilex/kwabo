# F4 Europallet — Fix-ronde plan (na Blok B-diagnose)

**Status:** GEBLOKKEERD op een open expertvraag (Cas/Nico). Geen code-fix uitgevoerd.
**Diagnose-commit:** `a8204c6` (`diag(europallet)…`). **Datum:** 2026-06-18.

## 1. Wat Blok B onthulde (bewezen, read-only)
De gevalideerde F4-uitkomst (#832→1, #833→1) was een **artefact van fictieve testdata**:
de oude `verify_funct4` seedde hardcoded `verkoop_eenheid=PALLET33`. Op de **echte prod-data**:

- Prod `verkoop_eenheid` voor 238601/238531/229231 = **`STUK`** (direct tegen prod geverifieerd).
- De europallet-telling gebruikt **`artikel_pallet_kennis` als PRIMAIRE bron** (bron `kennis`),
  die `verkoop_eenheid` overschaduwt.
- `artikel_pallet_kennis.per_pallet = 24` voor 238601 en 229231 — en **24 matcht geen enkele
  echte pallet-familie**:
  - 238601: echte pallet-maten 30/33/35/42 → per_pallet 24 = onmogelijk
  - 229231: echte pallet-maten 48/64/80/100 → per_pallet 24 = onmogelijk
  - 238531: **geen** kennis-rij (per_pallet None) → levert 0 bijdrage
- Echte uitkomst: **#832 = 2** (33/24=1,375→2), **#833 = 0** (229231 5/24=0,208 <drempel;
  238531 geen bron). Beide **data-gedreven fout**.

Breder (n10 op echte UoM): voor artikelen mét een echte pallet-`verkoop_eenheid` telt het
wél correct (#721 0→1, #550 0→1, #619 0→2, #685 0→7). Het probleem zit bij de multi-family
artikelen met `verkoop_eenheid=STUK` **én** een implausibele/ontbrekende kennis-waarde.

## 2. OPEN EXPERTVRAAG (Cas/Nico) — blokkeert de fix
1. **Wat is de juiste pallet-maat per artikel?** Voor 238601 (33 STUK = 1 pallet? → PALLET33),
   23691 (echte PALLET=20, kennis zegt 24), 229231 (48/64/80/100?). Ik mag dit niet zelf invullen.
2. **Welke bron is leidend** bij conflict: de NAV pallet-UoM/`verkoop_eenheid` (mits correct
   gevuld) of `artikel_pallet_kennis` (dashboard-leerwaarden)? Nu wint kennis — en die staat fout.
3. **Hoe is `per_pallet=24` ontstaan?** De rijen zijn `bevestigd_door=dashboard` (2026-06-15/16).
   Is dit een systematische invoer-/leerfout (veel artikelen op 24)? → mogelijk OPS-correctie nodig.

## 3. Voorgestelde fix (afhankelijk van het antwoord)

### Sowieso (verdedigbaar ongeacht het antwoord) — sanity-guard
Een `artikel_pallet_kennis.per_pallet` die **geen enkele echte pallet-UoM-familie** van het
artikel matcht, is per definitie verdacht. Voeg een guard toe in de pallet-bron-keuze
(`utils/pallet_logic.py`): negeer/deprioriteer zo'n kennis-waarde en val terug op de echte
pallet-UoM (`verkoop_eenheid`/PALLET-familie); kan de pallet-maat niet betrouwbaar bepaald
worden → **geen stille telling, maar een review-vlag** ("pallet-maat onzeker"). Grondwet:
liever leeg/gevlagd dan fout.

### Als NAV pallet-UoM/verkoop_eenheid leidend is (optie 2)
- Pallet-bron-prioriteit omdraaien: echte pallet-UoM (mits ondubbelzinnig of door
  `verkoop_eenheid` gedisambigueerd) **boven** kennis.
- Datacorrectie: `verkoop_eenheid` in de NAV-mirror op de juiste pallet-familie zetten voor de
  multi-family artikelen (sync-vraag), of een ander disambiguatie-signaal.

### Als artikel_pallet_kennis leidend blijft (optie 3)
- OPS-datacorrectie: de foute `per_pallet`-waarden (24 e.d.) corrigeren naar de echte pallet-maat
  via het dashboard/leer-pad; + de bovenstaande sanity-guard om herhaling te vangen.

## 4. Aanpak (na akkoord + antwoord)
- **TDD**: RED-test per scenario met de ECHTE data en de door Cas bevestigde juiste uitkomst
  (#832 → ?, #833 → ?), dan de fix tot GREEN. Geen geseede pallet-maten meer; fixture-gedreven.
- **Regressie**: de n10-broad-sample-europallets mogen niet verslechteren; de orders die nu
  correct tellen (#721/#550/#619/#685/#707/#716/#660) blijven gelijk of verbeteren.
- **Verificatie**: `verify_funct4` (diagnose) wordt een echte verificatie zodra de juiste
  uitkomst vaststaat; volledige suite groen; determinisme 3×.

## 5. Bestanden (verwacht)
`backend/src/kwabo/utils/pallet_logic.py` (bron-prioriteit + sanity-guard),
`backend/src/kwabo/graph/nodes/compute_europallet.py` (review-vlag bij onzekere pallet-maat),
`backend/tests/test_europallet_*.py` (RED→GREEN op echte data), `backend/scripts/verify_funct4_…`
(diagnose → verificatie). Mogelijk OPS-correctie op `artikel_pallet_kennis` (geen code).

## 6. Impact-waarschuwing
Tot deze fix is **F4 niet betrouwbaar op prod-data** voor multi-family artikelen: het
europallet-aantal kan te hoog/te laag zijn (#832=2 i.p.v. waarschijnlijk 1). De
EINDVALIDATIE/VALIDATIERAPPORT-claim "F4 BEWIJSBAAR-OPGELOST" is hiermee **ingetrokken** tot de
fix-ronde is afgerond.
