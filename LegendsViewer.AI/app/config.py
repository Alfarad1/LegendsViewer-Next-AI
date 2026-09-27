from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # auto | openai | anthropic  (auto: sk-ant- / anthropic.com → anthropic)
    llm_provider: str = "auto"

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = "ollama"
    openai_model: str = "gpt-4o-mini"

    lv_api_base_url: str = "http://localhost:15421"

    ai_host: str = "0.0.0.0"
    ai_port: int = 15423

    cors_origins: str = "*"

    # 0 = log full tool args/results and replies (no truncation)
    ai_log_max_chars: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
