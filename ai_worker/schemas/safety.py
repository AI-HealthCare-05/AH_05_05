from pydantic import BaseModel, Field

from ai_worker.schemas.enums import ConflictStatus, SafetyStatus
from ai_worker.schemas.guideline import RetrievedGuidelineChunk


class ConflictCheckResult(BaseModel):
    status: ConflictStatus
    usable_guideline_chunks: list[RetrievedGuidelineChunk] = Field(
        default_factory=list,
    )
    excluded_guideline_chunks: list[RetrievedGuidelineChunk] = Field(
        default_factory=list,
    )
    reason: str | None = None


class SafetyResult(BaseModel):
    status: SafetyStatus
    reason_codes: list[str] = Field(default_factory=list)
    message: str | None = None
