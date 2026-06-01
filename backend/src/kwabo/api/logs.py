"""Logs endpoint — serves the rotating log file + tail stream.

Both endpoints sit behind the Bearer gate (mounted with auth_gate in main.py).
The frontend consumes /stream with fetch()+ReadableStream and an Authorization
header (NOT EventSource) so the admin token never lands in a URL/query string.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_PATH = Path(__file__).resolve().parents[3] / "kwabo.log"


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


@router.get("/stream")
async def stream() -> StreamingResponse:
    """Server-sent events tail of the log file. Bearer-gated via auth_gate;
    the frontend opens it with fetch()+Authorization header so no token is
    ever placed in the URL."""
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
