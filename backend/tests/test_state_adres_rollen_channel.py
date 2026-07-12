"""F2.4 (her-diagnose 10-7, FASE1_DIAGNOSE.md categorie 2): adres_rollen
moet een declared channel van OrderState zijn.

extract.py:163 zet ``flat["adres_rollen"]`` (B1-rollen besteller/factuur/
aflever/eindontvanger), maar LangGraph bewaart alleen keys die als channel in
de OrderState-TypedDict gedeclareerd zijn — een niet-gedeclareerde key wordt
na de node stil GEDROPT. Gevolg: de rollen-dict is onzichtbaar voor alle
latere nodes, voor persistentie (order_log.order_state) en voor de UI; hij
overleeft alleen indirect in ``_meta['adressen'].value``.

Drie asserts:
  (a) ``adres_rollen`` staat in ``OrderState.__annotations__``;
  (b) een graph-doorloop waarin een node ``{"adres_rollen": {...}}``
      retourneert (zoals de echte extract-node doet) behoudt de key in de
      eindstate;
  (c) een stored-state-injectie (input-state met adres_rollen, patroon
      scripts/fase1_baseline.py run_order --no-llm) blijft in de output.

Zie tests/test_extract_adres_rollen.py voor de extract-logica zelf; dit
bestand test uitsluitend het channel-gedrag.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from kwabo.graph.state import OrderState

ROLLEN = {
    "besteller": {"naam": "BAUHAUS Bunnik", "postcode": "3981 LB", "plaats": "Bunnik"},
    "aflever": {"naam": "BAUHAUS Vestiging 462", "postcode": "7559 SR", "plaats": "Hengelo"},
}


def _mini_app(node):
    """StateGraph(OrderState) met één node — zelfde channel-semantiek als
    build_ingest_graph/build_sub_order_graph in kwabo.graph.graph."""
    wf = StateGraph(OrderState)
    wf.add_node("node", node)
    wf.set_entry_point("node")
    wf.add_edge("node", END)
    return wf.compile()


def test_adres_rollen_is_declared_orderstate_key():
    assert "adres_rollen" in OrderState.__annotations__


async def test_node_output_adres_rollen_overleeft_graph_doorloop():
    """Kern-assert: node retourneert {"adres_rollen": {...}} (zoals de echte
    extract-node) -> eindstate bevat de key."""

    def fake_extract(state: OrderState) -> dict:
        return {"adres_rollen": ROLLEN, "afleveradres": ROLLEN["aflever"]}

    app = _mini_app(fake_extract)
    out = await app.ainvoke({"email_id": "f24-kanaal-test", "orderregels": []})
    # Sanity: een wél-gedeclareerd veld uit dezelfde node-output overleeft.
    assert out.get("afleveradres") == ROLLEN["aflever"]
    assert out.get("adres_rollen") == ROLLEN


async def test_stored_state_injectie_adres_rollen_blijft_in_output():
    """Patroon fase1_baseline run_order --no-llm: adres_rollen zit al in de
    ge-injecteerde (stored) input-state -> moet ook in de output blijven."""

    def passthrough(state: OrderState) -> dict:
        return {}

    app = _mini_app(passthrough)
    out = await app.ainvoke({
        "email_id": "f24-injectie-test",
        "orderregels": [],
        "adres_rollen": ROLLEN,
    })
    assert out.get("adres_rollen") == ROLLEN
