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
    network blip. Each tick is recorded via `mail_poll_status.record_poll_tick`
    so /api/mailbox/status can surface "is the poller actually running?"
    without the operator having to grep Railway logs.
    """
    from kwabo.utils import mail_poll_status

    if settings.email_mode == "file_drop":
        log.info("mail_poll_skipped", reason="email_mode=file_drop")
        return
    # Small initial delay so a deploy doesn't immediately hammer Graph.
    await asyncio.sleep(min(30, interval_seconds))
    while True:
        try:
            from kwabo.api.intake_trigger import scan_inbox
            result = await scan_inbox()
            processed_n = len(result.get("processed") or [])
            err_list = result.get("errors") or []
            errors_n = len(err_list)
            partial = bool(result.get("partial"))
            # Surface the distinct per-mail error texts in the heartbeat so
            # /api/mailbox/status toont de OORZAAK (niet alleen een telling).
            # Zonder dit zagen we live errors=10 met last_poll_error_msg=null
            # en moesten we blind Railway-logs graven.
            err_summary = None
            if err_list:
                distinct = list(dict.fromkeys(
                    (e.get("error") or "") for e in err_list if e.get("error")
                ))
                err_summary = "; ".join(distinct)[:300] or None
            log.info(
                "mail_poll_tick",
                processed=processed_n,
                errors=errors_n,
                partial=partial,
                error_sample=err_summary,
            )
            mail_poll_status.record_poll_tick(
                success=True,
                processed=processed_n,
                errors=errors_n,
                partial=partial,
                error_msg=err_summary,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("mail_poll_tick_failed", error=str(exc)[:200])
            mail_poll_status.record_poll_tick(
                success=False, error_msg=str(exc)
            )
            from kwabo.utils.alerts import alert
            alert(
                "mail_poll_tick_failed",
                "high",
                {"error": str(exc)[:300]},
            )
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as s:
        seed(s)
    log.info("app_started", routes=len(app.routes))
    poll_task: asyncio.Task | None = None
    interval = settings.mail_poll_interval_seconds
    # Fase 5: multi-worker guard. De poll-task draait per Python-proces;
    # bij `WEB_CONCURRENCY > 1` (gunicorn met N workers) ploft hij N keer
    # tegelijk de Graph-mailbox. `mark_seen` is voor Graph idempotent
    # (PATCH isRead=true), maar Claude API-quotum is dat niet. Log een
    # luide WARNING en SKIP de poll-task in deze worker als WEB_CONCURRENCY
    # > 1 — operator moet dan in Railway óf 1 replica gebruiken óf een
    # dedicated single-worker process voor de poller opzetten.
    web_concurrency = int(os.environ.get("WEB_CONCURRENCY", "1") or "1")
    if web_concurrency > 1 and interval and interval >= 30:
        log.warning(
            "mail_poll_skipped_multi_worker",
            web_concurrency=web_concurrency,
            hint=(
                "WEB_CONCURRENCY>1 zou N-voudige Graph-scans veroorzaken. "
                "Zet WEB_CONCURRENCY=1 in Railway of run de poller in een "
                "aparte service. Skip poll-task in deze worker."
            ),
        )
        interval = 0  # neutraliseer de spawn-branch hieronder
    if interval and interval >= 30:
        poll_task = asyncio.create_task(_mail_poll_loop(interval))
        log.info("mail_poll_started", interval_seconds=interval)
    elif interval:
        log.warning(
            "mail_poll_disabled",
            reason="interval too low (<30s)",
            requested=interval,
        )
    elif settings.email_mode == "graph":
        # Loud warning: prod-config bug we hit before. With email_mode=graph
        # and interval=0 the mailbox is unreachable to the user (nothing
        # polls), but there's no error — just silence. Operator wonders why
        # no orders come in. Make it impossible to miss.
        log.warning(
            "mail_poll_disabled_in_graph_mode",
            interval=0,
            hint=(
                "MAIL_POLL_INTERVAL_SECONDS is 0 but EMAIL_MODE=graph. "
                "Without a poller no mails will be fetched. Set the env "
                "var to e.g. 300 (5 min) in Railway and redeploy."
            ),
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
