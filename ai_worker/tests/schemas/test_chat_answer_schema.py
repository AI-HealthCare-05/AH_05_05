import pytest
from pydantic import ValidationError

from ai_worker.schemas.chat import (
    ChatAnswerResult,
    ChatAnswerSupplement,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
    SafetyStatus,
)


def test_chat_answer_supplement_accepts_allowed_fields() -> None:
    supplement = ChatAnswerSupplement(
        general_response=["안녕하세요. 무엇을 도와드릴까요?"],
        public_information=["공공자료에 따른 추가 설명입니다."],
        lifestyle_guidance=["무리하지 말고 충분히 쉬세요."],
    )

    assert supplement.general_response == ["안녕하세요. 무엇을 도와드릴까요?"]
    assert supplement.public_information == ["공공자료에 따른 추가 설명입니다."]
    assert supplement.lifestyle_guidance == ["무리하지 말고 충분히 쉬세요."]


def test_chat_answer_supplement_rejects_patient_fact_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="medication_guide",
    ):
        ChatAnswerSupplement.model_validate(
            {
                "general_response": [],
                "public_information": [],
                "lifestyle_guidance": [],
                "medication_guide": ["아스피린 복용을 중단하세요."],
            }
        )


def test_chat_answer_result_tracks_versions_and_ai_label() -> None:
    result = ChatAnswerResult(
        request_id="chat-request-1",
        care_episode_id=100,
        answer=("환자 확정정보를 기준으로 안내합니다."),
        intent=ChatIntent.LIFESTYLE,
        route=ChatRoute.PATIENT_AND_RAG,
        risk_level=ChatRiskLevel.CAUTION,
        safety_status=SafetyStatus.SAFE,
        patient_context_hash="a" * 64,
        model_name="gpt-4o-mini",
        model_version=None,
        prompt_version="chat-answer-prompt-v1",
        schema_version="chat-answer-result-v2",
    )

    assert result.lifestyle_guidance_label == ("AI 생성 일반 안내")
    assert result.patient_context_hash == "a" * 64
    assert result.model_name == "gpt-4o-mini"
    assert result.prompt_version == ("chat-answer-prompt-v1")
    assert result.schema_version == ("chat-answer-result-v2")


def test_chat_answer_result_tracks_clarification_state() -> None:
    result = ChatAnswerResult(
        request_id="clarification-request-1",
        care_episode_id=100,
        answer="질문을 조금 더 구체적으로 알려주세요.",
        intent=ChatIntent.GENERAL,
        route=None,
        risk_level=ChatRiskLevel.CAUTION,
        needs_clarification=True,
        safety_status=SafetyStatus.RESTRICTED,
        patient_context_hash="a" * 64,
        model_name="rule-based-clarification",
        prompt_version="chat-clarification-v1",
        schema_version="chat-answer-result-v2",
    )

    assert result.needs_clarification is True


@pytest.mark.parametrize(
    ("route", "needs_clarification"),
    [
        (None, False),
        (ChatRoute.PATIENT_ONLY, True),
    ],
)
def test_chat_answer_result_rejects_inconsistent_clarification_state(
    route: ChatRoute | None,
    needs_clarification: bool,
) -> None:
    with pytest.raises(ValidationError, match="명확화"):
        ChatAnswerResult(
            request_id="clarification-request-1",
            care_episode_id=100,
            answer="테스트 답변",
            intent=ChatIntent.GENERAL,
            route=route,
            risk_level=ChatRiskLevel.CAUTION,
            needs_clarification=needs_clarification,
            safety_status=SafetyStatus.RESTRICTED,
            patient_context_hash="a" * 64,
            model_name="rule-based",
            prompt_version="chat-test-v1",
            schema_version="chat-answer-result-v2",
        )


def test_chat_answer_result_rejects_invalid_ai_label() -> None:
    with pytest.raises(ValidationError):
        ChatAnswerResult(
            request_id="chat-request-1",
            care_episode_id=100,
            answer="테스트 답변",
            intent=ChatIntent.GENERAL,
            route=ChatRoute.GENERAL_GUIDANCE,
            risk_level=ChatRiskLevel.LOW,
            lifestyle_guidance_label=("공공자료 기반 안내"),
            safety_status=SafetyStatus.SAFE,
            patient_context_hash="a" * 64,
            model_name="gpt-4o-mini",
            prompt_version="chat-answer-prompt-v1",
            schema_version="chat-answer-result-v1",
        )


def test_chat_answer_result_rejects_invalid_context_hash() -> None:
    with pytest.raises(
        ValidationError,
        match="patient_context_hash",
    ):
        ChatAnswerResult(
            request_id="chat-request-1",
            care_episode_id=100,
            answer="테스트 답변",
            intent=ChatIntent.GENERAL,
            route=ChatRoute.GENERAL_GUIDANCE,
            risk_level=ChatRiskLevel.LOW,
            safety_status=SafetyStatus.SAFE,
            patient_context_hash="invalid-hash",
            model_name="gpt-4o-mini",
            prompt_version="chat-answer-prompt-v1",
            schema_version="chat-answer-result-v1",
        )
