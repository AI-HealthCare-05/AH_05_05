from datetime import date

import pytest
from pydantic import ValidationError

from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole, SafetyStatus
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    MedicationAnswerFallbackReason,
    MedicationAnswerGenerationObservation,
    MedicationAnswerGenerationOutcome,
    MedicationAnswerRewriteStatus,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationSearchExecutionObservation,
)


def test_general_drug_question_accepts_missing_care_episode() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        care_episode_id=None,
        question=" 타이레놀은 어떤 약인가요? ",
        history=[
            ChatHistoryMessage(
                role=ChatRole.USER,
                content="해열진통제가 궁금해요.",
            )
        ],
    )

    assert request.care_episode_id is None
    assert request.question == "타이레놀은 어떤 약인가요?"


def test_medication_chat_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError, match="string_too_short"):
        MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="  ",
        )


def test_active_intake_context_preserves_confirmed_medication() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        preferred_care_episode_id=100,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="아스피린",
                dose="1정",
                times_per_day=1,
                days=7,
                prescribed_at=date(2026, 8, 25),
            )
        ],
    )

    assert context.medications[0].name == "아스피린"
    assert context.medications[0].care_episode_id == 100


def test_medication_chat_result_keeps_grounded_source_identifiers() -> None:
    result = MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer="확인된 제품 안내를 설명드립니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        sources=[
            MedicationChatSource(
                kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                title="e약은요 · 제품 사용 안내",
                medication_guide_id=12,
                organization="식품의약품안전처",
            )
        ],
        prompt_version="medication-chat-v1",
        schema_version="medication-chat-result-v1",
    )

    assert result.sources[0].medication_guide_id == 12
    assert result.sources[0].kind == MedicationChatSourceKind.MEDICATION_GUIDE


def test_medication_chat_result_excludes_internal_search_observation_from_api_dump() -> None:
    result = MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer="확인된 근거를 설명드립니다.",
        route=MedicationChatRoute.GENERAL_GUIDANCE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="medication-chat-v1",
        schema_version="medication-chat-result-v1",
        search_observation=MedicationSearchExecutionObservation(
            query_plan=MedicationKnowledgeQueryPlan(
                original_query="질문",
                expanded_query="검색 질문",
            ),
            query_plan_hash="a" * 64,
            execution_plan_hash="b" * 64,
        ),
    )

    assert result.search_observation is not None
    assert "search_observation" not in result.model_dump(mode="json")


def test_generation_outcome_keeps_observation_out_of_chat_result() -> None:
    result = MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer="안전한 초안입니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="medication-chat-v1",
        schema_version="medication-chat-result-v1",
    )
    outcome = MedicationAnswerGenerationOutcome(
        result=result,
        observation=MedicationAnswerGenerationObservation(
            status=MedicationAnswerRewriteStatus.DRAFT_FALLBACK,
            fallback_used=True,
            fallback_reason=(
                MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT
            ),
            draft_answer_hash="a" * 64,
            generated_answer_hash="b" * 64,
        ),
    )

    assert "observation" not in outcome.result.model_dump()
    assert outcome.observation.fallback_used is True


def test_generation_observation_validates_hash_and_status_contract() -> None:
    with pytest.raises(ValidationError, match="draft_answer_hash"):
        MedicationAnswerGenerationObservation(
            status=MedicationAnswerRewriteStatus.REWRITTEN,
            fallback_used=False,
            draft_answer_hash="invalid",
            generated_answer_hash="b" * 64,
        )

    with pytest.raises(ValidationError, match="fallback_reason"):
        MedicationAnswerGenerationObservation(
            status=MedicationAnswerRewriteStatus.DRAFT_FALLBACK,
            fallback_used=True,
            draft_answer_hash="a" * 64,
            generated_answer_hash="b" * 64,
        )

    with pytest.raises(ValidationError, match="fallback_reason"):
        MedicationAnswerGenerationObservation(
            status=MedicationAnswerRewriteStatus.REWRITTEN,
            fallback_used=False,
            fallback_reason=MedicationAnswerFallbackReason.CLIENT_ERROR,
            draft_answer_hash="a" * 64,
            generated_answer_hash="b" * 64,
        )
