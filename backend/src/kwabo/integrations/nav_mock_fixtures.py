"""Static seed data used by MockNavisionClient.

Extracted from navision_api.py so that file can focus on the protocol +
mock-client logic. These constants are pure data — the mock client copies
them on construction (`list(MOCK_CUSTOMERS)`, etc.) so consumers should
treat them as read-only.

`mixprijzen` flags drive the trigger-aware mock pricing rule (see
MockNavisionClient.create_sales_order_stepwise): mix-discount applies only
when BOTH the customer and the item carry the mixprijzen flag AND the line
quantity reaches the pallet-staffel threshold.
"""
from __future__ import annotations


# Seed gebaseerd op de 17 voorbeelden. Mock = in-memory + persist naar json.
MOCK_CUSTOMERS: list[dict] = [
    {"number": "10001", "displayName": "Ferney Diabolo B.V.", "email": "purchaseorders@ferney.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": True},
    {"number": "10002", "displayName": "TABS / PontMeyer", "email": "supplychain@tabsholland.nl",
     "paymentTermsCode": "14D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10003", "displayName": "Isero Ijzerwaren B.V.", "email": "fransvanvliet@isero.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": True},
    {"number": "10004", "displayName": "BMN Bouwmaterialen", "email": "jeroen.vanschooten@bmn.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10005", "displayName": "Omtzigt Bouw", "email": "kg@omtzigt-bouwmaterialen.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10006", "displayName": "Driessen Verf b.v.", "email": "bestellenhelmond@driessenverf.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10007", "displayName": "Stukbouw B.V.", "email": "willy@stukbouw.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10008", "displayName": "Enka Bouwmaterialen", "email": "e.sun@enkabouwmarkt.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLD",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10009", "displayName": "Connect Products GmbH", "email": "patricia@connectproducts.nl",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10010", "displayName": "Storch-Ciret GmbH", "email": "s.wilke@storch-ciret.com",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10011", "displayName": "Kirchner GmbH", "email": "tobias.leyhausen@kirchner-online.com",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10012", "displayName": "Werkzeuge Dietrich GmbH & Co. KG", "email": "malte.klippstein@werkzeuge-dietrich.de",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10013", "displayName": "Bugel AG", "email": "r.carvalho@bugel.ch",
     "paymentTermsCode": "30D", "currencyCode": "CHF", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10014", "displayName": "BAUHAUS", "email": "supplier@bahag.com",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "DEU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10015", "displayName": "Tectis OU", "email": "maarjaliisa.nomm@tectis.ee",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "ENU",
     "shipToCode": "MAIN", "mixprijzen": False},
    {"number": "10016", "displayName": "L. De Vos sa/nv", "email": "anja@lucdevos.be",
     "paymentTermsCode": "30D", "currencyCode": "EUR", "languageCode": "NLB",
     "shipToCode": "MAIN", "mixprijzen": False},
]

MOCK_ITEMS: list[dict] = [
    {"number": "1515155", "displayName": "Ferney stucloper 120cm",
     "baseUnitOfMeasureCode": "ROL", "mixprijzen": True},
    {"number": "228321", "displayName": "TABS hoeknaald 260cm",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "2597768", "displayName": "Isero topcoat 20kg",
     "baseUnitOfMeasureCode": "EMMER", "mixprijzen": True},
    {"number": "201291", "displayName": "BMN pallet 1",
     "baseUnitOfMeasureCode": "PAL", "mixprijzen": False},
    {"number": "83461", "displayName": "BMN kist statiegeld",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "122338", "displayName": "BAUHAUS product",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "47323", "displayName": "Tectis Proshield private label",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "975097", "displayName": "L. De Vos Greenboard B1 75m2",
     "baseUnitOfMeasureCode": "M2", "mixprijzen": False},
    {"number": "CICS-100-25", "displayName": "Werkzeuge Dietrich coating",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-OMTZIGT", "displayName": "Omtzigt product",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-DRIESSEN", "displayName": "Driessen Verf product",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-KIRCHNER-238534", "displayName": "Kirchner FORCH editie",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "DUMMY-BUGEL", "displayName": "Bugel Zwitserse editie",
     "baseUnitOfMeasureCode": "STUK", "mixprijzen": False},
    {"number": "SOFTBREATH-PALLET", "displayName": "Softbreath pallet",
     "baseUnitOfMeasureCode": "PAL", "mixprijzen": True},
]


# Default unit price per item, used by the mock's POST /salesOrderLines trigger
# emulation. Keep small — only items that the new tests touch need entries.
MOCK_PRICES: dict[str, float] = {
    "1515155": 100.0,
    "228321": 12.5,
    "2597768": 80.0,
    "201291": 250.0,
    "975097": 35.0,
    "SOFTBREATH-PALLET": 500.0,
}


# Pallet-staffel mix discount kicks in once a single line reaches this
# quantity AND both customer + item are mixprijzen=True.
MOCK_MIX_THRESHOLD: int = 24
MOCK_MIX_DISCOUNT_FACTOR: float = 0.9


# Ship-to addresses keyed by customer number. Each customer has at least
# the implicit "MAIN" address; some have extras to exercise the dropdown.
MOCK_SHIP_TOS: dict[str, list[dict]] = {
    "10001": [
        {"code": "MAIN", "name": "Ferney Diabolo B.V.",
         "address": "Industrieweg 1", "city": "Amsterdam",
         "postCode": "1000 AA", "country": "NL"},
        {"code": "DC-EAST", "name": "Ferney DC Oost",
         "address": "Logistiekpark 12", "city": "Apeldoorn",
         "postCode": "7300 BB", "country": "NL"},
    ],
    "10003": [
        {"code": "MAIN", "name": "Isero HQ",
         "address": "IJzerstraat 5", "city": "Rotterdam",
         "postCode": "3000 CC", "country": "NL"},
    ],
    "10013": [
        {"code": "MAIN", "name": "Bugel AG",
         "address": "Hauptstrasse 9", "city": "Zürich",
         "postCode": "8000", "country": "CH"},
    ],
}


# Item UoMs keyed by item number. The base UoM is repeated here with
# qtyPerUnitOfMeasure=1.0; alternates carry their conversion factor.
MOCK_ITEM_UOMS: dict[str, list[dict]] = {
    "1515155": [
        {"code": "ROL", "qtyPerUnitOfMeasure": 1.0},
        {"code": "PAL", "qtyPerUnitOfMeasure": 24.0},
    ],
    "228321": [
        {"code": "STUK", "qtyPerUnitOfMeasure": 1.0},
        {"code": "DOOS", "qtyPerUnitOfMeasure": 50.0},
    ],
    "2597768": [
        {"code": "EMMER", "qtyPerUnitOfMeasure": 1.0},
        {"code": "PAL", "qtyPerUnitOfMeasure": 33.0},
    ],
}


# Item references (cross-references): customer-specific item codes that map
# to a Kwabo item number. Used by the order-review UI to suggest a match
# when the email shows the customer's own SKU.
MOCK_ITEM_REFERENCES: list[dict] = [
    {"itemNumber": "1515155", "referenceType": "Customer",
     "referenceTypeNo": "10001", "referenceNo": "FER-STUC-120"},
    {"itemNumber": "2597768", "referenceType": "Customer",
     "referenceTypeNo": "10003", "referenceNo": "ISE-TC-20"},
]
