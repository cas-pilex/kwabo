"""Thin Supabase Storage REST wrapper (httpx).

Why not `supabase-py`: that pulls in `gotrue`, `postgrest`, `realtime`,
`storage3` and `websockets` while we only need three storage calls. Three
direct httpx calls cost less to keep working as Supabase versions drift,
and they share the same connection pool as the rest of the app.

Design notes
------------
The wrapper is **defensive on missing config**: when `supabase_url` or
`supabase_service_role_key` is empty (lokaal dev, CI, docker) the factory
returns ``None``. Callers MUST handle that — typically by falling back to
the legacy local-disk path. This keeps the dev loop friction-free and
makes the production-only persistence path opt-in via Railway env vars.

Bucket convention
-----------------
- ``by_email_id/<safe_email_id>.eml`` — Graph-fetched + drag-and-drop mails
- ``by_order/<order_id>/<sanitized_filename>`` — reviewer-uploaded source docs
  via POST /api/orders/{id}/incoming-doc (typically PDF, sometimes JPG/EML)

Both prefixes live in the same private bucket (default name
``incoming-docs``); separation is purely organizational so an operator
can see at a glance whether a key came from intake or from manual upload.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from kwabo.config import settings

log = logging.getLogger(__name__)


class SupabaseStorageClient:
    """Minimal Storage v1 client. Methods raise ``httpx.HTTPStatusError``
    on non-2xx so callers can decide whether to fall back or bubble up."""

    def __init__(
        self,
        *,
        url: str,
        service_role_key: str,
        bucket: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = url.rstrip("/")
        self.bucket = bucket
        # Supabase Storage authenticates with the service_role JWT on the
        # `Authorization` header AND the same value on the legacy `apikey`
        # header (PostgREST convention). Both are required.
        self._headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    # ---------- URL helpers ----------

    def _object_url(self, key: str) -> str:
        # NB: callers pass a forward-slash-separated key like
        # "by_email_id/abc123.eml". We don't urlencode '/' — Supabase
        # interprets the key with native slashes.
        return f"{self.base_url}/storage/v1/object/{self.bucket}/{key}"

    def _sign_url(self, key: str) -> str:
        return f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{key}"

    # ---------- operations ----------

    def put_object(self, key: str, content: bytes, content_type: str) -> None:
        """Upsert bytes at `key`. Idempotent (overwrite-allowed) via
        ``x-upsert: true`` — same key replaces same content silently. Larger
        than the bucket's max-size config raises HTTP 413; the caller logs
        and proceeds without storage.
        """
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                self._object_url(key),
                content=content,
                headers={
                    **self._headers,
                    "Content-Type": content_type or "application/octet-stream",
                    "x-upsert": "true",
                    "Cache-Control": "no-cache",
                },
            )
            r.raise_for_status()

    def get_object(self, key: str) -> bytes:
        with httpx.Client(timeout=self._timeout) as c:
            r = c.get(self._object_url(key), headers=self._headers)
            r.raise_for_status()
            return r.content

    def head_object(self, key: str) -> bool:
        """True iff the object exists. 404 ⇒ False; other errors raise."""
        with httpx.Client(timeout=self._timeout) as c:
            r = c.head(self._object_url(key), headers=self._headers)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            return True

    def signed_url(self, key: str, ttl_seconds: int) -> Optional[str]:
        """Mint a Supabase-side signed download URL. Useful when we want
        the browser to fetch directly without proxying through FastAPI.
        Returns None when the object doesn't exist (404). We currently use
        the proxy-fetch path everywhere, but the helper is here for future
        signed-URL iframe optimisation.
        """
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(
                self._sign_url(key),
                json={"expiresIn": ttl_seconds},
                headers={**self._headers, "Content-Type": "application/json"},
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            body = r.json() or {}
            signed = body.get("signedURL") or body.get("signedUrl") or ""
            if not signed:
                return None
            # signedURL is a relative path like "/object/sign/bucket/key?token=…"
            if signed.startswith("http"):
                return signed
            return f"{self.base_url}/storage/v1{signed.lstrip('/')}" if signed.startswith("/") else f"{self.base_url}/storage/v1/{signed}"


def get_supabase_storage() -> Optional[SupabaseStorageClient]:
    """Factory. Returns None when storage isn't configured — caller falls
    back to local disk. Centralising the "is it configured?" decision here
    means individual call-sites stay simple (``if client is None: ...``)."""
    url = getattr(settings, "supabase_url", "") or ""
    key = getattr(settings, "supabase_service_role_key", "") or ""
    bucket = getattr(settings, "supabase_bucket_incoming_docs", "incoming-docs") or "incoming-docs"
    if not url or not key:
        return None
    return SupabaseStorageClient(
        url=url, service_role_key=key, bucket=bucket
    )
