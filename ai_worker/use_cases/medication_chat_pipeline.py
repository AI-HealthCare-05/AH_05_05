"""의약품·영양제 채팅 UseCase 내부 단계 사이의 불변 전달 객체입니다."""

from dataclasses import dataclass

from ai_worker.schemas.knowledge import KnowledgeRetrievalResult, RetrievedKnowledgeChunk
from ai_worker.schemas.medication_chat import (
    InteractionRuleFact,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationGuideLookup,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationQuestionResolution,
    MedicationSearchExecutionPlan,
)


@dataclass(frozen=True)
class PreparedMedicationQuestion:
    """표현 정규화와 범위 판정을 마친 질문 단계의 출력입니다."""

    request: MedicationChatRequest
    resolution: MedicationQuestionResolution | None
    early_result: MedicationChatResult | None

    @property
    def question_for_planning(self) -> str:
        return self.request.question


@dataclass(frozen=True)
class MedicationEvidenceBundle:
    """규칙·RAG·제품 가이드 조회 뒤 결정론적 초안에 전달할 근거 묶음입니다."""

    query_plan: MedicationKnowledgeQueryPlan
    execution_plan: MedicationSearchExecutionPlan
    rules: tuple[InteractionRuleFact, ...]
    retrieval: KnowledgeRetrievalResult
    rag_unavailable: bool
    guide_lookup: MedicationGuideLookup
    answer_chunks: tuple[RetrievedKnowledgeChunk, ...]
    interaction_question: bool


@dataclass(frozen=True)
class MedicationChatDraft:
    """LLM 정제 전, 안전성 검증이 반드시 뒤따라야 하는 결정론적 초안입니다."""

    result: MedicationChatResult
    resolution: MedicationQuestionResolution | None

    @property
    def safety_validation_required(self) -> bool:
        return True
