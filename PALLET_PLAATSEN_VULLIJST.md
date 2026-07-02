# PALLET_PLAATSEN_VULLIJST — in te vullen door Nico/OPS (B4)

Per (artikel, eenheid): hoeveel PALLETPLAATSEN neemt één regel-eenheid in?
`0` = neemt geen plaats (bijpak-artikel). Voorbeeld: gaan er 33 stuks van een artikel op een pallet, dan is plaatsen_per_eenheid per STUK = 1/33 ≈ 0.0303.
Zonder waarde geeft de tool de vlag 'europallet onbekend' (geen gok; het vervuilde leerbestand per_pallet=24 wordt genegeerd).

**VOORKEURSROUTE — beheer in Navision, geen lijst nodig:** zet bij deze artikelen in NAV de
**Sales Unit of Measure (verkoopeenheid)** op de juiste pallet-code (bijv. PALLET33). De
bestaande NAV-sync pikt dat automatisch op en de europallet-telling klopt dan vanzelf —
dit bestand is alleen nodig als override voor uitzonderingen (bijv. bijpak-artikel = 0 plaatsen).
Zelfde geldt voor klant-artikelnummers: leg die als Item Reference in NAV vast (sync loopt al);
de app-leertabel groeit daarnaast vanzelf met elke goedkeuring.

## Corpus-artikelen zonder databron (vlag actief)

| artikel | naam | eenheid | NAV-pallet-varianten (qty/base) | corpus-order | plaatsen_per_eenheid (INVULLEN) |
|---|---|---|---|---|---|
| 184501 | Quality Covers|Foil Window/50m²/Groen/50 | ROL | PALLET(144), PALLET252(252), PALLET300(300) | #816 | |
| 229231 | Quality Covers|Foil Hard-floor/42m²/70cm | ROL | PALLET(80), PALLET100(100), PALLET64(64) | #816 | |
| 229231 | Quality Covers|Foil Hard-floor/42m²/70cm | STUK | PALLET(80), PALLET100(100), PALLET64(64) | #833 | |
| 234781 | Quality Covers|Nonwoven Premium/25m²/100 | ROL | PALLET(45), PALLET30(30), PALLET35(35), PALLET42(42) | #685 | |
| 23521 | Stiho|Board Premium/50m²/C2S/130cm | ROL | PALLET(35), PALLET30(30) | #685 | |
| 23545 | Bouwcenter|Board Premium/50m²/C2S/130cm | ROL | PALLET(35), PALLET30(30) | #685 | |
| 23559 | Pro Gold|Nonwoven Premium/25m²/100cm | STUK | PALLET30(30), PALLET35(35), PALLET42(42), PALLET45(45) | #941 | |
| 23853 | Top coat Heavy-Duty/25m²/100cm | ROL | PALLET(45), PALLET25(25), PALLET33(33), PALLET50(50), PALLET51(51), PALLET90(90) | #816 | |
| 238531 | Quality Cover|Top coat Heavy-Duty/25m²/1 | STUK | PALLET(45), PALLET25(25), PALLET33(33), PALLET35(35), PALLET42(42), PALLET45(45), PALLET50(50), PALLET51(51), PALLET90(90) | #833, #944 | |
| 238601 | Quality Covers|Top coat Heavy-duty/25m²/ | ROL | PALLET30(30), PALLET33(33), PALLET35(35), PALLET42(42) | #718 | |
| 238601 | Quality Covers|Top coat Heavy-duty/25m²/ | STUK | PALLET30(30), PALLET33(33), PALLET35(35), PALLET42(42) | #716, #832 | |
| 23923 | Bouwcenter|Top coat Heavy-Duty/25m²/100c | ROL | PALLET(45), PALLET33(33) | #685 | |
| 23924 | Bouwcenter|Top coat Heavy-Duty/50m²/100c | ROL | PALLET(20), PALLET22(22), PALLET24(24) | #685 | |
| 23989 | Bouwcenter|Top coat Heavy-duty/25m²/67cm | ROL | PALLET33(33), PALLET35(35), PALLET42(42) | #685 | |

## Ambigue NAV-families (meerdere pallet-varianten, verkoop_eenheid=STUK — veldwaarde maakt de telling exact)

- 238601 (Quality Covers|Top coat Heavy-duty/25m²/): varianten PALLET30(30), PALLET33(33), PALLET35(35), PALLET42(42); verkoop_eenheid=STUK
- 238531 (Quality Cover|Top coat Heavy-Duty/25m²/1): varianten PALLET(45), PALLET25(25), PALLET33(33), PALLET35(35), PALLET42(42), PALLET45(45), PALLET50(50), PALLET51(51), PALLET90(90); verkoop_eenheid=STUK
- 229231 (Quality Covers|Foil Hard-floor/42m²/70cm): varianten PALLET(80), PALLET100(100), PALLET64(64); verkoop_eenheid=STUK
- 23559 (Pro Gold|Nonwoven Premium/25m²/100cm): varianten PALLET30(30), PALLET35(35), PALLET42(42), PALLET45(45); verkoop_eenheid=STUK
