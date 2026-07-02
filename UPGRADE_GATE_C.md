# UPGRADE_GATE_C — Gebruiksvriendelijkheid (Nico's werk in één oogopslag)

**Datum:** 2026-07-02 · branch `upgrade/fase-a-golden-corpus` · gebaseerd op de frontend-gap-analyse (wat er van C1–C3 al stond uit F1–F7 is hergebruikt, alleen de gaten zijn gebouwd).

## C1 — Uitlegbaarheid
- **Match-reden permanent zichtbaar** (`order-review.tsx`, testid `klant-match-reden`): "gedeelde mailbox — gekozen op leveradres 3449 JE WOERDEN via ship-to van 'Jongeneel Woerden BA659'" staat nu áltijd onder de klantnaam — niet meer alleen verstopt in de bevestig-knop. Incl. "leveradres bevestigd"-badge (DEEL A2-promotie).
- **NAV-omrekening per regel** (`order-lines-table.tsx`, testid `regel-nav-eenheid-{pos}`): blauwe badge "→ NAV: 1 × PALLET" (mix > Branch A) met tooltip "Besteld 30 STUK — naar NAV gaat 1 × PALLET". Verscheen nooit eerder in de UI (`verkoop_uom_gekozen` was frontend-onbekend).
- **Europallet: ook wat NIET meegeteld is** (`EuropalletEditor.tsx`, testid `europallet-onbekend`): rood blok "Niet meegeteld (pallet-plaatsen onbekend): 88888 (10 STUK)" — B4's onbekend-lijst, nieuw in type `EuropalletMeta` én UI.
- **Adresrollen-chips** (`order-review.tsx`, testid `adres-rollen`): besteller/factuur grijs, aflever/eindontvanger groen — de reviewer ziet direct dat Bunnik (besteller) bewust níet het leveradres (Hengelo) is.
- Compose-reden bij 0 operaties bestond al (`nav-op-empty-reason`, F5) — ongewijzigd.

## C2 — Werkflow
- **Kandidaten-picker met zoek** (`KlantPicker.tsx`, testid `klant-zoek`): filtert live op naam/plaats/nummer met teller "1/3 kandidaten"; nodig voor agent-mailboxen met tientallen vestigingen.
- **Vlaggen in afhandel-volgorde** (`needs-review-banner.tsx`, `sorteerVlaggen`): klant → afleveradres/ship-to → artikel → eenheid/mix → aantal → europallet (klant eerst omdat die ship-to/prijzen/mix herbepaalt; artikel vóór eenheid omdat een artikel-wissel de eenheid herberekent). Stabiel binnen klassen.
- Bevestig-knop per klant-vlag en klant→ship-to-herberekening zonder reload bestonden al (F6-V2, F2) — gedekt door bestaande specs.

## C3 — Vertrouwenssignaal
- **"✓ klaar"-badge in de orderlijst** (`app/page.tsx`, testid `klaar-badge-{id}`): review-orders met 0 vlaggen tonen groen "✓ klaar" in de Mist-kolom — het detail-scherm had dit signaal al op drie plekken, de lijst nu ook.
- **Takenlijst-formulering** in de banner: "⚠ 3 dingen te controleren (in volgorde):" met klikbare scroll-knoppen (bestond functioneel, nu geteld+geordend zoals gevraagd).

## C4 — Playwright-bewijs
- Nieuwe spec `frontend/tests/fase-c-uitlegbaarheid.spec.ts` — **7/7 groen** tegen live servers (seed-order-endpoint, geen LLM nodig): match-reden, NAV-omrekening, europallet-onbekend, adresrollen, geordende takenlijst, kandidaten-zoek, klaar-badge.
- Volledige Playwright-run: **13 passed, 9 failed** — de 9 zijn geverifieerd níet door Fase C:
  - 7 draaien de echte pijplijn (scan/upload) en stranden op de lege Anthropic-credits: de B1-promptwijziging geeft nieuwe LLM-cache-keys → cache-miss → echte API-call → 400 "credit balance too low" (letterlijk gereproduceerd). Na credit-aanvulling vult één run de cache en zijn ze weer groen.
  - 2 (error-toast, prijsafspraken-CRUD) falen ook op de ONgewijzigde frontend (bewezen via stash-run) — pre-existing in deze omgeving.
- TypeScript: `tsc --noEmit` schoon.

## On-site te bewijzen (niet hier claimbaar)
Echte Vercel-UI met prod-data (de e2e draait tegen dev-server + sqlite-seed); de beleving van de volgorde/uitleg met Nico zelf (on-site testscript volgt in Fase D-rapport).
