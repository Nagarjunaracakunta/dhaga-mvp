"""All configuration in one place. Values come from environment variables or .env."""
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # ---- Connections (leave blank to run on local demo data / fallback mode) ----
    supabase_url: str = ""
    # Server-side key: the new "sb_secret_..." key or the legacy service_role JWT
    supabase_service_key: str = Field("", validation_alias=AliasChoices("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY",
                                                                        "supabase_service_key"))
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""          # used when anthropic_api_key is blank
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    knowledge_bucket: str = "knowledge"

    # ---- Data source for CX: "supabase", "demo", or "auto" (supabase if configured) ----
    cx_data_source: str = "auto"
    # Data source for Returns: "supabase", "csv" (demo files in data/), or "auto" (supabase if configured)
    returns_data_source: str = "auto"
    # Pretend today is this date when computing delays (useful with synthetic data)
    cx_today: Optional[date] = None

    # ---- Models ----
    model_fast: str = "claude-haiku-4-5"            # classify + check, temperature 0
    model_strong: str = "claude-opus-5-5"           # CX draft replies, effort low
    model_returns_strong: str = "claude-sonnet-5-5"  # returns escalation + brief writer (accepts temp 0)
    draft_effort: str = "low"
    llm_timeout_s: float = 60.0

    # USD per 1M tokens: (input, output)
    price_per_mtok: dict = {
        "claude-haiku-4-5": (1.00, 5.00),
        "claude-opus-5-5": (4.00, 20.00),
        "claude-sonnet-5-5": (2.00, 10.00),
    }

    # ---- CX rules (tune here, not in code) ----
    min_intent_confidence: float = 0.70
    delay_priority_days: int = 5
    return_window_days: int = 7          # confirm against the Returns Policy PDF
    max_draft_attempts: int = 2          # first draft + one regeneration

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def llm_provider(self) -> Optional[str]:
        if self.anthropic_api_key:
            return "anthropic"
        if self.openrouter_api_key:
            return "openrouter"
        return None

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider is not None

    @property
    def returns_mode(self) -> str:
        if self.returns_data_source == "auto":
            return "supabase" if self.supabase_configured else "csv"
        return self.returns_data_source

    @property
    def cx_mode(self) -> str:
        if self.cx_data_source == "auto":
            return "supabase" if self.supabase_configured else "demo"
        return self.cx_data_source


@lru_cache
def get_settings() -> Settings:
    return Settings()
