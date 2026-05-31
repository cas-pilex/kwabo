"""Logs endpoint — serves the rotating log file + tail stream."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from kwabo.api.auth import _extract_bearer, _verify
from kwabo.config import settings

# Bearer-gated router (mounted with auth_gate in main.py) — serves /tail.
router = APIRouter(prefix="/api/logs", tags=["logs"])
# UNGATED router for /stream: EventSource cannot send an Authorization header,
# so this endpoint authenticates a ?token= query param in-handler instead.
stream_router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_PATH = Path(__file__).resolve().parents[3] / "kwabo.log"


def _authorize_stream(token: str | None, authorization: str | None) -> None:
    """Auth for the SSE stream. The browser EventSource API can't set headers,
    so accept the same HMAC token via ?token=, falling back to a Bearer header.
    Mirrors require_admin: when ADMIN_PASSWORD is unset the gate is off (dev)."""
    if not settings.admin_password:
        return
    tok = token or _extract_bearer(authorization)
    if not tok or not _verify(tok, settings.jwt_secret):
        raise HTTPException(status_code=401, detail="Sessie ongeldig of verlopen")


@router.get("/tail")
def tail(lines: int = Query(default=300, ge=1, le=5000)) -> dict:
    if not LOG_PATH.exists():
        return {"path": str(LOG_PATH), "lines": [], "size": 0}
    size = LOG_PATH.stat().st_size
    # Read last N lines
    with LOG_PATH.open("rb") as f:
        block = 8192
        data = b""
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        while pos > 0 and data.count(b"\n") <= lines:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
    text = data.decode("utf-8", errors="replace")
    out = text.splitlines()[-lines:]
    return {"path": str(LOG_PATH), "size": size, "lines": out}


@stream_router.get("/stream")
async def stream(
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Server-sent events tail of the log file. Auth via ?token= (EventSource
    can't send an Authorization header) or Bearer header."""
    _authorize_stream(token, authorization)

    async def gen():
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.touch(exist_ok=True)
        with LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)
                    yield ": keep-alive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
