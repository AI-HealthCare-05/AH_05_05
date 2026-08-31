from typing import Protocol

from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatAnswerResult,
    ChatClassificationResult,
    ChatInputRiskResult,
)
from ai_worker.schemas.guide import RecoveryGuideResult
from ai_worker.schemas.guideline import (
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.knowledge import KnowledgeRetrievalResult
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationGuideLookup,
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


class ChatInputRiskClassifier(Protocol):
    def assess(
        self,
        question: str,
    ) -> ChatInputRiskResult: ...


class ChatQuestionClassifier(Protocol):
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult: ...


class ChatAnswerGenerator(Protocol):
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult: ...


class ChatOutputSafetyValidator(Protocol):
    async def validate(
        self,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> SafetyResult: ...


class ActiveIntakeContextProvider(Protocol):
    async def get_active_context(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> ActiveIntakeContext: ...


class MedicationGuideRepository(Protocol):
    async def find_by_name(
        self,
        product_name: str,
    ) -> MedicationGuideLookup: ...


class InteractionRuleRepository(Protocol):
    async def find_approved_rules(
        self,
        *,
        context: ActiveIntakeContext,
    ) -> list[InteractionRuleFact]: ...


class MedicationKnowledgeRetriever(Protocol):
    async def search_with_diagnostics(
        self,
        *,
        question: str,
        medication_names: list[str],
        supplement_names: list[str],
        interaction_pair_keys: list[str],
        limit: int,
    ) -> KnowledgeRetrievalResult: ...


class MedicationAnswerGenerator(Protocol):
    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult: ...


class GroundedClaimValidator(Protocol):
    async def validate(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult: ...
