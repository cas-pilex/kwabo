"""Runtime-override laag voor AI-prompts en instellingen.

De prompt-.txt-bestanden en config.py blijven de default/fallback. Een
DB-override (PromptVersion / AppConfigOverride) wint als die bestaat. Alles wordt
vers-per-call gelezen zodat een wijziging in de Configuratie-UI direct effect
heeft bij de eerstvolgende (her-)verwerking — geen redeploy of herstart nodig.

Volume is laag (één e-mail per keer), dus een DB-query per call is verwaarloosbaar.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from kwabo.config import settings
from kwabo.db import session as _db_session
from kwabo.db.models import AppConfigOverride, PromptVersion


def _engine():
    # Dynamisch i.p.v. `from ... import engine`: config_store wordt vroeg (via
    # de graph-nodes) geïmporteerd, en de test-suite rebindt db.session.engine
    # naar de test-DB ná die import. Vers uitlezen pakt de juiste engine.
    return _db_session.engine

# --- Prompts ---------------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# key -> (bestand, UI-label, korte uitleg "waar kijkt de AI naar")
PROMPT_FILES: dict[str, Path] = {
    "classify": PROMPTS_DIR / "classify.txt",
    "extract": PROMPTS_DIR / "extract_v2.txt",
}

PROMPT_META: dict[str, dict[str, str]] = {
    "classify": {
        "label": "E-mail classificatie",
        "beschrijving": (
            "Bepaalt of een binnenkomende e-mail een inkooporder/bestelling is "
            "die verwerkt moet worden. Kijkt naar afzender, onderwerp, body en "
            "de eerste tekst van elke bijlage. Output: JSON {is_order, reden, "
            "confidence}."
        ),
    },
    "extract": {
        "label": "Order-extractie",
        "beschrijving": (
            "Haalt de gestructureerde ordergegevens uit e-mail + PDF-bijlagen "
            "(artikelen, aantallen, eenheden, leverdata, klantnaam) met "
            "herkomst-metadata per veld. Ondersteunt meerdere orders per mail. "
            "Output: JSON-object of -array met {value, source, confidence, "
            "needs_review} per veld."
        ),
    },
}


def default_prompt_text(key: str) -> str:
    """De prompt zoals die in de repo staat (het .txt-bestand)."""
    return PROMPT_FILES[key].read_text(encoding="utf-8")


def resolve_prompt(key: str) -> str:
    """De effectieve prompt: actieve DB-override, anders het bestand.

    De file is de canonieke fallback (§design). Als de DB niet bereikbaar is of
    de override-tabel nog niet bestaat (bv. graph-node unit tests zonder DB, of
    een DB-outage in prod), valt de agent netjes terug op de meegeleverde prompt
    i.p.v. te crashen op elke e-mail.
    """
    try:
        with Session(_engine()) as s:
            row = s.exec(
                select(PromptVersion)
                .where(PromptVersion.prompt_key == key)
                .where(PromptVersion.is_active == True)  # noqa: E712
            ).first()
    except SQLAlchemyError:
        return default_prompt_text(key)
    if row is not None:
        return row.content
    return default_prompt_text(key)


# --- Instellingen ----------------------------------------------------------

# In de Configuratie-UI bewerkbare instellingen. `default` haalt de huidige
# config.py/env-waarde op; `type` stuurt parsing (JSON) + UI-widget.
EDITABLE_SETTINGS: list[dict[str, Any]] = [
    {
        "key": "anthropic_model",
        "label": "AI-model",
        "type": "string",
        "beschrijving": "Het Claude-model dat classify + extract gebruiken.",
        "default": lambda: settings.anthropic_model,
    },
    {
        "key": "llm_temperature",
        "label": "Temperature",
        "type": "number",
        "beschrijving": "0 = deterministisch. Hoger = meer variatie (afgeraden voor extractie).",
        "default": lambda: 0.0,
    },
    {
        "key": "nav2018_incoming_document_enabled",
        "label": "Bronbestand als inkomend document naar NAV (Functie 7)",
        "type": "bool",
        "beschrijving": "Alleen aanzetten zodra PLX_IncomingDocument in NAV gepubliceerd is.",
        "default": lambda: settings.nav2018_incoming_document_enabled,
    },
]

_EDITABLE_KEYS = {s["key"] for s in EDITABLE_SETTINGS}


def effective_setting(key: str, default: Any) -> Any:
    """Runtime-waarde: DB-override (JSON-decoded) of anders `default`.

    Valt terug op `default` (config.py/env) als de DB/override-tabel niet
    beschikbaar is — zelfde graceful-fallback als resolve_prompt().
    """
    try:
        with Session(_engine()) as s:
            row = s.exec(
                select(AppConfigOverride).where(AppConfigOverride.key == key)
            ).first()
    except SQLAlchemyError:
        return default
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (ValueError, TypeError):
        return row.value


# --- Pipeline-overzicht (read-only documentatie) ---------------------------

# Eén item per stap, in volgorde van graph/graph.py. Maakt zichtbaar "waar de
# AI/logica naar kijkt en hoe". `prompt_key` linkt een AI-stap aan de
# bewerkbare prompt; deterministische stappen hebben prompt_key=None.
PIPELINE_STEPS: list[dict[str, Any]] = [
    {
        "key": "intake",
        "label": "Intake",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Leest de e-mail + bijlagen in en normaliseert ze.",
        "input": "Ruwe e-mail (.eml) + bijlagen",
        "output": "Genormaliseerde OrderState",
        "bron": "graph/nodes/intake.py",
    },
    {
        "key": "classify",
        "label": "Classificatie",
        "type": "llm-prompt",
        "prompt_key": "classify",
        "beschrijving": PROMPT_META["classify"]["beschrijving"],
        "input": "Afzender, onderwerp, body, bijlage-previews",
        "output": "is_order + confidence",
        "bron": "graph/nodes/classify.py + prompts/classify.txt",
    },
    {
        "key": "extract",
        "label": "Order-extractie",
        "type": "llm-prompt",
        "prompt_key": "extract",
        "beschrijving": PROMPT_META["extract"]["beschrijving"],
        "input": "E-mail-envelop + PDF/Excel-bijlagen",
        "output": "Ordervelden met herkomst-metadata",
        "bron": "integrations/llm_extractor.py + prompts/extract_v2.txt",
    },
    {
        "key": "match_customer",
        "label": "Klant-matching",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Zoekt de NAV-klant op e-mail/alias/adres. Geen AI.",
        "input": "Afzender + afleveradres",
        "output": "NAV-klantnummer + confidence",
        "bron": "graph/nodes/match_customer.py",
    },
    {
        "key": "select_ship_to",
        "label": "Ship-to keuze",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Kiest het juiste leveradres (ship-to) via score op postcode/plaats.",
        "input": "Klant + leveradres",
        "output": "Ship-to-code",
        "bron": "graph/nodes/select_ship_to.py",
    },
    {
        "key": "match_articles",
        "label": "Artikel-matching",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Matcht klant-SKU's op Kwabo-artikelen (kruisverwijzing/fuzzy). Geen AI.",
        "input": "Geëxtraheerde orderregels",
        "output": "Kwabo-artikelnummers per regel",
        "bron": "graph/nodes/match_articles.py",
    },
    {
        "key": "apply_mixprijzen",
        "label": "Mixprijzen",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Past mix-/volumeprijs-eenheden toe waar van toepassing.",
        "input": "Gematchte regels + klant/artikel-config",
        "output": "Regels met juiste prijs-eenheid",
        "bron": "graph/nodes/apply_mixprijzen.py",
    },
    {
        "key": "compute_europallet",
        "label": "Europallet-telling",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Berekent het aantal europallets deterministisch.",
        "input": "Regels + pallet-kennis",
        "output": "Europallet-regel",
        "bron": "graph/nodes/compute_europallet.py",
    },
    {
        "key": "validate_prices",
        "label": "Prijs-validatie",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Valideert prijzen/afspraken en markeert afwijkingen.",
        "input": "Regels + prijsafspraken",
        "output": "Validatie-vlaggen",
        "bron": "graph/nodes/validate_prices.py",
    },
    {
        "key": "compose_order",
        "label": "Order samenstellen",
        "type": "deterministisch",
        "prompt_key": None,
        "beschrijving": "Stelt de definitieve NAV-order samen en logt de state.",
        "input": "Volledige OrderState",
        "output": "NAV-order-payload + order_log",
        "bron": "graph/nodes/compose_order.py",
    },
]
