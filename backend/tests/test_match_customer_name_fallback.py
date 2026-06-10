"""K3+K4 (Fase 2): klant-naam-fallback met kandidatenlijst.

Bij portaal/agent/onbekende-afzender-mails levert de e-mailcascade niets op;
de geëxtraheerde KLANTNAAM uit de bestelling (klantnaam_besteller, of de
forward-naam) wordt dan fuzzy gematcht tegen de klantenkaarten-mirror.

Drempels, empirisch bepaald op alle 1787 echte klantnamen
(scripts/analyze_name_fallback.py, 10-06-2026, token_set_ratio na
rechtsvorm-strip):
  * exacte faalorder-namen scoren 100 met gap >= 22 naar nr. 2
    (Witzand/Van Dongen/GBI Borne/Kuipers);
  * franchise-namen ('Jongeneel': ~40 vestigingen @100, gap 0) en
    generieke namen ('Holland': 3×@100) hebben GEEN unieke winnaar;
  * 'TABS Holland' haalt max 87 (AST Holland — fout artikel!).
  → accepteer alleen top >= 90 ÉN gap >= 10; kandidaten tonen vanaf 75,
    nooit autopick (grondwet 5).

Tests draaien tegen ALLE echte klantenkaarten (fixtures-export).
"""
from __future__ import annotations

import json

import pytest

from kwabo.db.models import Klantenkaart
from kwabo.graph.nodes.match_customer import match_customer_node

from conftest import STATES_DIR, load_state


@pytest.fixture
def app_engine(session, monkeypatch):
    from kwabo.db import session as db_session_mod
    from kwabo.graph.nodes import match_customer as mc_mod

    new_engine = session.get_bind()
    monkeypatch.setattr(db_session_mod, "engine", new_engine)
    monkeypatch.setattr(mc_mod, "engine", new_engine)
    yield


@pytest.fixture
def echte_klantenkaarten(session):
    """Laad alle echte klantenkaarten (1787) uit de prod-export in de test-DB."""
    p = STATES_DIR / "klantenkaarten.json"
    if not p.is_file():
        pytest.skip("klantenkaarten.json ontbreekt — draai export_order_states.py")
    rows = json.loads(p.read_text(encoding="utf-8"))
    bestaande = {k.nav_klantnr for k in session.exec(
        __import__("sqlmodel").select(Klantenkaart)
    ).all()}
    for r in rows:
        if r["nav_klantnr"] in bestaande:
            continue
        session.add(Klantenkaart(
            nav_klantnr=r["nav_klantnr"], naam=r["naam"] or "",
            email=r.get("email"), email_bestelling=r.get("email_bestelling"),
        ))
    session.commit()
    yield


def _state(email_from: str, subject: str = "", klantnaam: str | None = None,
           body: str = "") -> dict:
    return {
        "email_id": "k3-test",
        "email_from": email_from,
        "email_subject": subject,
        "email_body": body,
        "bijlagen": [],
        "stappen_log": [],
        "klantnaam_besteller": klantnaam,
        "orderregels": [],
    }


@pytest.mark.asyncio
async def test_witzand_718_matcht_op_naam(session, app_engine, echte_klantenkaarten):
    """#718: afzender inkoop@witzand.nl matcht nergens op e-mail; de
    geëxtraheerde naam moet 60892 opleveren."""
    env = load_state("order_718")
    st = _state(env["email_from"], env["email_subject"],
                klantnaam="Witzand Bouwmaterialen B.V.")
    out = await match_customer_node(st)
    m = out["klant_match"]
    assert m is not None, out.get("validatie_warnings")
    assert m["navision_klantnr"] == "60892"
    assert m["match_bron"] == "naam_extract"
    assert m["match_confidence"] == 0.8
    assert "klant_match" not in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_gbi_borne_707_portaal_matcht_op_naam(session, app_engine, echte_klantenkaarten):
    """#707: zevij-portaal — afzender support@zevij-necomij.com is de klant
    niet; de naam uit het portal-onderwerp moet 61948 opleveren."""
    env = load_state("order_707")
    st = _state(env["email_from"], env["email_subject"], klantnaam="GBI Borne")
    out = await match_customer_node(st)
    m = out["klant_match"]
    assert m is not None, out.get("validatie_warnings")
    assert m["navision_klantnr"] == "61948"
    assert m["match_bron"] == "naam_extract"


@pytest.mark.asyncio
async def test_van_dongen_721_matcht_op_naam(session, app_engine, echte_klantenkaarten):
    env = load_state("order_721")
    st = _state(env["email_from"], env["email_subject"],
                klantnaam="Van Dongen Verf BV")
    out = await match_customer_node(st)
    m = out["klant_match"]
    assert m is not None, out.get("validatie_warnings")
    assert m["navision_klantnr"] == "61472"


@pytest.mark.asyncio
async def test_franchise_naam_geeft_kandidaten_geen_autopick(session, app_engine, echte_klantenkaarten):
    """'Jongeneel' heeft ~40 vestigingen @100 — kandidaten tonen, NIET kiezen
    (grondwet 5)."""
    st = _state("J.Kremer@jongeneel.nl", "Bestelling 4506855359 642",
                klantnaam="Jongeneel")
    out = await match_customer_node(st)
    assert out["klant_match"] is None
    kandidaten = out.get("klant_kandidaten") or []
    assert len(kandidaten) >= 2
    assert all(k.get("navision_klantnr") and k.get("klantnaam") for k in kandidaten)
    assert any("MEERDERE KLANTEN" in w for w in out["validatie_warnings"])
    assert "klant_match" in out["needs_review_fields"]


@pytest.mark.asyncio
async def test_tabs_holland_pakt_nooit_ast_holland(session, app_engine, echte_klantenkaarten):
    """'TABS Holland' scoort max 87 op 'AST Holland B.V.' — dat is een ANDER
    bedrijf en mag nooit automatisch gekozen worden."""
    st = _state("Joran.de.Waard@pontmeyer.nl", "Bestelling 4506860196 633",
                klantnaam="TABS Holland")
    out = await match_customer_node(st)
    assert out["klant_match"] is None


@pytest.mark.asyncio
async def test_forward_naam_als_fallback_signaal(session, app_engine, echte_klantenkaarten):
    """K4: geen klantnaam_besteller, wél een geparsede forward → gebruik de
    originele afzendernaam als naam-signaal."""
    body = (
        "FYI, kun je deze verwerken?\n\n"
        "---------- Forwarded message ----------\n"
        "Van: Witzand Bouwmaterialen B.V. <inkoop@witzand.nl>\n"
        "Onderwerp: Inkooporder 50040984\n"
    )
    st = _state("nico@kwabo.nl", "Fwd: Inkooporder 50040984", klantnaam=None, body=body)
    out = await match_customer_node(st)
    m = out["klant_match"]
    assert m is not None, out.get("validatie_warnings")
    assert m["navision_klantnr"] == "60892"
    assert m["match_bron"] == "naam_extract"


@pytest.mark.asyncio
async def test_portaal_domein_skipt_domein_substring_stap(session, app_engine, echte_klantenkaarten, monkeypatch):
    """K4: bij een puur portaal-domein (zevij-necomij) zonder naam-signaal mag
    de domein-substring-stap NIET draaien (actief schadelijk signaal)."""
    from kwabo.graph.nodes import match_customer as mc_mod

    naam_zoekopdrachten: list[str] = []

    class _SpyNav:
        async def search_customers(self, naam=None, email=None):
            if naam is not None:
                naam_zoekopdrachten.append(naam)
            return []

    monkeypatch.setattr(mc_mod, "get_navision_client", lambda: _SpyNav())
    st = _state("support@zevij-necomij.com", "Order van GBI Borne - 2601922")
    out = await match_customer_node(st)
    assert out["klant_match"] is None
    assert naam_zoekopdrachten == [], "domein-stap draaide toch voor portaal-domein"


@pytest.mark.asyncio
async def test_regressie_k1_email_wint_van_naam(session, app_engine, echte_klantenkaarten):
    """Regressieguard: een bekende e-mail (K1) blijft winnen — de naam-fallback
    draait alleen als de e-mailcascade niets oplevert."""
    st = _state("purchaseorders@ferney.nl", "Inkooporder",
                klantnaam="Witzand Bouwmaterialen B.V.")  # tegenstrijdig signaal
    out = await match_customer_node(st)
    m = out["klant_match"]
    assert m is not None
    assert m["match_bron"] in ("email", "forward_email")
    assert m["navision_klantnr"] == "10001"  # demo-seed Ferney
