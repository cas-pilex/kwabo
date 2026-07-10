# FASE 2 — Besluitenlog (aannames bij Gate 1-akkoord zonder beantwoorde beslislijst)

Gate 1 is akkoord gegeven ("ga door met de andere fases") zonder antwoorden op de
beslislijst A-I. Onderstaande gedocumenteerde besluiten gelden als werkaannames; elk
besluit is masterdata-gestaafd en wordt bij Gate 2/3 expliciet ter bevestiging
teruggelegd. Geen enkel besluit is een hardcode: alle regels zijn generiek en
data-gedreven.

## A. #716 "Würth 66 i.p.v. 2×PALLET33" — MECHANISME AANWEZIG, DATA-ACTIE NODIG

Feiten (read-only prod, 10-7):
- 238601 heeft plain `PALLET33` (33,0) als geldige Item-UoM (naast PALLET30/35/42);
- 238601's `verkoop_eenheid` = **STUK**;
- het bestaande Branch-A-mechanisme converteert STUK-aantallen naar de NAV-
  **verkoop_eenheid** bij exacte deelbaarheid (bewijs: #954 — artikel 228321 heeft
  verkoop_eenheid=PALLET → 60 STUK → PALLET×1; #941 — 23522/23523 → PALLET×2);
- `palletable` is een dode kolom (NULL voor alle 3757 artikelen) — geen discriminator.

**Besluit:** de generieke regel blijft "converteer naar de verkoop_eenheid van het
artikel bij exacte deelbaarheid; anders bestelde eenheid behouden (geen valse
omrekening)". Voor #716 is de gewenste 2×PALLET33 daarmee een **NAV-data-actie**:
`verkoop_eenheid` van 238601 op `PALLET33` zetten — exact de voorkeursroute die Kwabo
zelf koos (vullijst-commit 07f3fe5: "verkoopeenheid op pallet-code zetten i.p.v.
app-lijst"). Tot die data-actie: GT-716 blijft STUK×66 (meet de pipeline, niet Nico's
openstaande NAV-invoer) mét annotatie; het mechanisme wordt bewezen met een
fixture-test (verkoop_eenheid=PALLET33 in wegwerp-sqlite → 66→PALLET33×2).
Status richting klant: **GEBLOKKEERD-VEILIG-AFGEHANDELD** (zelfde klasse als
europallet-vullijst).

## B. #847 "STUK-blijft-STUK" vs GT PALLET 31/35

**Besluit:** GT-847 blijft PALLET 31/35. De conversies zijn exact en masterdata-uniek
(930 = 31×30 via 23730-PALLET(30); 700 = 35×20 via 23733-PALLET(20)); bestelde eenheid
was bovendien ROL (ongeldig) — er is geen "STUK-bestelling" die vals omgerekend wordt.
De scenario-eis "geen valse omrekening" wordt generiek geborgd: artikelen met
verkoop_eenheid=STUK of niet-exacte deelbaarheid blijven STUK (bewijs: #816 pos2/3/9
= STUK 34/42/45, run 1 JUIST).

## C. #941 ship-to

**Besluit:** `4814 RR` bevestigd als GT — het is de enige bestaande Breda-ship-to van
61483 (extract-adres 4815 PN bestaat niet als ship-to). Openstaand richting Nico: moet
er een 4815 PN-ship-to in NAV komen?

## F. 15620 pallet-maat

**Besluit:** plain `PALLET` (30) is de niet-mix-variant en consistent met "60 stuks /
2 PAL" → maat 30 bevestigd als werkaanname; PALLET35 blijft de vlag-waardige
alternatief-case (E3).

## G. Vestigingsnummers

**Besluit:** 954→50094, 832→61468, 833→61019, 834→61088 gelden als bevestigd — alle
vier via read-only SELECT herleid tot exact één klantenkaart met de juiste
naam+leveradres (gt_evidence.json). Formele bevestiging blijft gate-punt.

## D/E. Europallet-waarden — GEBLOKKEERD (ongewijzigd)

`pallet_plaatsen_basis` = 0 rijen; leerbestand vervuild (per_pallet=24, genegeerd).
Mechanisme wordt in F2.6 met fixture-data bewezen; prod-waarden wachten op de
vullijst. NB: zodra besluit A's NAV-data-actie (verkoop_eenheid=PALLET33 voor 238601)
is uitgevoerd, telt #832 (33 STUK → PALLET33×1) automatisch europallet=1 via de
verkoop_pal-route — één data-actie lost dan twee K-targets op.

## H. #717/#685 regel-GT

**Besluit:** blijft leeg; deze orders bewijzen vlag-gedrag (fail-loud), geen
regel-uitkomsten, tot Kwabo artikelnummers aanlevert.

## I. F6-prijs-signaal

**Besluit:** blijft GEBLOKKEERD op 7002-data (prijsafspraken=0); alleen vlag-gedrag
toetsbaar; wordt nooit als "opgelost" gerapporteerd.

## Beleidsvraag A8 (0 ship-to-kandidaten → vlagloos kaartadres)

**Besluit (werkaanname):** vlagloos blijft acceptabel wanneer klant-match zelf al
gevlagd is of conf 1.0 met kaartadres-levering; wordt als expliciete vraag in Gate 2
herhaald.

## E3-consistentiecheck (nieuw gedrag, Fase 2)

**Besluit:** als het brondocument een pallet-aanduiding bevat die NIET consistent is
met de gekozen pallet-maat (bijv. "2 PAL" bij 70 stuks waar maat 30/35 geen exacte
match geeft), kiest de resolver niets stil: bestelde eenheid + vlag.
