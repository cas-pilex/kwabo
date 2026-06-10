# FASE 0 — Nulmeting Kwabo Order Intake (productie)

> Datum: 2026-06-09 · Methode: read-only · Backend: `kwabo-production.up.railway.app`
> (Railway) · Frontend: `kwabo-pilex.vercel.app` (Vercel) · DB+Storage: Supabase.
> Referentie-audit: `KWABO_TECHNISCHE_AUDIT.md` (2026-05-28). Waar de audit afwijkt van de
> gemeten realiteit staat dat expliciet als **AUDIT ACHTERHAALD**.
>
> Read-only uitgevoerd: file-reads + admin-gated diagnostics-GETs + read-only API-aggregaties.
> Geen code/config/DB-wijziging, geen migraties, geen NAV-writes, geen OAuth connect/disconnect.

## Samenvatting (TL;DR)

- Backend, NAV, DB, Supabase Storage en de poller draaien; **mailbox is `connected=true`** en
  mails komen binnen (laatste order id=720, 2026-06-09T11:52). De Graph access-token ververst
  automatisch via de refresh-token (`offline_access` werkt). *NB: bij een eerdere probe (~11:15)
  stond de mailbox kort `connected=false`/`degraded` — een transiënte staat (access-token net
  verlopen, refresh nog niet gevuurd) die zichzelf herstelde; geen actie nodig.*
- Veel audit-zorgen zijn al opgelost: **ephemere-FS** (nu Supabase Storage, live bewezen),
  **MAIL_POLL_INTERVAL** (staat op 300), **NAV-master-sync** (gedraaid, alle counts > 0),
  **mixprijzen klant+artikel** (code gate't terecht alléén op de klantvlag),
  **incoming-doc download** (route bestaat en werkt).
- Echt openstaand: (1) `PLX_IncomingDocument` is NAV-zijdig 404 (inkomend document niet
  koppelbaar); (2) `mail_mode=log` (bevestigingsmails worden niet verzonden); (3) geen
  NAV-prijspage (tabel 7002) geëxposeerd → 7002-beslissteun is technisch niet te voeden vanuit
  NAV-webservices.

## Verificatietabel

| # | Punt | Verwacht | Waargenomen | Bewijs (commando → output) |
|---|------|----------|-------------|-----------------------------|
| A1 | order_log-stand | rijen/laatste/failed | **685 rijen**; laatste `created_at` = `2026-06-09T11:52:04` (order 720, status not_order); **failed = 1** | `GET /api/audit/stats` → `total_orders=685, by_status{not_order:454, review:213, failed:1, pushed:7, rejected:10}`; `GET /api/orders` gesorteerd → top id=720 created 2026-06-09T11:52:04 |
| A2 | diagnostics/config | prod-config gezet | `email_mode=graph`, `navision_mode=nav2018`, `nav_username_set=true`, `nav_password_set=true`, `database_url_kind=postgres`, `admin_password.set=true (len9)`, `jwt_secret_is_dev_default=false`, **`supabase.storage_active=true`**. MAIL_POLL_INTERVAL niet in deze dump, wél via mailbox-status (zie A3). | `GET /api/diagnostics/config` |
| A3 | mailbox/status | connected + token geldig | (verse probe 12:06) `mode=graph`, **`connected=true`**, `state=active` ("Graph verbonden als pilex@kwabo.nl"), `account_email=pilex@kwabo.nl`, **`expires_at=2026-06-09T12:25:43` (toekomst)**. **`poll_interval_seconds=300`, `poll_enabled=true`**, `last_poll_at=2026-06-09T12:02:07` `status=ok` `processed=0`, `last_token_refresh_at=2026-06-09T11:20:03`. *NB: vroege probe ~11:15 toonde transiënt `connected=false`/`degraded`; auto-refresh herstelde het.* | `GET /api/mailbox/status` |
| A4 | db-counts | > 0 ⇒ sync gedraaid | **klanten=1787, artikelen=3757, kruisverwijzingen=3000, ship_to=2506, artikel_eenheden=12963** → NAV-master-sync IS in prod gedraaid. | `GET /api/admin/db-counts` |
| A5 | uvicorn-workers | 1 = ok | `Procfile` + `railway.toml` starten kale `uvicorn` (geen `-w`/gunicorn) ⇒ **1 worker**. `GET /api/health` → `poller=alive` (één heartbeat, één `last_poll_at`) consistent met 1 worker. *WEB_CONCURRENCY niet via API zichtbaar — zie "Niet te verifiëren".* | `railway.toml:2`, `Procfile:1`, `GET /api/health` → `{status:ok, poller:alive}` |
| B6 | NAV page-probes | 200 per page | PLX_SalesOrder **200**, PLX_Customer **200**, PLX_Item **200**, PLX_ItemReference **200**, PLX_ShipToAddress **200**, PLX_ItemUnitOfMeasure **200**, **PLX_IncomingDocument 404**. | `GET /api/diagnostics/nav?page=<page>` per page |
| B7 | NAV services | incoming-doc + 7002? | 42 entity sets. Aanwezig: PLX_Customer, PLX_Item, PLX_ItemReference, PLX_ItemUnitOfMeasure, PLX_SalesOrder, PLX_SalesOrderLines, PLX_SalesOrderSalesLines, PLX_ShipToAddress. **GEEN PLX_IncomingDocument. GEEN Verkoopprijzen/7002/SalesPrice/Klantprijsgroep-page.** | `GET /api/diagnostics/nav/services` → `count=42`, names-lijst |
| C8 | .eml's op container-FS | bestaan na deploy? | Container-FS niet `ls`-baar vanuit deze sessie (geen Railway-shell). **Moot**: `storage_active=true` + alle 20 gescande recente review-orders hebben `storage_key=by_email_id/<id>-<hash>.eml` met **leeg `disk_path`** ⇒ .eml's staan in **Supabase Storage**, niet op de ephemere FS. | `GET /api/diagnostics/config` + scan `order_state` van 20 recente review-orders |
| C9 | incoming_document_path bestaat? | p.exists() | Recente orders hebben **geen** `incoming_document_path` (leeg) maar wél een Supabase `storage_key`. **Live retrieval bewezen**: order 716 → bijlage uit .eml-in-Supabase opgehaald = **HTTP 200, application/pdf, 37230 bytes, `%PDF-`**. De disk-`p.exists()`-vraag is achterhaald door Supabase. | `POST /api/orders/716/bijlagen-token` → `GET /api/orders/716/bijlagen?...&token=` → 200 application/pdf 37230 bytes |
| D10 | download-pad geüploade PDF | terug-leesbaar in browser? | **JA.** Upload `POST /{id}/incoming-doc` → Supabase `by_order/{id}/<naam>` (disk-fallback). Download `POST /{id}/incoming-doc-token` + **publieke** `GET /{id}/incoming-doc/file?token=` (resolve Supabase-first, disk-fallback). Losse PDF (geen .eml) is dus retrieveerbaar. .eml-bijlage-route ook live bewezen (C9). | `orders.py:879-993` (upload), `orders.py:1057-1133` (token+download), `supabase_storage.py` |
| E11 | checkt code klant **én** artikel? | audit zegt "beide" | **NEE.** `apply_mixprijzen.py:124-134` gate't **alléén** op `klant.mixprijzen`. Docstring r.12-14: artikel-vlag "unreliable and intentionally NOT required". → **AUDIT ACHTERHAALD** (§3 rij 7). | `apply_mixprijzen.py:124-148` |
| E12 | gate = alleen klantvlag? | klant tabel 18 veld 50013 | **Bevestigd.** Gate = `Klantenkaart.mixprijzen` ← sync van `PLX_Customer.Mix_Prices_Allowed`. Code leest géén artikel-vlag in de gate (`artikelkaarten.mixprijzen`/`artikel_eenheden.is_mix_uom` worden door de gate niet geraadpleegd). | `apply_mixprijzen.py:114-148` |
| E13 | herkomst prijzen/eenheidscodes; 7002-mirror? | hoe gekozen? | Mix-eenheidscodes uit **`ArtikelEenheid`** (mirror van PLX_ItemUnitOfMeasure, 12963 rijen prod), geparsed via `parse_mix_code`; units-per-pallet = `qty_per_base` (autoritatief, **niet** de PALxx-suffix). **Geen 7002-mirror** (geen DB-tabel + geen NAV-price-page, zie B7). Tool berekent **geen** prijzen — **NAV** prijst de regel bij push met mix-UOM. `prijsafspraken`-tabel = alleen >5%-sanity-warning in `validate_prices`, niet autoritatief. | `apply_mixprijzen.py:6-33,97-111`; `services`-lijst (geen price-page); audit §6.c (geen 7002-tabel) |
| E14 | Veris klantnr 60203 vs 60659 | welke is Veris? | **60203 = "Veris Bouwmaterialengroep B.V."** (`Inkoop_vlc@veris.nl`) = écht Veris. **60659 = "ProCoatings Leiden B.V."** (PPG, `Facturen.Inkoop.ProCoatings@ppg.com`) = **andere** entiteit, niet Veris. Naam-zoek 'veris' matcht alleen 60203. Feedback-nummer (60203) klopt; screenshot-60659 is een andere klant. *(Niets opgelost.)* | `GET /api/klanten/60203`, `GET /api/klanten/60659`, `GET /api/klanten` (filter naam~veris) |

## Niet (volledig) te verifiëren in deze read-only sessie

1. **Mixprijzen-vlagwaarde per klant (incl. Veris 60203).** `KlantOut` exposeert het
   `mixprijzen`-veld **niet** (velden: nav_klantnr, naam, email, email_bestelling, taal,
   is_4plus). "0 klanten met mixprijzen=true" via de API is dus een serialisatie-artefact,
   géén bewijs dat de vlag overal false is. Er is geen generieke SQL-endpoint en geen
   Supabase-DB-credential in deze sessie. → Nodig: directe DB-query óf `KlantOut` uitbreiden.
   Dit raakt de staande mixprijs-calibratie van Veris (we kunnen nu niet read-only bevestigen
   dat 60203 de mixvlag aan heeft).
2. **Aantal uvicorn-workers (hard).** Procfile/railway.toml = 1 worker; geen `WEB_CONCURRENCY`
   zichtbaar in de config-dump. Eén poll-heartbeat is consistent met 1 worker, maar 100%
   zekerheid vereist het Railway-dashboard (Variables).
3. **Container-FS-inhoud (`ls /app/data/...`).** Geen Railway-shell in deze sessie. Architectuur
   maakt het moot (Supabase is canoniek), maar een directe `ls` is niet uitgevoerd.
4. **Bevestigingsmail-aflevering.** `mail_mode=log` ⇒ er wordt alleen gelogd, niet verzonden;
   echte smtp/graph-verzending is niet getest.
5. **Monitoring/alerting (audit §14.10).** Niet onderzocht in FASE 0.

## OPS-lijst (acties die geen code zijn)

| # | Actie | Status nu | Nodig? |
|---|-------|-----------|--------|
| a | `MAIL_POLL_INTERVAL_SECONDS` in Railway | **al gezet = 300**, `poll_enabled=true` | ✅ geen actie |
| b | Graph re-login via `/email` (pilex@kwabo.nl) | `connected=true`, auto-refresh werkt (verse probe 12:06) | ✅ niet nodig nu — alleen als status blijvend `degraded` blijft |
| c | `offline_access`-consent bevestigen | refresh lukte eerder (`last_token_refresh_at` vandaag) ⇒ scope vermoedelijk OK | bevestig bij re-login |
| d | NAV-master-sync draaien | counts allemaal > 0 | ✅ geen actie |
| e | `PLX_IncomingDocument`-page NAV-zijdig publiceren | 404 | nodig als inkomend-document koppelen live moet |
| f | `mail_mode` → `graph`/`smtp` | staat op `log` | nodig als bevestigingsmails écht verstuurd moeten worden |
| g | (optioneel) `KlantOut` uitbreiden met `mixprijzen` | veld niet geëxposeerd | handig voor mixprijs-calibratie-verificatie |

## Audit-correcties (audit 2026-05-28 vs realiteit 2026-06-09)

**Achterhaald (inmiddels opgelost/gedeployed):**
- Ephemere-FS-thesis (§6.d, §12.A, §12.C, §14.1, §14.4) → Supabase Storage actief (Fase 2/3),
  live bewezen.
- `.eml` storage-key collision → gefixt; unieke `-<hash>`-suffixen zichtbaar in alle keys.
- Mixprijzen "klant **én** artikel beide true" (§3 rij 7) → fout; gate = alléén klantvlag.
- `MAIL_POLL_INTERVAL` niet gezet / poller draait niet (§12.B, §14.2) → staat op 300, draait.
- NAV-master-sync nooit gedraaid (§6.c, §13.7) → gedraaid (counts > 0).
- Incoming-doc download ontbreekt (§12.C, §14.4) → route bestaat en werkt.

**Nog steeds geldig uit de audit:**
- `PLX_IncomingDocument` skip-pad (§6.b, §13.5) → bevestigd 404 + niet in 42 services.
- `mail_mode=log` (§13.8) → bevestigd.
- Geen monitoring/alerting (§14.10) → niet onderzocht.

**Genuanceerd:**
- Graph-token "verlopen" als permanente blokkade (§12.B, §14.3) → **achterhaald**: auto-refresh
  via refresh-token werkt, `connected=true` (verse probe 12:06). Wél zichtbaar dat de access-token
  tussen refreshes kort kan verlopen (transiënt `degraded`) — dat is zelfherstellend, geen actie.

## Verificatie van dit rapport
Reproduceerbaar door de genoemde GETs opnieuw te draaien tegen `kwabo-production.up.railway.app`
met een admin-bearer (POST `/api/auth/login`). Verse herbevestiging: **2026-06-09 ~12:06–12:08 UTC**
(een eerdere probe ~11:15 toonde de transiënte `degraded` mailbox-staat; daarom de A3-correctie).
