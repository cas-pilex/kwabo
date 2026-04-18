"""Application configuration."""
from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    database_url: str = "sqlite:///./kwabo.db"
    navision_mode: str = "mock"
    email_mode: str = "file_drop"
    inbox_dir: str = "../data/inbox"
    processed_dir: str = "../data/processed"
    navision_mock_dir: str = "../data/navision_mock"
    langchain_tracing_v2: bool = False
    langchain_project: str = "kwabo-order-intake"
    log_level: str = "INFO"
    mail_mode: str = "log"  # log | smtp | graph
    llm_cache_mode: str = "on"
    llm_cache_dir: str = "../data/llm_cache"
    # "on" to mount /api/testing/* routes. Accepts KWABO_TEST_MODE or TEST_MODE.
    test_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("KWABO_TEST_MODE", "TEST_MODE", "test_mode"),
    )

    @property
    def inbox_path(self) -> Path:
        return Path(self.inbox_dir).resolve()

    @property
    def processed_path(self) -> Path:
        return Path(self.processed_dir).resolve()

    @property
    def navision_mock_path(self) -> Path:
        return Path(self.navision_mock_dir).resolve()


settings = Settings()
