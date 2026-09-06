import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeStudyPopulation,
)

_SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeSourceTarget(StrEnum):
    MYSQL = "MYSQL"
    QDRANT = "QDRANT"
    QDRANT_DISABLED_UNTIL_VERIFIED = "QDRANT_DISABLED_UNTIL_VERIFIED"


class KnowledgeProcessingStatus(StrEnum):
    STRUCTURED_SOURCE = "STRUCTURED_SOURCE"
    TEXT_EXTRACTABLE = "TEXT_EXTRACTABLE"
    OCR_REQUIRED = "OCR_REQUIRED"


class KnowledgeManualReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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
    manual_review_status: KnowledgeManualReviewStatus = KnowledgeManualReviewStatus.PENDING
    title: str | None = None
    source_url: str | None = None
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1900, le=2100)
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    evidence_level: KnowledgeEvidenceLevel = KnowledgeEvidenceLevel.UNKNOWN
    study_population: KnowledgeStudyPopulation = KnowledgeStudyPopulation.UNKNOWN
    verified_text_replacements: dict[str, str] = Field(default_factory=dict)
    verified_section_headings: list[str] = Field(default_factory=list)
    approved_chunk_content_hashes: list[str] = Field(default_factory=list)

    @field_validator("verified_section_headings")
    @classmethod
    def normalize_verified_section_headings(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized: list[str] = []
        for value in values:
            heading = value.strip()
            if not heading:
                raise ValueError("검증된 섹션 제목은 비어 있을 수 없습니다.")
            if heading not in normalized:
                normalized.append(heading)
        return normalized

    @field_validator("approved_chunk_content_hashes")
    @classmethod
    def validate_approved_chunk_content_hashes(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized: list[str] = []
        for value in values:
            content_hash = value.strip().lower()
            if not _SHA256_PATTERN.fullmatch(content_hash):
                raise ValueError("수동 승인 청크 content_hash는 64자리 SHA-256이어야 합니다.")
            if content_hash not in normalized:
                normalized.append(content_hash)
        return normalized

    @model_validator(mode="after")
    def require_valid_verified_text_replacements(self):
        for source, replacement in self.verified_text_replacements.items():
            if not source.strip() or not replacement.strip():
                raise ValueError("검증된 텍스트 치환의 원문과 대체문은 비어 있을 수 없습니다.")
            if source == replacement:
                raise ValueError("검증된 텍스트 치환의 원문과 대체문은 달라야 합니다.")
        return self


class KnowledgePilotManifest(BaseModel):
    policy: str = Field(min_length=1)
    pilots: list[KnowledgePilotEntry]

    @model_validator(mode="after")
    def require_unique_document_ids(self):
        document_ids = [pilot.document_id for pilot in self.pilots]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document_id는 파일럿 매니페스트에서 중복될 수 없습니다.")
        return self
