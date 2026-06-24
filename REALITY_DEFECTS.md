# REALITY_DEFECTS — wat de werkelijkheid-meting vindt (24-06-2026)

Gemeten met `backend/scripts/verify_reality.py` (verse pijplijn, read-only prod-mirror,
prod-schaarste behouden) + read-only prod-diagnose (`_reality_diag.py`, `_reality_probe941.py`).
Alle prod-toegang was **SELECT-only** (geen write). Dit is Fase 2 (meten) — nog géén fixes.

> **Eerlijke kanttekening vooraf:** dit is een *eerste* meting met twee structurele beperkingen
> die de meting nog niet volledig maken: (1) **MockNAV** vervuilt lokaal de klant- en
> artikel-matching (zie D1), en (2) ik heb (nog) **geen verse raw .eml** en **geen concrete
> foutenlijst van het team**. De bevindingen hieronder zijn wat nú hard bewijsbaar is; de
> volledige meting vereist de drie punten onder "Wat ik van jullie nodig heb".

---

## 0. Masterdata-realiteit (read-only prod, harde tellingen)

| Tabel | Rijen | Oordeel |
|---|---:|---|
| klantenkaarten | 1787 | ok — **maar postcode/plaats = 0/1787 (allemaal NULL)** |
| klantenkaart_ship_to | 2506 | ok — postcode/plaats **2506/2506 gevuld (100%)** |
| artikelkaarten | 3757 | ok — **verkoop_eenheid 3718/3757 gevuld (99%)**, 7 mix-code-datafouten |
| artikel_eenheden | 12963 | ok (item-UoM, voedt eenheid-fix) |
| artikel_kruisverwijzing | 3000 | **verdacht** — exact 3000, 604 klanten, max 7/klant, bron allemaal 'Customer' |
| klantenkaart_artikelen | **24** | **bijna leeg** — klant-specifieke mapping |
| artikel_matching_history | **24** | **bijna leeg** — learning-loop wordt niet gevoed |
| artikel_pallet_kennis | 19 | schaars (europallet-kennis) |
| prijsafspraken | **0** | **leeg** — prijsvalidatie/F6 volledig no-op |
| klant_email_aliases | **1** | **bijna leeg + stale** (zie C3) |

**Conclusie laag 0:** de *infrastructuur*-masterdata (klantkaarten, ship-to, artikelkaarten,
eenheden) is gezond. De *relationele/lerende* masterdata (klant-artikel-mappings, history,
prijsafspraken, aliassen) is vrijwel leeg → veel orders vallen in prod terug op fuzzy/manueel →
dit verklaart een groot deel van de klacht **"te veel review"**.

---

## A. Bevestigde bevindingen (hard bewijs)

### A1 — Klantkaarten missen postcode/plaats (0/1787)
`sync_customers` schrijft geen postcode/plaats; alle 1787 kaarten zijn NULL. De
klant-disambiguatie leunt daarom volledig op de ship-to-master (die wél 100% gevuld is).
Niet fataal, maar fragiel: zodra een klant geen ship-to-rijen heeft, is er geen adres-signaal.
*Bewijs:* `SELECT count(postcode) FROM klantenkaarten` = 0.

### A2 — Relationele masterdata bijna leeg → review-ruis
klantenkaart_artikelen=24, history=24, prijsafspraken=0. In prod betekent dit: voor vrijwel
elke klant zonder kruisverwijzing valt artikel-matching door naar fuzzy (cap 0.84 → altijd
review) of manueel. Dit is **data**, geen code — en is de meest waarschijnlijke hoofdoorzaak
van "te veel handmatige controle".

### A3 — artikel_kruisverwijzing exact 3000 (te verifiëren tegen live NAV)
604 distincte klanten, max 7 refs/klant, één `bron='Customer'`. De sync paginéért wél
(`get_collection` volgt `@odata.nextLink`), dus 3000 kán het echte totaal zijn — maar het ronde
getal verdient een live-NAV-controle (telt NAV méér itemReferences dan 3000?). **Open vraag,
niet bevestigd als bug.**

---

## B. Per-order bevindingen (3 eerder-gerapporteerde orders, verse mirror)

### B1 — #941 PPG: artikel-match 0/3 (root-cause = MockNAV-gate, zie D1 + C2)
Trace (`_reality_probe941.py`, klant 61483):
- regel bestelt Kwabo-eigen nummers (23559/23522/23523) — die bestaan álle als artikelkaart.
- `artikelnummer_kwabo` uit de extractie = 804600/804555/804430 — die bestaan **niet**.
- match_articles stap 1b wordt geblokkeerd door een expliciete klantenkaart-mapping (61483,23559);
  stap 3 vindt die mapping maar **gate't op `await nav.get_item(23559)`** → MockNAV kent 23559
  niet → val door naar `manual`. ⇒ 0/3.
- **In prod (echte nav2018) zou `get_item(23559)` slagen → match conf 0.9.** Dus 0/3 is grotendeels
  een *mock-artefact*; de échte vraag is C1 (foute kwabo-extractie) + C2 (gate-robuustheid).

### B2 — #944 BAUHAUS: klant → 10014 = MockNAV-artefact (geen prod-bug)
Het demo-bereik 10001–10016 is **leeg in prod** (geverifieerd). De match op 10014 kwam uit de
MockNAV-e-mailzoekstap (K2), niet uit de prod-mirror. ⇒ puur een lokaal mock-artefact.

### B3 — #954 TABS: klant 61793 via e-mail conf 1.0 (let op: stale alias, zie C3)
Op de stored extractie matcht #954 op 61793 via `email` conf 1.0. Dat is mede te wijten aan de
ene stale alias-rij (@pontmeyer.nl→61793). Vereist verse/echte meting om te bevestigen of de
FASE1-disambiguatie hier nu correct grijpt.

---

## C. Echte code-/extractie-/data-defecten (kandidaat-fixes voor Fase 4)

### C1 — Extractie vult `artikelnummer_kwabo` met niet-bestaande nummers (hallucinatie-risico)
Prod's stored extractie zette 804600/804555/804430 in `artikelnummer_kwabo`; geen ervan bestaat
in de artikelkaart-mirror. match_articles stap 1 vertrouwt dit veld **blind** (mirror-hit →
conf 1.0). Als zo'n verzonnen nummer ooit botst met een echt NAV-artikel → **confident fout
artikel zonder vlag (stille fout)**. *Te bevestigen met de bron-PDF (mogelijk is het een
EAN/klantcode i.p.v. hallucinatie).* Fix-richting: prompt instrueren nooit een Kwabo-nummer te
raden + stap 1 alleen vertrouwen als het nummer in de mirror bevestigd is met een tweede signaal.

### C2 — match_articles stap 2/3/4 zijn niet mirror-first (stap 1 wel)
Stap 1 is "mirror-first" (artikelkaart-mirror bevestigt bestaan zonder NAV). Stap 2
(kruisverwijzing), 3 (klantenkaart) en 4 (history) gate'en nog op een **live `nav.get_item`**,
óók als de artikelkaart-mirror het artikel al kent. Gevolg in prod: NAV-traagheid/-storing zet
goede mappings stil op `manual` → review-ruis. Fix-richting: bevestig bestaan via
`ArtikelkaartRepo.get()` (mirror) met `nav.get_item` alleen als fallback — symmetrisch met stap 1.

### C3 — Stale/contradictoire e-mail-alias
De enige alias-rij mapt `@pontmeyer.nl → 61793` (label: "fix-ronde 11-06"). Dat is precies de
**oude foute** TABS→PontMeyer-mapping die FASE1 corrigeerde. Een pontmeyer-domein-order kan
hierdoor weer naar 61793 worden geduwd. Fix-richting: deze rij heroverwegen/verwijderen en de
alias-tabel bewust vullen (of leeglaten) i.p.v. één stale relikwie.

---

## D. Meet-beperkingen

### D1 — MockNAV-vervuiling — OPGELOST met mirror-backed NAV-stub
Aanvankelijk vervuilde MockNAV de lokale meting (K2 → demo-klanten 10001–16; get_item-gate faalt
voor echte artikelen). **Opgelost** door `NAVISION_MODE=mirror` (`navision_mirror.py`): get_item/
search_items/search_customers lezen nu uit de gesyncde prod-mirror. Daarmee is offline klant- +
artikel-matching faithfully meetbaar zonder live NAV. Bewijs: #941 ging van 0/3 (mock) → **3/3
(mirror, klantenkaart conf 0.9)**, #944 van 10014 (mock-demo) → **61854 Bauhaus (correct)**.

---

## E. FAITHFUL METING (mirror-NAV) — wat de echte matching doet

### E1 — De 3 gerapporteerde orders zijn onder faithful meting CORRECT
| order | klant | ship-to | artikelen | eenheden | oordeel |
|---|---|---|---|---|---|
| #954 TABS | 50094 Jongeneel Woerden (leveradres, 0.9, **vlag**) | 3449 JE | 228321 exact_klantnr | PALLET 1 | correct + vlag |
| #944 BAUHAUS | 61854 Bauhaus (naam, 0.8, **vlag**) | 7559 SR Hengelo | 238531 exact | STUK 45 | correct + vlag |
| #941 PPG | 61483 Driessen (naam, 0.8, **vlag**) | 4814 RR | 23559/23522/23523 klantenkaart 0.9 | STUK45/PAL2/PAL2 | correct + vlag* |

\* #941: geëxtraheerd afleveradres `4815 PN Breda` ≠ gekozen ship-to `4814 RR` — **te verifiëren**
tegen grondwaarheid (kan correcte Breda-ship-to zijn of een ship-to-fout).

⇒ Op deze 3 orders zijn er **geen verkeerde matches** — wat het team op déze orders zag was óf het
oude mock-artefact óf de review-vlag. **De échte foute orders van het team zitten elders** (D3).

### E2 — Review-last gekwantificeerd (50 recente orders) — DE "te veel review"-klacht
- **43/50 orders gevlagd (86%).** Dominante oorzaak: **klant_match 41/50.**
- Klant match-bron: **email (conf 1.0, géén vlag) = 9/50 (18%)**; naam_extract (0.8) = 23; ship-to
  (0.9) = 10; géén match = 8. ⇒ **alleen een afzender-e-mail-op-kaart vermijdt de vlag**; 82% wordt
  gevlagd, óók als de match correct is (zie E1).
- Artikel-matching is juist gezond: **113 regels, 6 unmatched (95% gematcht)** (exact 69,
  exact_klantnr 24, klantenkaart 6) — ondanks de bijna-lege relationele tabellen, doordat klanten
  Kwabo-eigen nummers bestellen.
- Mix_uom-vlaggen (13) zaten allemaal op **één** 12-regelige mix-order; ship_to slechts 2.

**Kernconclusie:** de "te veel review"-klacht is echt en zit vrijwel volledig in **klant-review**:
het systeem vraagt voor 82% van de orders handmatige klant-akkoord omdat alleen een e-mailmatch
conf 1.0 haalt. Dit is een **business-afweging** (vlaggen-vs-auto-akkoord-risico), te kalibreren
zonder stille-fout te introduceren (bv. sterke unieke naam+ship-to-overeenkomst → hogere conf).

---

## F. GEGRADEERD tegen grondwaarheid — 14 PUSHED orders (NAV accepteerde = bevestigd)

GT gebouwd uit de 14 `pushed` orders (`order_log.status='pushed'`, NAV gaf VO-nummer). **Let op twee
meetvalkuilen die ik eruit heb gefilterd:**
1. **GT-contaminatie:** pushed orders zijn met PRÉ-fix-code gepusht → hun opgeslagen state bevat de
   ÓUDE waarden. Bewezen: #944 GT ship-to `3981 LB` (de oude Bunnik-bug) vs harness `7559 SR` Hengelo
   (de FASE1-fix); #941 GT eenheid `M1PAL30` (oude bug) vs harness `PALLET` (f98482c-fix). Dat zijn
   dus **de fixes die werken**, geen regressies.
2. **Klant-cascade:** als de klant afwijkt, wijken ook ship-to + artikel-mappings van die klant af —
   dat zijn geen losse ship-to/artikel-bugs.

**Na filtering blijft één echt signaal over — klant-automatch ≠ mens (6/14, allemaal GEVLAGD):**
| order | mens (bevestigd) | automatch | type |
|---|---|---|---|
| #121/#567/#833 | 61793 (PontMeyer-umbrella) | 61047/60995/61019 (tak-specifiek) | TABS-agentmailbox → PontMeyer-takken |
| #516/#847 | 60103/61532 | 61502/61816 | Werkzeuge-Dietrich → Duitse eindklant (**Strecken**) |
| #537 | 50000 | 50789 | BMN multi-vestiging |

**Root cause (geverifieerd):** alle 6 zijn **agent-/distributeur-/multi-vestiging-orders** — de
afzender-e-mail staat op géén klantenkaart; de order moet op leveradres naar een specifieke
klant/vestiging. Dit is exact de **Strecken/dropship-disambiguatie** die deels is uitgesteld
(funct1 DEEL B). **Allemaal gevlagd → géén stille fout**, maar mens en automatch kiezen een andere
(vaak specifiekere) klant. ⇒ leest als "matching verkeerd" ÉN "te veel review" tegelijk.

**Eindstand graded (na correcte filtering): 0 bevestigde stille fouten.** Het systeem is grotendeels
veilig (vlagt onzekerheid). De échte pijn = **review-volume op agent/distributeur/multi-vestiging-
orders** + parser-kolomverwisseling (C1) + review-kalibratie.

---

## G. PARSER-CHECK (alle 318 opgeslagen extracties — wat prod's parser produceerde)

- **315/662 regels (48%): `artikelnummer_kwabo` bestaat NIET in de artikelkaart-master.** Mechanisme
  (uit voorbeelden #816/#522/PPG): de LLM zet de **klant-SKU** in het *Kwabo*-veld en het echte
  Kwabo-nummer in het *klant*-veld — **kolommen verwisseld**. Vandaag opgevangen door match_articles
  stap 1b, maar het is een echte parser-semantiek-bug + stille-fout-risico bij botsing met een echt
  artikel. Fix: prompt — nooit een klant-/EAN-nummer in `artikelnummer_kwabo`; leeg laten of alleen
  een echt Kwabo-nummer.
- **228/318 orders (72%): `klantnaam_besteller` leeg** → verzwakt de naam-gebaseerde klant-match
  (K3) → meer agent-orders zonder naam-signaal → meer review.
- 20 regels zonder enig artikelnummer; 3 regels `hoeveelheid<=0`; 0 zonder eenheid.
- *Beperking:* dit analyseert wat de parser produceerde; de Vision-laag (raw PDF) is niet
  her-getest — daarvoor zijn verse .eml's nodig (D2).

---

## I. DOORGEVOERDE FIXES (24-06, getest)

| Fix | Wat | Bewijs |
|---|---|---|
| **C2 match_articles mirror-first** | stap 2/3/4 bevestigen artikel via de mirror i.p.v. een verplichte live `nav.get_item` → NAV-traagheid/-storing zet een geldige mapping niet meer stil op `manual` | 3 nieuwe tests + suite 678 groen |
| **C1 parser-prompt** | `extract_v2.txt`: nooit een Kwabo-nummer raden; bij twijfel/EAN → `artikelnummer_klant` (veilig geverifieerd) | nog te meten op verse e-mails |
| **A2 review-kalibratie** | naam-match die UNIEK door de leverpostcode wordt bevestigd (2 onafhankelijke signalen) → conf 1.0, géén vlag; gedeelde/afwijkende postcode → blijft gevlagd; agent-pad (`leveradres_shipto`) bewust uitgesloten | 3 tests; **review-last 50-sample 86%→64%**; **18/18 niet-gevlagde orders == mens-bevestigde klant (0 fout-akkoord)** |
| **UI (6×)** | zie sectie H | — |

**Agent/Strecken-routing (b): NIET blind gewijzigd.** De umbrella-vs-vestiging-keuze (PontMeyer 61793
vs takken; Werkzeuge-Dietrich→Duitse eindklant) is een **business-regel** die ik niet ken — fout
"corrigeren" zou het erger maken. Agent-orders blijven correct gevlagd. Vereist bevestiging van het team.

## H. UI-FIXES (gedaan, low-risk)

`frontend/` (Next 16). Gefixt: (1) order-detail-status toonde ruwe code (`not_order`) → `statusLabel()`;
(2) geslaagde afwijzing kleurde rood → `✓`-prefix; (3) Refresh-knop slikte fouten stil → `toast.error`;
(4) NeedsReviewBanner toonde ruwe veldcodes (`ship_to_gekozen`, regel-subvelden) → leesbare labels;
(5) dode `useEffect` + ongebruikte import verwijderd; (6) debug-`console.log` uit de logs-pagina.
Grotere UX-kans (apart, business-besluit): soft-CONTROLEER-velden niet hard laten blokkeren (nu
forceert élk gevlagd veld de "Tóch goedkeuren"-checkbox → de "te veel review"-beleving).

### D2 — Geen verse raw .eml → Vision-extractie niet te reproduceren
Opgeslagen orders missen de raw PDF-bytes; verse extractie draait dan alleen op de tekstlaag.
De #1-klacht (extractie/uitlezen) vereist de echte .eml's met PDF om Vision te testen.

### D3 — Geen concrete foutenlijst van het team (grondwaarheid ontbreekt)
Zonder per-order "verwacht vs. gekregen" kan de harness wel divergenties tonen, maar niet
betrouwbaar JUIST/FOUT scoren.

---

## Wat ik van jullie nodig heb om dit 100% af te maken

1. **De concrete foutgevallen van het team** — per order: ordernr, wat verwacht, wat het systeem
   deed (screenshots/exports). Dit is de grondwaarheid (D3).
2. **nav2018 read-credentials** (test-endpoint) — `NAV_BASE_URL`, `NAV_COMPANY`, `NAV_USERNAME`,
   `NAV_PASSWORD` — zodat klant/artikel-matching faithfully meet i.p.v. via MockNAV (D1).
   *Alternatief dat ik zelf kan bouwen:* een mirror-backed NAV-stub (get_item/search_items uit de
   gesyncde mirror) — dan kan ik offline faithful meten zonder live NAV.
3. **Een handvol verse echte .eml's** (met PDF-bijlage) van de probleemorders — voor de
   Vision-extractietest (D2). Droppen in `C:\Kwabo\data\inbox` volstaat.

## Voorlopige fix-agenda (na input hierboven)
- **Data (grootste hefboom):** vul de relationele masterdata (kruisverwijzing volledig verifiëren,
  klant-artikel-mappings, prijsafspraken) → halveert review-ruis zonder code te versoepelen.
- **C2** mirror-first maken voor stap 2/3/4 (robuustheid + minder review-ruis bij NAV-traagheid).
- **C1** extractie-prompt: nooit Kwabo-nummers raden; stap-1-vertrouwen aanscherpen.
- **C3** stale alias opruimen.
- **Harness:** mirror-backed NAV-stub bouwen zodat de meting niet langer op MockNAV leunt.
