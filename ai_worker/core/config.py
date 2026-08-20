import zoneinfo
from dataclasses import field

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    TIMEZONE: zoneinfo.ZoneInfo = field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))

    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = Field(default=1536, gt=0)
    OPENAI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    OPENAI_MAX_RETRIES: int = Field(default=2, ge=0)

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "public_guidelines_small_v1"
    QDRANT_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    RAG_MIN_SIMILARITY_SCORE: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    RUN_OPENAI_INTEGRATION_TESTS: bool = False
