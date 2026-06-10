# Go-live checklist — wat alleen Cas nog moet doen

Code-status van deze branch:
- 242 backend tests groen, 0 failures
- Admin auth (login-pagina + middleware-redirect, JWT bearer in cookie) actief
- NAV 2018 OData V4 client (`navision_nav2018.py`) klaar, 10 unit-tests groen
- Frontend build slaagt op Vercel onder cas-pilex scope
- Railway backend live op `https://kwabo-production.up.railway.app`
- **Commit 88166c2** (`fix(mailbox): expose OAuth start/callback publicly + parametrize frontend URL`):
  - `/api/mailbox/oauth/start` en `/oauth/callback` zitten nu in een
    aparte public router; Microsoft kan callback bereiken zonder Bearer
    token (was `{"detail":"Niet ingelogd"}`). CSRF blijft via state-token.
  - Nieuwe `FRONTEND_URL` env-var vervangt het hardcoded
    `http://localhost:3000` in de callback-pagina (zie env-tabel).

Wat hieronder staat zijn de stappen die alleen jij kan doen omdat ze
externe systeemtoegang of fysieke configuratie vereisen.

---

## 1. Admin password instellen op Railway

Verplicht. Zonder password is auth uit (dev-mode) en kan iedereen het
dashboard openen.

Railway → kwabo-production service → **Variables** → **New Variable**:

```
ADMIN_PASSWORD=<kies-een-sterk-wachtwoord>
JWT_SECRET=<32+ random chars, ander dan ADMIN_PASSWORD>
```

`JWT_SECRET` rotation = alle sessies vervallen. Bewaar deze 2 in een
password manager. Deel **alleen** ADMIN_PASSWORD met Kwabo-personeel.

Na save → Railway deployt automatisch opnieuw → login werkt.

## 2. NAV 2018 koppeling activeren

Railway → Variables → toevoegen:

```
NAVISION_MODE=nav2018
NAV_BASE_URL=https://sf-112840.dynamicstocloud.com:1143/ST-124593/ODataV4
NAV_COMPANY=Kopie 2026 Kwabo Techniek B.V.
NAV_USERNAME=<service-user-in-NAV>
NAV_PASSWORD=<web-service-access-key>
NAV_VERIFY_SSL=true
```

> Kopie 2026 is het nieuwe test-bedrijf voor de overdracht (was 2023).
> Port **1143** met instance `ST-124593` per de mail van NAV-beheer. Als
> NAV op deze port Digest-auth weigert, fallback: port `1153` met instance
> `ST-124593-WS` en zelfde NAV_COMPANY waarde — de `Nav2018ODataClient`
> verwerkt beide setups zonder code-wijzigingen.

### Hoe je de Web Service Access Key krijgt

1. NAV 2018 → **User Setup** of **Users** lijst → user-kaart van de
   service-account
2. **Web Service Access Key** veld → **Generate** of **New** →
   kopieer de waarde (28+ alfanumerieke tekens)
3. Als deze user nog niet bestaat: maak een dedicated `KWABO_API` user
   met permissies (`P/G`) op:
   - PLX_SalesOrder, PLX_SalesOrderLines (write)
   - PLX_Customer, PLX_Item, PLX_ItemReference (read)
   - PLX_ShipToAddress, PLX_ItemUnitOfMeasure (read)

### Connectiviteit testen vanuit het dashboard

Na deploy: open in je browser
`https://kwabo-pilex.vercel.app/api/diagnostics/nav` (vervang door je
eigen Vercel URL). Output:

```json
{
  "ok": true,
  "status": 200,
  "url": "https://sf-112840.../Company('...')/PLX_SalesOrder",
  "page": "PLX_SalesOrder",
  "company": "Kopie 2023 Kwabo Techniek B.V.",
  "preview": "..."
}
```

- `ok: false, status: 401` → username/key fout
- `ok: false, status: 404` → page name fout (NAV_PAGE_* vars overriden)
- `ok: false, error: ConnectError` → DNS/firewall probleem

### Page names anders dan PLX_* ?

Override per env var:

```
NAV_PAGE_SALES_ORDER=<jouw_page>
NAV_PAGE_SALES_ORDER_LINES=<jouw_page>
# etc.
```

## 3. Microsoft Graph mailbox via dashboard koppelen

Stappen voor Kwabo-personeel (na inloggen):

1. **Login** op `https://kwabo-pilex.vercel.app/` met het admin password
2. Open `/email` in het dashboard
3. Azure AD app registratie:
   - `portal.azure.com` → App registrations → Kwabo-app
   - **Authentication** → Redirect URIs → voeg de productie-URL toe:
     ```
     https://kwabo-production.up.railway.app/api/mailbox/oauth/callback
     ```
     (NIET `kwabo-pilex.vercel.app/api/...` — die geeft 404 op Vercel
     omdat de FastAPI backend op Railway draait.)
   - **API permissions** (Microsoft Graph, delegated):
     `Mail.ReadWrite`, `User.Read`, `offline_access` — Admin consent.
   - **Certificates & secrets** → noteer Tenant ID, Client ID, Client Secret
4. In `/email` dashboard:
   - Vul Tenant ID, Client ID, Client Secret in
   - **Redirect URI** veld → vul exact dezelfde Railway-URL in als in stap 3
   - **Config opslaan**
   - **Connect with Microsoft** → OAuth-flow → consent
5. Daarna verschijnt elke nieuwe mail in `info@kwabo.nl` automatisch in
   de Order Queue

### Backend env vars die de mailbox-flow nodig heeft

Naast de admin-vars uit §1:
```
FRONTEND_URL=https://kwabo-pilex.vercel.app
EMAIL_MODE=graph
```

`FRONTEND_URL` bepaalt waar de OAuth-callback de gebruiker terug-redirect
na een succesvolle Microsoft-login (zonder dit: redirect naar localhost).

## 4. Eén staging-push als acceptatietest

Vóór je productie aanzet — drop één test-`.eml` in `data/inbox/` lokaal,
of laat het via mailbox binnenkomen. Verifieer in NAV staging dat:

- [ ] Sales Header is aangemaakt met klantgegevens (Sell_to_Customer_Name,
  Payment_Terms_Code, Currency_Code) — bewijs dat de OnValidate van
  `Sell_to_Customer_No` is gelopen
- [ ] Sales Line bevat Unit_Price > 0 (niet 0) — bewijs dat NAV's
  prijs-codeunit liep na de PATCH op `No`
- [ ] External_Document_No, Requested_Delivery_Date, Shipment_Date
  staan op de orderkop
- [ ] Bij mix-klant + mix-artikel: Unit_Price wijzigt nadat de
  quantity-PATCH binnenkomt (bewijs dat mix-staffel codeunit liep)

Als alle vier kloppen → veilig om productie aan te zetten.

## 5. On-site verificatie ná go-live (Fase 3/4-restpunten)

- [ ] **pgbouncer-veiligheid (Supabase poort 6543, transaction-mode).** Vuur
  een reeks opeenvolgende DB-zware requests af (b.v. 10× achter elkaar een
  order herverwerken en/of de orderslijst + artikelen-endpoints verversen)
  en controleer de Railway-logs op prepared-statement-fouten
  (`DuplicatePreparedStatement` / "prepared statement ... already exists").
  De pooling-test (`test_db_engine_pooling`, `prepare_threshold=None`) is
  characterization van de engine-config — dít is het runtime-bewijs op de
  echte bouncer.
- [ ] **Veris-mixorder (klant 60203).** Stuur/herverwerk een echte
  Veris-order en verifieer op de NAV-order: juiste `M{X}PAL{Y}`-codes per
  regel én juiste aantallen (staffel volgt order-totaal-pallets:
  1→M1, 8→M7, 12→M10). Vereist eerst NAV-side **OPS-item g**: de
  mixprijzen-vlag exposen op de KlantOut/PLX_Customer-page — zolang die
  vlag niet meekomt staat mixprijzen voor echte klanten uit en is deze
  check niet uitvoerbaar.

### Open punten (geen code — eerst business-antwoord)

- **7002-cascade (Fase 3, STAP 5).** Open vraag aan de NAV-expert: moet de
  app de Verkoopprijs-cascade (tabel 7002) als beslissteun spiegelen, en zo
  ja via welke page? NAV exposet de 7002-page nu niet
  (FASE0_NULMETING B7: geen PLX_SalesPrice/Verkoopprijzen in de 42 entity
  sets); prijsbepaling blijft NAV's eigen codeunit en de app rekent zelf
  geen prijzen. Bewust géén code gebouwd tot hier antwoord op is.

## Kort overzicht van environment-variabelen

| Variabele | Waar | Vereist | Doel |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Railway | ✓ | Claude voor LLM-extract |
| `DATABASE_URL` | Railway | ✓ | Supabase Postgres URL |
| `ADMIN_PASSWORD` | Railway | ✓ (productie) | Login-gate |
| `JWT_SECRET` | Railway | ✓ (productie) | Session-signing key |
| `NAVISION_MODE` | Railway | ✓ | `nav2018` voor jouw test-env |
| `NAV_BASE_URL` | Railway | bij nav2018 | OData V4 root URL |
| `NAV_COMPANY` | Railway | bij nav2018 | Display name in NAV |
| `NAV_USERNAME` | Railway | bij nav2018 | NAV user |
| `NAV_PASSWORD` | Railway | bij nav2018 | Web Service Access Key |
| `FRONTEND_URL` | Railway | ✓ (productie) | `https://kwabo-pilex.vercel.app` — bepaalt OAuth-callback redirect |
| `EMAIL_MODE` | Railway | bij Graph | `graph` |
| `KWABO_CORS_EXTRA` | Railway | ✓ | `https://kwabo-pilex.vercel.app` |
| `NEXT_PUBLIC_API_BASE` | Vercel | ✓ | `https://kwabo-production.up.railway.app` |

## Hoe je deze stack pauseert / debugt

- **Backend logs**: Railway → service → Logs tab (live tail)
- **Frontend build logs**: Vercel → project → Deployments → klik laatste
- **NAV connectiviteit**: `/api/diagnostics/nav` (dashboard auth nodig)
- **Auth probleem**: `/api/auth/me` met `Authorization: Bearer ...`
  header curlen — moet `{"ok": true}` geven
