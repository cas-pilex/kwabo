"""Regressie: als de NAV-client het inkomend-document overslaat (NAV 2018 heeft
geen PLX_IncomingDocument-page), mag dat NIET stil gebeuren. De order werd
'pushed' zonder enige indicatie dat de bestelling niet in NAV gekoppeld is — de
reviewer denkt dan ten onrechte dat het document erbij zit. We zetten nu een
reviewer-zichtbare waarschuwing op de order. Ontdekt 01-06-2026.
[[nav-spec-conformiteit-mix-incomingdoc]]
"""
from __future__ import annotations

import json

from kwabo.graph.nodes.push_navision import _skipped_attachment_warning, push_navision_node


def test_helper_warns_when_incoming_doc_skipped():
    ops = [
        {"operation": {"op": "POST", "path": "/salesOrders"}, "status": 201,
         "autofilled": {"Sell_to_Customer_Name": "X"}},
        {"operation": {"op": "POST", "path": "/incomingDocuments"}, "status": 0,
         "autofilled": {"_skipped": "incomingDocuments not supported on nav2018"}},
    ]
    w = _skipped_attachment_warning(ops)
    assert w and "handmatig" in w.lower()


def test_helper_no_warning_on_clean_push():
    ops = [
        {"operation": {"op": "POST", "path": "/salesOrders"}, "status": 201,
         "autofilled": {"Sell_to_Customer_Name": "X"}},
        {"operation": {"op": "POST", "path": "/salesOrders({id})/salesOrderLines"},
         "status": 201, "autofilled": {"Description": "Y", "Unit_Price": 1.0}},
    ]
    assert _skipped_attachment_warning(ops) is None


class _StubSkipClient:
    """NAV client whose stepwise push skips the incoming-doc op (nav2018-like)."""

    async def create_sales_order_stepwise(self, operations):
        return {
            "sales_order_id": "VO-TEST-1",
            "sales_order_number": "VO-TEST-1",
            "nav_autofilled": {"Sell_to_Customer_Name": "Testklant"},
            "operation_results": [
                {"operation": {"op": "POST", "path": "/salesOrders"}, "status": 201,
                 "response_body": {}, "autofilled": {"Sell_to_Customer_Name": "Testklant"}},
                {"operation": {"op": "POST", "path": "/incomingDocuments"}, "status": 0,
                 "response_body": {},
                 "autofilled": {"_skipped": "incomingDocuments not supported on nav2018"}},
            ],
        }


async def test_skipped_attachment_lands_in_row_warnings(session, monkeypatch):
    """End-to-end: a skipped attachment must persist to row.warnings so the
    dashboard (warnings_count / OrderDetail.warnings) shows it."""
    from kwabo.db.repository import OrderLogRepo
    from kwabo.graph.nodes import push_navision as pn

    monkeypatch.setattr(pn, "engine", session.get_bind())
    monkeypatch.setattr(pn, "get_navision_client", lambda: _StubSkipClient())

    row = OrderLogRepo(session).create(
        email_id="att-skip-1", status="review", is_order=True,
        warnings=json.dumps(["bestaande prijs-warning"]),
        order_state=json.dumps({"orderregels": []}),
    )
    oid = row.id

    state = {"order_log_id": oid, "email_id": "att-skip-1",
             "nav_operations": [{"op": "POST", "path": "/salesOrders", "body": {"customerNumber": "50000"}}]}
    out = await push_navision_node(state)
    assert out["navision_status"] == "Draft"

    from sqlmodel import Session
    with Session(session.get_bind()) as s2:
        refreshed = OrderLogRepo(s2).get(oid)
        warns = json.loads(refreshed.warnings or "[]")
    assert any("handmatig" in w.lower() for w in warns), warns
    # bestaande warnings blijven behouden
    assert "bestaande prijs-warning" in warns
