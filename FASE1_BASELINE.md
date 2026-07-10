# FASE 1 — RODE BASELINE (her-diagnose, opdracht 1b)

Volledige per-order-output van de HUIDIGE gecommitte pipeline met echte extractie
en echte prod-masterdata (read-only mirror). Niets samengevat: per order staat de
integrale meetrecord van run 1 (vers) hieronder geplakt. Judge = geauditeerd
(`FASE1_JUDGE_AUDIT.md`); corpus-getrouwheid = her-gelabeld (`tests/corpus/manifest.json`).

## Run-metadata

- **run1** (fase1_run1_vers.json): git `cd190a6abe7f`, model `claude-sonnet-4-5`, cache `read-only` (41→41 entries), NAV `mirror`, 21 records, 2026-07-10T12:58:10.086481+00:00
- **run2** (fase1_run2_replay.json): git `cd190a6abe7f`, model `claude-sonnet-4-5`, cache `read-only` (41→41 entries), NAV `mirror`, 21 records, 2026-07-10T12:58:34.505168+00:00
- **run3** (fase1_run3_replay.json): git `cd190a6abe7f`, model `claude-sonnet-4-5`, cache `read-only` (41→41 entries), NAV `mirror`, 21 records, 2026-07-10T12:58:42.364414+00:00
- **run4** (fase1_run4_vers2.json): git `cd190a6abe7f`, model `claude-sonnet-4-5`, cache `on` (0→10 entries), NAV `mirror`, 5 records, 2026-07-10T13:00:59.454737+00:00

## Totaal (run 1, geauditeerde judge)

| stille fouten | fout-met-vlag | juist | geen-GT | crashes |
|---|---|---|---|---|
| **0** | 3 | 14 | 4 | 0 |

Masterdata-tellingen (schaarste zichtbaar): klantenkaarten=1787, klant_email_aliases=1, klantenkaart_ship_to=2506, artikelkaarten=3757, artikel_eenheden=12963, klantenkaart_artikelen=25, artikel_kruisverwijzing=3000, artikel_matching_history=25, artikel_pallet_kennis=20, prijsafspraken=0, pallet_plaatsen_basis=0

## Overzicht per order (run 1)

| order | bron | extractie | oordeel | niet-juiste velden | vlaggen |
|---|---|---|---|---|---|
| #944 | tekst_reconstructie | tekst | JUIST | — | 1 |
| #954 | tekst_reconstructie | tekst | JUIST | — | 1 |
| #941 | tekst_reconstructie | tekst | JUIST | — | 2 |
| #847 | tekst_reconstructie | tekst | JUIST | — | 3 |
| #847 (eml:Bestellung Werkzeuge Dietrich GmbH & Co. KG.eml) | echt_eml | vision_eml_echt | geen_grondwaarheid | — | 2 |
| #847 (eml:Werkzeuge Dietrich GmbH & Co. KG.eml) | echt_eml | vision_eml_echt | geen_grondwaarheid | — | 0 |
| #819 | tekst_reconstructie | tekst | JUIST | — | 1 |
| #845 | tekst_reconstructie | tekst | JUIST | — | 1 |
| #203 | tekst_reconstructie | tekst | review | regel2.artikel=FOUT-met-vlag | 2 |
| #816 | tekst_reconstructie | tekst | JUIST | — | 11 |
| #832 | tekst_reconstructie | tekst | review | europallet_aantal=FOUT-met-vlag | 2 |
| #833 | tekst_reconstructie | tekst | review | europallet_aantal=FOUT-met-vlag | 2 |
| #834 | tekst_reconstructie | tekst | JUIST | — | 1 |
| #716 | tekst_reconstructie | tekst | JUIST | — | 1 |
| #717 | tekst_reconstructie | tekst | JUIST | — | 2 |
| #718 | tekst_reconstructie | tekst | JUIST | — | 3 |
| #721 | tekst_reconstructie | tekst | JUIST | — | 2 |
| #707 | tekst_reconstructie | tekst | JUIST | — | 2 |
| #685 | tekst_reconstructie | tekst | JUIST | — | 17 |
| #619 | tekst_reconstructie | tekst | geen_grondwaarheid | — | 2 |
| #712 | tekst_reconstructie | tekst | geen_grondwaarheid | — | 1 |

## Replay-delta run1↔run2 (pipeline-determinisme)

*Geen enkele delta — byte-identiek op samenvatting+oordeel.*

## Replay-delta run1↔run3 (pipeline-determinisme)

*Geen enkele delta — byte-identiek op samenvatting+oordeel.*

## Verse-trekking-delta run1↔run4 (LLM-variantie, 5 ankers)

### 941|state
```
samenvatting.extract.adres_rollen.aflever.plaats: "Breda" -> "BREDA"
samenvatting.extract.afleveradres.plaats: "Breda" -> "BREDA"
samenvatting.regels[0].art_klant: null -> "804600"
samenvatting.regels[0].oms: "ProGold Afdekvlies ETP 25m2 804600 Per Rol" -> "ProGold Afdekvlies ETP 25m2 Per Rol"
samenvatting.regels[1].art_klant: null -> "804555"
samenvatting.regels[1].oms: "ProGold Stucloper 50m2 804555" -> "ProGold Stucloper 50m2"
samenvatting.regels[2].art_klant: null -> "804430"
samenvatting.regels[2].oms: "ProGold Stucloper 30m2 804430" -> "ProGold Stucloper 30m2"
```
### 845|state
```
samenvatting.extract.adres_rollen.besteller.naam: "Lasaulec B.V." -> "Lasaulec BV"
samenvatting.extract.klantnaam_besteller: "Lasaulec B.V." -> "Lasaulec BV"
```

## Volledige per-order-records (run 1, ongesamenvat)

### Order #944 — BAUHAUS 1049577521

```json
{
  "order": "944",
  "label": "BAUHAUS 1049577521",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "adresrollen (besteladres vs afleveradres)",
    "klantresolutie"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "BAUHAUS Nederland C.V.",
      "bestelnummer_klant": "1049577521",
      "taal": "NL",
      "afleveradres": {
        "naam": "BAUHAUS Nederland C.V.",
        "straat": "Het Plein 10",
        "postcode": "7559 SR",
        "plaats": "Hengelo",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "BAUHAUS Nederland C.V.",
          "straat": "Regulierenring 2G",
          "postcode": "3981 LB",
          "plaats": "Bunnik",
          "land": "NL"
        },
        "factuur": {
          "naam": "BAUHAUS Nederland C.V.",
          "straat": "Regulierenring 2G",
          "postcode": "3981 LB",
          "plaats": "Bunnik",
          "land": "NL"
        },
        "aflever": {
          "naam": "BAUHAUS Nederland C.V.",
          "straat": "Het Plein 10",
          "postcode": "7559 SR",
          "plaats": "Hengelo",
          "land": "NL"
        },
        "eindontvanger": {
          "naam": "BAUHAUS Nederland C.V.",
          "straat": "Het Plein 10",
          "postcode": "7559 SR",
          "plaats": "Hengelo",
          "land": "NL"
        }
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61854",
      "naam": "Bauhaus Nederland C.V.",
      "bron": "naam_extract",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "7559 SR",
    "ship_to_kandidaten": [
      {
        "code": "2635 BS",
        "pc": "2635 BS",
        "plaats": "Den Hoorn"
      },
      {
        "code": "3981 LB",
        "pc": "3981 LB",
        "plaats": "BUNNIK"
      },
      {
        "code": "5916 PR",
        "pc": "5916 PR",
        "plaats": "VENLO"
      },
      {
        "code": "7559 SR",
        "pc": "7559 SR",
        "plaats": "HENGELO OV"
      },
      {
        "code": "9723 AW",
        "pc": "9723 AW",
        "plaats": "GRONINGEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "31489201",
        "art_matched": "238531",
        "oms": "AFDEKVLIES 25M² VLOEISTOFDI. TOPLAAG",
        "hoeveelheid": 45.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 45.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": [
        {
          "artikelnr": "238531",
          "qty": 45.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 8,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 238531 (45.0 STUK) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (238531) — NAV berekent de prijs zelf; de mailprijs (€22.95) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #954 — TABS 4506877460

```json
{
  "order": "954",
  "label": "TABS 4506877460",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "klantresolutie (agent-mailbox)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "TABS Holland B.V.",
      "bestelnummer_klant": "4506877460",
      "taal": "NL",
      "afleveradres": {
        "naam": "Jongeneel Woerden BA659",
        "straat": "Pijpenmakersweg 2",
        "postcode": "3449 JE",
        "plaats": "WOERDEN",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "TABS Holland B.V.",
          "straat": "Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "factuur": {
          "naam": "TABS Holland B.V.",
          "straat": "Supply Chain TABS ( BA 633 ), Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "aflever": {
          "naam": "Jongeneel Woerden BA659",
          "straat": "Pijpenmakersweg 2",
          "postcode": "3449 JE",
          "plaats": "WOERDEN",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "50094",
      "naam": "Jongeneel Woerden BA659",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "3449 JE",
    "ship_to_kandidaten": [
      {
        "code": "3449 JE",
        "pc": "3449 JE",
        "plaats": "WOERDEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "228321",
        "art_matched": "228321",
        "oms": "stucloper/protectiekarton onbedrukt 950-1050mm r",
        "hoeveelheid": 30.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 1,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "1.0 pallets in order → 1 europallet (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "228321",
          "qty": 30.0,
          "eenheid": "STUK",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 11,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "Geen prijsafspraak in DB voor regel 1 (228321) — NAV berekent de prijs zelf; de mailprijs (€20.75) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #941 — PPG/Driessen XO092614

```json
{
  "order": "941",
  "label": "PPG/Driessen XO092614",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "eenheid/aantal (mix)",
    "europallet"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Driessen Verf B.V.",
      "bestelnummer_klant": "XO092614",
      "taal": "NL",
      "afleveradres": {
        "naam": "Driessen Verf Breda",
        "straat": "Huifakkerstraat 16",
        "postcode": "4815 PN",
        "plaats": "Breda",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Driessen Verf B.V.",
          "straat": null,
          "postcode": null,
          "plaats": null,
          "land": "NL"
        },
        "factuur": null,
        "aflever": {
          "naam": "Driessen Verf Breda",
          "straat": "Huifakkerstraat 16",
          "postcode": "4815 PN",
          "plaats": "Breda",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 3
    },
    "klant": {
      "nr": "61483",
      "naam": "PPG - Driessen Verf B.V.",
      "bron": "naam_extract",
      "conf": 0.8,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "4814 RR",
    "ship_to_kandidaten": [
      {
        "code": "4704 RK",
        "pc": "4704 RK",
        "plaats": "ROOSENDAAL"
      },
      {
        "code": "4814 RR",
        "pc": "4814 RR",
        "plaats": "BREDA"
      },
      {
        "code": "4906 CT",
        "pc": "4906 CT",
        "plaats": "OOSTERHOUT NB"
      },
      {
        "code": "5048 AB",
        "pc": "5048 AB",
        "plaats": "TILBURG"
      },
      {
        "code": "5652 CL",
        "pc": "5652 CL",
        "plaats": "EINDHOVEN"
      },
      {
        "code": "5705 DK",
        "pc": "5705 DK",
        "plaats": "HELMOND"
      },
      {
        "code": "5707 AP",
        "pc": "5707 AP",
        "plaats": "HELMOND"
      },
      {
        "code": "5707 CL",
        "pc": "5707 CL",
        "plaats": "HELMOND"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": null,
        "art_matched": "23559",
        "oms": "ProGold Afdekvlies ETP 25m2 804600 Per Rol",
        "hoeveelheid": 45.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 45.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      },
      {
        "pos": 2,
        "art_klant": null,
        "art_matched": "23522",
        "oms": "ProGold Stucloper 50m2 804555",
        "hoeveelheid": 60.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 2,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      },
      {
        "pos": 3,
        "art_klant": null,
        "art_matched": "23523",
        "oms": "ProGold Stucloper 30m2 804430",
        "hoeveelheid": 60.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 2,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 4,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "4.0 pallets in order → 4 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23522",
          "qty": 60.0,
          "eenheid": "STUK",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 2.0
        },
        {
          "artikelnr": "23523",
          "qty": 60.0,
          "eenheid": "STUK",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 2.0
        }
      ],
      "onbekend": [
        {
          "artikelnr": "23559",
          "qty": 45.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 16,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 23559 (45.0 STUK) — telling kan onvolledig zijn."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel3.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel3.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel3.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #847 — Werkzeuge Dietrich -> se Huber (Strecken)

```json
{
  "order": "847",
  "label": "Werkzeuge Dietrich -> se Huber (Strecken)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "adresrollen",
    "klantresolutie (agent)",
    "ship-to"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Werkzeuge Dietrich GmbH & Co. KG",
      "bestelnummer_klant": "4270245223",
      "taal": "DE",
      "afleveradres": {
        "naam": "Huber GmbH & Co KG Straubing",
        "straat": "Borsigstr. 15",
        "postcode": "94315",
        "plaats": "Straubing",
        "land": "DE"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Werkzeuge Dietrich GmbH & Co. KG",
          "straat": "Leineweberstraße 4",
          "postcode": "31303",
          "plaats": "Burgdorf",
          "land": "DE"
        },
        "factuur": {
          "naam": "Werkzeuge Dietrich GmbH & Co. KG",
          "straat": "Leineweberstraße 4",
          "postcode": "31303",
          "plaats": "Burgdorf",
          "land": "DE"
        },
        "aflever": {
          "naam": "Huber GmbH & Co KG Straubing",
          "straat": "Borsigstr. 15",
          "postcode": "94315",
          "plaats": "Straubing",
          "land": "DE"
        },
        "eindontvanger": {
          "naam": "Huber GmbH & Co KG Straubing",
          "straat": "Borsigstr. 15",
          "postcode": "94315",
          "plaats": "Straubing",
          "land": "DE"
        }
      },
      "verzendwijze": null,
      "n_regels": 2
    },
    "klant": {
      "nr": "61532",
      "naam": "se Huber Straubing GmbH & Co KG",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "94315",
    "ship_to_kandidaten": [
      {
        "code": "85551",
        "pc": "85551",
        "plaats": "KIRCHHEIM B. MÜNCHEN"
      },
      {
        "code": "94315",
        "pc": "94315",
        "plaats": "Straubing"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "23730",
        "art_matched": "23730",
        "oms": "WD Abdeckvlies TFC 180g/qm 1x50m",
        "hoeveelheid": 930.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 31,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 2,
        "art_klant": "23733",
        "art_matched": "23733",
        "oms": "WD Abdeckvlies TFC 220g/qm 1x50m",
        "hoeveelheid": 700.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 35,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 66,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "66.0 pallets in order → 66 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23730",
          "qty": 930.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 31.0
        },
        {
          "artikelnr": "23733",
          "qty": 700.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 35.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 14,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "orderregels[0].eenheid",
      "orderregels[1].eenheid"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23730 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 2): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23733 (gebruikt nu standaard 'STUK').",
      "Geen prijsafspraak in DB voor regel 1 (23730) — NAV berekent de prijs zelf; de mailprijs (€13.05) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 2 (23733) — NAV berekent de prijs zelf; de mailprijs (€15.7) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #847 — eml:Bestellung Werkzeuge Dietrich GmbH & Co. KG.eml — Werkzeuge Dietrich -> se Huber (Strecken)

```json
{
  "order": "847",
  "variant": "eml:Bestellung Werkzeuge Dietrich GmbH & Co. KG.eml",
  "label": "Werkzeuge Dietrich -> se Huber (Strecken)",
  "bron_type": "echt_eml",
  "extractie_mode": "vision_eml_echt",
  "gt_status": "geen (familie-order, niet dezelfde order)",
  "categorieen": [
    "adresrollen",
    "klantresolutie (agent)",
    "ship-to"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Werkzeuge Dietrich GmbH & Co. KG",
      "bestelnummer_klant": "4401054959",
      "taal": "DE",
      "afleveradres": {
        "naam": "farbtex GmbH & Co KG",
        "straat": "Hewlett-Packard-Str. 1 Geb.",
        "postcode": "71083",
        "plaats": "Herrenberg-Gültstein",
        "land": "DE"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Werkzeuge Dietrich GmbH & Co. KG",
          "straat": "Leineweberstraße 4",
          "postcode": "31303",
          "plaats": "Burgdorf",
          "land": "DE"
        },
        "factuur": {
          "naam": "Werkzeuge Dietrich GmbH & Co. KG",
          "straat": "Leineweberstraße 4",
          "postcode": "31303",
          "plaats": "Burgdorf",
          "land": "DE"
        },
        "aflever": {
          "naam": "farbtex GmbH & Co KG",
          "straat": "Hewlett-Packard-Str. 1 Geb.",
          "postcode": "71083",
          "plaats": "Herrenberg-Gültstein",
          "land": "DE"
        },
        "eindontvanger": {
          "naam": "farbtex GmbH & Co KG",
          "straat": "Hewlett-Packard-Str. 1 Geb.",
          "postcode": "71083",
          "plaats": "Herrenberg-Gültstein",
          "land": "DE"
        }
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61502",
      "naam": "Farbtex Zentrallager",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "71083",
    "ship_to_kandidaten": [
      {
        "code": "71083",
        "pc": "71083",
        "plaats": "Herrenberg"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "4086-019309",
        "art_matched": "23733",
        "oms": "WD Abdeckvlies TFC 220g/qm 1x50m",
        "hoeveelheid": 1320.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 66,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 66,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "66.0 pallets in order → 66 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23733",
          "qty": 1320.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 66.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 11,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "orderregels[0].eenheid"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23733 (gebruikt nu standaard 'STUK').",
      "Geen prijsafspraak in DB voor regel 1 (23733) — NAV berekent de prijs zelf; de mailprijs (€15.7) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "geen_grondwaarheid",
    "velden": []
  }
}
```

### Order #847 — eml:Werkzeuge Dietrich GmbH & Co. KG.eml — Werkzeuge Dietrich -> se Huber (Strecken)

```json
{
  "order": "847",
  "variant": "eml:Werkzeuge Dietrich GmbH & Co. KG.eml",
  "label": "Werkzeuge Dietrich -> se Huber (Strecken)",
  "bron_type": "echt_eml",
  "extractie_mode": "vision_eml_echt",
  "gt_status": "geen (familie-order, niet dezelfde order)",
  "categorieen": [
    "adresrollen",
    "klantresolutie (agent)",
    "ship-to"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": null,
      "bestelnummer_klant": null,
      "taal": null,
      "afleveradres": {
        "naam": null,
        "straat": null,
        "postcode": null,
        "plaats": null,
        "land": null
      },
      "adres_rollen": null,
      "verzendwijze": null,
      "n_regels": 0
    },
    "klant": {
      "nr": null,
      "naam": null,
      "bron": null,
      "conf": null,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": null,
    "ship_to_kandidaten": [],
    "regels": [],
    "europallet": {
      "regel": null,
      "uitleg": null,
      "onderbouwing_regels": null,
      "onbekend": []
    },
    "compose": {
      "status": "leeg",
      "error": null,
      "nav_ops_count": 0,
      "ops": [],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [],
    "validatie_warnings": [],
    "is_order": false
  },
  "oordeel": {
    "status": "geen_grondwaarheid",
    "velden": []
  }
}
```

### Order #819 — Nexttcom afhaalorder (4 Paletten 23691)

```json
{
  "order": "819",
  "label": "Nexttcom afhaalorder (4 Paletten 23691)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "eenheid/aantal (pallet-UoM)",
    "verzendwijze (afhaal)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "NEXTTCOM GmbH",
      "bestelnummer_klant": null,
      "taal": "DE",
      "afleveradres": {
        "naam": null,
        "straat": null,
        "postcode": null,
        "plaats": null,
        "land": null
      },
      "adres_rollen": {
        "besteller": {
          "naam": "NEXTTCOM GmbH",
          "straat": "Hammerstraße 23",
          "postcode": "57645",
          "plaats": "Nister",
          "land": "DE"
        },
        "factuur": null,
        "aflever": null,
        "eindontvanger": null
      },
      "verzendwijze": "EXW",
      "n_regels": 1
    },
    "klant": {
      "nr": "61969",
      "naam": "Nexttcom gmbh",
      "bron": "naam_extract",
      "conf": 0.8,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": null,
    "ship_to_kandidaten": [],
    "regels": [
      {
        "pos": 1,
        "art_klant": "23691",
        "art_matched": "23691",
        "oms": "Heavy-Duty 180 g/m² 1 m x 50 m",
        "hoeveelheid": 4.0,
        "eenheid": "PALLET",
        "eenheid_origineel": "PAL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 4,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "4.0 pallets in order → 4 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23691",
          "qty": 4.0,
          "eenheid": "PAL",
          "bron": "pal_1op1",
          "pallet_maat": null,
          "pallets": 4.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 9,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentMethodCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match"
    ],
    "validatie_warnings": [
      "Forward: outer-from @kwabo.nl, subject-prefix; originele afzender=devin.schmitt@nexttcom.de",
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "Geen prijsafspraak in DB voor regel 1 (23691) — NAV berekent de prijs zelf; de mailprijs (€33.2) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "verzendwijze",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #845 — Lasaulec INK0090679 (art. 15620)

```json
{
  "order": "845",
  "label": "Lasaulec INK0090679 (art. 15620)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "eenheid/aantal (pallet-UoM)",
    "ship-to (drop-ship Polem Lemmer)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Lasaulec B.V.",
      "bestelnummer_klant": "INK0090679",
      "taal": "NL",
      "afleveradres": {
        "naam": "Polem B.V.",
        "straat": "Industrieweg 7",
        "postcode": "8531 PA",
        "plaats": "Lemmer",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Lasaulec B.V.",
          "straat": "Julianaweg 210 A",
          "postcode": "1131 DL",
          "plaats": "Volendam",
          "land": "NL"
        },
        "factuur": {
          "naam": "Lasaulec BV",
          "straat": "Postbus 405",
          "postcode": "8440 AK",
          "plaats": "HEERENVEEN",
          "land": "NL"
        },
        "aflever": {
          "naam": "Polem B.V.",
          "straat": "Industrieweg 7",
          "postcode": "8531 PA",
          "plaats": "Lemmer",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61745",
      "naam": "Lasaulec B.V.",
      "bron": "naam_extract",
      "conf": 0.8,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "8531 PA",
    "ship_to_kandidaten": [
      {
        "code": "8531 PA",
        "pc": "8531 PA",
        "plaats": "LEMMER"
      },
      {
        "code": "8747 GK",
        "pc": "8747 GK",
        "plaats": "HEERENVEEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "A552291",
        "art_matched": "15620",
        "oms": "Stucloper TFC Board Premium B keuze 70m2 per pal",
        "hoeveelheid": 2.0,
        "eenheid": "PALLET",
        "eenheid_origineel": "PAL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 2,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "2.0 pallets in order → 2 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "15620",
          "qty": 2.0,
          "eenheid": "PAL",
          "bron": "pal_1op1",
          "pallet_maat": null,
          "pallets": 2.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 10,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden"
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #203 — Lasaulec INK0084314 (2e Lasaulec-order, generiek-bewijs)

```json
{
  "order": "203",
  "label": "Lasaulec INK0084314 (2e Lasaulec-order, generiek-bewijs)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "artikelmatching",
    "eenheid/aantal"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Lasaulec BV",
      "bestelnummer_klant": "INK0084314",
      "taal": "NL",
      "afleveradres": {
        "naam": "Centraal magazijn",
        "straat": "A Kûper 2",
        "postcode": "8447 GK",
        "plaats": "Heerenveen",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Lasaulec BV",
          "straat": "Postbus 405",
          "postcode": "8440 AK",
          "plaats": "HEERENVEEN",
          "land": "NL"
        },
        "factuur": {
          "naam": "Lasaulec BV",
          "straat": "Postbus 405",
          "postcode": "8440 AK",
          "plaats": "HEERENVEEN",
          "land": "NL",
          "email": "po.invoice@lasaulec.nl"
        },
        "aflever": {
          "naam": "Centraal magazijn",
          "straat": "A Kûper 2",
          "postcode": "8447 GK",
          "plaats": "Heerenveen",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 2
    },
    "klant": {
      "nr": "61745",
      "naam": "Lasaulec B.V.",
      "bron": "naam_extract",
      "conf": 0.8,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "8747 GK",
    "ship_to_kandidaten": [
      {
        "code": "8531 PA",
        "pc": "8531 PA",
        "plaats": "LEMMER"
      },
      {
        "code": "8747 GK",
        "pc": "8747 GK",
        "plaats": "HEERENVEEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "A552291",
        "art_matched": "15620",
        "oms": "Stucloper TFC Board Premium B keuze 70m2 per pal",
        "hoeveelheid": 2.0,
        "eenheid": "PALLET",
        "eenheid_origineel": "PAL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      },
      {
        "pos": 2,
        "art_klant": "A602245",
        "art_matched": "22468-1",
        "oms": "Stucloper TFC Board Premium 30m2 65cm C2S",
        "hoeveelheid": 6.0,
        "eenheid": "ROL",
        "eenheid_origineel": null,
        "eenheid_default": null,
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "manual",
        "conf": 0.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 2,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "2.0 pallets in order → 2 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "15620",
          "qty": 2.0,
          "eenheid": "PAL",
          "bron": "pal_1op1",
          "pallet_maat": null,
          "pallets": 2.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 10,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [
        2
      ],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "orderregels[1].artikelnummer_kwabo_matched"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ Regel 2 (Stucloper TFC Board Premium 30m2 65cm C2S) heeft geen artikel-match en is NIET in de NAV-operaties opgenomen."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "review",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.artikel",
        "oordeel": "FOUT-met-vlag",
        "verwacht": "224681",
        "kreeg": null
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 1
  }
}
```

### Order #816 — Zevij-portaal IOR26-008934

```json
{
  "order": "816",
  "label": "Zevij-portaal IOR26-008934",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "artikel-prijs-signaal (23853 vs 238531)",
    "eenheid/aantal"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Zevij-Necomij B.V.",
      "bestelnummer_klant": "IOR26-008934",
      "taal": "NL",
      "afleveradres": {
        "naam": "Zevij-Necomij B.V.",
        "straat": "Touwslagerijweg 4",
        "postcode": "4906 CS",
        "plaats": "OOSTERHOUT NB",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Zevij-Necomij B.V.",
          "straat": "Touwslagerijweg 4",
          "postcode": "4906 CS",
          "plaats": "OOSTERHOUT NB",
          "land": "NL"
        },
        "factuur": null,
        "aflever": {
          "naam": "Zevij-Necomij B.V.",
          "straat": "Touwslagerijweg 4",
          "postcode": "4906 CS",
          "plaats": "OOSTERHOUT NB",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 10
    },
    "klant": {
      "nr": "60245",
      "naam": "Zevij-Necomij B.V.",
      "bron": "naam_extract",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "4906 CS",
    "ship_to_kandidaten": [
      {
        "code": "1099 BS",
        "pc": "1099 BS",
        "plaats": "AMSTERDAM"
      },
      {
        "code": "1114 AM",
        "pc": "1114 AM",
        "plaats": "AMSTERDAM-DUIVENDRECHT"
      },
      {
        "code": "1118 AM",
        "pc": "1118 AM",
        "plaats": "Luchthaven Schiphol"
      },
      {
        "code": "1131 DL",
        "pc": "1131 DL",
        "plaats": "VOLENDAM"
      },
      {
        "code": "1505 HH",
        "pc": "1505 HH",
        "plaats": "ZAANDAM"
      },
      {
        "code": "1948 NB",
        "pc": "1948 NB",
        "plaats": "BEVERWIJK"
      },
      {
        "code": "2171 AG",
        "pc": "2171 AG",
        "plaats": "SASSENHEIM"
      },
      {
        "code": "2222 AK",
        "pc": "2222 AK",
        "plaats": "Katwijk (Zh)"
      },
      {
        "code": "2371",
        "pc": "2371 TX",
        "plaats": "ROELOFARENDSVEEN"
      },
      {
        "code": "2404 CE",
        "pc": "2404 CE",
        "plaats": "ALPHEN AAN DEN RIJN"
      },
      {
        "code": "2516 BS",
        "pc": "2516 BS",
        "plaats": "Den Haag"
      },
      {
        "code": "2645 EC",
        "pc": "2645 EC",
        "plaats": "DELFGAUW"
      },
      {
        "code": "2665 PD",
        "pc": "2665 PD",
        "plaats": "Bleiswijk"
      },
      {
        "code": "2718 RH",
        "pc": "2718 RH",
        "plaats": "ZOETERMEER"
      },
      {
        "code": "2921 LP",
        "pc": "2921 LP",
        "plaats": "KRIMPEN AAN DEN IJSSEL"
      },
      {
        "code": "3133 ES",
        "pc": "3133 ES",
        "plaats": "VLAARDINGEN"
      },
      {
        "code": "3341 LT",
        "pc": "3341 LT",
        "plaats": "HENDRIK-IDO-AMBACHT"
      },
      {
        "code": "3433 PJ",
        "pc": "3433 PJ",
        "plaats": "NIEUWEGEIN"
      },
      {
        "code": "3526 AB",
        "pc": "3526 AB",
        "plaats": "UTRECHT"
      },
      {
        "code": "4338 PL",
        "pc": "4338 PL",
        "plaats": "MIDDELBURG"
      },
      {
        "code": "4906 CS",
        "pc": "4906 CS",
        "plaats": "OOSTERHOUT NB"
      },
      {
        "code": "5344 AE",
        "pc": "5349 BA",
        "plaats": "OSS"
      },
      {
        "code": "5421 XL",
        "pc": "5421 XL",
        "plaats": "GEMERT"
      },
      {
        "code": "5473 HC",
        "pc": "5473 HC",
        "plaats": "HEESWIJK-DINTHER"
      },
      {
        "code": "7418 AT",
        "pc": "7418 AT",
        "plaats": "DEVENTER"
      },
      {
        "code": "7418 CK",
        "pc": "7418 CK",
        "plaats": "DEVENTER"
      },
      {
        "code": "8028 PM",
        "pc": "8028 PM",
        "plaats": "ZWOLLE"
      },
      {
        "code": "8912 AM",
        "pc": "8912 AM",
        "plaats": "LEEUWARDEN"
      },
      {
        "code": "9500 AE",
        "pc": "9500 AE",
        "plaats": "STADSKANAAL"
      },
      {
        "code": "9716 JN",
        "pc": "9716 JN",
        "plaats": "GRONINGEN"
      },
      {
        "code": "9731 BL",
        "pc": "9731 BL",
        "plaats": "GRONINGEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "23520",
        "art_matched": "23520",
        "oms": "TFC Stucloper Blok 4, 75m2 / C2S / 130 cm",
        "hoeveelheid": 120.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 4,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 2,
        "art_klant": "229231",
        "art_matched": "229231",
        "oms": "Zelfklevende Beschermfolie",
        "hoeveelheid": 34.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 34.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 3,
        "art_klant": "184501",
        "art_matched": "184501",
        "oms": "Zelfklevende Raamfolie",
        "hoeveelheid": 42.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 42.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 4,
        "art_klant": "23516",
        "art_matched": "23516",
        "oms": "TFC Stucloper Blok 4, 60m2 / C2S / 130 cm",
        "hoeveelheid": 210.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 7,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 5,
        "art_klant": "23515",
        "art_matched": "23515",
        "oms": "TFC Stucloper Blok 4, 60m2 / C2S / 65 cm",
        "hoeveelheid": 120.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 4,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 6,
        "art_klant": "23517",
        "art_matched": "23517",
        "oms": "TFC Stucloper Blok 4, 60m2 / C2S / 100 cm",
        "hoeveelheid": 144.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 6,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 7,
        "art_klant": "23511",
        "art_matched": "23511",
        "oms": "TFC Stucloper Blok 4, 50m2 / C2S / 100 cm",
        "hoeveelheid": 30.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 8,
        "art_klant": "23513",
        "art_matched": "23513",
        "oms": "TFC Stucloper blok 2, 60m2 / C2s / 130 cm",
        "hoeveelheid": 35.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 9,
        "art_klant": "23853",
        "art_matched": "23853",
        "oms": "TFC Top-Coat heavy duty Zelfklevend wit afdekvli",
        "hoeveelheid": 45.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 45.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      },
      {
        "pos": 10,
        "art_klant": "23518",
        "art_matched": "23518",
        "oms": "TFC Stucloper Blok 4, 75m2 / C2S / 100 cm",
        "hoeveelheid": 24.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "klantenkaart",
        "conf": 0.9
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 24,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "24.0 pallets in order → 24 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23520",
          "qty": 120.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 4.0
        },
        {
          "artikelnr": "23516",
          "qty": 210.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 7.0
        },
        {
          "artikelnr": "23515",
          "qty": 120.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 4.0
        },
        {
          "artikelnr": "23517",
          "qty": 144.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 6.0
        },
        {
          "artikelnr": "23511",
          "qty": 30.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        },
        {
          "artikelnr": "23513",
          "qty": 35.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        },
        {
          "artikelnr": "23518",
          "qty": 24.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        }
      ],
      "onbekend": [
        {
          "artikelnr": "229231",
          "qty": 34.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "184501",
          "qty": 42.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "23853",
          "qty": 45.0,
          "eenheid": "ROL"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 38,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "orderregels[0].eenheid",
      "orderregels[1].eenheid",
      "orderregels[2].eenheid",
      "orderregels[3].eenheid",
      "orderregels[4].eenheid",
      "orderregels[5].eenheid",
      "orderregels[6].eenheid",
      "orderregels[7].eenheid",
      "orderregels[8].eenheid",
      "orderregels[9].eenheid",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23520 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 2): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 229231 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 3): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 184501 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 4): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23516 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 5): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23515 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 6): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23517 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 7): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23511 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 8): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23513 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 9): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23853 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 10): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23518 (gebruikt nu standaard 'STUK').",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 229231 (34.0 ROL), 184501 (42.0 ROL), 23853 (45.0 ROL) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (23520) — NAV berekent de prijs zelf; de mailprijs (€28.75) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 2 (229231) — NAV berekent de prijs zelf; de mailprijs (€30.3) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 3 (184501) — NAV berekent de prijs zelf; de mailprijs (€25.75) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 4 (23516) — NAV berekent de prijs zelf; de mailprijs (€23.5) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 5 (23515) — NAV berekent de prijs zelf; de mailprijs (€23.5) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 6 (23517) — NAV berekent de prijs zelf; de mailprijs (€23.55) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 7 (23511) — NAV berekent de prijs zelf; de mailprijs (€20.2) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 8 (23513) — NAV berekent de prijs zelf; de mailprijs (€20.7) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 9 (23853) — NAV berekent de prijs zelf; de mailprijs (€20.75) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 10 (23518) — NAV berekent de prijs zelf; de mailprijs (€29.05) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel3.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel3.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel3.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel4.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel4.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel4.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel5.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel5.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel5.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel6.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel6.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel6.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel7.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel7.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel7.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel8.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel8.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel8.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel9.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel9.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel9.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel10.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel10.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel10.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #832 — TABS 4506870435 -> PontMeyer Zoetermeer

```json
{
  "order": "832",
  "label": "TABS 4506870435 -> PontMeyer Zoetermeer",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "klantresolutie (agent, vestiging)",
    "europallet"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "TABS Holland B.V.",
      "bestelnummer_klant": "4506870435",
      "taal": "NL",
      "afleveradres": {
        "naam": "BA116 PontMeyer Zoetermeer",
        "straat": "Radonstraat 290",
        "postcode": "2718 TB",
        "plaats": "ZOETERMEER",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "TABS Holland B.V.",
          "straat": "Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "factuur": {
          "naam": "TABS Holland B.V.",
          "straat": "Supply Chain TABS ( BA 157 ), Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "aflever": {
          "naam": "BA116 PontMeyer Zoetermeer",
          "straat": "Radonstraat 290",
          "postcode": "2718 TB",
          "plaats": "ZOETERMEER",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61468",
      "naam": "Pontmeyer Zoetermeer",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "2718 TB",
    "ship_to_kandidaten": [
      {
        "code": "2718 TB",
        "pc": "2718 TB",
        "plaats": "ZOETERMEER"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "238601",
        "art_matched": "238601",
        "oms": "tfc top coat premium afdekvlies 670mm rol a 25m2",
        "hoeveelheid": 33.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 33.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": [
        {
          "artikelnr": "238601",
          "qty": 33.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 8,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 238601 (33.0 STUK) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (238601) — NAV berekent de prijs zelf; de mailprijs (€23.1) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "review",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "europallet_aantal",
        "oordeel": "FOUT-met-vlag",
        "verwacht": 1,
        "kreeg": null
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 1
  }
}
```

### Order #833 — TABS 4506870437 -> PontMeyer Heemstede

```json
{
  "order": "833",
  "label": "TABS 4506870437 -> PontMeyer Heemstede",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "klantresolutie (agent, vestiging)",
    "europallet"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "TABS Holland B.V.",
      "bestelnummer_klant": "4506870437",
      "taal": "NL",
      "afleveradres": {
        "naam": "BA148 PontMeyer Heemstede",
        "straat": "Nijverheidsweg 14",
        "postcode": "2102 LL",
        "plaats": "HEEMSTEDE",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "TABS Holland B.V.",
          "straat": "Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "factuur": {
          "naam": "TABS Holland B.V.",
          "straat": "Supply Chain TABS ( BA 157 ), Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "aflever": {
          "naam": "BA148 PontMeyer Heemstede",
          "straat": "Nijverheidsweg 14",
          "postcode": "2102 LL",
          "plaats": "HEEMSTEDE",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 2
    },
    "klant": {
      "nr": "61019",
      "naam": "PontMeyer Heemstede",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "2102 LL",
    "ship_to_kandidaten": [
      {
        "code": "2102 LL",
        "pc": "2102 LL",
        "plaats": "HEEMSTEDE"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": null,
        "art_matched": "229231",
        "oms": "beschermfolie harde vloeren zelfklev 700mm rol 6",
        "hoeveelheid": 5.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 5.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      },
      {
        "pos": 2,
        "art_klant": null,
        "art_matched": "238531",
        "oms": "tfc top coat premium afdekvlies 1000mm rol a 25m",
        "hoeveelheid": 15.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 15.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": [
        {
          "artikelnr": "229231",
          "qty": 5.0,
          "eenheid": "STUK"
        },
        {
          "artikelnr": "238531",
          "qty": 15.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 11,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 229231 (5.0 STUK), 238531 (15.0 STUK) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (229231) — NAV berekent de prijs zelf; de mailprijs (€32.85) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 2 (238531) — NAV berekent de prijs zelf; de mailprijs (€24.8) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "review",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "europallet_aantal",
        "oordeel": "FOUT-met-vlag",
        "verwacht": 1,
        "kreeg": null
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel2.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 1
  }
}
```

### Order #834 — TABS 4506870444 -> PontMeyer Zwaag (2e agent-order, generiek-bewijs)

```json
{
  "order": "834",
  "label": "TABS 4506870444 -> PontMeyer Zwaag (2e agent-order, generiek-bewijs)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "klantresolutie (agent, vestiging)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "TABS Holland B.V.",
      "bestelnummer_klant": "4506870444",
      "taal": "NL",
      "afleveradres": {
        "naam": "BA223 PontMeyer Zwaag",
        "straat": "De Factorij 23",
        "postcode": "1689 AK",
        "plaats": "ZWAAG",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "TABS Holland B.V.",
          "straat": "Supply Chain TABS ( BA 157 )",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "factuur": {
          "naam": "TABS Holland B.V.",
          "straat": "Supply Chain TABS ( BA 157 ), Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "aflever": {
          "naam": "BA223 PontMeyer Zwaag",
          "straat": "De Factorij 23",
          "postcode": "1689 AK",
          "plaats": "ZWAAG",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61088",
      "naam": "PontMeyer Zwaag",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "1689 AK",
    "ship_to_kandidaten": [
      {
        "code": "1689 AK",
        "pc": "1689 AK",
        "plaats": "ZWAAG"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "K700100007",
        "art_matched": "228321",
        "oms": "stucloper/protectiekarton onbedrukt 950-1050mm r",
        "hoeveelheid": 30.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 1,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "1.0 pallets in order → 1 europallet (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "228321",
          "qty": 30.0,
          "eenheid": "STUK",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 11,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "Geen prijsafspraak in DB voor regel 1 (228321) — NAV berekent de prijs zelf; de mailprijs (€20.75) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "afleveradres_postcode",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #716 — Würth 0095588334 (regressie + F3-anker)

```json
{
  "order": "716",
  "label": "Würth 0095588334 (regressie + F3-anker)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "regressie",
    "eenheid/aantal (expliciete STUK)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Würth Nederland B.V.",
      "bestelnummer_klant": "95588334",
      "taal": "NL",
      "afleveradres": {
        "naam": "Würth-Nederland B.V.",
        "straat": "Het Sterrenbeeld 35, Industrie terrein de Brand",
        "postcode": "5215 MK",
        "plaats": "'S-HERTOGENBOSCH-DOOR 3",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Würth Nederland B.V.",
          "straat": "Het Sterrenbeeld 35",
          "postcode": "5215 MK",
          "plaats": "'s-Hertogenbosch",
          "land": "NL"
        },
        "factuur": {
          "naam": "KWABO Techniek B.V.",
          "straat": "Julianaweg 210 A",
          "postcode": "1131 DL",
          "plaats": "VOLENDAM",
          "land": "NL"
        },
        "aflever": {
          "naam": "Würth-Nederland B.V.",
          "straat": "Het Sterrenbeeld 35, Industrie terrein de Brand",
          "postcode": "5215 MK",
          "plaats": "'S-HERTOGENBOSCH-DOOR 3",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61030",
      "naam": "Würth Nederland B.V.",
      "bron": "email",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "5215 MK",
    "ship_to_kandidaten": [
      {
        "code": "5215 MK",
        "pc": "5215 MK",
        "plaats": "'S-HERTOGENBOSCH"
      },
      {
        "code": "9861 GK",
        "pc": "9861 GK",
        "plaats": "GROOTEGAST"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "9501017951990",
        "art_matched": "238601",
        "oms": "ZELFKLEVEND-AFDEKVLIES-170GR-B0,67M-L25M",
        "hoeveelheid": 66.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 66.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": [
        {
          "artikelnr": "238601",
          "qty": 66.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 8,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 238601 (66.0 STUK) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (238601) — NAV berekent de prijs zelf; de mailprijs (€20.2) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.eenheid",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.aantal",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #717 — Kuipers BMH 20173111 (regressie)

```json
{
  "order": "717",
  "label": "Kuipers BMH 20173111 (regressie)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "regressie"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Kuipers Bouwmaterialen Hardenberg B.V.",
      "bestelnummer_klant": "20173111",
      "taal": "NL",
      "afleveradres": {
        "naam": "C.F. Kunststoffen B.V.",
        "straat": "Doorbraakweg 45",
        "postcode": "7783 DC",
        "plaats": "Gramsbergen",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Kuipers Bouwmaterialen Hardenberg B.V.",
          "straat": "Kruiwiel 13",
          "postcode": "7773 NL",
          "plaats": "Hardenberg",
          "land": "NL"
        },
        "factuur": {
          "naam": "Kwabo Techniek B.V.",
          "straat": "Julianaweg 210 A",
          "postcode": "1131 DL",
          "plaats": "Volendam",
          "land": "NL"
        },
        "aflever": {
          "naam": "C.F. Kunststoffen B.V.",
          "straat": "Doorbraakweg 45",
          "postcode": "7783 DC",
          "plaats": "Gramsbergen",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61844",
      "naam": "Kuipers BMH",
      "bron": "email",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "7783 DC",
    "ship_to_kandidaten": [
      {
        "code": "7783 DC",
        "pc": "7783 DC",
        "plaats": "GRAMSBERGEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "0007738178",
        "art_matched": null,
        "oms": "Stucloper grijs rol a 36 m2 breedte 60-65cm",
        "hoeveelheid": 360.0,
        "eenheid": "STUK",
        "eenheid_origineel": null,
        "eenheid_default": null,
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "manual",
        "conf": 0.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": []
    },
    "compose": {
      "status": "error",
      "error": "ValueError: Cannot compose NAV order for 717: no matched articles (1 regels, all unmatched).",
      "nav_ops_count": 0,
      "ops": [],
      "regels_zonder_match": [
        1
      ],
      "regelverlies_gevlagd": false
    },
    "needs_review_fields": [
      "orderregels[0].artikelnummer_kwabo",
      "orderregels[0].artikelnummer_kwabo_matched"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden"
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #718 — Witzand PN50040984 (regressie, mix-klant)

```json
{
  "order": "718",
  "label": "Witzand PN50040984 (regressie, mix-klant)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "regressie",
    "artikelmatching"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Witzand Bouwmaterialen B.V.",
      "bestelnummer_klant": "PN50040984",
      "taal": "NL",
      "afleveradres": {
        "naam": "Vriezenveen Afhaalcenter",
        "straat": "Hammerweg 11",
        "postcode": "7671 JE",
        "plaats": "Vriezenveen",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Witzand Bouwmaterialen B.V.",
          "straat": "Sluiskade N.Z. 36",
          "postcode": "7602 HR",
          "plaats": "Almelo",
          "land": "NL"
        },
        "factuur": {
          "naam": "Witzand Bouwmaterialen",
          "straat": "Sluiskade N.Z. 36",
          "postcode": "7602 HR",
          "plaats": "Almelo",
          "land": "NL"
        },
        "aflever": {
          "naam": "Vriezenveen Afhaalcenter",
          "straat": "Hammerweg 11",
          "postcode": "7671 JE",
          "plaats": "Vriezenveen",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": "EXW",
      "n_regels": 1
    },
    "klant": {
      "nr": "60892",
      "naam": "Witzand Bouwmaterialen B.V.",
      "bron": "naam_extract",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "7671 JE",
    "ship_to_kandidaten": [
      {
        "code": "7131 PZ",
        "pc": "7131 PZ",
        "plaats": "LICHTENVOORDE"
      },
      {
        "code": "7151 HT",
        "pc": "7151 HT",
        "plaats": "EIBERGEN"
      },
      {
        "code": "7547 SK",
        "pc": "7547 SK",
        "plaats": "ENSCHEDE"
      },
      {
        "code": "7602 HR",
        "pc": "7602 HR",
        "plaats": "ALMELO"
      },
      {
        "code": "7671 JE",
        "pc": "7671 JE",
        "plaats": "VRIEZENVEEN"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "5021180003",
        "art_matched": "238601",
        "oms": "Afdekvlies 0,67x37 mt wit met zelfklevende onder",
        "hoeveelheid": 33.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": [
        {
          "artikelnr": "238601",
          "qty": 33.0,
          "eenheid": "ROL"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 8,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentMethodCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "orderregels[0].eenheid",
      "mix_uom:1",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 238601 (gebruikt nu standaard 'STUK').",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 238601 (33.0 ROL) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (238601) — NAV berekent de prijs zelf; de mailprijs (€21.35) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #721 — Van Dongen 2601382 (regressie)

```json
{
  "order": "721",
  "label": "Van Dongen 2601382 (regressie)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "regressie"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Van Dongen Verf BV",
      "bestelnummer_klant": "2601382",
      "taal": "NL",
      "afleveradres": {
        "naam": "Van Dongen Verf B.V.",
        "straat": "Industrieweg 42",
        "postcode": "3241 MA",
        "plaats": "Middelharnis",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Van Dongen Verf BV",
          "straat": "Industrieweg 42",
          "postcode": "3241 MA",
          "plaats": "Middelharnis",
          "land": "NL"
        },
        "factuur": null,
        "aflever": {
          "naam": "Van Dongen Verf B.V.",
          "straat": "Industrieweg 42",
          "postcode": "3241 MA",
          "plaats": "Middelharnis",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61472",
      "naam": "Van Dongen Verf B.V.",
      "bron": "naam_extract",
      "conf": 0.8,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "3240 AG",
    "ship_to_kandidaten": [
      {
        "code": "3240 AG",
        "pc": "3240 AG",
        "plaats": "MIDDELHARNIS"
      },
      {
        "code": "8356",
        "pc": "8356 VS",
        "plaats": "BLOKZIJL"
      },
      {
        "code": "8621 DV",
        "pc": "8621 DV",
        "plaats": "HEEG"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "228321",
        "art_matched": "228321",
        "oms": "Stucloper 50m²-100cm",
        "hoeveelheid": 30.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 1,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "1.0 pallets in order → 1 europallet (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "228321",
          "qty": 30.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 11,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "orderregels[0].eenheid"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 228321 (gebruikt nu standaard 'STUK').",
      "Geen prijsafspraak in DB voor regel 1 (228321) — NAV berekent de prijs zelf; de mailprijs (€19.45) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #707 — GBI Borne 2601922 via Zevij-portaal (regressie)

```json
{
  "order": "707",
  "label": "GBI Borne 2601922 via Zevij-portaal (regressie)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "regressie",
    "klantresolutie (portaal)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "GBI Borne",
      "bestelnummer_klant": "2601922",
      "taal": "NL",
      "afleveradres": {
        "naam": "GBI Borne",
        "straat": "Hanzestraat 1",
        "postcode": "7622 AX",
        "plaats": "BORNE",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "GBI Borne",
          "straat": "Hanzestraat 1",
          "postcode": "7622 AX",
          "plaats": "BORNE",
          "land": "NL"
        },
        "factuur": null,
        "aflever": {
          "naam": "GBI Borne",
          "straat": "Hanzestraat 1",
          "postcode": "7622 AX",
          "plaats": "BORNE",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "61948",
      "naam": "GBI Borne",
      "bron": "naam_extract",
      "conf": 0.8,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": null,
    "ship_to_kandidaten": [],
    "regels": [
      {
        "pos": 1,
        "art_klant": "23512",
        "art_matched": "23512",
        "oms": "TFC STUCLOPER BLOK 4, 50M2 / C2S / 130 CM",
        "hoeveelheid": 35.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 1,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "1.0 pallets in order → 1 europallet (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23512",
          "qty": 35.0,
          "eenheid": "ROL",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        }
      ],
      "onbekend": []
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 10,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "orderregels[0].eenheid"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23512 (gebruikt nu standaard 'STUK')."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "regel1.artikel",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #685 — Veris 822200 (regressie, mix-klant)

```json
{
  "order": "685",
  "label": "Veris 822200 (regressie, mix-klant)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "regressie"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Veris Bouwmaterialengroep",
      "bestelnummer_klant": "822200",
      "taal": "NL",
      "afleveradres": {
        "naam": "Veris Bouwmaterialengroep",
        "straat": "Voltaweg 14",
        "postcode": "6101 XK",
        "plaats": "Echt",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Zevij Necomij / Total Floorcovering",
          "straat": "Julianaweg 210A",
          "postcode": "1131 DL",
          "plaats": "Volendam",
          "land": "NL"
        },
        "factuur": null,
        "aflever": {
          "naam": "Veris Bouwmaterialengroep",
          "straat": "Voltaweg 14",
          "postcode": "6101 XK",
          "plaats": "Echt",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 8
    },
    "klant": {
      "nr": "60203",
      "naam": "Veris Bouwmaterialengroep B.V.",
      "bron": "email",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "6101 XK",
    "ship_to_kandidaten": [
      {
        "code": "6101 XK",
        "pc": "6101 XK",
        "plaats": "ECHT"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "23545",
        "art_matched": "23545",
        "oms": "Bouwcenter stucloper 50m2 100-130cm bruin-wit 2-",
        "hoeveelheid": 455.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 2,
        "art_klant": "23544",
        "art_matched": "23544",
        "oms": "Bouwcenter stucloper 50m2 90-100 cm bruin-wit 2-",
        "hoeveelheid": 150.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 3,
        "art_klant": "23546",
        "art_matched": "23546",
        "oms": "Bouwcenter stucloper 35 m2 55-70 cm bruin-wit 2-",
        "hoeveelheid": 120.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 4,
        "art_klant": "23521",
        "art_matched": "23521",
        "oms": "Stiho stucloper 50 m2 120/130 cm bruin-wit 2-zij",
        "hoeveelheid": 245.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 5,
        "art_klant": "234781",
        "art_matched": "234781",
        "oms": "TFC non-woven afdekvlies 1x25 mt absorberende to",
        "hoeveelheid": 45.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 6,
        "art_klant": "23923",
        "art_matched": "23923",
        "oms": "Bouwcenter afdekvlies 1x25 mt wit non woven zelf",
        "hoeveelheid": 45.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 7,
        "art_klant": "23924",
        "art_matched": "23924",
        "oms": "Bouwcenter afdekvlies 1x50 mt wit non woven zelf",
        "hoeveelheid": 22.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      },
      {
        "pos": 8,
        "art_klant": "23989",
        "art_matched": "23989",
        "oms": "Bouwcenter afdekvlies 0,67x37 mt wit non woven z",
        "hoeveelheid": 33.0,
        "eenheid": "STUK",
        "eenheid_origineel": "ROL",
        "eenheid_default": "STUK",
        "verkoop_uom": null,
        "verkoop_aantal": null,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 7,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "7.0 pallets in order → 7 europallets (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "23544",
          "qty": 150.0,
          "eenheid": "ROL",
          "bron": "uom_verkoopeenheid",
          "pallet_maat": 30.0,
          "pallets": 5.0
        },
        {
          "artikelnr": "23546",
          "qty": 120.0,
          "eenheid": "ROL",
          "bron": "uom_verkoopeenheid",
          "pallet_maat": 60.0,
          "pallets": 2.0
        }
      ],
      "onbekend": [
        {
          "artikelnr": "23545",
          "qty": 455.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "23521",
          "qty": 245.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "234781",
          "qty": 45.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "23923",
          "qty": 45.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "23924",
          "qty": 22.0,
          "eenheid": "ROL"
        },
        {
          "artikelnr": "23989",
          "qty": 33.0,
          "eenheid": "ROL"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 23,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "orderregels[0].eenheid",
      "orderregels[1].eenheid",
      "orderregels[2].eenheid",
      "orderregels[3].eenheid",
      "orderregels[4].eenheid",
      "orderregels[5].eenheid",
      "orderregels[6].eenheid",
      "orderregels[7].eenheid",
      "mix_uom:1",
      "mix_uom:2",
      "mix_uom:3",
      "mix_uom:4",
      "mix_uom:5",
      "mix_uom:6",
      "mix_uom:7",
      "mix_uom:8",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EENHEID CONTROLEREN (regel 1): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23545 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 2): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23544 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 3): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23546 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 4): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23521 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 5): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 234781 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 6): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23923 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 7): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23924 (gebruikt nu standaard 'STUK').",
      "⚠ EENHEID CONTROLEREN (regel 8): klant bestelde 'ROL' maar dit is geen geldige eenheid voor artikel 23989 (gebruikt nu standaard 'STUK').",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 23545 (455.0 ROL), 23521 (245.0 ROL), 234781 (45.0 ROL), 23923 (45.0 ROL), 23924 (22.0 ROL), 23989 (33.0 ROL) — telling kan onvolledig zijn."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "JUIST",
    "velden": [
      {
        "veld": "klant_nr",
        "oordeel": "JUIST"
      },
      {
        "veld": "ship_to_code",
        "oordeel": "JUIST"
      }
    ],
    "n_stille_fouten": 0,
    "n_review": 0
  }
}
```

### Order #619 — Bestelling 4506859249 157 (TABS-formaat, observatie)

```json
{
  "order": "619",
  "label": "Bestelling 4506859249 157 (TABS-formaat, observatie)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {
    "email_body_bevat_lossy_pdf": true
  },
  "categorieen": [
    "observatie (geen grondwaarheid)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "TABS Holland B.V.",
      "bestelnummer_klant": "4506859249",
      "taal": "NL",
      "afleveradres": {
        "naam": "BA123 PontMeyer Den Haag",
        "straat": "Mercuriusweg 40",
        "postcode": "2516 AW",
        "plaats": "'S-GRAVENHAGE",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "TABS Holland B.V.",
          "straat": "Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "factuur": {
          "naam": "TABS Holland B.V.",
          "straat": "Supply Chain TABS ( BA 157 ), Postbus 2206",
          "postcode": "1500 GE",
          "plaats": "ZAANDAM",
          "land": "NL"
        },
        "aflever": {
          "naam": "BA123 PontMeyer Den Haag",
          "straat": "Mercuriusweg 40",
          "postcode": "2516 AW",
          "plaats": "'S-GRAVENHAGE",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 2
    },
    "klant": {
      "nr": "60982",
      "naam": "PontMeyer Den Haag Mercuriusweg",
      "bron": "leveradres_shipto",
      "conf": 0.9,
      "vlag": true,
      "kandidaten": []
    },
    "ship_to_gekozen": "2516 AW",
    "ship_to_kandidaten": [
      {
        "code": "2516 AW",
        "pc": "2516 AW",
        "plaats": "'S-GRAVENHAGE"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": null,
        "art_matched": "228321",
        "oms": "stucloper/protectiekarton onbedrukt 950-1050mm r",
        "hoeveelheid": 30.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "PALLET",
        "verkoop_aantal": 1,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      },
      {
        "pos": 2,
        "art_klant": null,
        "art_matched": "229231",
        "oms": "beschermfolie harde vloeren zelfklev 700mm rol 6",
        "hoeveelheid": 5.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 5.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": {
        "hoeveelheid": 1,
        "eenheid": "STUK",
        "confidence": 0.7
      },
      "uitleg": "1.0 pallets in order → 1 europallet (afgerond naar boven).",
      "onderbouwing_regels": [
        {
          "artikelnr": "228321",
          "qty": 30.0,
          "eenheid": "STUK",
          "bron": "verkoop_pal",
          "pallet_maat": null,
          "pallets": 1.0
        }
      ],
      "onbekend": [
        {
          "artikelnr": "229231",
          "qty": 5.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 14,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "requestedDeliveryDate"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "klant_match",
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 229231 (5.0 STUK) — telling kan onvolledig zijn.",
      "Geen prijsafspraak in DB voor regel 1 (228321) — NAV berekent de prijs zelf; de mailprijs (€20.75) dient alleen ter controle.",
      "Geen prijsafspraak in DB voor regel 2 (229231) — NAV berekent de prijs zelf; de mailprijs (€32.85) dient alleen ter controle."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "geen_grondwaarheid",
    "velden": []
  }
}
```

### Order #712 — Bestelnummer 12600242 (observatie)

```json
{
  "order": "712",
  "label": "Bestelnummer 12600242 (observatie)",
  "bron_type": "tekst_reconstructie",
  "extractie_mode": "tekst",
  "getrouwheid": {},
  "categorieen": [
    "observatie (geen grondwaarheid)"
  ],
  "samenvatting": {
    "extract": {
      "klantnaam_besteller": "Stucshowroom B.V.",
      "bestelnummer_klant": "12600242",
      "taal": "NL",
      "afleveradres": {
        "naam": "Kwabo Techniek B.V.",
        "straat": "Julianaweg 210 a",
        "postcode": "1131 DL",
        "plaats": "VOLENDAM",
        "land": "NL"
      },
      "adres_rollen": {
        "besteller": {
          "naam": "Stucshowroom B.V.",
          "straat": "Rooseveltstraat 40",
          "postcode": "2321 BM",
          "plaats": "Leiden",
          "land": "NL"
        },
        "factuur": null,
        "aflever": {
          "naam": "Kwabo Techniek B.V.",
          "straat": "Julianaweg 210 a",
          "postcode": "1131 DL",
          "plaats": "VOLENDAM",
          "land": "NL"
        },
        "eindontvanger": null
      },
      "verzendwijze": null,
      "n_regels": 1
    },
    "klant": {
      "nr": "60228",
      "naam": "Stucshowroom B.V.",
      "bron": "email",
      "conf": 1.0,
      "vlag": false,
      "kandidaten": []
    },
    "ship_to_gekozen": "2321 BM",
    "ship_to_kandidaten": [
      {
        "code": "2321 BM",
        "pc": "2321 BM",
        "plaats": "LEIDEN"
      },
      {
        "code": "3072 LL",
        "pc": "3072 LL",
        "plaats": "ROTTERDAM"
      },
      {
        "code": "3956 NS",
        "pc": "3956 NS",
        "plaats": "LEERSUM"
      }
    ],
    "regels": [
      {
        "pos": 1,
        "art_klant": "23384",
        "art_matched": "23384",
        "oms": "MULTI-CUTTER TFC | elektrische schaar",
        "hoeveelheid": 10.0,
        "eenheid": "STUK",
        "eenheid_origineel": "STUK",
        "eenheid_default": "STUK",
        "verkoop_uom": "STUK",
        "verkoop_aantal": 10.0,
        "mix_uom": null,
        "mix_aantal": null,
        "methode": "exact_klantnr",
        "conf": 1.0
      }
    ],
    "europallet": {
      "regel": null,
      "uitleg": "0.0 pallets in order — onder de drempel, geen europallet.",
      "onderbouwing_regels": [],
      "onbekend": [
        {
          "artikelnr": "23384",
          "qty": 10.0,
          "eenheid": "STUK"
        }
      ]
    },
    "compose": {
      "status": "ok",
      "error": null,
      "nav_ops_count": 7,
      "ops": [
        {
          "op": "POST",
          "path": "/salesOrders",
          "body_keys": [
            "customerNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipToCode"
          ],
          "optional": true
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "externalDocumentNumber"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrders({id})",
          "body_keys": [
            "shipmentDate"
          ],
          "optional": false
        },
        {
          "op": "POST",
          "path": "/salesOrders({id})/salesOrderLines",
          "body_keys": [
            "itemNumber",
            "lineType"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "unitOfMeasureCode"
          ],
          "optional": false
        },
        {
          "op": "PATCH",
          "path": "/salesOrderLines({id})",
          "body_keys": [
            "quantity"
          ],
          "optional": false
        }
      ],
      "regels_zonder_match": [],
      "regelverlies_gevlagd": true
    },
    "needs_review_fields": [
      "europallet"
    ],
    "validatie_warnings": [
      "⚠ KLANT IS GEEN 4+ LID — controleer aankoopvoorwaarden",
      "⚠ EUROPALLET ONBEKEND: geen pallet_plaatsen_basis-waarde en geen bruikbare NAV-eenheid voor: 23384 (10.0 STUK) — telling kan onvolledig zijn."
    ],
    "is_order": true
  },
  "oordeel": {
    "status": "geen_grondwaarheid",
    "velden": []
  }
}
```
