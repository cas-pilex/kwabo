"""Functie 5 — afhaal/ophalen detecteren -> verzendwijze (Shipment Method Code = EXW).

Een afhaalorder (klant haalt zelf op) moet in NAV de juiste verzendwijze krijgen
i.p.v. de default-verzending. Detectie is deterministisch (geen LLM) op
afhaal-signalen in subject/body/afleverinstructies/opmerkingen/bijlagen; de
composer zet de Shipment Method Code via een aparte single-field PATCH. Door Cas
bevestigd: veld = Shipment Method Code (shipmentMethodCode -> Shipment_Method_Code),
code = EXW, europallet/leverdatum ongewijzigd.
"""
from __future__ import annotations

import pytest

from kwabo.integrations.nav_operations import _assert_op_invariants
from kwabo.integrations.navision_nav2018 import _DEFAULT_FIELD_MAP
from kwabo.integrations.navision_steps import compose_navision_operations
from kwabo.utils.verzendwijze import (
    AFHAAL_SHIPMENT_METHOD,
    detect_verzendwijze,
    is_afhaal,
)


# --- detectie ----------------------------------------------------------

@pytest.mark.parametrize("tekst", [
    "AFHAALORDER",
    "Dit is een afhaalorder, wij halen het zelf op",
    "Graag klaarzetten, wij komen afhalen",
    "De goederen worden door ons opgehaald",
    "Bitte zur Abholung bereitstellen",
    "Selbstabholer — wir holen die Ware ab",
    "Wird abgeholt",
])
def test_is_afhaal_positief(tekst):
    assert is_afhaal(tekst) is True


@pytest.mark.parametrize("tekst", [
    "",
    "Graag bezorgen op het onderstaande adres",
    "Levering volgende week, verzenden per pallet",
    "Bitte liefern Sie an die folgende Adresse",
    "Standaard verzending, geen bijzonderheden",
    # Valse-positief-guards (code review): 'ab Werk'/'ab Lager' zijn juist
    # LEVER-incoterms; figuurlijk 'halen' is geen afhaal.
    "wir holen das ab Werk angebotene Material",
    "Bitte holen Sie die Bestätigung ab",
    "u kunt voordeel halen als u zelf laat bezorgen",
    "wij willen er korting uit halen, betaal zelf de rest",
])
def test_is_afhaal_negatief(tekst):
    assert is_afhaal(tekst) is False


@pytest.mark.parametrize("tekst", [
    "wij halen het zelf op",
    "wir holen die Ware ab",
])
def test_is_afhaal_positief_proximity(tekst):
    assert is_afhaal(tekst) is True


def test_detect_verzendwijze_uit_afleverinstructies():
    state = {"afleverinstructies": "AFHAALORDER - klant haalt zelf op"}
    assert detect_verzendwijze(state) == AFHAAL_SHIPMENT_METHOD == "EXW"


def test_detect_verzendwijze_uit_bijlage():
    state = {"bijlagen": [{"inhoud_tekst": "Auftrag — Abholung durch Kunde"}]}
    assert detect_verzendwijze(state) == "EXW"


def test_detect_verzendwijze_geen_signaal():
    state = {"email_subject": "Bestelling", "email_body": "Graag bezorgen.",
             "opmerkingen": "spoed"}
    assert detect_verzendwijze(state) is None


# --- composer ----------------------------------------------------------

def _state(**extra):
    base = {
        "klant_match": {"navision_klantnr": "10001", "klantnaam": "X"},
        "orderregels": [{"positie": 1, "artikelnummer_kwabo_matched": "9001",
                         "hoeveelheid": 1, "eenheid": "STUK"}],
    }
    base.update(extra)
    return base


def test_composer_emits_shipment_method_for_afhaal():
    ops = compose_navision_operations(_state(verzendwijze="EXW"))
    method_ops = [o for o in ops
                  if o["op"] == "PATCH" and o["body"].get("shipmentMethodCode")]
    assert len(method_ops) == 1
    assert method_ops[0]["body"] == {"shipmentMethodCode": "EXW"}
    for idx, op in enumerate(ops):
        _assert_op_invariants(idx, op)  # single-field invariant


def test_composer_no_shipment_method_without_afhaal():
    ops = compose_navision_operations(_state())
    assert not [o for o in ops if o.get("body", {}).get("shipmentMethodCode")]


def test_nav2018_field_map_has_shipment_method():
    assert _DEFAULT_FIELD_MAP["shipmentMethodCode"] == "Shipment_Method_Code"
