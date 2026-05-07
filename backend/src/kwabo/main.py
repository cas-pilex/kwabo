"""FastAPI app entry point."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from kwabo.api.artikelen import router as artikelen_router
from kwabo.api.audit import router as audit_router
from kwabo.api.auth import require_admin, router as auth_router
from kwabo.api.intake_trigger import router as intake_router
from kwabo.api.klanten import router as klanten_router
from kwabo.api.logs import router as logs_router
from kwabo.api.mailbox import router as mailbox_router
from kwabo.api.orders import router as orders_router
from kwabo.api.preview import router as preview_router
from kwabo.api.prijsafspraken import router as prijs_router
from kwabo.config import settings
from kwabo.db.seed import seed
from kwabo.db.session import engine, init_db
from kwabo.utils.logging import log, setup_logging


def _cors_origins() -> list[str]:
    base = ["http://localhost:3000", "http://127.0.0.1:3000"]
    extra = os.environ.get("KWABO_CORS_EXTRA", "").strip()
    if extra:
        for item in extra.split(","):
            item = item.strip()
            if item and item not in base:
                base.append(item)
    return base


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as s:
        seed(s)
    log.info("app_started", routes=len(app.routes))
    yield


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Kwabo Order Intake AI",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Auth router is unprotected (login itself can't require auth).
    app.include_router(auth_router)

    # All other routers require a valid admin session. When ADMIN_PASSWORD
    # is unset (development), the dependency short-circuits with auth
    # disabled — see api/auth.py:require_admin.
    auth_gate = [Depends(require_admin)]
    app.include_router(orders_router, dependencies=auth_gate)
    app.include_router(klanten_router, dependencies=auth_gate)
    app.include_router(artikelen_router, dependencies=auth_gate)
    app.include_router(audit_router, dependencies=auth_gate)
    app.include_router(intake_router, dependencies=auth_gate)
    app.include_router(logs_router, dependencies=auth_gate)
    app.include_router(mailbox_router, dependencies=auth_gate)
    app.include_router(preview_router, dependencies=auth_gate)
    app.include_router(prijs_router, dependencies=auth_gate)

    # NAV connectivity diagnostic — handy for the dashboard, also auth-gated.
    from kwabo.api.diagnostics import router as diagnostics_router
    app.include_router(diagnostics_router, dependencies=auth_gate)

    if getattr(settings, "test_mode", "off") == "on":
        from kwabo.api import testing as testing_api

        app.include_router(testing_api.router)

    @app.get("/")
    def root() -> dict:
        return {"name": "kwabo-order-intake", "version": "0.1.0"}

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
