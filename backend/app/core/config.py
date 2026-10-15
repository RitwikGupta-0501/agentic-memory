"""Application configuration settings."""

from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # FalkorDB Connection
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_password: str = ""

    # Backend Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

    # Multi-Tenancy Defaults
    default_tenant_id: str = "acme-payments"
    default_user_id: str = "alice_sre"

    # LLM Settings
    llm_provider: str = "mock"  # mock, openai, gemini, anthropic
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    # Embedding Settings
    embedding_provider: str = "mock"  # mock, gemini, openai, ollama
    embedding_dimension: int = 768
    embedding_model_name: str = "models/text-embedding-004"
    ollama_base_url: str = "http://localhost:11434"
    embedding_cache_size: int = 1024
    auto_reindex_on_model_change: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]


settings = Settings()
