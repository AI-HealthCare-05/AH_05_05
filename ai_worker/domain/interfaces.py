from typing import Protocol

from ai_worker.schemas.guide import RecoveryGuideResult
from ai_worker.schemas.guideline import (
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.safety import (
    ConflictCheckResult,
    SafetyResult,
)


class PatientContextProvider(Protocol):
    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext: ...


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]: ...

    async def embed_query(
        self,
        query: str,
    ) -> list[float]: ...


class GuidelineRetriever(Protocol):
    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]: ...


class GuidelineConflictResolver(Protocol):
    async def resolve(
        self,
        patient_context: PatientContext,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ConflictCheckResult: ...


class GuideGenerator(Protocol):
    async def generate(
        self,
        patient_context: PatientContext,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> RecoveryGuideResult: ...


class OutputSafetyValidator(Protocol):
    async def validate(
        self,
        patient_context: PatientContext,
        result: RecoveryGuideResult,
    ) -> SafetyResult: ...
