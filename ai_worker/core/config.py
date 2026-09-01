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
    OPENAI_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    OPENAI_MAX_RETRIES: int = Field(default=2, ge=0)

    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: SecretStr | None = None
    LANGSMITH_PROJECT: str = "ai-health-medication-chat"
    LANGSMITH_ENVIRONMENT: str = "local"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_WORKSPACE_ID: str | None = None
    LANGSMITH_CAPTURE_CONTENT: bool = False
    LANGSMITH_HASH_SALT: SecretStr | None = None
    LANGSMITH_CLOSE_TIMEOUT_SECONDS: float = Field(
        default=2.0,
        gt=0,
    )
    RUN_LANGSMITH_INTEGRATION_TESTS: bool = False

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "public_guidelines_small_v1"
    KNOWLEDGE_QDRANT_COLLECTION: str = "medication_knowledge_full_v1"
    KNOWLEDGE_DATASET_VERSION: str = "knowledge-full-v1"
    INTERACTION_RULE_DATASET_VERSION: str = "interaction-pilot-v1"
    MEDICATION_SAFETY_RULE_DATASET_VERSION: str = "medication-safety-v1"
    QDRANT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    RAG_MIN_SIMILARITY_SCORE: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    RUN_OPENAI_INTEGRATION_TESTS: bool = False
