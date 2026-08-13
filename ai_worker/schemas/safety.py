#현재 환자 데이터와 공공데이터의 충돌 및 최종 답변 안전성 검사 결과를 담아두는 스키마

from pydantic import BaseModel, Field

from ai_worker.schemas.enums import ConflictStatus, SafetyStatus
from ai_worker.schemas.public_data import RetrievedPublicChunk


class ConflictCheckResult(BaseModel): #충돌 검사 결과
    status: ConflictStatus

    usable_public_chunks: list[RetrievedPublicChunk] = Field(
        default_factory=list
    )
    excluded_public_chunks: list[RetrievedPublicChunk] = Field(
        default_factory=list
    )

    reason: str | None = None


class SafetyResult(BaseModel): #최종 답변 안전성 검사 결과
    status: SafetyStatus
    reason_codes: list[str] = Field(default_factory=list)
    message: str | None = None