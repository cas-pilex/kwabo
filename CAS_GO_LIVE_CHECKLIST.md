# Go-live checklist — wat alleen Cas nog moet doen

Code-status van deze branch:
- 232 backend tests groen, 0 failures
- Admin auth (login-pagina + middleware-redirect, JWT bearer in cookie) actief
- NAV 2018 OData V4 client (`navision_nav2018.py`) klaar, 10 unit-tests groen
- Frontend build slaagt op Vercel onder cas-pilex scope
- Railway backend live op `https://kwabo-production.up.railway.app`

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
NAV_BASE_URL=https://sf-112840.dynamicstocloud.com:1153/ST-124593-WS/ODataV4
NAV_COMPANY=Kopie 2023 Kwabo Techniek B.V.
NAV_USERNAME=<service-user-in-NAV>
NAV_PASSWORD=<web-service-access-key>
NAV_VERIFY_SSL=true
```

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

Geen code-wijzigingen nodig. Stappen voor Kwabo-personeel (na inloggen):

1. **Login** op `https://kwabo-pilex.vercel.app/` met het admin password
2. Open `/email` in het dashboard
3. Volg de in-app walkthrough:
   - Azure AD app registreren (`portal.azure.com`)
   - 3 waarden invoeren (Tenant ID, Client ID, Client Secret)
   - Klik **Connect with Microsoft** → OAuth-flow → consent
4. Daarna verschijnt elke nieuwe mail in `info@kwabo.nl` automatisch in
   de Order Queue

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
| `KWABO_CORS_EXTRA` | Railway | ✓ | `https://kwabo-pilex.vercel.app` |
| `NEXT_PUBLIC_API_BASE` | Vercel | ✓ | `https://kwabo-production.up.railway.app` |

## Hoe je deze stack pauseert / debugt

- **Backend logs**: Railway → service → Logs tab (live tail)
- **Frontend build logs**: Vercel → project → Deployments → klik laatste
- **NAV connectiviteit**: `/api/diagnostics/nav` (dashboard auth nodig)
- **Auth probleem**: `/api/auth/me` met `Authorization: Bearer ...`
  header curlen — moet `{"ok": true}` geven
