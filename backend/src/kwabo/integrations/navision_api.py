"""Navision API protocol + MockNavisionClient + stub for real client."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional, Protocol

from kwabo.config import settings


class NavisionClient(Protocol):
    async def get_customer(self, nr: str) -> Optional[dict]: ...
    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]: ...
    async def get_item(self, nr: str) -> Optional[dict]: ...
    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]: ...
    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict: ...


# Seed gebaseerd op de 17 voorbeelden. Mock = in-memory + persist naar json.
MOCK_CUSTOMERS: list[dict] = [
    {"number": "10001", "displayName": "Ferney Diabolo B.V.", "email": "purchaseorders@ferney.nl"},
    {"number": "10002", "displayName": "TABS / PontMeyer", "email": "supplychain@tabsholland.nl"},
    {"number": "10003", "displayName": "Isero Ijzerwaren B.V.", "email": "fransvanvliet@isero.nl"},
    {"number": "10004", "displayName": "BMN Bouwmaterialen", "email": "jeroen.vanschooten@bmn.nl"},
    {"number": "10005", "displayName": "Omtzigt Bouw", "email": "kg@omtzigt-bouwmaterialen.nl"},
    {"number": "10006", "displayName": "Driessen Verf b.v.", "email": "bestellenhelmond@driessenverf.nl"},
    {"number": "10007", "displayName": "Stukbouw B.V.", "email": "willy@stukbouw.nl"},
    {"number": "10008", "displayName": "Enka Bouwmaterialen", "email": "e.sun@enkabouwmarkt.nl"},
    {"number": "10009", "displayName": "Connect Products GmbH", "email": "patricia@connectproducts.nl"},
    {"number": "10010", "displayName": "Storch-Ciret GmbH", "email": "s.wilke@storch-ciret.com"},
    {"number": "10011", "displayName": "Kirchner GmbH", "email": "tobias.leyhausen@kirchner-online.com"},
    {"number": "10012", "displayName": "Werkzeuge Dietrich GmbH & Co. KG", "email": "malte.klippstein@werkzeuge-dietrich.de"},
    {"number": "10013", "displayName": "Bugel AG", "email": "r.carvalho@bugel.ch"},
    {"number": "10014", "displayName": "BAUHAUS", "email": "supplier@bahag.com"},
    {"number": "10015", "displayName": "Tectis OU", "email": "maarjaliisa.nomm@tectis.ee"},
    {"number": "10016", "displayName": "L. De Vos sa/nv", "email": "anja@lucdevos.be"},
]

MOCK_ITEMS: list[dict] = [
    {"number": "1515155", "displayName": "Ferney stucloper 120cm"},
    {"number": "228321", "displayName": "TABS hoeknaald 260cm"},
    {"number": "2597768", "displayName": "Isero topcoat 20kg"},
    {"number": "201291", "displayName": "BMN pallet 1"},
    {"number": "83461", "displayName": "BMN kist statiegeld"},
    {"number": "122338", "displayName": "BAUHAUS product"},
    {"number": "47323", "displayName": "Tectis Proshield private label"},
    {"number": "975097", "displayName": "L. De Vos Greenboard B1 75m2"},
    {"number": "CICS-100-25", "displayName": "Werkzeuge Dietrich coating"},
    {"number": "DUMMY-OMTZIGT", "displayName": "Omtzigt product"},
    {"number": "DUMMY-DRIESSEN", "displayName": "Driessen Verf product"},
    {"number": "DUMMY-KIRCHNER-238534", "displayName": "Kirchner FORCH editie"},
    {"number": "DUMMY-BUGEL", "displayName": "Bugel Zwitserse editie"},
    {"number": "SOFTBREATH-PALLET", "displayName": "Softbreath pallet"},
]


class MockNavisionClient:
    """In-memory Navision mock. Persists created orders to JSON on disk."""

    def __init__(self, out_dir: Path | None = None) -> None:
        self.customers = list(MOCK_CUSTOMERS)
        self.items = list(MOCK_ITEMS)
        self.out_dir = (out_dir or (settings.navision_mock_path / "orders")).resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)

    async def get_customer(self, nr: str) -> Optional[dict]:
        return next((c for c in self.customers if c["number"] == nr), None)

    async def search_customers(
        self, naam: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        results = []
        for c in self.customers:
            if email and c.get("email", "").lower() == email.lower():
                results.append(c)
                continue
            if naam and naam.lower() in c.get("displayName", "").lower():
                results.append(c)
        return results

    async def get_item(self, nr: str) -> Optional[dict]:
        return next((i for i in self.items if i["number"] == nr), None)

    async def search_items(self, beschrijving: Optional[str] = None) -> list[dict]:
        if not beschrijving:
            return list(self.items)
        q = beschrijving.lower()
        return [i for i in self.items if q in i.get("displayName", "").lower()]

    async def create_sales_order(self, header: dict, lines: list[dict]) -> dict:
        order_id = str(uuid.uuid4())
        order_nr = f"SO-{order_id[:8].upper()}"
        payload = {
            "id": order_id,
            "number": order_nr,
            "header": header,
            "lines": lines,
            "status": "Draft",
        }
        (self.out_dir / f"{order_nr}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return payload


def get_navision_client() -> NavisionClient:
    mode = settings.navision_mode
    if mode == "mock":
        return MockNavisionClient()
    if mode == "replay":
        from kwabo.integrations.navision_real import ReplayNavisionClient
        from pathlib import Path
        fixture = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "navision_replay.json"
        return ReplayNavisionClient(fixture)
    if mode == "real":
        from kwabo.integrations.navision_real import RealNavisionClient
        return RealNavisionClient()
    raise ValueError(f"Unknown NAVISION_MODE: {mode}")


def build_sales_order_payload(state: dict) -> dict:
    """Build the exact header + lines that will be POSTed to Navision.

    Shared by `push_navision` and the `/api/orders/{id}/navision-preview` endpoint
    so that the dashboard preview is byte-identical to what gets pushed.
    """
    from kwabo.utils.eenheid_mapping import normalize_eenheid

    klant = state.get("klant_match") or {}
    header: dict = {
        "customerNumber": klant.get("navision_klantnr"),
        "externalDocumentNumber": state.get("bestelnummer_klant", "") or "",
        "requestedDeliveryDate": state.get("gewenste_leverdatum"),
    }
    ship = state.get("afleveradres")
    if ship:
        header.update(
            {
                "shipToName": ship.get("naam", ""),
                "shipToAddressLine1": ship.get("straat", ""),
                "shipToCity": ship.get("plaats", ""),
                "shipToPostCode": ship.get("postcode", ""),
                "shipToCountry": ship.get("land", "NL"),
            }
        )
    if state.get("opmerkingen"):
        header["comment"] = state["opmerkingen"]
    if state.get("afleverinstructies"):
        header["shippingInstructions"] = state["afleverinstructies"]

    lines: list[dict] = []
    for r in state.get("orderregels") or []:
        if not r.get("artikelnummer_kwabo_matched"):
            continue
        line = {
            "itemNumber": r["artikelnummer_kwabo_matched"],
            "quantity": r.get("hoeveelheid"),
            "unitOfMeasureCode": normalize_eenheid(r.get("eenheid")),
        }
        if r.get("prijs_per_eenheid") is not None and r.get("prijs_validated") is True:
            line["unitPrice"] = r["prijs_per_eenheid"]
        if r.get("leverdatum_regel"):
            line["shipmentDate"] = r["leverdatum_regel"]
        if r.get("opmerkingen"):
            line["description2"] = r["opmerkingen"]
        lines.append(line)

    return {"header": header, "lines": lines}
