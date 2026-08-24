from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
)

_SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"


class KnowledgeSourceTarget(StrEnum):
    MYSQL = "MYSQL"
    QDRANT = "QDRANT"
    QDRANT_DISABLED_UNTIL_VERIFIED = "QDRANT_DISABLED_UNTIL_VERIFIED"


class KnowledgeProcessingStatus(StrEnum):
    STRUCTURED_SOURCE = "STRUCTURED_SOURCE"
    TEXT_EXTRACTABLE = "TEXT_EXTRACTABLE"
    OCR_REQUIRED = "OCR_REQUIRED"


class KnowledgeSourceConfig(BaseModel):
    source_id: str = Field(
        min_length=1,
        pattern=_SAFE_IDENTIFIER_PATTERN,
    )
    provider: str = Field(min_length=1)
    access_scope: KnowledgeAccessScope
    target: KnowledgeSourceTarget
    raw_path: Path
    document_type: KnowledgeDocumentType | None = None
    note: str | None = None

    @model_validator(mode="after")
    def require_document_type_for_vector_source(self):
        if self.target != KnowledgeSourceTarget.MYSQL and self.document_type is None:
            raise ValueError("Qdrant 지식 출처에는 document_type이 필요합니다.")
        return self

    @property
    def index_eligible(self) -> bool:
        return self.target == KnowledgeSourceTarget.QDRANT


class KnowledgeSourcesManifest(BaseModel):
    schema_version: str = Field(min_length=1)
    sources: list[KnowledgeSourceConfig]

    @model_validator(mode="after")
    def require_unique_source_ids(self):
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_id는 출처 매니페스트에서 중복될 수 없습니다.")
        return self


class KnowledgePilotEntry(BaseModel):
    source_id: str = Field(
        min_length=1,
        pattern=_SAFE_IDENTIFIER_PATTERN,
    )
    document_id: str = Field(
        min_length=1,
        pattern=_SAFE_IDENTIFIER_PATTERN,
    )
    repo_path: Path
    processing_status: KnowledgeProcessingStatus
    selection_reason: str = Field(min_length=1)


class KnowledgePilotManifest(BaseModel):
    policy: str = Field(min_length=1)
    pilots: list[KnowledgePilotEntry]

    @model_validator(mode="after")
    def require_unique_document_ids(self):
        document_ids = [pilot.document_id for pilot in self.pilots]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document_id는 파일럿 매니페스트에서 중복될 수 없습니다.")
        return self
