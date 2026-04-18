"""Classify node — is this email an order?"""
from __future__ import annotations

from datetime import datetime

from kwabo.utils import utcnow
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from kwabo.graph.llm import get_llm
from kwabo.graph.state import OrderState
from kwabo.utils.json_parser import parse_json_loose
from kwabo.utils.logging import log

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "classify.txt"


async def classify_node(state: OrderState) -> OrderState:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    bijlagen = state.get("bijlagen") or []
    bijl_preview = ""
    for b in bijlagen:
        bijl_preview += f"\n--- {b.get('naam')} ---\n{(b.get('inhoud_tekst') or '')[:600]}\n"

    human = (
        f"E-mail van: {state.get('email_from')}\n"
        f"Onderwerp: {state.get('email_subject')}\n"
        f"Body:\n{(state.get('email_body') or '')[:2000]}\n\n"
        f"Bijlagen: {', '.join(b.get('naam', '') for b in bijlagen)}\n"
        f"Eerste 600 chars van elke bijlage:\n{bijl_preview[:3000]}"
    )

    llm = get_llm()
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    try:
        parsed = parse_json_loose(resp.content)
    except Exception as e:  # noqa: BLE001
        parsed = {"is_order": True, "reden": f"parse-fallback: {e}", "confidence": 0.3}

    stap = {
        "stap": "classify",
        "timestamp": utcnow().isoformat(),
        "beslissing": ("ORDER" if parsed.get("is_order") else "GEEN_ORDER")
        + f" (conf={parsed.get('confidence')})",
        "details": parsed,
    }
    log.info(
        "classify", email_id=state.get("email_id"), is_order=parsed.get("is_order"),
        confidence=parsed.get("confidence"), subject=(state.get("email_subject") or "")[:60],
    )
    steps = list(state.get("stappen_log") or [])
    steps.append(stap)
    return {
        **state,
        "is_order": bool(parsed.get("is_order")),
        "classificatie_reden": parsed.get("reden", ""),
        "classificatie_confidence": parsed.get("confidence"),
        "stappen_log": steps,
    }
