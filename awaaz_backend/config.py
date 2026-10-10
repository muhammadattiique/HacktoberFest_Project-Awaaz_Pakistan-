import os
from pathlib import Path
from typing import List, Union, Any
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration for Awaaz Pakistan.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Awaaz Pakistan"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api"

    # Audio Processing & Whisper
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    UPLOAD_MAX_BYTES: int = 25 * 1024 * 1024  # 25MB limit
    AUDIO_MIN_DURATION_SECONDS: float = 0.5
    AUDIO_MAX_DURATION_SECONDS: float = 120.0

    # Local Ollama LLM
    OLLAMA_MODEL: str = "qwen2.5:1.5b-instruct"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_TIMEOUT: float = 30.0

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./awaaz.db"

    # Reference rate list path
    RATE_LIST_PATH: str = str(Path(__file__).parent / "rate-list.json")

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    # Administrative portal security.
    # The React admin portal sends this value in the `X-API-Key` header.
    # Set AWAAZ_ADMIN_API_KEY (preferred) or ADMIN_API_KEY in the environment.
    # The default is the documented DEMO key - override it in production.
    ADMIN_API_KEY: str = Field(
        default="awaaz-admin-2024",
        validation_alias=AliasChoices("AWAAZ_ADMIN_API_KEY", "ADMIN_API_KEY"),
        description="Shared secret required for administrative endpoints.",
    )

    @field_validator("ADMIN_API_KEY", mode="before")
    @classmethod
    def assemble_admin_api_key(cls, v: Any) -> str:
        if isinstance(v, str) and v.strip():
            return v.strip()
        return "awaaz-admin-2024"

    # Official Placeholders (Required local context)
    # NOTE: These are placeholder numbers for demo/hackathon purposes.
    # VERIFY BEFORE PRODUCTION: Ensure official clearance from ICT/Punjab gov before live deployment.
    DISTRICT_HELPLINE_ICT: str = "051-9108194"  # VERIFY BEFORE PRODUCTION: ICT Admin complaint cell
    DISTRICT_HELPLINE_RAWALPINDI: str = "051-9292514"  # VERIFY BEFORE PRODUCTION: Rawalpindi DC office
    PERA_ENFORCEMENT_HELPLINE: str = "1717"  # VERIFY BEFORE PRODUCTION: Punjab Enforcement & Regulatory Authority
    PFA_FOOD_SAFETY_HELPLINE: str = "1223"  # VERIFY BEFORE PRODUCTION: Punjab Food Authority toll-free
    CDA_MUNICIPAL_HELPLINE: str = "1819"  # VERIFY BEFORE PRODUCTION: Capital Development Authority
    WASA_RAWALPINDI_HELPLINE: str = "1334"  # VERIFY BEFORE PRODUCTION: WASA Rawalpindi
    LEGAL_FINE_MIN_PKR: int = 5000  # VERIFY BEFORE PRODUCTION: Price Control & Prevention of Profiteering Act min fine
    LEGAL_FINE_MAX_PKR: int = 100000  # VERIFY BEFORE PRODUCTION: Maximum fine for repeat hoarding/overpricing

    # Thresholds
    OVERCHARGE_ALERT_THRESHOLD_PCT: float = 20.0  # Alert if item price exceeds official rate by 20%
    HIGH_SEVERITY_THRESHOLD_PCT: float = 50.0  # Urgent enforcement dispatch recommended

    @field_validator("DEBUG", mode="before")
    @classmethod
    def assemble_debug(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            norm = v.lower().strip()
            if norm in ("true", "1", "yes", "debug", "on"):
                return True
            return False
        return bool(v)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]


settings = Settings()
