# GO-LIVE RAPPORT — Fase 6 pre-go-live codecontrole

**Datum:** 2026-06-11 · **Branch:** `feat/fase2-matching` · **HEAD:** `b7ea9e18a9d30701cf8227a6e8f3df42581024bb`
**Controle:** READ-ONLY (geen code gewijzigd; enige nieuwe file is dit rapport)

---

## 0. Verdict & blokkades

**GO.** Alle backend-tests + 21 LLM-regressietests + 84 gerichte invariant-tests zijn groen, en geen van de zeven architectuur-invarianten (grondwet §7) is geschonden. De drie blokkerende bevindingen uit de branch-review (V1–V3) zijn **op 11-06 gefixt (TDD)** en met tests bewezen — inclusief een live Playwright-run van de nieuwe bevestig-knop:

| # | Was | Fix (11-06) | Bewijs |
|---|---|---|---|
| V1 | Handmatige hoeveelheid-/artikel-/eenheid-fix werd bij push overschreven door stale `verkoop_*`/`mix_*`-velden (#716-foutklasse) | `patch_field` wist de afgeleide velden bij elke bronveld-patch (`REGEL_BRONVELD_RE`, preview.py) | `test_patch_field_manual_override.py::test_patch_hoeveelheid_wist_afgeleide_verkoopvelden`, `::test_patch_artikel_wist_afgeleide_mix_en_eenheidvelden`, `::test_patch_eenheid_wist_afgeleide_uom_keuzes` |
| V2 | CONTROLEER-vlag (<1.0) blokkeerde approve zonder bevestig-route (her-typen of force) | "✓ Bevestig deze klant"-knop (order-review.tsx) her-patcht het nummer in één klik; backend behoudt daarbij nu de 4+/krediet-context (= V8-fix) | e2e `order-review-manual-override.spec.ts::CONTROLEER-klant` — **live gedraaid, passed**; backend `::test_patch_klant_match_verrijkt_4plus_en_krediet` |
| V3 | Klant-SKU die toevallig Kwabo-nr is werd zonder klant-match vlagvrij ingevuld (0.95) en daarna permanent aangeleerd | Confidence zonder klant-match → 0.84 (onder review-drempel) → reviewer bevestigt eerst | `test_match_articles_klantnr_exact.py::test_zonder_klant_nr_krijgt_review_vlag` |

Bekende NAV-side blokkades (geen code-issue, wel go-live-conditie — zie §6):
- **PLX_IncomingDocument**-page niet gepubliceerd → inkomend document wordt geskipt (reviewer-warning aanwezig).
- **Mixprijzen-vlag** niet OData-exposed op PLX_Customer → mixprijzen-pad ligt stil in prod. (Plus: het backend-API-schema `KlantOut` exposeert `mixprijzen` zelf óók niet — kleine backend-wijziging nodig zodra NAV het veld levert.)
- `MAIL_MODE=log` → bevestigingsmails worden nog niet verstuurd.

---

## 1. Verificatiemethode

| Aspect | Waarde |
|---|---|
| HEAD | `b7ea9e1` (fix(intake): file_drop mark_seen overleeft herstart, 11-06) |
| Working tree | Clean op tracked files; untracked: `backend/kwabo.log.1`, `checkpoint-fase5-order1.png`, `order685.jpeg`, `queue.jpeg`, `data/` (lokaal werkafval, geen code) |
| Volledige suite | `python -m pytest -q` → **582 passed, 17 skipped** in 124,1s (skips = `--regression`-gated) |
| LLM-regressie op HEAD | `pytest tests/test_regression.py tests/test_selflearning_e2e.py --regression -q` → **21 passed** in 9,6s |
| Gerichte invariant-run | 10 testbestanden (zie §4) → **84 passed** in 11,4s |
| Code-review | 7 finder-agents over volledige diff `main...HEAD` (93 files, 19 commits) + 6 verifier-agents; bevindingen in §7 |

**Kanttekeningen bij de bewijskracht (eerlijkheid):**
1. Tests draaien op **SQLite** (conftest-guard forceert `DATABASE_URL=sqlite:///./kwabo.db` vóór imports). Postgres/pgbouncer-gedrag (pooling, RLS, locks) is hiermee níét bewezen — on-site check.
2. De LLM-regressie liep in 9,6s en dus vrijwel zeker via de **LLM-cache** (by design: "eerste run vult 'm; volgende runs zijn gratis"). Dit bewijst de pipeline-logica op deze HEAD met identieke LLM-antwoorden; de **live extractiekwaliteit** is bewezen op checkpoint 10-06 (17/17), niet opnieuw met verse API-calls.
3. NAV-tests draaien tegen mock/gemockte HTTP — body-vórm is bewezen, NAV-acceptatie niet (zie §7).

---

## 2. Fix-matrix Fase 1–5

Status: **BEWEZEN** = testfunctie groen in de run van §1. **ALLEEN ON-SITE** = geen geautomatiseerd bewijs in deze run. **SPEC AANWEZIG** = Playwright-spec bestaat maar draaide niet (frontend-e2e vergt handmatige servers, zie memory frontend-e2e-setup).

**Let op:** Fase 1 (commits `4ccc535` 26-05, `3964c46` 28-05) en de fixes van 31-05/02-06 (login/logs-auth, item-UOM-sync, ship-to, mixprijzen-7002-refactor) staan **al op `main`** — ze vallen buiten de rollback van deze branch (§5) maar zijn voor volledigheid opgenomen.

### Fase 1 — Observability & preventieve fixes (op main)

| Fix | Commit | Status | Bewijs | On-site verificatie |
|---|---|---|---|---|
| 6 preventieve silent-failure-fixes | 4ccc535 | BEWEZEN | `test_fase1_preventieve_fixes.py` (o.a. `test_persist_source_eml_returns_none_tuple_on_failure`) | — |
| Poll-heartbeat + interval-warning | 3964c46 | BEWEZEN | `test_mailbox_status.py::test_mail_poll_status_updated_on_each_tick`, `::test_polled_interval_warning_logged` | `GET /api/mailbox/status` → ticks_total loopt op |
| Token-refresh-timestamp | 3964c46 | BEWEZEN | `test_mailbox_status.py::test_token_timestamp_written_on_refresh` | `GET /api/mailbox/status` → `last_token_refresh_at` vers |

### Fase 2 — Klant-/artikelmatching (deze branch, a42c11c…1340b4f)

| Fix | Commit | Status | Bewijs | On-site verificatie |
|---|---|---|---|---|
| A1: klant-artnr dat Kwabo-nr is → exact | 7728635 | BEWEZEN | `test_match_articles_klantnr_exact.py::test_klant_artnr_dat_kwabo_nr_is_matcht_exact`, `::test_echte_witzand_regel_718`, `::test_echte_kolomswap_regel_550` | Order met klant-SKU=Kwabo-nr door pipeline; check match_methode `exact_klantnr` (let op bevinding V3, §7) |
| A5: fuzzy-drempel 80→90 | 933d9f2 | BEWEZEN | `test_match_articles_fuzzy_threshold.py::test_junk_score_86_wordt_niet_meer_ingevuld` + 4 echte junk-gevallen (parametrized) | Automatch-% volgen eerste week (verwacht: minder junk, mogelijk iets lagere rate) |
| K3.1: klantnaam_besteller-extractie | 31ddaf3 | BEWEZEN | `test_extract_klantnaam_besteller.py::test_klantnaam_besteller_komt_in_state_met_provenance` | — |
| K3/K4: naam-fallback + kandidaten + portaal-skip | a6e36cb | BEWEZEN | `test_match_customer_name_fallback.py::test_witzand_718_matcht_op_naam`, `::test_gbi_borne_707_portaal_matcht_op_naam`, `::test_franchise_naam_geeft_kandidaten_geen_autopick` | Eerste portaal-order (Zevij/orders.nl) live volgen |
| CONTROLEER-vlag op klant-match <1.0 | a6e36cb/1340b4f | BEWEZEN | `test_match_customer_name_fallback.py::test_naam_match_krijgt_zachte_controleer_vlag` | Reviewer-flow: vlag wissen kost her-patch (bevinding V2, §7) |
| M1: handmatige override plakt | e026bf0 | BEWEZEN | `test_patch_field_manual_override.py::test_patch_klant_match_wist_review_status`, `::test_patch_artikel_naam_vulling_en_confidence` | UI: badge wordt groen na fix |
| M1-UI: badge/pills verversen direct | 19ea2ff | SPEC AANWEZIG | `frontend/tests/order-review-manual-override.spec.ts` (niet gedraaid in deze controle) | UI: artikel handmatig fixen → badge ververst zonder reload |
| K3.3: KlantPicker (kandidaten kiezen) | 4c6d85d | SPEC AANWEZIG | `frontend/tests/klant-picker.spec.ts` (niet gedraaid) | UI: order zonder klant-match toont picker; keuze patcht klant |
| Eindverificatie echte faalorders | a4d2b66 | BEWEZEN | verify-script + fixtures (`backend/scripts/export_order_states.py`-data) | — |

### Fase 3 — Eenheidscode / Branch A (3733901)

| Fix | Commit | Status | Bewijs | On-site verificatie |
|---|---|---|---|---|
| E1/E2: verkoopeenheid + omrekening (#716: 66 STUK → 2 PALLET33) | 3733901 | BEWEZEN | `test_branch_a_verkoopeenheid.py::test_716_base_eenheid_wordt_verkoopeenheid_met_omrekening`, `::test_artikelkaart_heeft_verkoop_eenheid_veld` | Na deploy: items-sync draaien (vult `verkoop_eenheid`-kolom!) en order #716-achtig geval spot-checken in NAV |
| E2: niet-gehele omrekening → expliciete base | 3733901 | BEWEZEN | `::test_niet_gehele_omrekening_dwingt_expliciete_base_af` | — |
| E3: ongeldige eenheid nooit naar NAV | 3733901 | BEWEZEN | `::test_ongeldige_besteleenheid_rol_gaat_nooit_naar_nav` | — |
| Niet-base besteleenheid blijft staan | 3733901 | BEWEZEN | `::test_geldige_niet_base_besteleenheid_blijft_staan` | — |
| E4: europallet telt Branch-A-pallets | 3733901 | BEWEZEN | `::test_europallet_telt_branch_a_pallets_716` | — |
| Mix wint van Branch A | 3733901 | BEWEZEN | `::test_composer_mix_wint_van_verkoopkeuze` + `test_compose_navision_mix.py` | — |
| Bijlage met ':' in naam (#706, PPG) | 0eaaf0c | ALLEEN ON-SITE | log onderscheidt `attachment_zip_not_found` vs `attachment_not_found` | Order #706-bijlage openen via `GET /api/orders/{id}/attachment/{name}?token=…` |

### Fase 4 — Performance & concurrency (55fa725)

| Fix | Commit | Status | Bewijs | On-site verificatie |
|---|---|---|---|---|
| C2: parallelle match_articles (sem 5) | 55fa725 | BEWEZEN | `test_match_articles_concurrency.py::test_semaphore_limiet_gerespecteerd_en_echt_parallel`, `::test_output_blijft_in_inputvolgorde`, `::test_conc1_en_conc5_geven_identieke_uitkomst`, `::test_crash_semantiek_ongewijzigd` | Order-doorlooptijd in logs (verwacht ~0,65s i.p.v. 3,2s voor matching) |
| B1: mirror-first + NAV-client-scope (socket-leak) | 55fa725 | BEWEZEN | `test_nav_client_scope.py::test_scope_provides_single_shared_instance`, `::test_scope_calls_aclose_on_exit`, `::test_mirror_first_skips_nav_when_artikel_in_db` | — |
| NAV-GET-retry (429/5xx) | 55fa725 | BEWEZEN | retry-tests in `test_navision_nav2018.py` | — |
| Pool-borging | 55fa725 | BEWEZEN | `test_db_engine_pooling.py` | pgbouncer-gedrag alleen on-site (§3 punt 9) |

### Fase 6 — Review-fixes V1/V2/V3/V8 (11-06, na de controle)

| Fix | Status | Bewijs | On-site verificatie |
|---|---|---|---|
| V1: bronveld-patch wist afgeleide verkoop/mix-velden | BEWEZEN | `test_patch_field_manual_override.py::test_patch_hoeveelheid_wist_afgeleide_verkoopvelden` + 2 zustertests | Order met Branch-A-regel: hoeveelheid corrigeren → preview toont nieuwe hoeveelheid/eenheid |
| V2: bevestig-knop CONTROLEER-klant | BEWEZEN (e2e, live) | `order-review-manual-override.spec.ts::CONTROLEER-klant` — 3 passed lokaal 11-06 | Order met domein/naam-match openen → knop "✓ Bevestig deze klant" → vlag weg, approve vrij |
| V3: collisie zonder klant-match → CONTROLEER | BEWEZEN | `test_match_articles_klantnr_exact.py::test_zonder_klant_nr_krijgt_review_vlag` | — |
| V8: klant-patch behoudt 4+/krediet | BEWEZEN | `test_patch_field_manual_override.py::test_patch_klant_match_verrijkt_4plus_en_krediet` | Klant bevestigen → 4+/krediet-badges blijven staan |

### Fase 5 — Observability & prod-hardening (2411c3d…b7ea9e1)

| Fix | Commit | Status | Bewijs | On-site verificatie |
|---|---|---|---|---|
| 5A: leesbare reden bij 0 NAV-operaties | 2411c3d | BEWEZEN | `test_navision_preview_reason.py::test_geen_gematchte_regels_geeft_leesbare_reden`, `::test_geen_klant_geeft_leesbare_reden` | Order zonder matches openen → reden zichtbaar i.p.v. lege preview |
| 5B: alerts-ringbuffer + Slack-sink + throttle | 7ca55d9 | BEWEZEN | `test_alerts.py::test_alert_posts_to_slack_when_sink_configured`, `::test_throttling_blocks_repeated_alerts`, `::test_alert_without_sink_is_noop`, `::test_alert_swallows_post_exception` | `GET /api/diagnostics/health-summary` → alerts-array |
| 5C: tick-teller / poller-heartbeat | 7ca55d9 | BEWEZEN | `test_health_summary.py::test_record_poll_tick_telt_cumulatief`, `::test_poller_heartbeat_bij_lege_inbox` | health-summary: ticks_total loopt elke ~300s op |
| 5F: crash-sites vuren alerts | 7ca55d9 | BEWEZEN | `test_health_summary.py::test_match_single_crash_vuurt_alert`, `::test_geforceerde_alert_verschijnt_in_health_summary` | — |
| 5D: warnings-banner op order-detail | 68b2a33 | ALLEEN ON-SITE | geen test (frontend) | Order met bron-doc-skip openen → amber banner zichtbaar |
| 5E: file_drop mark_seen overleeft herstart | b7ea9e1 | BEWEZEN | `test_file_drop_mark_seen.py::test_mark_seen_na_herstart_verplaatst_alsnog`, `::test_mark_seen_zelfde_instantie_blijft_werken` | (file_drop is dev-mode; prod draait graph) |

---

## 3. ALLEEN ON-SITE TE VERIFIËREN — gebundeld

Na deploy, in deze volgorde:

1. **Deploy-versie**: `GET /api/version` → sha == `b7ea9e1` (of de merge-sha).
2. **Liveness**: `GET /api/health` → `{"status":"ok","poller":"alive"}`.
3. **Health-summary**: `GET /api/diagnostics/health-summary` → ticks_total loopt op (poll-interval ~300s), alerts leeg of verklaard, token-expiry in de toekomst, `workers.web_concurrency=1`, `poller_task_alive=true`.
4. **Config-sanity**: `GET /api/diagnostics/config` → `jwt_secret_is_dev_default=false`, `email_mode=graph`, `navision_mode=nav2018`, supabase storage actief.
5. **NAV-connectiviteit**: `GET /api/diagnostics/nav?page=PLX_Item` en `?page=PLX_Customer` → ok=true.
6. **Mailbox**: `GET /api/mailbox/status` → connected=true, account `pilex@kwabo.nl`, `last_token_refresh_at` vers.
7. **Master-sync**: `POST /api/admin/nav-sync?domains=customers,items,cross_ref,ship_to,item_uoms` → job done; daarna `GET /api/admin/db-counts` (ArtikelEenheid ~12963; **cruciaal: items-sync vult nu ook de nieuwe `verkoop_eenheid`-kolom — vóór die sync valt Branch A terug op afleiding, zie §7 V5**).
8. **UI-checks** (geen e2e in CI): (a) warnings-banner op order met bron-doc-skip (5D); (b) KlantPicker bij order zonder klant-match (K3.3); (c) badge/pills verversen direct na handmatige fix (M1); (d) bijlage met ':' in naam opent (#706).
9. **pgbouncer/pool** (uit FASE0/STATUS): onder last geen `QueuePool limit`-errors in Railway-logs; let op tijdens eerste poller-burst.
10. **Veris-mixorder**: eerste echte mix-klant-order handmatig naast NAV leggen (mixprijzen-pad ligt stil tot NAV het vlag-veld exposeert).
11. **End-to-end acceptatie**: 1 staging-push — order mailen naar pilex@kwabo.nl → review → approve → in NAV: velden + triggers + géén prijs meegestuurd + externalDocumentNumber gevuld; daarna zelfde mail nogmaals → dedup (geen tweede order).
12. **Playwright-specs** (optioneel, handmatig): backend+frontend lokaal starten en `frontend/tests/klant-picker.spec.ts` + `order-review-manual-override.spec.ts` draaien.

---

## 4. Grondwet §7 — architectuur-invarianten, per stuk gecheckt

Run-bewijs: 84 tests groen in `test_navision_steps.py`, `test_nav_stepwise.py`, `test_navision_dedup.py`, `test_navision_nav2018.py`, `test_pipeline_e2e.py`, `test_compose_navision_mix.py`, `test_select_ship_to.py`, `test_mock_uom_trigger.py`, `test_match_articles_concurrency.py`, `test_db_engine_pooling.py`.

| Invariant | Code-anker | Bewijs | Restrisico |
|---|---|---|---|
| a) Order-POST exact 1 veld `{customerNumber}` | `nav_operations.py:120-126` | `test_nav_stepwise.py::test_mock_stepwise_rejects_multi_field_post_to_sales_orders` (negatief) + alle composer-tests | — |
| b) Regel-POST exact 2 velden `{lineType,itemNumber}` | `nav_operations.py:127-133` | idem + `test_pipeline_e2e.py` | — |
| c) Elke PATCH exact 1 veld | `nav_operations.py:134-138` | `test_nav_stepwise.py::test_real_patch_rejects_multi_field_body`, `::test_mock_stepwise_rejects_multi_field_patch` | Marker-keys (`_`-prefix) tellen bewust niet mee en worden vóór transport gestript (`_strip_marker_keys`) |
| d) Nooit prijs/omschrijving meesturen | grep `unitPrice\|description` over `navision_steps.py`: enige body-hit is regel 321 — de `/incomingDocuments`-POST (bron-document, géén sales-pad) | `test_navision_steps.py` happy-paths + `test_mock_uom_trigger.py` (NAV vult prijs/omschrijving via trigger-simulatie) | Grep is zwak bewijs; het echte vangnet is dat `_assert_op_invariants` op het **transportpad** van alle drie clients zit: `navision_nav2018.py:660`, `navision_real.py:473`, `navision_api.py:241` (mock) — geverifieerd |
| e) Idempotentie/dedup op External_Document_No | `nav_operations.py:211` (`_extract_external_doc_number`) + `navision_nav2018.py:572-579` (`$filter External_Document_No eq …`), `navision_real.py:441-450`, mock `navision_api.py:214-222` | `test_navision_dedup.py` | Mock test clientlogica; de echte NAV-filterquery alleen via on-site staging-push (§3.11) |
| f) Ship-to best-effort | select_ship_to-node + nav2018 veldnaam-fix `_x003C_Ship_to_Code_2_x003E_` (02-06) | `test_select_ship_to.py`, `test_admin_ship_to_sync.py` | Weiger-pad (NAV weigert code → warning i.p.v. harde fout) alleen live triggerbaar |
| g) Trigger-aware volgorde (UOM-PATCH vóór quantity) | composer `navision_steps.py` | `test_navision_steps.py::test_minimal_happy_path_uom_then_quantity_ordering`, `::test_multi_line_with_one_mix_line_emits_uom_patch_before_quantity` | — |

**Fase 4-parallelisatie vs. invarianten** (memory-waarschuwing): `match_articles.py:155-188` gecontroleerd — semaphore op `settings.match_concurrency`, **één `Session(engine)` per regel** (r161, geen gedeelde sessie over taken), `asyncio.gather` + expliciete sort op idx (deterministische volgorde), crash-fallback per regel zonder poison-pill. Geen gedeelde mutabele state geïntroduceerd. Determinisme bewezen door `test_conc1_en_conc5_geven_identieke_uitkomst`.

**Conclusie: geen architectuur-invariant geschonden.**

---

## 5. Rollback per fase

Twee sporen. **Spoor 1 (minuten, geen deploy): feature-flags** — altijd eerst proberen:

| Symptoom | Flag | Effect |
|---|---|---|
| Race/pool-problemen matching | `MATCH_CONCURRENCY=1` | Fase 4-parallelisme de facto uit (semaphore=1, identieke uitkomst bewezen) |
| Poller-problemen | `MAIL_POLL_INTERVAL_SECONDS=0` | Intake stopt; handmatig `POST /api/intake/scan` blijft |
| NAV-writes stoppen | `NAVISION_MODE=mock` | Geen echte NAV-orders meer (review-flow blijft werken) |
| Mail-problemen | `MAIL_MODE=log` | Bevestigingsmails alleen geloggd (is nu al de stand) |
| Slack-blokkades (V7, §7) | `KWABO_SLACK_WEBHOOK_URL` leeg | alert() wordt no-op naast ringbuffer/log |

**Spoor 2: git revert per fase** (revert in omgekeerde volgorde, Fase 5 → 2, om conflicten te beperken; daarna gewone deploy):

| Fase | Commit-range op deze branch | Revert-recept | Data-impact |
|---|---|---|---|
| 5 (A–F) | `2411c3d`, `7ca55d9`, `68b2a33`, `b7ea9e1` | `git revert --no-commit b7ea9e1 68b2a33 7ca55d9 2411c3d` | Alerts-ringbuffer is in-memory (verdwijnt); mark_seen-state op disk blijft (onschadelijk) |
| Bijlagen-fix | `0eaaf0c` | `git revert --no-commit 0eaaf0c` | Geen — maar PPG-bijlagen (#706) breken weer |
| 4 | `55fa725` | `git revert --no-commit 55fa725` | Geen DB-impact; overweeg eerst `MATCH_CONCURRENCY=1` |
| 3 | `3733901` | `git revert --no-commit 3733901` | **Let op:** de `verkoop_eenheid`-kolom (additieve migratie) blijft in de DB staan — onschadelijk, wordt genegeerd. Reverten heropent #716 (NAV-default-eenheid-bug)! |
| 2 | `a42c11c..1340b4f` (11 commits) | `git revert --no-commit 1340b4f a4d2b66 4c6d85d a6e36cb 31ddaf3 933d9f2 7728635 19ea2ff e026bf0 b1683da a42c11c` | Geleerde mappings/history-rijen blijven in DB (door beide versies leesbaar) |
| 1 | n.v.t. — `4ccc535`/`3964c46` staan op `main` | aparte revert op main indien ooit nodig | — |

Generiek: reverts wissen **geen** DB-rijen (alle migraties zijn additief) en geen Supabase-objecten. Volledige terugval = Railway redeployen op de laatste main-sha (`262f9dc`).

---

## 6. Definitieve OPS-checklist go-live

**Env-vars (Railway):**
- [ ] `ADMIN_PASSWORD` gezet (leeg = auth-bypass!)
- [ ] `JWT_SECRET` ≠ `dev-only-change-me-in-prod` (check: `GET /api/diagnostics/config` → `jwt_secret_is_dev_default=false`)
- [ ] `DATABASE_URL` = Supabase transaction-pooler (poort 6543)
- [ ] `EMAIL_MODE=graph`, `MAIL_POLL_INTERVAL_SECONDS=300` (let op exact deze naam — les Fase 5)
- [ ] `MAIL_MODE`: besluit nemen `log` → `smtp`/`graph` (nu log = klant krijgt geen bevestiging)
- [ ] `NAVISION_MODE=nav2018` + `NAV_BASE_URL` (poort 1153/ODataV4), `NAV_COMPANY="Kopie 2026 Kwabo Techniek B.V."` → bij echte go-live: **productie-company**, `NAV_USERNAME`/`NAV_PASSWORD` (web-service-key)
- [ ] `MATCH_CONCURRENCY=5` (niet >~10 i.v.m. pool 5+10)
- [ ] `WEB_CONCURRENCY=1` of unset (anders pollt geen enkele worker)
- [ ] `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + bucket `incoming-docs`
- [ ] `ANTHROPIC_API_KEY`; `SEED_DEMO_DATA` irrelevant op postgres maar demo-seed purgen: `POST /api/admin/purge-demo-seed` (memory: seed-klanten 10001-10016 vervuilden prod-matching)
- [ ] Optioneel: `KWABO_SLACK_WEBHOOK_URL` (zie §7 V7 vóór aanzetten)
- [ ] **Frontend (Vercel):** `NEXT_PUBLIC_API_BASE` = backend-URL — **wordt bij `next build` ingebakken** (les Fase 2): na wijziging re-deployen

**OAuth/Graph:**
- [ ] `PUT /api/mailbox/oauth/config` (tenant, client, secret, redirect-uri geregistreerd in Azure)
- [ ] Flow doorlopen via `/email`-pagina → `GET /api/mailbox/status` connected, scopes Mail.ReadWrite + offline_access

**NAV-master-sync:**
- [ ] `POST /api/admin/nav-sync?domains=customers,items,cross_ref,ship_to,item_uoms` direct na deploy (items-sync vult de nieuwe `verkoop_eenheid`-kolom — vereiste voor Branch A zoals bedoeld, zie §7 V5)
- [ ] `GET /api/admin/db-counts` plausibel (klanten ~1787, artikel_eenheden ~12963)

**NAV-side (Kwabo/expert):**
- [ ] `PLX_IncomingDocument`-page publiceren (OData V4) → daarna backend-stap activeren en staging-push herhalen
- [ ] Mixprijzen-vlag (`Mix_Prices_Allowed`/variant) exposen op PLX_Customer → daarna customers-sync; **plus backend-taakje: `KlantOut`-schema exposeert `mixprijzen` nog niet** (bevinding, klein)
- [ ] Open expertvraag 7002 (prijsstaffel-cascade) blijft open — gedocumenteerd in ARCHITECTURE.md §16

**Acceptatie:**
- [ ] §3-lijst volledig afgewerkt, incl. staging-push + dedup-herhaaltest

---

## 7. Beperkingen, schijnzekerheid & code-review-bevindingen

### 7a. Wat deze controle NIET bewijst
1. **Mock ≠ NAV 2018**: invariant-tests bewijzen de vorm van elke operatie, niet dat de echte server ze accepteert (page-namen, veldnamen, URL-conventie). Vangnet: §3.11 staging-push.
2. **SQLite ≠ Postgres/pgbouncer**: pooling-, lock- en RLS-gedrag onbewezen; §3.9.
3. **LLM-regressie via cache**: pipeline-logica op HEAD bewezen met gecachte LLM-antwoorden; verse-extractiekwaliteit is het 10-06-checkpoint.
4. **Races zijn probabilistisch**: concurrency-tests bewijzen determinisme van de uitkomst, niet afwezigheid van races onder productielast; sessie-per-regel is een structureel argument.
5. **Frontend zonder CI-e2e**: alle UI-claims per definitie on-site (specs bestaan wel, §3.12).

### 7b. Code-review-bevindingen (7 finders × volledige diff, daarna per bevinding geverifieerd)

**Blokkerende bevindingen — GEFIXT op 11-06 (TDD, zie §0 voor de testbewijzen):**

| # | Status | Bevinding + fix |
|---|---|---|
| V1 | ✅ GEFIXT | **Stale afgeleide velden na handmatige fix.** `patch_field` wiste bij een hoeveelheid-/artikel-/eenheid-correctie de afgeleide `verkoop_uom_gekozen`/`verkoop_aantal`/`mix_*` niet; de composer (`navision_steps.py:164-169`) gaf die voorrang → oude waarde naar NAV. Fix: `REGEL_BRONVELD_RE`-blok in preview.py wist de afgeleiden bij elke bronveld-patch (bij artikel-wissel ook `mix_uom_kandidaat` + `eenheid_default`); de composer-fallback pakt dan de letterlijke reviewer-waarden. |
| V2 | ✅ GEFIXT | **Geen bevestig-route voor de CONTROLEER-vlag.** Fix: "✓ Bevestig deze klant"-knop in order-review.tsx (zichtbaar bij gevulde-maar-gevlagde match, toont de match-bron) die het huidige nummer her-patcht; gecombineerd met de V8-fix gaat daarbij geen 4+/krediet-context meer verloren. Live e2e-bewezen. |
| V3 | ✅ GEFIXT | **Exact-klantnr zonder klant-match was vlagvrij + zelfversterkend.** Fix: `match_articles.py` geeft de collisie-interpretatie zonder klant-match nu conf 0.84 (< drempel 0.85) → CONTROLEER; pas na reviewer-bevestiging leert `_learn_from_approved` de mapping. |
| V8 | ✅ GEFIXT | **Klant-patch wiste 4+/krediet-context.** Fix: de klant-branch in `patch_field` verrijkt `is_4plus`/`kredietlimiet`/`betalingsconditie` uit de mirror, zoals match_customer dat doet. |

**Aandachtspunten (accepteerbaar voor go-live, wel op de lijst):**

| # | Verdict | Bevinding |
|---|---|---|
| V4 | CONFIRMED | Naam-kandidaten (score 75-89, geen autopick) **skippen de NAV-domein-fallback** (`and not klant_kandidaten`, match_customer.py:256) — orders die vóór de branch automatisch via domein matchten (conf 0.7) komen nu ongematcht binnen met picker. Mogelijk bewuste voorzichtigheid (grondwet "nooit automatisch kiezen"), maar het is een gedragsverandering → automatch-% monitoren (§3). |
| V5 | CONFIRMED | Branch-A-afleiding vuurt ook als `verkoop_eenheid` NULL (heel prod tot de items-resync!) of == base: bij precies één gehele niet-mix ArtikelEenheid wordt 66 STUK → 2 PALLET33 omgezet, hoeveelheid-behoudend maar zonder vlag of log-onderscheid. Het NULL-geval is bedoeld (besluit Cas 10-06, getest); het ==base-subgeval (kaart zegt expliciet base) is ongetest. Mitigatie: items-sync direct na deploy (§6); wens: vlag/log wanneer afleiding i.p.v. kaartwaarde besliste. |
| V6 | CONFIRMED | `pallet_logic.py:128-135`: Branch-A-pallettelling staat vóór de geleerde `ArtikelPalletKennis`-lookup; geleerde `pallet_required=False` wordt voor die regels genegeerd (docstring zegt andersom). Volgt precedent van het mix-blok; conflictgeval ongetest. |
| V7 | CONFIRMED (conditioneel) | `alert()` doet een **synchrone** Slack-post (timeout tot ~7s) vanuit async paden (match-crash-handler, NAV-push-pad, poller). Alleen actief als `KWABO_SLACK_WEBHOOK_URL` gezet is; throttle 1/5min per (event,severity). Advies: webhook pas aanzetten na offload naar `asyncio.to_thread`, of geaccepteerd risico documenteren. |
| V9 | CONFIRMED | De M1-fix (needs_review-clear) zit alleen in `patch_field`; het oudere `PATCH /api/orders/{id}` (patch_order) heeft hem niet. Frontend gebruikt patch_order nergens → alleen API-consumenten. |
| V10 | CONFIRMED (klein) | `RECHTSVORM_RE`: het `& co. kg`-alternatief is dood (`\b` vóór `&` matcht nooit) → junk-tokens `co kg` blijven in genormaliseerde Duitse namen (score-inflatie 36→70, blijft onder kandidaten-lat 75 in het 2-token-geval). `PORTAL_DOMAINS` is exacte match — subdomeinen (mail.zevij…) passeren de K4-skip. |
| V11 | CONFIRMED (gemitigeerd) | Preview-compose ving `Exception` zonder log/alert (HTTP 200 `compose_error`) — maar pipeline-compose logt luid en approve-pad gooit wél 500 bij onverwachte fouten, dus niet dagen onzichtbaar. |
| V12 | PLAUSIBLE | Pool-druk bij NAV-storing: 5 sessies per pipeline-run blijven open over de NAV-retry (tot ~minuten). Poller serialiseert orders, dus alleen bij samenloop (poller + handmatige rerun) richting pool-limiet. Kill-switch: `MATCH_CONCURRENCY=1`. |

**Cleanup-aanbevelingen (geen go-live-blokkers; backlog):** dubbele kruisverwijzing/mapping-lookups in match_articles stap 1b vs 2/3; `_match_by_name` laadt per mail alle ~1787 klantenkaarten zonder cache; RLS-`ALTER TABLE`s draaien bij elke boot (locks) i.p.v. conditioneel; UoM/quantity-prioriteit op 3 plekken (navision_steps ×2 + pallet_logic) → één resolved (uom,aantal)-paar; 9 handmatige alert-call-sites i.p.v. één decorator/log-processor; KlantPicker ≈ kopie ShipToPicker (incl. ontbrekende rollback-bij-fout); `analyze_name_fallback.py` meet token_sort_ratio terwijl prod token_set_ratio gebruikt (onderbouwing drempel 90 klopt daardoor niet met de meting); status-teksten dubbel in backend-reason en frontend-statusBadge; `match_methode="handmatig"` naast bestaand `"manual"`.

---

## 8. Bijlage — letterlijke testuitkomsten (HEAD b7ea9e1, 2026-06-11)

```
# Volledige suite (backend, .venv, SQLite-guard actief) — vóór de V-fixes
$ python -m pytest -q
582 passed, 17 skipped in 124.10s (0:02:04)

# Ná de V1/V2/V3/V8-fixes (11-06)
$ python -m pytest -q
586 passed, 17 skipped in 139.67s (0:02:19)

# Playwright lokaal (servers handmatig, mock-NAV, test-mode):
#   tests/order-review-manual-override.spec.ts → 3 passed (11.8s)
#   tests/klant-picker.spec.ts → 1 passed (5.3s)

# LLM-regressie + self-learning e2e (--regression, ANTHROPIC_API_KEY, LLM-cache)
$ python -m pytest tests/test_regression.py tests/test_selflearning_e2e.py --regression -q
21 passed in 9.64s

# Gerichte invariant-run (grondwet §7 + Fase 4)
$ python -m pytest tests/test_navision_steps.py tests/test_nav_stepwise.py \
    tests/test_navision_dedup.py tests/test_navision_nav2018.py tests/test_pipeline_e2e.py \
    tests/test_compose_navision_mix.py tests/test_select_ship_to.py tests/test_mock_uom_trigger.py \
    tests/test_match_articles_concurrency.py tests/test_db_engine_pooling.py -q
84 passed in 11.39s
```

*Opgesteld door Fase 6 pre-go-live codecontrole (read-only). Gebruikte skills: verification-before-completion (elke BEWEZEN-claim na gedraaide test), code-review high (7 finders + 6 verifiers over main...HEAD), systematic-debugging stond stand-by (geen testfailures opgetreden).*
