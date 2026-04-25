"""LangGraph build/compile (PDF §3.3).

We split into two graphs:
  - ingest_graph: intake → classify → extract → match_customer → select_ship_to →
    match_articles → apply_mixprijzen → compute_europallet → validate_prices →
    compose_order → END
  - finalize_graph: push_navision → send_confirmation → END
The review happens externally (dashboard approves, then calls finalize).
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from kwabo.graph.nodes.apply_mixprijzen import apply_mixprijzen_node
from kwabo.graph.nodes.classify import classify_node
from kwabo.graph.nodes.compose_order import compose_order_node
from kwabo.graph.nodes.compute_europallet import compute_europallet_node
from kwabo.graph.nodes.extract import extract_node
from kwabo.graph.nodes.intake import intake_node
from kwabo.graph.nodes.match_articles import match_articles_node
from kwabo.graph.nodes.match_customer import match_customer_node
from kwabo.graph.nodes.push_navision import push_navision_node, send_confirmation_node
from kwabo.graph.nodes.select_ship_to import select_ship_to_node
from kwabo.graph.nodes.validate_prices import validate_prices_node
from kwabo.graph.state import OrderState


def _route_after_classify(state: OrderState) -> str:
    return "extract" if state.get("is_order") else "compose"


def build_ingest_graph():
    wf = StateGraph(OrderState)
    wf.add_node("intake", intake_node)
    wf.add_node("classify", classify_node)
    wf.add_node("extract", extract_node)
    wf.add_node("match_customer", match_customer_node)
    wf.add_node("select_ship_to", select_ship_to_node)
    wf.add_node("match_articles", match_articles_node)
    wf.add_node("apply_mixprijzen", apply_mixprijzen_node)
    wf.add_node("compute_europallet", compute_europallet_node)
    wf.add_node("validate_prices", validate_prices_node)
    wf.add_node("compose", compose_order_node)

    wf.set_entry_point("intake")
    wf.add_edge("intake", "classify")
    wf.add_conditional_edges("classify", _route_after_classify, {"extract": "extract", "compose": "compose"})
    wf.add_edge("extract", "match_customer")
    wf.add_edge("match_customer", "select_ship_to")
    wf.add_edge("select_ship_to", "match_articles")
    wf.add_edge("match_articles", "apply_mixprijzen")
    wf.add_edge("apply_mixprijzen", "compute_europallet")
    wf.add_edge("compute_europallet", "validate_prices")
    wf.add_edge("validate_prices", "compose")
    wf.add_edge("compose", END)
    return wf.compile()


def build_sub_order_graph():
    """Downstream chain for an extra sub-order (skip classify + extract).

    Used when the LLM returns multiple orders in one email (e.g. Kirchner with 2 PDFs).
    The runner builds a pre-filled state with the sub-order's flat fields + _meta and
    then invokes this graph to match, validate and persist it.
    """
    wf = StateGraph(OrderState)
    wf.add_node("match_customer", match_customer_node)
    wf.add_node("select_ship_to", select_ship_to_node)
    wf.add_node("match_articles", match_articles_node)
    wf.add_node("apply_mixprijzen", apply_mixprijzen_node)
    wf.add_node("compute_europallet", compute_europallet_node)
    wf.add_node("validate_prices", validate_prices_node)
    wf.add_node("compose", compose_order_node)
    wf.set_entry_point("match_customer")
    wf.add_edge("match_customer", "select_ship_to")
    wf.add_edge("select_ship_to", "match_articles")
    wf.add_edge("match_articles", "apply_mixprijzen")
    wf.add_edge("apply_mixprijzen", "compute_europallet")
    wf.add_edge("compute_europallet", "validate_prices")
    wf.add_edge("validate_prices", "compose")
    wf.add_edge("compose", END)
    return wf.compile()


def build_finalize_graph():
    wf = StateGraph(OrderState)
    wf.add_node("push_navision", push_navision_node)
    wf.add_node("send_confirmation", send_confirmation_node)
    wf.set_entry_point("push_navision")
    wf.add_edge("push_navision", "send_confirmation")
    wf.add_edge("send_confirmation", END)
    return wf.compile()


ingest_app = None
finalize_app = None
sub_order_app = None


def get_ingest_app():
    global ingest_app
    if ingest_app is None:
        ingest_app = build_ingest_graph()
    return ingest_app


def get_finalize_app():
    global finalize_app
    if finalize_app is None:
        finalize_app = build_finalize_graph()
    return finalize_app


def get_sub_order_app():
    global sub_order_app
    if sub_order_app is None:
        sub_order_app = build_sub_order_graph()
    return sub_order_app
