# FASE 1 — validatie van de 3 fixes (brede read-only steekproef)

**Datum:** 23-06-2026 · branch `feat/fase2-matching` · read-only t.o.v. prod.

De drie fixes (TABS gedeelde-mailbox / BAUHAUS ship-to-postcode / PPG mix-code-verkoopeenheid) zijn
naast de unit-tests (669 groen) breed getoetst op **echte prod-orders**: de gewijzigde nodes
(`match_customer → select_ship_to → apply_mixprijzen`) zijn over **alle 326 is-order-orders** gedraaid
op hun opgeslagen extractie tegen verse read-only prod-masterdata (wegwerp-sqlite). Harness:
`backend/scripts/_fase1_steekproef.py` (wegwerp).

## Segment A — TABS-groep (gedeelde mailbox), 52 orders
- **Confident-foute 61793-matches: 34 → 0.** Alle TABS-orders die voorheen blind naar PontMeyer
  Heerenveen gingen, doen dat niet meer.
- 38 worden nu op het **leveradres** naar de juiste vestiging gerouteerd (ship-to-disambiguatie),
  14 gaan naar **kandidaten + CONTROLEER** (geen gok bij gelijkspel/ontbrekend leveradres).

## Segment B — regressiecheck: 70 orders met opgeslagen `match_bron=email`
- 67 ongewijzigd (conf 1.0 e-mailmatch onaangeroerd — dat pad is niet aangeraakt).
- 3 gewijzigd, alle verdedigbaar (0 echte regressie):
  - **#123** `werkzeuge-dietrich.de`: demo-/seedklant **10012 → echte klant 60600** (leveradres) — winst.
  - **#400/#213** `storch-ciret.com` (3 distincte entiteiten: STORCH 61536 / Sourcing 61240 / Ciret
    61241): nu **kandidaten** i.p.v. een confidente gok op de e-mailkaart. #213 heeft géén afleveradres
    → kandidaten is de enige juiste uitkomst; #400 valt op een postcode-prefix (`D 99837` vs `99837`)
    net buiten een unieke pick → review. Veiliger dan blind 61536.

## Segment C — ship-to-delta's bij ongewijzigde klant: 7
- 5 verbeteringen: was géén ship-to (None) → nu **exact de afleveradres-postcode** (#89/#26/#20/#3/#2).
- 2 historische-vergelijkingsruis (klantverschil destijds). Géén order kreeg een slechtere ship-to.

## Segment D — eenheid mix-code-guard geraakt: 4 orders
- **#941 / #922**: een artikel met mix-staffelcode als `verkoop_eenheid` (M1PAL30) valt nu terug op
  STUK + review-vlag i.p.v. stil 2× M1PAL30 — precies de PPG-fix, breder dan alleen #941.
- #885 / #244: benigne (geen waardewijziging resp. Branch-A vult verse velden).

## Conclusie
Geen echte regressie. De fixes elimineren de systemische TABS-fout (34→0), verbeteren ship-to en
eenheid op echte orders, en routeren genuinely-ambigue gedeelde domeinen veilig naar review. **GO.**

Wegwerp-artefacten (`backend/scripts/_fase1_steekproef.py`, `backend/_fase0/`) zijn niet voor commit.
