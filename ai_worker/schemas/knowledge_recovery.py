import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ai_worker.schemas.knowledge import KnowledgeAccessScope

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeRecoveryChunkStatus(StrEnum):
    PENDING = "PENDING"


class KnowledgeOcrManifestOrigin(StrEnum):
    CATALOG = "CATALOG"
    DYNAMIC = "DYNAMIC"


class KnowledgePendingChunkRecoveryTarget(BaseModel):
    chunk_id: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    status: KnowledgeRecoveryChunkStatus

    @field_validator("page_end")
    @classmethod
    def require_valid_page_range(cls, value: int, info) -> int:
        page_start = info.data.get("page_start")
        if isinstance(page_start, int) and value < page_start:
            raise ValueError("page_end는 page_start보다 작을 수 없습니다.")
        return value


class PartialChunkRecoveryEntry(BaseModel):
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    repo_path: Path
    source_sha256: str
    approved_content_hashes: list[str] = Field(default_factory=list)
    pending_chunks: list[KnowledgePendingChunkRecoveryTarget] = Field(min_length=1)

    @field_validator("source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("source_sha256은 64자리 SHA-256이어야 합니다.")
        return normalized

    @field_validator("approved_content_hashes")
    @classmethod
    def validate_approved_content_hashes(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            content_hash = value.strip().lower()
            if not _SHA256_PATTERN.fullmatch(content_hash):
                raise ValueError("approved_content_hashes는 64자리 SHA-256이어야 합니다.")
            if content_hash not in normalized:
                normalized.append(content_hash)
        return normalized


class KnowledgeOcrManifestEntry(BaseModel):
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    repo_path: Path
    source_sha256: str
    origin: KnowledgeOcrManifestOrigin
    access_scope: KnowledgeAccessScope | None = None

    @field_validator("source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("source_sha256은 64자리 SHA-256이어야 합니다.")
        return normalized


class KnowledgeRecoveryManifestResult(BaseModel):
    partial_entries: list[PartialChunkRecoveryEntry]
    ocr_entries: list[KnowledgeOcrManifestEntry]

    @property
    def partial_document_count(self) -> int:
        return len(self.partial_entries)

    @property
    def pending_chunk_count(self) -> int:
        return sum(len(entry.pending_chunks) for entry in self.partial_entries)

    @property
    def ocr_document_count(self) -> int:
        return len(self.ocr_entries)
