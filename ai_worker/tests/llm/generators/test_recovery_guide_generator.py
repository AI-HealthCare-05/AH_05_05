from typing import Any

from ai_worker.llm.generators.recovery_guide_generator import (
    OpenAIRecoveryGuideGenerator,
)
from ai_worker.schemas.enums import (
    InstructionType,
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guide import (
    RecoveryGuideContent,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
    PatientInstruction,
    PatientMedication,
)


class FakeGuideClient:
    def __init__(
        self,
        response: RecoveryGuideContent,
    ) -> None:
        self._response = response
        self.received_messages: Any = None

    async def ainvoke(
        self,
        messages: Any,
    ) -> RecoveryGuideContent:
        self.received_messages = messages
        return self._response


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=987654,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
        medications=[
            PatientMedication(
                entity_key="medication-1",
                drug_name="아스피린",
                dose="1정",
                frequency="1일 1회",
                duration="7일",
                administration_instruction=(
                    "아침 식후 복용"
                ),
                source_field_ids=[101, 102],
            )
        ],
        instructions=[
            PatientInstruction(
                instruction_type=(
                    InstructionType.PRECAUTION
                ),
                content="무리한 활동은 피하세요.",
                source_field_id=103,
            )
        ],
        follow_up_schedules=[
            FollowUpSchedule(
                description="신경과 외래 진료",
                scheduled_at=(
                    "2026-08-20T10:00:00+09:00"
                ),
                institution_name="테스트병원",
                source_field_ids=[104],
            )
        ],
    )


def build_guideline_chunk() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="public-chunk-1",
        content=(
            "퇴원 후에는 가벼운 활동부터 "
            "점진적으로 시작할 수 있습니다."
        ),
        similarity_score=0.91,
        metadata=GuidelineMetadata(
            dataset_key="PUBLIC_GUIDELINE",
            dataset_version="2020",
            document_id="stroke-guideline-2020",
            title="Stroke Guideline",
            organization="Test Organization",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="LIFESTYLE",
            section_title="Activity",
            page_number=10,
            source_url="https://example.com/guide",
        ),
    )


def build_llm_response() -> RecoveryGuideContent:
    return RecoveryGuideContent(
        medication_guide=[
            "아스피린은 안내받은 방법대로 복용하세요."
        ],
        patient_instructions=[
            "무리한 활동은 피하세요."
        ],
        public_information=[
            "활동은 몸 상태를 살피며 천천히 늘리세요."
        ],
        lifestyle_guide=[
            "충분히 쉬고 무리하지 마세요."
        ],
        warning_signs=[
            "증상이 심해지면 의료기관에 연락하세요."
        ],
        follow_up_schedule=[
            "예정된 신경과 외래 진료를 확인하세요."
        ],
        safety_notice=(
            "이 안내는 의료진의 진료를 "
            "대체하지 않습니다."
        ),
    )


async def test_generate_returns_structured_guide() -> None:
    expected_content = build_llm_response()
    fake_client = FakeGuideClient(
        response=expected_content
    )
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=fake_client,
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[
            build_guideline_chunk()
        ],
    )

    assert result.care_episode_id == 100
    assert result.guide_content == expected_content
    assert (
        result.safety_status
        == SafetyStatus.PENDING
    )


async def test_generate_builds_patient_and_public_sources() -> None:
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=FakeGuideClient(
            response=build_llm_response()
        ),
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[
            build_guideline_chunk()
        ],
    )

    patient_source_ids = {
        source.extracted_field_id
        for source in result.sources
        if (
            source.source_type
            == SourceType.PATIENT_SAVED_FIELD
        )
    }

    public_sources = [
        source
        for source in result.sources
        if (
            source.source_type
            == SourceType.PUBLIC_RAG_CHUNK
        )
    ]

    assert patient_source_ids == {
        101,
        102,
        103,
        104,
    }
    assert len(public_sources) == 1
    assert (
        public_sources[0].vector_chunk_id
        == "public-chunk-1"
    )
    assert (
        public_sources[0].source_record_key
        == "stroke-guideline-2020"
    )


async def test_generate_prompt_prioritizes_patient_data() -> None:
    fake_client = FakeGuideClient(
        response=build_llm_response()
    )
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=fake_client,
    )

    await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[
            build_guideline_chunk()
        ],
    )

    prompt_text = " ".join(
        str(message.content)
        for message in fake_client.received_messages
    )

    assert "환자 확정 정보" in prompt_text
    assert "가장 높은 우선순위" in prompt_text
    assert "공공 가이드라인" in prompt_text
    assert "아스피린" in prompt_text
    assert "public-chunk-1" in prompt_text
    assert "987654" not in prompt_text
