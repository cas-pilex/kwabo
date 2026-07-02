"""B1 (structurele upgrade): extractie levert adressen MET ROL.

Vier rollen: besteller / factuur / aflever / eindontvanger. Het afgeleide
``afleveradres`` (waar ship-to op draait) komt UITSLUITEND uit
aflever/eindontvanger — nooit uit het besteladres (BAUHAUS #944: besteld door
Bunnik 3981 LB, geleverd in Hengelo 7559 SR) of factuuradres. Bij twijfel over
de rollen (needs_review op ``adressen``) wordt ``afleveradres`` gevlagd i.p.v.
gegokt. Oude prompt-output (alleen ``afleveradres``, geen ``adressen``) blijft
werken: de prompt is live-overridebaar en kan in prod nog de oude vorm leveren.
"""
from __future__ import annotations

from kwabo.graph.nodes.extract import _build_state_from_extract
from kwabo.integrations.email_client import RawEmail


def _raw() -> RawEmail:
    return RawEmail(
        email_id="b1-test", email_from="supplier@bahag.com",
        email_subject="1049577521", email_date="", email_body="", bijlagen=[],
    )


def _adr(naam, postcode, plaats):
    return {"naam": naam, "straat": None, "postcode": postcode, "plaats": plaats, "land": "NL"}


def _adressen(value, needs_review=False):
    return {"value": value, "source": "pdf", "source_detail": "p.1",
            "confidence": 0.95, "needs_review": needs_review}


def test_afleveradres_komt_uit_aflever_rol_niet_besteller():
    """#944-patroon: besteld door Bunnik, geleverd in Hengelo -> Hengelo wint."""
    parsed = {
        "adressen": _adressen({
            "besteller": _adr("BAUHAUS Bunnik", "3981 LB", "Bunnik"),
            "aflever": _adr("BAUHAUS Vestiging 462", "7559 SR", "Hengelo"),
        }),
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert flat["afleveradres"]["postcode"] == "7559 SR"
    assert flat["adres_rollen"]["besteller"]["postcode"] == "3981 LB"
    assert "afleveradres" not in needs


def test_eindontvanger_wint_bij_strecken():
    """#847-patroon: agent bestelt, eindontvanger se Huber Straubing 94315."""
    parsed = {
        "adressen": _adressen({
            "besteller": _adr("Werkzeuge Dietrich GmbH & Co. KG", "31303", "Burgdorf"),
            "eindontvanger": _adr("se Huber GmbH & Co KG", "94315", "Straubing"),
        }),
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert flat["afleveradres"]["postcode"] == "94315"
    assert flat["afleveradres"]["plaats"] == "Straubing"
    assert "afleveradres" not in needs


def test_alleen_besteller_adres_geeft_geen_afleveradres_en_geen_gok():
    """Geen aflever/eindontvanger -> afleveradres None (klant-kaartadres geldt),
    en het besteladres wordt NOOIT stilzwijgend afleveradres."""
    parsed = {
        "adressen": _adressen({
            "besteller": _adr("Firma X", "1234 AB", "Ergens"),
        }),
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert flat["afleveradres"] is None
    assert flat["adres_rollen"]["besteller"]["postcode"] == "1234 AB"
    assert "afleveradres" not in needs


def test_twijfel_over_rollen_vlagt_afleveradres():
    """LLM twijfelt (needs_review op adressen) -> vlag, geen gok."""
    parsed = {
        "adressen": _adressen({
            "aflever": _adr("Firma Y", "5678 CD", "Elders"),
        }, needs_review=True),
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert "afleveradres" in needs


def test_oude_promptvorm_zonder_adressen_blijft_werken():
    """Live prompt-overrides kunnen nog de oude vorm leveren."""
    parsed = {
        "afleveradres": {"value": _adr("Oud Formaat BV", "9999 ZZ", "Oudorp"),
                         "source": "pdf", "source_detail": None,
                         "confidence": 0.9, "needs_review": False},
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert flat["afleveradres"]["postcode"] == "9999 ZZ"
    assert flat.get("adres_rollen") == {}


def test_aflever_rol_vult_ook_oude_afleveradres_meta():
    """_meta.afleveradres moet de herkomst (rol) tonen voor de UI."""
    parsed = {
        "adressen": _adressen({
            "aflever": _adr("Firma Z", "1111 AA", "Stad"),
        }),
        "orderregels": [],
    }
    flat, meta, needs = _build_state_from_extract(parsed, _raw())
    assert meta["afleveradres"]["value"]["postcode"] == "1111 AA"
    assert "aflever" in (meta["afleveradres"]["source_detail"] or "")
