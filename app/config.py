from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CareFlow Backend"
    environment: str = "local"
    auto_create_schema: bool = True
    database_url: str = "sqlite+aiosqlite:///./careflow.db"
    redis_url: str | None = None
    transcript_ttl_seconds: int = Field(default=1800, ge=60, le=86_400)
    max_chunk_chars: int = Field(default=2000, ge=100, le=10_000)
    note_generator_mode: Literal["deterministic", "anthropic"] = "deterministic"
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_version: str = "2023-06-01"
    anthropic_max_tokens: int = Field(default=1600, ge=256, le=8192)
    llm_timeout_seconds: float = Field(default=60.0, ge=1.0, le=120.0)
    speech_recognition_mode: Literal["disabled", "faster_whisper"] = "disabled"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = Field(default=5, ge=1, le=10)
    speech_max_audio_bytes: int = Field(default=10_000_000, ge=1024, le=50_000_000)
    speech_max_duration_seconds: float = Field(default=45.0, ge=1.0, le=300.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
