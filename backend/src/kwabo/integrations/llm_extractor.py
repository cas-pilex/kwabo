"""Claude Vision-based PDF extractor.

Sends the entire e-mail (body + every PDF as a `document` block + other attachments
inline) in one Anthropic API call. Claude reads tabular and image-based PDFs natively.

Returns the parsed JSON dict (or list of dicts for multi-order). Each field is a
provenance object {value, source, source_detail, confidence, needs_review}.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import anthropic

from kwabo.config import settings
from kwabo.config_store import effective_setting, resolve_prompt
from kwabo.graph.llm_cache import cache_get, cache_key, cache_put
from kwabo.integrations.email_client import RawEmail
from kwabo.utils.json_parser import parse_json_loose

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_blocks(raw: RawEmail) -> list[dict[str, Any]]:
    """Build content blocks: PDF attachments → document; others → text."""
    blocks: list[dict[str, Any]] = []
    pdf_count = 0
    for b in raw.bijlagen:
        if b.type == "pdf" and b.raw:
            try:
                data = base64.standard_b64encode(b.raw).decode("ascii")
                blocks.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": data,
                        },
                        "title": b.naam,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
                pdf_count += 1
            except Exception:  # noqa: BLE001
                # Fallback to text if PDF can't be encoded
                blocks.append(
                    {
                        "type": "text",
                        "text": f"=== PDF (binary missing): {b.naam} ===\n{b.inhoud_tekst[:8000]}",
                    }
                )
        elif b.type in ("excel", "csv"):
            blocks.append(
                {
                    "type": "text",
                    "text": f"=== {b.naam} ({b.type}) ===\n{(b.inhoud_tekst or '')[:12000]}",
                }
            )
        else:
            # Unknown attachment types — include as text if any
            if b.inhoud_tekst:
                blocks.append({"type": "text", "text": f"=== {b.naam} ===\n{b.inhoud_tekst[:6000]}"})
    # Multi-PDF hint: if there are 2+ PDFs each may be a separate order
    multi_pdf_hint = ""
    if pdf_count >= 2:
        multi_pdf_hint = (
            f"LET OP: er zijn {pdf_count} PDF-bijlagen. Als elke PDF een afzonderlijke "
            f"order bevat (verschillende Bestellnummer/Bestelnummer/Ordernummer per PDF), "
            f"retourneer dan een JSON ARRAY met één element per order — niet één "
            f"gecombineerde order.\n\n"
        )
    # Always add the email envelope last so Claude sees PDFs first
    blocks.append(
        {
            "type": "text",
            "text": (
                f"\n--- E-MAIL ENVELOPPE ---\n"
                f"Van: {raw.email_from}\n"
                f"Onderwerp: {raw.email_subject}\n"
                f"Datum: {raw.email_date}\n"
                f"Body:\n{(raw.email_body or '')[:8000]}\n\n"
                f"Bijlagen meegestuurd: {len(raw.bijlagen)} "
                f"(waarvan {pdf_count} PDF als document-block)\n\n"
                f"{multi_pdf_hint}"
                f"Extraheer alle ordergegevens volgens het schema in de system-prompt. "
                f"Output uitsluitend pure JSON."
            ),
        }
    )
    return blocks


async def extract_from_email(raw: RawEmail, model: str | None = None, max_retries: int = 2) -> Any:
    """Run Claude on the email + attachments and return parsed JSON.

    Returns either a dict (single order) or a list[dict] (multi-order).
    Retries on transient API errors (rate-limit, 5xx) with exponential backoff.
    """
    import asyncio

    system = resolve_prompt("extract")
    blocks = _build_blocks(raw)
    used_model = model or effective_setting("anthropic_model", settings.anthropic_model)

    user_repr = json.dumps(blocks, default=str, sort_keys=True)
    key = cache_key(
        used_model,
        system,
        user_repr,
        extras={"max_tokens": 16000, "node": "extract"},
    )
    cached = cache_get(key)
    if cached is not None:
        return parse_json_loose(cached.get("response", ""))

    client = _get_client()

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            msg = await client.messages.create(
                model=used_model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": blocks}],
            )
            text = "".join(block.text for block in msg.content if getattr(block, "type", None) == "text")
            cache_put(key, {"model": used_model, "response": text})
            return parse_json_loose(text)
        except anthropic.RateLimitError as e:
            last_err = e
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
        except anthropic.APIStatusError as e:
            last_err = e
            if e.status_code >= 500 and attempt < max_retries:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            raise
        except Exception:
            raise
    raise last_err or RuntimeError("extract_from_email failed after retries")
