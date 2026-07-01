"""Configuratie-endpoints: AI-prompts bekijken/bewerken/terugrollen + instellingen.

Voedt de Configuratie-pagina in de frontend. Alle schrijf-acties nemen direct
effect: de resolver in config_store leest prompts/instellingen vers-per-call, dus
een volgende (her-)verwerking gebruikt de nieuwe waarde zonder redeploy.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from kwabo.config_store import (
    EDITABLE_SETTINGS,
    PIPELINE_STEPS,
    PROMPT_FILES,
    PROMPT_META,
    default_prompt_text,
)
from kwabo.db import session as _db_session
from kwabo.db.models import AppConfigOverride, PromptVersion
from kwabo.utils import utcnow

router = APIRouter(prefix="/api/config", tags=["config"])


def _engine():
    # Dynamisch uitlezen (i.p.v. import-time binding) zodat de test-suite, die
    # db.session.engine naar de test-DB rebindt, dezelfde engine ziet als de
    # config_store-resolver. Voorkomt lezer/schrijver-splitsing tussen tests.
    return _db_session.engine


# ---------- schemas ----------


class PromptOut(BaseModel):
    key: str
    label: str
    beschrijving: str
    content: str  # effectieve prompt (override of bestand)
    default_content: str  # het .txt-bestand
    is_overridden: bool
    active_version_id: int | None = None
    updated_at: datetime | None = None


class PromptVersionOut(BaseModel):
    id: int
    prompt_key: str
    content: str
    note: str | None
    is_active: bool
    source: str
    created_by: str | None
    created_at: datetime


class PromptSaveIn(BaseModel):
    content: str
    note: str | None = None


class SettingOut(BaseModel):
    key: str
    label: str
    beschrijving: str
    type: str
    value: Any
    default: Any
    is_overridden: bool


# ---------- helpers ----------


def _active_version(s: Session, key: str) -> PromptVersion | None:
    return s.exec(
        select(PromptVersion)
        .where(PromptVersion.prompt_key == key)
        .where(PromptVersion.is_active == True)  # noqa: E712
    ).first()


def _save_version(
    s: Session, key: str, content: str, source: str, note: str | None = None
) -> PromptVersion:
    """Deactiveer de huidige actieve versie en voeg een nieuwe actieve toe."""
    current = _active_version(s, key)
    if current is not None:
        current.is_active = False
        s.add(current)
    row = PromptVersion(
        prompt_key=key, content=content, note=note, is_active=True, source=source
    )
    s.add(row)
    s.commit()
    s.refresh(row)
    return row


def _prompt_out(s: Session, key: str) -> PromptOut:
    active = _active_version(s, key)
    default = default_prompt_text(key)
    return PromptOut(
        key=key,
        label=PROMPT_META[key]["label"],
        beschrijving=PROMPT_META[key]["beschrijving"],
        content=active.content if active is not None else default,
        default_content=default,
        is_overridden=active is not None,
        active_version_id=active.id if active is not None else None,
        updated_at=active.created_at if active is not None else None,
    )


def _require_known_key(key: str) -> None:
    if key not in PROMPT_FILES:
        raise HTTPException(404, f"Onbekende prompt '{key}'")


# ---------- prompts ----------


@router.get("/prompts", response_model=list[PromptOut])
def list_prompts() -> list[PromptOut]:
    with Session(_engine()) as s:
        return [_prompt_out(s, key) for key in PROMPT_FILES]


@router.get("/prompts/{key}/versions", response_model=list[PromptVersionOut])
def list_versions(key: str) -> list[PromptVersionOut]:
    _require_known_key(key)
    with Session(_engine()) as s:
        rows = s.exec(
            select(PromptVersion)
            .where(PromptVersion.prompt_key == key)
            .order_by(PromptVersion.created_at.desc())
        ).all()
        return [PromptVersionOut(**r.model_dump()) for r in rows]


@router.put("/prompts/{key}", response_model=PromptOut)
def save_prompt(key: str, body: PromptSaveIn) -> PromptOut:
    _require_known_key(key)
    if not (body.content or "").strip():
        raise HTTPException(400, "Prompt mag niet leeg zijn")
    with Session(_engine()) as s:
        _save_version(s, key, body.content, source="edit", note=body.note)
        return _prompt_out(s, key)


@router.post("/prompts/{key}/rollback/{version_id}", response_model=PromptOut)
def rollback_prompt(key: str, version_id: int) -> PromptOut:
    _require_known_key(key)
    with Session(_engine()) as s:
        target = s.get(PromptVersion, version_id)
        if target is None or target.prompt_key != key:
            raise HTTPException(404, "Versie niet gevonden")
        _save_version(
            s, key, target.content, source="rollback", note=f"teruggerold naar v{version_id}"
        )
        return _prompt_out(s, key)


@router.post("/prompts/{key}/reset", response_model=PromptOut)
def reset_prompt(key: str) -> PromptOut:
    """Zet de prompt terug op de repo-default (het .txt-bestand)."""
    _require_known_key(key)
    with Session(_engine()) as s:
        _save_version(
            s, key, default_prompt_text(key), source="reset", note="hersteld naar standaard"
        )
        return _prompt_out(s, key)


# ---------- instellingen ----------


@router.get("/settings", response_model=list[SettingOut])
def get_settings() -> list[SettingOut]:
    out: list[SettingOut] = []
    with Session(_engine()) as s:
        for spec in EDITABLE_SETTINGS:
            key = spec["key"]
            default = spec["default"]()
            override = s.exec(
                select(AppConfigOverride).where(AppConfigOverride.key == key)
            ).first()
            if override is not None:
                try:
                    value = json.loads(override.value)
                except (ValueError, TypeError):
                    value = override.value
            else:
                value = default
            out.append(
                SettingOut(
                    key=key,
                    label=spec["label"],
                    beschrijving=spec["beschrijving"],
                    type=spec["type"],
                    value=value,
                    default=default,
                    is_overridden=override is not None,
                )
            )
    return out


@router.put("/settings", response_model=list[SettingOut])
def update_settings(body: dict[str, Any]) -> list[SettingOut]:
    valid_keys = {spec["key"] for spec in EDITABLE_SETTINGS}
    unknown = set(body) - valid_keys
    if unknown:
        raise HTTPException(400, f"Onbekende instelling(en): {', '.join(sorted(unknown))}")
    with Session(_engine()) as s:
        for key, value in body.items():
            row = s.exec(
                select(AppConfigOverride).where(AppConfigOverride.key == key)
            ).first()
            encoded = json.dumps(value)
            if row is None:
                s.add(AppConfigOverride(key=key, value=encoded))
            else:
                row.value = encoded
                row.updated_at = utcnow()
                s.add(row)
        s.commit()
    return get_settings()


# ---------- pipeline-overzicht ----------


@router.get("/steps")
def get_steps() -> dict[str, Any]:
    return {"steps": PIPELINE_STEPS}
