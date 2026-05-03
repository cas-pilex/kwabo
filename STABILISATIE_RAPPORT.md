# Stabilisatie + plumbing voor go-live — rapport

Branch: `feat/nav-trigger-respecting-order-entry`
Datum: 2026-05-03
Plan: `.claude/plans/oke-ik-wil-dat-validated-biscuit.md`

## Eindstatus

**DONE** — klaar om in `.env` `NAVISION_MODE=real` te zetten en (na OAuth) `EMAIL_MODE=graph`.

| Verificatie | Resultaat |
|---|---|
| Backend tests | **212 passed / 17 skipped** (was 191; +21 nieuwe regressies) |
| `verify_t12.py` forbidden fields | **0 occurrences** over 17 emails |
| Redundante UOM PATCHes | **0** |
| `run_e2e_10x.py` (10 iteraties × 17 emails) | **170/170 OK, 0 flaky, 0 always-failing** |
| Pipeline determinism | 1 distinct ops-hash per email over 10 iteraties |

## Wat is gefixt

### Bugs

1. **Bug 1 — Mock path-routing** — _false positive_. Recon-agent zag escape-artefacten in JSON-output van grep; daadwerkelijke code in `navision_api.py:357-368` gebruikt forward slashes consistent. Geen fix nodig.

2. **Bug 2 — Mock UOM trigger te losjes** (`navision_api.py:494-518`). Mock paste mix-discount toe op alleen `quantity ≥ threshold`, ongeacht UOM. Echte NAV vereist dat de lijn-UOM de mix-UOM is (alternate UOM met `qtyPerUnitOfMeasure > 1.0`). Fix: nieuwe helper `_is_mix_uom_for_item()` die de mock real-NAV-faithful maakt — composer-bugs (verkeerd UOM) worden nu zichtbaar i.p.v. gemaskeerd. Tests: `test_mock_uom_trigger.py` (4) + `test_nav_stepwise.py` aangepast.

3. **Bug 3 — Composer header-only guard** (`navision_steps.py`). Composer produceerde silently 0 line-ops als alle artikelen unmatched waren → header-only order in NAV. Fix: ValueError bij `matched_count == 0`. `compose_order_node` vangt op naar `state["compose_error"]`. Tests: `test_compose_unmatched_guard.py` (5) + nieuwe `compose_error` veld in OrderState.

4. **Bug 4 — Stepwise dedup** (`navision_real.py`, `navision_api.py`). `create_sales_order_stepwise` had geen dedup op `externalDocumentNumber` — re-push faalde op echte NAV met unique-key violation. Fix: shared helper `_extract_external_doc_number()` in `nav_operations.py`; dedup-guard vóór eerste POST in beide stepwise clients. Tests: `test_navision_dedup.py` (3).

### Observability

**NAV stepwise failure logs** (`navision_real.py:586-610`). De `except`-block in `create_sales_order_stepwise` logde alleen op-label en error-string. Voor go-live debugging is dat onbruikbaar. Uitgebreid naar:
- `op_index`, `op_label`, `op_method`, `op_path`
- `request_body` (gefilterd via `_redact_body` voor toekomstige credential-keys)
- `response_status`, `response_body` (getrimd via `_truncate_text` op 2000 chars)
- `error_type`, `error_message`

Tests: `test_navision_logging.py` (2) — gebruikt `httpx.MockTransport` + `structlog.testing.capture_logs()`.

### Plumbing

**Email-client factory** (`email_client.py`). Nieuwe `get_email_client()` analoog aan `get_navision_client()`. Switching naar Microsoft Graph mailbox is nu `EMAIL_MODE=graph` + OAuth → geen code-wijziging.

**`GraphEmailClient` stub** (`email_client_graph.py`). Implementeert EmailClient-protocol; `list_new()` raised `RuntimeError` met instructie naar `/api/mailbox/oauth/start` als geen token, anders `NotImplementedError` met TODO-aanwijzing. Tests: `test_email_client_factory.py` (7).

**`.env.example` + README** geüpdatet met alle productie env-vars (NAV_BASE_URL, NAV_AUTH_MODE, GRAPH_*, etc.) en go-live instructies.

### Test infrastructuur

**`run_e2e_10x.py`** orchestrator. Draait pipeline N keer, hasht composed ops per email (excl. `shipmentDate` voor calendar-day-stable hashes), schrijft markdown-rapport naar `backend/reports/`. Exit code 2 als een email in elke iteratie faalt.

## Bestanden

### Nieuw (8)
- `backend/scripts/run_e2e_10x.py`
- `backend/src/kwabo/integrations/email_client_graph.py`
- `backend/tests/test_mock_uom_trigger.py`
- `backend/tests/test_compose_unmatched_guard.py`
- `backend/tests/test_navision_dedup.py`
- `backend/tests/test_navision_logging.py`
- `backend/tests/test_email_client_factory.py`
- `backend/reports/` (.gitkept folder voor 10x rapporten)

### Aangepast (10)
- `backend/src/kwabo/integrations/navision_api.py` — Bug 2 fix + dedup + factory import
- `backend/src/kwabo/integrations/navision_real.py` — dedup + observability + helpers
- `backend/src/kwabo/integrations/navision_steps.py` — Bug 3 guard
- `backend/src/kwabo/integrations/nav_operations.py` — `_extract_external_doc_number` helper
- `backend/src/kwabo/integrations/email_client.py` — `get_email_client()` factory
- `backend/src/kwabo/graph/nodes/compose_order.py` — `compose_error` propagatie
- `backend/src/kwabo/graph/state.py` — `compose_error` veld
- `backend/src/kwabo/api/intake_trigger.py` — gebruikt factory
- `backend/.env.example` — alle productie-vars
- `README.md` — go-live sectie geüpdatet
- `backend/tests/test_nav_stepwise.py` — bestaande mix-test bijgewerkt naar real-NAV-faithful gedrag

## Go-live checklist (post-merge)

1. `.env` invullen volgens `backend/.env.example`:
   - `NAVISION_MODE=real`
   - `NAV_BASE_URL`, `NAV_COMPANY_ID`, `NAV_AUTH_MODE` + credentials
   - `EMAIL_MODE=graph` (of laat `file_drop` voor handmatige drop)
2. `python backend/scripts/sync_navision_masters.py --full` — eenmalige master-data sync
3. (Bij `EMAIL_MODE=graph`) — bezoek `/api/mailbox/oauth/start` voor token
4. Implementatie van `GraphEmailClient.list_new()` — momenteel stub, vereist Graph-credentials om af te bouwen
5. Eerste live order: monitor `kwabo.log` voor `event=nav_stepwise_failure` records met volledige diagnostiek

## Niet in scope (voor latere ronde)

Bewust uitgesteld in dit plan:
- Echte `GraphEmailClient.list_new()` implementatie (alleen werkende stub)
- Retry/backoff op NAV 5xx
- NL-feestdagenkalender voor `shipmentDate`
- Kill-switch/fallback van real → mock op error
- Auto-match rate-verbeteringen (LLM extract + fuzzy matching) — separate werkstroom
