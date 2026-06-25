# GO_OVERDRACHT — Finale GO-check overdrachtsmail

> **ACTUEEL EINDOORDEEL (12-06-2026, 16:18): GO** — alle 4 acties uit §3 zijn uitgevoerd en vers bewezen, zie §1c. De concept-mailalinea in §5 kan gebruikt worden. §1 en §1b hieronder zijn de historie van 11-06 en de tussenstand van 12-06 14:47.

**Datum/tijd check:** 11-06-2026, 23:08–23:17 (alle probes vers, timestamps per check hieronder)
**Gecheckt door:** read-only GO-check (plan goedgekeurd 11-06 ±23:05); géén code-, config-, DB- of NAV-wijzigingen gedaan
**Gedeployde ref:** `main` @ `988136d` (merge PR #3 = `feat/fase2-matching` @ `b2af07d`)

---

## 1. EINDOORDEEL: **NO-GO** (vanavond) — morgen vroeg haalbaar GO na 4 acties

**Eén zin waarom:** de gevalideerde code staat correct live en al het lokale bewijs is vandaag opnieuw groen, maar de productie-pipeline kan op dit moment géén enkele nieuwe mail verwerken (Anthropic-API-limiet bereikt; 2 echte mails vanavond in quarantaine), de verplichte items-sync na deploy is niet gedraaid (geen pallet-notatie → acceptatietest stap 6 faalt op het oog) en er staan 5 demo-orders in de review-queue die Nico morgen als eerste ziet.

Alle blokkades zijn Cas-acties van bij elkaar < 30 minuten + één hercheck. De overdrachtsmail kan daarna alsnog — de concepttekst staat klaar in §5.

---

## 1b. HERCHECK 12-06-2026, 14:47–14:53 (read-only): **nog steeds NO-GO — 3 van de 4 acties open**

| Actie uit §3 | Waargenomen (vers, 12-06) | Status |
|---|---|---|
| 1. Anthropic-limiet | 14:50:26Z — pipeline verwerkt sinds 07:57 weer mails: 18 mails verwerkt (orders 770–787), laatste quarantaine-alert 07:26:14Z, daarna geen enkele meer; poller 225 ticks / 0 failed | ✅ **OPGELOST** |
| 2. Quarantaine-mails herverwerken | 14:52 — inmiddels **6** gequarantainede mails (2 van gisteravond + 4 van vanochtend 06:00–07:26, vóór de limiet-fix). SQL-bewijs: **géén** van de 6 email-ids komt voor in `order_log`; de id-reeks loopt er naadloos omheen (…W611K = #769 → gat W611L/M + XvNpr–u → hervat bij XvNpv = #770). Ze staan als-gelezen in de mailbox en zijn dus nooit verwerkt — daar kunnen echte klantorders tussen zitten | ❌ **OPEN** (nu 6 i.p.v. 2) |
| 3. Items-sync | 14:50:51Z — `verkoop_eenheid` nog steeds 0× gevuld (van 3757 artikelkaarten); `artikel_eenheden` = 12963 (oude baseline) | ❌ **OPEN** |
| 4. Demo-orders | 14:50:51Z — ids 4, 6, 7, 137, 139 staan alle vijf nog in status `review` (queue: 232) | ❌ **OPEN** |

**Wel nieuw groen bewijs:**

- **A1/A3 opnieuw bevestigd (14:47–14:49):** `/api/version` = `988136d`; live Vercel-orderdetailpagina (#785, met cookie) bevat "Bevestig deze klant", CONTROLEER-badge en `order-warnings-banner` in zowel de server-gerenderde HTML als de route-chunk; API-base correct.
- **Deel C nu wél bewezen (14:51–14:52):** 5 verse orders van vandaag door de nieuwe code beoordeeld — **0 stille fouten**:
  - #770 (Stukbouw, klant conf 1.0): artikelen niet gematcht → eerlijk `manual`/conf 0.0 + review-vlaggen + 0 ops mét leesbare reden;
  - #771 (PontMeyer via TABS-domein, conf 1.0): beide regels exact conf 1.0, expliciete UoM in de ops, 0 review-velden;
  - #772 (EinzA, naam_extract conf 0.8): **`klant_match`-vlag gezet** (CONTROLEER-gedrag werkt live) + ROL→STUK-twijfel per regel gevlagd;
  - #776 (Van Dongen, conf 1.0): PAL→STUK-conversie gevlagd (`orderregels[0].eenheid`), preview 11 ops met `customerNumber` 61472;
  - #785 (KCN via exact.com, naam_extract conf 0.8): klant-vlag + eenheid-vlag, preview-reden "1 veld vereist aanvulling vóór push".
  - Bijlage-download #776: token-mint → HTTP 200, `application/pdf`, 261.570 bytes, geldige PDF-magic (14:52:33Z).
- De vele `eenheid`-reviewvlaggen op PAL-regels zijn precies het zichtbare gevolg van de ontbrekende items-sync (actie 3): veilig gevlagd in plaats van stil fout, maar acceptatietest stap 6 (pallet-notatie) faalt zolang de sync niet is gedraaid.

**Conclusie hercheck:** het zwaarste risico (pipeline dood door API-limiet) is weg en deel C is alsnog gesloten. Resterend vóór de mail: acties 2, 3 en 4 — samen ~15 min Cas-werk + korte hercheck van die drie punten.

---

## 1c. UITVOERING RESTPUNTEN 12-06-2026, 15:16–16:18 — **GO**

Alle 4 acties uitgevoerd (plan goedgekeurd; read-only richting NAV gehandhaafd — de sync leest NAV en schrijft alleen de eigen DB) en afgesloten met de 5-punts-hercheck. Eindstand:

| # | Actie | Uitvoering + bewijs (vers, 12-06) | Status |
|---|---|---|---|
| 1 | Anthropic-limiet | Was al opgelost vóór deze ronde (§1b). Nulmeting 15:16:37Z én hercheck 16:18:21Z: **0 nieuwe** `intake_mail_quarantined` (de 6 oude alerts blijven historisch in de ringbuffer staan); poller 241 ticks / 0 failed | ✅ |
| 2 | 6 quarantaine-mails herverwerken | 16:10:08Z: alle 6 via Graph `PATCH isRead=false` (6× HTTP 200; token via read-only SELECT uit `oauth_tokens`, nooit gelogd). Poller pikte ze op: **6/6 in `order_log` om 16:17:32Z** (id-suffix-match). Uitkomst: #789/#790/#793 = `not_order` met leesbare, correcte reden (nieuwsbrief / sollicitatie / nieuwsbrief); #791 (doorgestuurde "Bestelling", klant 60409 naam_extract 0.8) → klant-vlag + alle 3 regels eerlijk `manual` + 0 ops; #792 (Olijslager 61667, 0.8) → klant-vlag, artikel exact 1.0, expliciete `unitOfMeasureCode`-patch; #794 (PPG 60282, conf 1.0) → 3 regels exact 1.0, `mix_uom`-reviewvlaggen (veilig mix-gedrag). **0 stille fouten → deel C definitief gesloten** | ✅ |
| 3 | NAV-items-sync | Job `3d26a8535aaa` gestart 15:17:24Z, klaar 16:09:07Z, `state=done`, 0 errors: customers 1787/1787, items 3757/3757, cross_ref 3000 upserted (1659 skipped), ship_to 2506/2510, item_uoms 12963/12971. SQL 16:18:28Z: `verkoop_eenheid` **3718** gevuld (was 0), `artikel_eenheden` 12963. verify_fase3 (sqlite-guard geciteerd) 15:26:45Z: `2 x PALLET33` + expliciete UoM-patch + geforceerde ROL → 400 | ✅ |
| 4 | Demo-orders weg | 15:17:05Z: DELETE 4/6/7/137/139 (5× `{"ok":true}` na klantnr-precheck 10003–10016). Hercheck 16:18: API-queue 0 demo-klantnrs, SQL 0 rijen, ids bestaan niet meer | ✅ |
| 5 | Suite | 15:26:36–15:28:33Z met `ADMIN_PASSWORD=""`: **593 passed / 17 skipped** | ✅ |

**⚠️ Belangrijke operationele waarneming (voor §7 open punten):** tijdens de volledige 5-domeinen-sync (52 min) was de **HTTP-API vrijwel onafgebroken onbereikbaar** (upstream errors / timeouts 15:19–16:09; twee korte vensters daargelaten). De app herstelde zonder restart en de poller miste geen ticks blijvend, maar: **draai de volledige nav-sync buiten kantooruren** of per domein apart. Dit is dezelfde event-loop-verhongering als de outages van 2-6; de thread-offload dekt het kennelijk niet volledig bij de bulk-domeinen.

**Kanttekeningen (eerlijkheid):**
- Bestaande orders van vóór de sync (bv. #776) houden hun STUK-keuze + `eenheid`-reviewvlag — preview componeert uit opgeslagen state; alleen mails die ná de sync verwerkt worden krijgen pallet-notatie automatisch. Voor de queue-backlog blijft de reviewvlag de vangrail.
- cross_ref: 1659 van 4659 rijen geskipt (skip-redenen in de job-output; geen errors). Niet onderzocht — staat los van de 4 acties, maar benoemd voor volledigheid.
- verify_fase3 bewijst het code-gedrag op een fixture; het prod-data-bewijs is de SQL-count (3718).

---

## 2. CHECKTABEL A1–E4

| Check | Waargenomen (vers, 11-06) | Verwacht | Status |
|---|---|---|---|
| **A1** versie live | 23:08:48 — `GET /api/version` → `988136d5a2b8…` = merge PR #3; `b2af07d`, `c08a637`, `af3c218`, `9a7fdf9`, `4e39dd3` allemaal ancestor van `origin/main` (`git merge-base --is-ancestor`) | gevalideerd commit + complete fix-ronde live | ✅ PASS |
| **A2** git-staat | 23:08 — `git fetch`; `origin/main..feat/fase2-matching` leeg (alles gemerged); tracked tree schoon; `git diff origin/main HEAD -- backend/ frontend/` leeg → lokale HEAD = gedeployde code. Untracked: alleen validatie-artefacten (zie §4 punt 7) | branch gemerged, geen ongecommit validatie-werk in code | ✅ PASS |
| **A3** frontend live | 23:13 + 23:16 — `kwabo-pilex.vercel.app` redirect naar `/login` (auth-middleware); API-base `kwabo-production.up.railway.app` in de live bundle; strings "Bevestig deze klant", "CONTROLEER" (badge) en `order-warnings-banner` in de live JS-chunks (pagina `/orders/767` met cookie, HTTP 200). Compose-reden komt uit de backend (preview.py:170) en is live geprobed (zie C2) | juiste backend + nieuwe UI-elementen aanwezig | ✅ PASS |
| **B1** items-sync na deploy | 23:10:50 — kolom `artikelkaarten.verkoop_eenheid` bestaat (aangemaakt door startup-migratie, session.py:107) maar **0 van de rijen gevuld**; `artikel_eenheden` = 12963 = oude baseline van 2-6 (geen verse sync) | sync gedraaid: `verkoop_eenheid` gevuld > 0 | ❌ **FAIL** |
| **B2** artefact-opruiming | 23:10:50 — rij 517 bestaat niet meer (verwijderd 11-06 20:55, rapport §5.7c) ✓; máár scan vond **5 demo-orders in status `review`**: ids 4, 6, 7, 137, 139 (klantnrs 10016, 10009, 10003, 10014) — om 23:13 bevestigd zichtbaar via `GET /api/orders?status=review` (queue: 224 items) | review-queue vrij van demo-artefacten | ❌ **FAIL** |
| **B3** 127 mixprijzen-vlaggen | 23:10:50 — count = 127; 60203 (Veris) = True, 60282 (PPG) = True, 60659 (ProCoatings) = True. Herkomst onbeantwoord. Veilig gedrag vandaag opnieuw bewezen: N10-run 23:11:51 zet mix-eenheden op review (`mix_uom:*`-vlaggen), geen automatische staffel zonder bevestiging | herkomst beantwoord ÓF veilig gedrag + benoemen als beperking | ⚠️ PASS als bekende beperking (staat in §5-mail + §6) |
| **B4** incident-nasleep | 23:10:50 — klantenkaarten = 1787 (exact schone baseline); 0 klanten in 10001–10016; 0 demo-rijen in `klantenkaart_artikelen` en `artikel_kruisverwijzing`; guard-commit `af3c218` zit in de gedeployde ref (A1) | schone baseline + guard live | ✅ PASS |
| **B5** ops-vlaggen | 23:13:01 — mailbox: `graph`, connected, `pilex@kwabo.nl`, token-expiry 21:49:50Z (= 23:49 lokaal, toekomst) met werkende auto-refresh (laatste 20:33Z); poller: 15 ticks / 0 failed, laatste poll 23:08:32 lokaal; `storage_active` = true; `admin_password` set, `jwt_secret` 64 tekens en niet dev-default. **Máár:** alerts bevatten 2× `intake_mail_quarantined` (severity high, 20:53:25Z en 21:13:36Z) — oorzaak: *"You have reached your specified API usage limits. You will regain access on 2026-07-01"* (Anthropic). Geen `nav2018_stepwise_failure`, geen `intake_source_eml_save_failed` | mailbox/poller/storage OK én geen onverwachte recente failures | ❌ **FAIL** (op de API-limiet; infra zelf is groen) |
| **B6** MAIL_MODE | 23:13:01 — `mail_mode=log` (diagnostics/config), `email_mode=graph` | consistent met overdrachtsmail | ✅ PASS — mailtekst in §5 belooft expliciet géén automatische bevestigingsmails |
| **C1** verse orders door nieuwe code | 23:10–23:15 — 0 orders in `order_log` sinds deploy (21:56 lokaal); laatste order #769 om 14:51. Er kwamen wél 2 echte mails binnen ná de deploy — beide gequarantained door de API-limiet (B5) | ≥ 3 verse orders beoordelen | ❌ **FAIL / niet-uitvoerbaar** (geen valse smoke gedaan) |
| **C2** kwaliteit van wat er is | 23:13–23:16 — #767 (oude-code-intake, vandaag 13:01): klant eerlijk NIET gematcht mét warning, artikel JOKA→22249 conf 1.0 via kruisverwijzing, bijlage-download via getekende URL → HTTP 200, `application/pdf`, 447.474 bytes. Live op de nieuwe backend: preview #767/#765 → 0 ops mét leesbare reden ("Geen klant gematcht — kies eerst een klant…") en correcte needs-review-velden | geen stille fouten; vlag-gedrag correct | ✅ PASS op het beschikbare (maar géén vervanging voor C1) |
| **C3** stille fouten | in alles wat vandaag bekeken is (C2 + D3-herverwerking): 0 stille fouten | 0 | ✅ geen waargenomen — volledige check pas mogelijk na actie 1 |
| **D1** volledige suite | 23:14:56–23:16:35 — **593 passed / 17 skipped** op HEAD (= byte-identiek aan gedeployde code, zie A2). Kanttekening: eerste run gaf 52 fails doordat het zojuist aan `backend/.env` toegevoegde `ADMIN_PASSWORD` in de testomgeving lekte; geverifieerd door herrun met `ADMIN_PASSWORD=""` (5 representatieve fails → groen, daarna volledige suite groen). Lokaal test-env-gat, géén prod-issue — zie §4 punt 6 | 593/17 | ✅ PASS |
| **D2** LLM-regressie | 23:16:35–23:16:43 — **17/17 passed** (8s → cache-replays, zoals bij de eindvalidatie; verse API-calls zijn momenteel sowieso onmogelijk door de limiet) | 17/17 | ✅ PASS (met cache-kanttekening) |
| **D3** verify-scripts | 23:11:47–23:11:51 — guards vooraf in de bron bevestigd (alle drie: temp-sqlite + mock-NAV vóór elke import). verify_fase2: klant/artikel-uitkomsten conform; verify_fase3: 2×PALLET33, europallet 2×19820, geforceerde ROL-PATCH → 400, mix-staffels M2PAL33/M1PAL30/M7PAL30/M10PAL30; verify_eindvalidatie_n10: exit 0, E6-check "geen enkele operation bevat unitPrice/description — OK" | uitkomsten onveranderd t.o.v. EINDVALIDATIERAPPORT | ✅ PASS |
| **E1** rapport actueel | EINDVALIDATIERAPPORT klopte vanmiddag; 3 zaken zijn achterhaald → addendum-tekst in §6 (rapport zelf niet aangepast — read-only) | addendum aangeleverd | ✅ gedaan |
| **E2** acceptatietest-script | stappen kloppen met de live UI (A3-bewijs voor de knoppen); stap 0 herformuleren: deploy ✓ gedaan, **NAV-sync ✗ nog te doen** (B1); stap 6 en 7 pas zinvol ná die sync; herformulering in §6 | script uitvoerbaar zoals beschreven | ⚠️ na actie 3 |
| **E3** open-puntenlijst | geactualiseerd in §7 | actueel | ✅ gedaan |
| **E4** rollback-plan | alinea in §8 | concreet | ✅ gedaan |

---

## 3. ACTIELIJST (alle vóór morgenvroeg haalbaar)

| # | Actie | Wie | Tijd | Hercheck (read-only) |
|---|---|---|---|---|
| 1 | **Anthropic-API-limiet opheffen**: in de Anthropic Console de usage-limit van de prod-key verhogen, of een andere key zetten in Railway (`ANTHROPIC_API_KEY`) + redeploy/restart | Cas | ~10 min | `/api/diagnostics/health-summary` → volgende poll zonder `invalid_request_error` |
| 2 | **2 quarantaine-mails herverwerken** (ná actie 1). Volgens de code (intake_trigger.py:190) staan ze nog in de mailbox, gemarkeerd als gelezen — *aanname, nog niet zelf waargenomen*: markeer ze ongelezen of trigger handmatige intake; email-ids staan in de alerts (20:53:25Z en 21:13:36Z) | Cas | ~5 min | beide verschijnen als order in de queue, klant/artikel met vlag-gedrag, geen stille fout → **dit sluit alsnog deel C** |
| 3 | **NAV-items-sync draaien**: `POST /api/admin/nav-sync?domains=customers,items,cross_ref,ship_to,item_uoms` | Cas | ~5 min (+ syncduur) | SQL: `verkoop_eenheid` not-null count > 0; `artikel_eenheden` ≥ 12963 |
| 4 | **Demo-orders 4, 6, 7, 137, 139 uit de review-queue** (reject met reden "demo-artefact", of `DELETE /api/orders/{id}?confirm=true`) | Cas | ~5 min | `GET /api/orders?status=review` → geen klantnrs 100xx meer |

Daarna één hercheck-ronde (read-only, ~10 min) en de mail kan de deur uit.

---

## 4. EERLIJKHEIDSPARAGRAAF — beperkingen van deze check

1. **Read-only-afdwinging op DB-niveau mislukte technisch:** de pgbouncer-pooler (poort 6543) geeft startup-options niet door — `SHOW default_transaction_read_only` gaf `off`. De discipline was uitsluitend `SELECT`; er is niets geschreven, maar de harde rem zat niet op de verbinding.
2. **Twee POST-calls gedaan, beide state-loos:** `/api/auth/login` (token-uitgifte) en `/api/orders/767/bijlagen-token` (mint van een download-token; code geverifieerd: geen DB-write, orders.py:657–672).
3. **C is niet bewezen:** er is sinds de deploy geen enkele mail succesvol door de nieuwe code gegaan (API-limiet). De 2 binnengekomen mails zijn gequarantained. "Echte nieuwe mails door de nieuwe code" blijft dus open tot actie 1+2 zijn gedaan — exact het gat dat de eindvalidatie al benoemde.
4. **D2 draaide op cache-replays** (8 s voor 17 tests): pipeline-code vers bewezen, LLM-antwoorden zijn deterministische replays. Een verse API-call was vanavond per definitie onmogelijk (limiet).
5. **Tijdzone-aanname bij C1:** `order_log.created_at` is timezone-naïef; onder zowel de UTC- als lokale-tijd-lezing zijn er 0 orders ná de deploy.
6. **Test-env-gat (lokaal):** `tests/conftest.py` neutraliseert `DATABASE_URL` maar niet `ADMIN_PASSWORD` — een gevuld `.env`-wachtwoord laat 52 API-tests falen. Workaround vandaag: `ADMIN_PASSWORD=""` als env-var. Kleine fix voor later; geen prod-impact.
7. **Untracked validatie-tooling:** `scripts/verify_eindvalidatie_n10.py`, `scripts/export_shipto_masterdata.py` en de fixtures onder `tests/test_data/states/` zitten niet in git. De vandaag gedraaide verificatie is daardoor niet reproduceerbaar vanaf de repo alleen — committen aanbevolen (geen blokkade voor de mail).
8. **Review-queue telt 224 items** — historische backlog, geen nieuw-code-probleem, maar wel iets om in de verwachtingen richting het team te benoemen (zij gaan die queue nu actief gebruiken).

---

## 5. CONCEPT-ALINEA OVERDRACHTSMAIL (verzenden zodra §3 groen is)

> Beste Nico, beste team,
>
> De vernieuwde order-intake staat sinds gisteravond live. De klachten waarmee dit traject begon — verkeerde artikelnummers, niet-gevonden klanten, bijlagen die niet openden — zijn stuk voor stuk aangepakt: in de eindvalidatie zijn 18 echte orders van jullie opnieuw door het systeem gehaald, met nul stille fouten (ter vergelijking: in de oude situatie ging het bij 20 van de 32 orderregels ongemerkt mis). Het systeem werkt nu volgens één principe: wat het zeker weet vult het in, en bij twijfel vraagt het zichtbaar om jullie bevestiging — een oranje melding bij de klant, een keuzelijst bij meerdere kandidaten, een leeg-maar-uitgelegd NAV-paneel als er iets ontbreekt. Elke correctie die jullie invoeren onthoudt het systeem voor de volgende keer. Twee dingen werken bewust nog niet: mixprijs-staffels gaan pas automatisch nadat onze NAV-partner het mixvlag-veld heeft opengezet (tot die tijd vraagt het systeem bij mix-eenheden altijd om bevestiging), en het origineel-document wordt nog niet aan de NAV-order gekoppeld (daar wacht een NAV-pagina op publicatie; jullie zien daarover een nette waarschuwingsbalk). Het systeem verstuurt verder géén automatische mails naar klanten — alles gaat pas naar NAV na jullie akkoord. Mogen we jullie vragen om morgen het acceptatietest-script van ±30 minuten door te lopen (bijlage)? Bel of mail gerust bij alles wat opvalt.

---

## 6. ADDENDUM-TEKST VOOR EINDVALIDATIERAPPORT.md (door Cas toe te voegen, niet door deze check gedaan)

> **Addendum 11-06, 23:17 (post-deploy GO-check):**
> 1. De kopregel "deze branch is dus nog NIET gedeployed" is achterhaald: PR #3 is gemerged en `/api/version` toont `988136d` (geverifieerd 23:08). Al het pre-deploy-bewijs geldt daarmee voor de draaiende productie; suite (593/17), LLM-regressie (17/17) en de verify-scripts zijn op 11-06 23:11–23:16 opnieuw groen gedraaid.
> 2. Open punt §5.4 (items-sync) is **nog niet uitgevoerd**: `verkoop_eenheid` is in prod aanwezig maar leeg (0 rijen, 23:10). Acceptatietest stap 0 luidt daarom nu: "Deploy is gedaan (✓ 988136d); draai vóór de test eenmalig de NAV-sync en controleer dat de pallet-notatie in een Würth-achtige preview verschijnt." Stappen 6 en 7 zijn pas zinvol ná die sync.
> 3. Nieuw incident: op 11-06 20:53Z en 21:13Z zijn 2 echte mails gequarantained omdat de Anthropic-API-maandlimiet is bereikt ("regain access 2026-07-01"). Tot de limiet is verhoogd verwerkt de pipeline géén nieuwe mails; de eerlijkheidsparagraaf-regel "echte nieuwe mails door de nieuwe code" is dus nog steeds niet bewezen.
> 4. De artefact-opruiming (§5.7c) was beperkt tot rij 517; de demo-orders 4, 6, 7, 137 en 139 (klantnrs 100xx) staan nog in de review-queue.

---

## 7. OPEN-PUNTENLIJST (actueel per 11-06 23:17)

1. **NIEUW + BLOKKEREND: Anthropic-API-limiet** — zie actielijst 1; zonder dit staat de hele intake stil tot 1-7.
2. **Items-sync na deploy** (actielijst 3) — was al open punt §5.4, nu met vers bewijs dat hij nog niet gedraaid is.
3. **Demo-orders in queue** (actielijst 4).
4. **7002-expertvraag** — onveranderd open bij de NAV-expert.
5. **PLX_IncomingDocument-page** — wacht op NAV-partner; waarschuwingsbanner live bevestigd (A3).
6. **OPS-item g: mixvlag** — NAV-veld 50013 via OData + `KlantOut.mixprijzen`; herkomst van de 127 prod-vlaggen (60203/60282/60659 alle True, 23:10) nog te verifiëren vóór mix live gaat. Veilig gedrag (review-vlag) opnieuw bewezen.
7. **MAIL_MODE=log** — bewuste keuze, consistent met de mailtekst; omzetten naar graph zodra het team bevestigingsmails wil.
8. **pgbouncer onder last** — alleen na-deploy onder echt verkeer meetbaar; vanavond geen poolfouten in de alerts gezien (wel: het verkeer was minimaal).
9. **Klein/lokaal:** conftest neutraliseert `ADMIN_PASSWORD` niet (§4.6); verificatie-scripts + fixtures committen (§4.7).

---

## 8. ROLLBACK-PLAN

Gaat er morgen iets ernstig mis met de nieuwe code: zet in Railway én Vercel een redeploy van de vorige ref `262f9dc` aan (beide platforms bewaren eerdere deployments — "Redeploy" op de laatste main-deploy van vóór 11-06 21:56; geen git-revert nodig). De database hoeft niet teruggedraaid: de nieuwe kolommen (o.a. `verkoop_eenheid`) zijn door de startup-migratie additief toegevoegd en worden door de oude code genegeerd, en de domein-aliastabel bestond al (de oude code heeft geen K2b-stap en gebruikt hem niet). Orders die intussen door de nieuwe code zijn verwerkt blijven gewoon in `order_log` staan en zijn in de oude UI reviewbaar; alleen nieuwe-code-velden (preview-reden, CONTROLEER-vlaggen) verliezen hun weergave. Let op: ook na rollback blijft de Anthropic-limiet gelden — actie 1 is in elk scenario nodig.

---

*Alle waarnemingen in dit document zijn van 11-06-2026 23:08–23:17, read-only verkregen (GET-probes, SELECT-queries, lokale test-runs met sqlite-guards). Wat niet vers verifieerbaar was, staat als zodanig gemarkeerd — niet als groen.*
