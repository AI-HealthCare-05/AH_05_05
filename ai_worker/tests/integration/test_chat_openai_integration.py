from datetime import date

import pytest

from ai_worker.core.config import Config
from ai_worker.llm.generators.chat_answer_generator import (
    OpenAIChatAnswerGenerator,
)
from ai_worker.llm.generators.chat_question_classifier import (
    OpenAIChatQuestionClassifier,
)
from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
    ChatInputRiskResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
    SafetyStatus,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import (
    PatientContext,
    PatientInstruction,
    PatientMedication,
)

settings = Config()

live_test_enabled = settings.RUN_OPENAI_INTEGRATION_TESTS and settings.OPENAI_API_KEY is not None

pytestmark = pytest.mark.skipif(
    not live_test_enabled,
    reason=("실제 OpenAI 테스트는 RUN_OPENAI_INTEGRATION_TESTS=1과 OPENAI_API_KEY가 필요합니다."),
)


def build_request() -> ChatAnswerRequest:
    return ChatAnswerRequest(
        request_id="openai-chat-integration-1",
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        question=("뇌졸중 퇴원 후 안전하게 운동을 시작하는 방법을 공공 가이드라인과 함께 알려줘."),
    )


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=1,
        care_episode_id=100,
        confirmation_hash="a" * 64,
        diagnoses=["뇌졸중"],
        surgery="혈관 내 치료",
        discharge_date=date(2026, 8, 10),
        medications=[
            PatientMedication(
                medication_id=101,
                name="아스피린",
                dose="1정",
                times_per_day=1,
                note="아침 식후 복용",
                days=7,
            )
        ],
        instructions=[
            PatientInstruction(
                care_advice_id=201,
                content=("퇴원 후 무리한 활동은 피하세요."),
                display_order=1,
            )
        ],
    )


def build_guideline_chunk() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="openai-stroke-chunk-1",
        content=("퇴원 후 신체 활동은 환자의 상태를 고려하여 가벼운 활동부터 점진적으로 늘릴 수 있다."),
        similarity_score=0.91,
        metadata=GuidelineMetadata(
            dataset_key="PUBLIC_GUIDELINE",
            dataset_version="2020-v1",
            document_id="canadian-stroke-2020",
            title="Canadian Stroke Guideline",
            organization=("Heart and Stroke Foundation"),
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="LIFESTYLE",
            section_title="Physical Activity",
            page_number=10,
            source_url=("https://example.com/stroke-guideline"),
            license="CC BY-NC-ND 4.0",
        ),
    )


async def test_openai_classifies_lifestyle_question() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model=settings.OPENAI_CHAT_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )

    result = await classifier.classify(
        request=build_request(),
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        ),
    )

    assert isinstance(
        result,
        ChatClassificationResult,
    )
    assert result.intent == ChatIntent.LIFESTYLE
    assert result.route == ChatRoute.GENERAL_GUIDANCE
    assert result.normalized_query is None


async def test_openai_routes_interaction_question_to_knowledge_rag() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model=settings.OPENAI_CHAT_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )
    request = build_request().model_copy(
        update={"question": ("아스피린과 오메가3를 같이 먹을 때 알려진 상호작용 정보가 있어?")}
    )

    result = await classifier.classify(
        request=request,
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        ),
    )

    assert result.intent == ChatIntent.MEDICATION
    assert result.route == ChatRoute.PATIENT_AND_RAG
    assert result.normalized_query is not None
    assert result.risk_level in {
        ChatRiskLevel.LOW,
        ChatRiskLevel.CAUTION,
    }


async def test_openai_generates_structured_chat_answer() -> None:
    generator = OpenAIChatAnswerGenerator(
        model=settings.OPENAI_CHAT_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )

    classification = ChatClassificationResult(
        intent=ChatIntent.LIFESTYLE,
        route=ChatRoute.PATIENT_AND_RAG,
        risk_level=ChatRiskLevel.CAUTION,
        normalized_query=("뇌졸중 퇴원 후 안전한 운동과 활동"),
    )

    result = await generator.generate(
        request=build_request(),
        patient_context=build_patient_context(),
        classification=classification,
        guideline_chunks=[build_guideline_chunk()],
    )

    assert result.request_id == ("openai-chat-integration-1")
    assert result.care_episode_id == 100
    assert result.intent == ChatIntent.LIFESTYLE
    assert result.route == ChatRoute.PATIENT_AND_RAG
    assert result.safety_status == SafetyStatus.PENDING
    assert result.model_name == (settings.OPENAI_CHAT_MODEL)

    assert "퇴원 후 무리한 활동은 피하세요." in (result.answer)
    assert "참고용 정보" in result.answer
    assert "의료진의 진료를 대체하지 않습니다." in result.answer
