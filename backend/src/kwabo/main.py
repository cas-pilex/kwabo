"""FastAPI app entry point."""
from __future__ import annotations

import asyncio
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
from kwabo.api.mailbox import (
    router as mailbox_router,
    router_public as mailbox_public_router,
)
from kwabo.api.orders import (
    router as orders_router,
    router_public as orders_public_router,
)
from kwabo.api.preview import router as preview_router
from kwabo.api.prijsafspraken import router as prijs_router
from kwabo.config import settings
from kwabo.db.seed import seed
from kwabo.db.session import engine, init_db
from kwabo.utils.logging import log, setup_logging


def _cors_origins() -> list[str]:
    """Explicit allow-list. Combined with `_cors_origin_regex` below; either
    match wins (FastAPI checks both). The hardcoded production hostnames
    short-circuit the env-var dependency that bit us during go-live."""
    base = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://kwabo-pilex.vercel.app",
        "https://kwabo-frontend.vercel.app",
    ]
    extra = os.environ.get("KWABO_CORS_EXTRA", "").strip()
    if extra:
        for item in extra.split(","):
            item = item.strip()
            if item and item not in base:
                base.append(item)
    return base


# Allow ANY Vercel preview deployment (auto-generated URLs change per
# build), so we don't have to maintain an env-var list as previews come
# and go. This pattern matches both `<project>.vercel.app` and the
# hash-form `<project>-<hash>-<team>.vercel.app`.
_CORS_ORIGIN_REGEX = r"https://.*\.vercel\.app$"


async def _mail_poll_loop(interval_seconds: int) -> None:
    """Background coroutine that calls /api/intake/scan logic on a timer.

    Honours `mail_poll_interval_seconds`. Skips when email_mode='file_drop'
    (no remote inbox to poll). Catches all exceptions so a single failure
    doesn't kill the loop — Nico shouldn't have to re-deploy after one
    network blip.
    """
    if settings.email_mode == "file_drop":
        log.info("mail_poll_skipped", reason="email_mode=file_drop")
        return
    # Small initial delay so a deploy doesn't immediately hammer Graph.
    await asyncio.sleep(min(30, interval_seconds))
    while True:
        try:
            from kwabo.api.intake_trigger import scan_inbox
            result = await scan_inbox()
            log.info(
                "mail_poll_tick",
                processed=len(result.get("processed") or []),
                errors=len(result.get("errors") or []),
                partial=result.get("partial"),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("mail_poll_tick_failed", error=str(exc)[:200])
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as s:
        seed(s)
    log.info("app_started", routes=len(app.routes))
    poll_task: asyncio.Task | None = None
    interval = settings.mail_poll_interval_seconds
    if interval and interval >= 30:
        poll_task = asyncio.create_task(_mail_poll_loop(interval))
        log.info("mail_poll_started", interval_seconds=interval)
    elif interval:
        log.warning(
            "mail_poll_disabled",
            reason="interval too low (<30s)",
            requested=interval,
        )
    try:
        yield
    finally:
        if poll_task is not None:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Kwabo Order Intake AI",
        version="0.1.0",
        lifespan=lifespan,
    )
    cors_origins = _cors_origins()
    log.info("cors_config", origins=cors_origins, regex=_CORS_ORIGIN_REGEX)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=_CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Auth router is unprotected (login itself can't require auth).
    app.include_router(auth_router)
    # Microsoft OAuth2 browser-redirect endpoints are unprotected: the
    # callback comes in via a 302 from login.microsoftonline.com with no
    # Authorization header. CSRF is handled by the state-token issued in
    # /oauth/start and verified in /oauth/callback (see mailbox.py).
    app.include_router(mailbox_public_router)
    # Attachment download endpoint validates a short-lived signed token in
    # the query string; cannot live behind the Bearer-header gate because
    # `<a target="_blank">` loses the header. CSRF/auth is enforced via the
    # HMAC token minted at /api/orders/{id}/bijlagen-token.
    app.include_router(orders_public_router)

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

    # Admin ops (NAV master-sync, DB counts) — auth-gated.
    from kwabo.api.admin import router as admin_router
    app.include_router(admin_router, dependencies=auth_gate)

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
