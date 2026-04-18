# Kwabo Order Intake AI

AI-gestuurd systeem dat inkomende order-e-mails op `info@kwabo.nl` automatisch verwerkt tot conceptverkooporders in Microsoft Dynamics NAV 2018. Zie `../kwabo_technische_beschrijving.md.pdf` voor de volledige specificatie.

## Status (huidige implementatie)

- ✅ **Python backend:** LangGraph-pipeline van 7 nodes (intake → classify → extract → match_customer → match_articles → validate_prices → compose_order) + finalize (push_navision → send_confirmation)
- ✅ **LLM-extractie:** Claude Sonnet 4.5 met prompt voor NL/DE/EN orders; robuuste JSON-parser die truncatie repareert
- ✅ **Mock Navision:** in-memory met persist naar `data/navision_mock/orders/*.json`
- ✅ **File-drop mailbox:** `.eml` bestanden in `data/inbox/` → `POST /api/intake/scan`
- ✅ **SQLite DB:** klantenkaarten, artikelmappings, prijsafspraken, matching history, order_log
- ✅ **FastAPI REST:** `/api/orders`, `/api/klanten`, `/api/artikelen`, `/api/audit`, `/api/intake`
- ✅ **Next.js 16 dashboard:** queue, order-review met inline artikel-correctie, klantenbeheer, audit log met stats
- ✅ **Self-learning:** dashboard-correcties worden opgeslagen in `artikel_matching_history` en `klantenkaart_artikelen` — volgende gelijke e-mail wordt automatisch gematcht

### Baseline regressie op 17 voorbeeld-emails

| Metric | Resultaat |
|---|---|
| Emails geparseerd | 17/17 |
| Als order geclassificeerd | 16/17 (1 = lege duplicaat Werkzeuge Dietrich, correct afgewezen) |
| Klant gematcht | 12/16 (75%) |
| Sales orders in Navision mock | 16/17 (94%) |
| Artikel auto-match | ~22% (lage baseline omdat seed mappings slechts voorbeelden dekken) |

Artikel-match-rate verbetert structureel naarmate de dashboard-reviewer correcties opslaat (self-learning loop).

## Quickstart

### Eenmalig

```bash
cd backend
pip install -r requirements.txt           # of: uv sync
cp .env.example .env                      # vul ANTHROPIC_API_KEY in
cd ../frontend
pnpm install
```

### Backend draaien

```bash
cd backend
PYTHONPATH=src python -m uvicorn kwabo.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
```

### Frontend draaien

```bash
cd frontend
pnpm dev                                  # http://localhost:3000 (of 3001)
```

### Verwerkings­flow testen

```bash
# 1) single email
cd backend
python scripts/run_single_email.py "tests/test_data/emails/Ferney inkooporder 4200056148.eml" --approve

# 2) batch alle 17 — resultatenrapport
python scripts/run_all.py

# 3) via API: drop emails in data/inbox/ en scan
curl -X POST http://localhost:8000/api/intake/scan
```

## Repository layout

```
kwabo-order-intake/
├── backend/
│   ├── src/kwabo/
│   │   ├── config.py              Settings (pydantic-settings)
│   │   ├── main.py                FastAPI app
│   │   ├── api/                   orders, klanten, artikelen, audit, intake_trigger
│   │   ├── db/                    SQLModel schema + repository + seed
│   │   ├── graph/
│   │   │   ├── state.py           OrderState TypedDict
│   │   │   ├── graph.py           StateGraph build
│   │   │   ├── llm.py             Anthropic Claude
│   │   │   ├── runner.py          convenience runner
│   │   │   └── nodes/             intake, classify, extract, match_customer, match_articles, validate_prices, compose_order, push_navision
│   │   ├── prompts/               classify.txt, extract.txt
│   │   ├── integrations/          pdf_parser, email_client (FileDrop), navision_api (Mock)
│   │   └── utils/                 eenheid_mapping, json_parser, logging
│   ├── scripts/                   run_single_email.py, run_all.py
│   └── tests/test_data/emails/    17 voorbeeld .eml bestanden
├── frontend/
│   ├── app/
│   │   ├── page.tsx               Order queue
│   │   ├── orders/[id]/           Order review (split-view + inline correcties)
│   │   ├── klanten/[nr]/          Klantenbeheer + artikelmappings
│   │   └── audit/                 Audit log + stats
│   └── lib/api.ts                 Typed API client
└── data/
    ├── inbox/                     Drop .eml hier voor scan
    ├── processed/                 Verwerkte .eml bestanden
    └── navision_mock/orders/      Mock ERP orders als JSON
```

## Swap naar echte externe systemen

- **Navision 2018 REST:** implementeer `RealNavisionClient` achter `NavisionClient`-protocol in `integrations/navision_api.py` (PDF §10) en zet `NAVISION_MODE=real` in `.env`.
- **IMAP/Graph mailbox:** implementeer `ImapEmailClient` achter `EmailClient`-protocol; zet `EMAIL_MODE=imap`.
- **SharePoint klantenkaart-import:** nieuw script `scripts/import_klantenkaarten.py` via Microsoft Graph.

Geen andere code hoeft aangepast — alle nodes en API-routes zijn integratie-agnostisch.

## Volgende stappen om naar 100% werkende orders te komen

1. **Artikel-match verbeteren:** seed mapping aanvullen op basis van echte Kwabo-masterdata (Nav items export) zodat exact/klantenkaart-matches slagen i.p.v. fuzzy → 80%+ auto-match.
2. **Echte Navision credentials** toevoegen en `RealNavisionClient` implementeren; item-search geeft dan live hits i.p.v. mock.
3. **Prompt-tuning:** extract-prompt iteratief verfijnen per klant-format (TABS/PontMeyer speciaal; Kirchner multi-order array).
4. **Forwarded-email afzenderdetectie:** nu vallen 4 forwards (Ivar/Mark/Nico @ kwabo.nl) naar "klant niet gevonden" — regex op forwarded-content toevoegen.
5. **Tests uitbreiden:** per-email JSON fixtures in `tests/test_data/expected/` en `pytest` regressie-harness.
6. **LangSmith tracing** aanzetten (`LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`) voor productie-observability.
