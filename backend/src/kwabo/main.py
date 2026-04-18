"""FastAPI app entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kwabo.api.artikelen import router as artikelen_router
from kwabo.api.audit import router as audit_router
from kwabo.api.intake_trigger import router as intake_router
from kwabo.api.klanten import router as klanten_router
from kwabo.api.logs import router as logs_router
from kwabo.api.orders import router as orders_router
from kwabo.api.preview import router as preview_router
from kwabo.api.prijsafspraken import router as prijs_router
from kwabo.utils.logging import log, setup_logging
from kwabo.db.session import engine, init_db
from kwabo.db.seed import seed
from sqlmodel import Session


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Kwabo Order Intake AI", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(orders_router)
    app.include_router(klanten_router)
    app.include_router(artikelen_router)
    app.include_router(audit_router)
    app.include_router(intake_router)
    app.include_router(logs_router)
    app.include_router(preview_router)
    app.include_router(prijs_router)

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        with Session(engine) as s:
            seed(s)
        log.info("app_started", routes=len(app.routes))

    @app.get("/")
    def root() -> dict:
        return {"name": "kwabo-order-intake", "version": "0.1.0"}

    return app


app = create_app()
