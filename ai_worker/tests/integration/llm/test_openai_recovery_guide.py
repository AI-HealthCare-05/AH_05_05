import os

import pytest
from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from ai_worker.llm.generators.recovery_guide_generator import (
    OpenAIRecoveryGuideGenerator,
)
from ai_worker.schemas.enums import (
    InstructionType,
    SafetyStatus,
    SourceType,
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


class LiveTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: SecretStr | None = None


settings = LiveTestSettings()

pytestmark = pytest.mark.skipif(
    (
        os.getenv("RUN_LIVE_OPENAI_TESTS")
        != "1"
        or settings.OPENAI_API_KEY is None
    ),
    reason=(
        "실제 OpenAI 테스트는 "
        "RUN_LIVE_OPENAI_TESTS=1과 "
        "OPENAI_API_KEY가 필요합니다."
    ),
)


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=1,
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
                source_field_ids=[101],
            )
        ],
        instructions=[
            PatientInstruction(
                instruction_type=(
                    InstructionType.PRECAUTION
                ),
                content=(
                    "퇴원 후 무리한 활동은 "
                    "피하십시오."
                ),
                source_field_id=102,
            )
        ],
        follow_up_schedules=[
            FollowUpSchedule(
                description="신경과 외래 진료",
                scheduled_at=(
                    "2026-08-20T10:00:00+09:00"
                ),
                institution_name="테스트병원",
                source_field_ids=[103],
            )
        ],
    )


def build_guideline_chunk() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="stroke-public-1",
        content=(
            "퇴원 후 활동은 환자의 상태를 "
            "고려하여 점진적으로 늘리고, "
            "무리한 활동은 피하도록 안내한다."
        ),
        similarity_score=0.92,
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


async def test_generate_guide_with_gpt_4o_mini() -> None:
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        api_key=settings.OPENAI_API_KEY,
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[
            build_guideline_chunk()
        ],
    )

    assert generator.model_name == "gpt-4o-mini"
    assert result.care_episode_id == 100
    assert (
        result.safety_status
        == SafetyStatus.PENDING
    )
    assert result.guide_content.safety_notice
    assert result.guide_content.medication_guide
    assert result.guide_content.patient_instructions

    public_source_ids = {
        source.vector_chunk_id
        for source in result.sources
        if (
            source.source_type
            == SourceType.PUBLIC_RAG_CHUNK
        )
    }

    assert public_source_ids == {
        "stroke-public-1"
    }
