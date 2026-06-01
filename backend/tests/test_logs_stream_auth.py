"""Regressie: /api/logs/tail én /api/logs/stream zitten achter de Bearer-gate
(require_admin). De frontend opent /stream met fetch()+Authorization-header (geen
EventSource), zodat de admin-token nooit in een URL/query belandt (HIGH
security-finding 31-05-2026). Deze test borgt de router-wiring zonder DB/lifespan
nodig te hebben. [[logs-pagina-401-geen-auth]]
"""
from __future__ import annotations

from kwabo.api.auth import require_admin
from kwabo.main import create_app


def _route_dep_calls(app, path):
    for r in app.routes:
        if getattr(r, "path", None) == path and getattr(r, "dependant", None):
            return [d.call for d in r.dependant.dependencies]
    raise AssertionError(f"route {path} niet gevonden")


def test_logs_stream_is_gated():
    app = create_app()
    assert require_admin in _route_dep_calls(app, "/api/logs/stream")


def test_logs_tail_is_gated():
    app = create_app()
    assert require_admin in _route_dep_calls(app, "/api/logs/tail")
