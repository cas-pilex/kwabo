"""Tests for the admin PLX_Customer sync mapping (_customer_to_klantenkaart).

Functie 1: de customers-sync moet het vestigingsadres (City/Post_Code)
overnemen, zodat de klant-matching de juiste franchise-vestiging op het
leveradres kan kiezen en de UI de plaats kan tonen.
"""
from __future__ import annotations

from kwabo.api.admin import _customer_to_klantenkaart
from kwabo.db.models import Klantenkaart


def test_customer_mapping_captures_plaats_and_postcode_new():
    row = {
        "No": "61088",
        "Name": "PontMeyer Zwaag",
        "E_Mail": "zwaag@pontmeyer.nl",
        "City": "Zwaag",
        "Post_Code": "1689 AK",
    }
    obj = _customer_to_klantenkaart(row, None)
    assert obj.nav_klantnr == "61088"
    assert obj.plaats == "Zwaag"
    assert obj.postcode == "1689 AK"


def test_customer_mapping_updates_plaats_and_postcode_existing():
    existing = Klantenkaart(nav_klantnr="61088", naam="PontMeyer Zwaag (oud)")
    row = {
        "No": "61088",
        "Name": "PontMeyer Zwaag",
        "City": "Zwaag",
        "Post_Code": "1689 AK",
    }
    obj = _customer_to_klantenkaart(row, existing)
    assert obj is existing
    assert obj.plaats == "Zwaag"
    assert obj.postcode == "1689 AK"


def test_customer_mapping_tolerates_missing_address():
    row = {"No": "60892", "Name": "Witzand Bouwmaterialen"}
    obj = _customer_to_klantenkaart(row, None)
    assert obj.plaats is None
    assert obj.postcode is None
