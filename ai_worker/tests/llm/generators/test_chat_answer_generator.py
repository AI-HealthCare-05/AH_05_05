from datetime import date
from typing import Any

from ai_worker.llm.generators.chat_answer_generator import (
    OpenAIChatAnswerGenerator,
)
from ai_worker.schemas.chat import (
    CHAT_ANSWER_SCHEMA_VERSION,
    ChatAnswerRequest,
    ChatAnswerSupplement,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
    PatientSourceKind,
    SafetyStatus,
    SourceType,
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


class FakeChatAnswerClient:
    def __init__(
        self,
        response: ChatAnswerSupplement | dict[str, Any],
    ) -> None:
        self._response = response
        self.received_messages: list[Any] = []

    async def ainvoke(
        self,
        messages: Any,
    ) -> ChatAnswerSupplement | dict[str, Any]:
        self.received_messages = list(messages)

        return self._response


def build_request() -> ChatAnswerRequest:
    return ChatAnswerRequest(
        request_id="chat-request-1",
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        question="퇴원 후 운동은 어떻게 해야 해?",
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
                content="무리한 활동은 피하세요.",
                display_order=1,
            )
        ],
    )


def build_guideline_chunk() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="chunk-1",
        content=("퇴원 후에는 가벼운 활동부터 점진적으로 시작할 수 있습니다."),
        similarity_score=0.91,
        metadata=GuidelineMetadata(
            dataset_key="PUBLIC_GUIDELINE",
            dataset_version="2020-v1",
            document_id="canadian-stroke-2020",
            title="Canadian Stroke Guideline",
            organization="Heart and Stroke Foundation",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="LIFESTYLE",
            section_title="Physical Activity",
            page_number=10,
            source_url="https://example.com/guideline",
            license="CC BY-NC-ND 4.0",
        ),
    )


async def test_generate_returns_patient_first_answer_with_sources() -> None:
    generator = OpenAIChatAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeChatAnswerClient(
            response=ChatAnswerSupplement(
                public_information=["가벼운 활동부터 시작할 수 있습니다."],
                lifestyle_guidance=["피곤하면 쉬면서 활동하세요."],
            )
        ),
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

    patient_index = result.answer.index("무리한 활동은 피하세요.")
    public_index = result.answer.index("가벼운 활동부터 시작할 수 있습니다.")
    ai_index = result.answer.index("피곤하면 쉬면서 활동하세요.")

    assert patient_index < public_index < ai_index

    assert result.request_id == "chat-request-1"
    assert result.care_episode_id == 100
    assert result.intent == ChatIntent.LIFESTYLE
    assert result.route == ChatRoute.PATIENT_AND_RAG
    assert result.risk_level == ChatRiskLevel.CAUTION
    assert result.safety_status == SafetyStatus.PENDING

    assert result.patient_context_hash == "a" * 64
    assert result.model_name == "gpt-4o-mini"
    assert result.schema_version == (CHAT_ANSWER_SCHEMA_VERSION)

    assert len(result.sources) == 2

    patient_source = result.sources[0]
    assert patient_source.source_type == (SourceType.PATIENT_SAVED_FIELD)
    assert patient_source.patient_source_kind == (PatientSourceKind.CARE_ADVICE)
    assert patient_source.care_advice_id == 201
    assert patient_source.citation_order == 1

    public_source = result.sources[1]
    assert public_source.source_type == (SourceType.PUBLIC_RAG_CHUNK)
    assert public_source.vector_chunk_id == "chunk-1"
    assert public_source.source_record_key == ("canadian-stroke-2020")
    assert public_source.source_page_number == 10
    assert public_source.citation_order == 2


async def test_generate_without_chunks_excludes_public_information() -> None:
    generator = OpenAIChatAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeChatAnswerClient(
            response=ChatAnswerSupplement(
                public_information=["검색 근거 없이 LLM이 만든 공공자료 설명"],
                lifestyle_guidance=["피곤하면 쉬면서 활동하세요."],
            )
        ),
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
        guideline_chunks=[],
    )

    assert "검색 근거 없이 LLM이 만든 공공자료 설명" not in result.answer
    assert "피곤하면 쉬면서 활동하세요." in result.answer
    assert all(source.source_type != SourceType.PUBLIC_RAG_CHUNK for source in result.sources)


async def test_generate_patient_only_uses_confirmed_medication_source() -> None:
    generator = OpenAIChatAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeChatAnswerClient(
            response=ChatAnswerSupplement(
                general_response=["아스피린 복용을 중단하세요."],
                public_information=["LLM이 만든 복약 설명"],
                lifestyle_guidance=["복용량을 두 배로 늘리세요."],
            )
        ),
    )
    classification = ChatClassificationResult(
        intent=ChatIntent.MEDICATION,
        route=ChatRoute.PATIENT_ONLY,
        risk_level=ChatRiskLevel.LOW,
    )

    result = await generator.generate(
        request=build_request(),
        patient_context=build_patient_context(),
        classification=classification,
        guideline_chunks=[build_guideline_chunk()],
    )

    assert ("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일") in result.answer

    assert "복용을 중단하세요" not in result.answer
    assert "LLM이 만든 복약 설명" not in result.answer
    assert "복용량을 두 배로 늘리세요" not in result.answer

    assert len(result.sources) == 1

    source = result.sources[0]

    assert source.source_type == (SourceType.PATIENT_SAVED_FIELD)
    assert source.patient_source_kind == (PatientSourceKind.MEDICATION)
    assert source.medication_id == 101
    assert source.citation_order == 1
