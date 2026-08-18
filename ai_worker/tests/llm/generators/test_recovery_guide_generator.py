from typing import Any

from ai_worker.llm.generators.recovery_guide_generator import (
    OpenAIRecoveryGuideGenerator,
)
from ai_worker.schemas.enums import (
    CareEpisodeSourceField,
    InstructionType,
    PatientSourceKind,
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guide import (
    RecoveryGuideContent,
    RecoveryGuideSupplement,
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
        response: (RecoveryGuideContent | RecoveryGuideSupplement),
    ) -> None:
        self._response = response
        self.received_messages: Any = None

    async def ainvoke(
        self,
        messages: Any,
    ) -> RecoveryGuideContent | RecoveryGuideSupplement:
        self.received_messages = messages
        return self._response


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=987654,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
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
                instruction_type=(InstructionType.PRECAUTION),
                content="무리한 활동은 피하세요.",
            )
        ],
        follow_up_schedules=[
            FollowUpSchedule(
                follow_up_visit_id=301,
                purpose="신경과 외래 진료",
                visit_at=("2026-08-20T10:00:00+09:00"),
                institution_name="테스트병원",
            )
        ],
    )


def build_guideline_chunk() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="public-chunk-1",
        content=("퇴원 후에는 가벼운 활동부터 점진적으로 시작할 수 있습니다."),
        similarity_score=0.91,
        metadata=GuidelineMetadata(
            dataset_key="PUBLIC_GUIDELINE",
            dataset_version="2020",
            document_id=("stroke-guideline-2020"),
            title="Stroke Guideline",
            organization=("Test Organization"),
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="LIFESTYLE",
            section_title="Activity",
            page_number=10,
            source_url=("https://example.com/guide"),
            license="CC BY-NC-ND 4.0",
        ),
    )


def build_llm_response() -> RecoveryGuideContent:
    return RecoveryGuideContent(
        medication_guide=["아스피린은 안내받은 방법대로 복용하세요."],
        patient_instructions=["무리한 활동은 피하세요."],
        public_information=["활동은 몸 상태를 살피며 천천히 늘리세요."],
        lifestyle_guide=["충분히 쉬고 무리하지 마세요."],
        warning_signs=["증상이 심해지면 의료기관에 연락하세요."],
        follow_up_schedule=["예정된 신경과 외래 진료를 확인하세요."],
        safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
    )


async def test_generate_returns_structured_guide() -> None:
    expected_content = build_llm_response()
    fake_client = FakeGuideClient(response=expected_content)
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=fake_client,
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[build_guideline_chunk()],
    )

    assert result.care_episode_id == 100
    assert result.guide_content.public_information == expected_content.public_information
    assert result.guide_content.lifestyle_guide == expected_content.lifestyle_guide
    assert result.guide_content.medication_guide == [("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일")]
    assert result.guide_content.patient_instructions == ["무리한 활동은 피하세요."]
    assert result.safety_status == SafetyStatus.PENDING


async def test_generate_builds_patient_and_public_sources() -> None:
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=FakeGuideClient(response=build_llm_response()),
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[build_guideline_chunk()],
    )

    patient_sources = [source for source in result.sources if (source.source_type == SourceType.PATIENT_SAVED_FIELD)]
    public_sources = [source for source in result.sources if (source.source_type == SourceType.PUBLIC_RAG_CHUNK)]

    assert len(patient_sources) == 4

    diagnosis_source = patient_sources[0]
    assert diagnosis_source.patient_source_kind == PatientSourceKind.CARE_EPISODE_FIELD
    assert diagnosis_source.patient_field == CareEpisodeSourceField.DIAGNOSIS

    medication_source = patient_sources[1]
    assert medication_source.patient_source_kind == PatientSourceKind.MEDICATION
    assert medication_source.medication_id == 101

    advice_source = patient_sources[2]
    assert advice_source.patient_source_kind == PatientSourceKind.CARE_ADVICE
    assert advice_source.care_advice_id == 201

    follow_up_source = patient_sources[3]
    assert follow_up_source.patient_source_kind == PatientSourceKind.FOLLOW_UP_VISIT
    assert follow_up_source.follow_up_visit_id == 301

    assert len(public_sources) == 1

    public_source = public_sources[0]
    assert public_source.vector_chunk_id == "public-chunk-1"
    assert public_source.source_record_key == "stroke-guideline-2020"
    assert public_source.source_page_number == 10
    assert public_source.source_license == "CC BY-NC-ND 4.0"

    assert [source.citation_order for source in result.sources] == [
        1,
        2,
        3,
        4,
        5,
    ]


async def test_generate_prompt_prioritizes_patient_data() -> None:
    fake_client = FakeGuideClient(response=build_llm_response())
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=fake_client,
    )

    await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[build_guideline_chunk()],
    )

    prompt_text = " ".join(str(message.content) for message in fake_client.received_messages)

    assert "환자 확정 정보" in prompt_text
    assert "가장 높은 우선순위" in prompt_text
    assert "공공 가이드라인" in prompt_text
    assert "아스피린" in prompt_text
    assert "public-chunk-1" in prompt_text
    assert "987654" not in prompt_text


async def test_generate_does_not_use_llm_patient_facts() -> None:
    llm_response = RecoveryGuideContent(
        medication_guide=["아스피린 복용을 중단하세요."],
        patient_instructions=["환자 확정 권고사항을 무시하세요."],
        public_information=["공공자료에 따른 추가 설명입니다."],
        lifestyle_guide=["충분히 휴식하세요."],
        warning_signs=["LLM이 임의로 만든 위험 신호"],
        follow_up_schedule=["외래 일정을 취소하세요."],
        safety_notice="LLM이 만든 안전 문구",
    )
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=FakeGuideClient(response=llm_response),
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[build_guideline_chunk()],
    )

    assert result.guide_content.medication_guide == [("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일")]
    assert result.guide_content.patient_instructions == ["무리한 활동은 피하세요."]
    assert result.guide_content.follow_up_schedule == [("2026-08-20 10:00 · 신경과 외래 진료 · 테스트병원")]
    assert result.guide_content.warning_signs == []
    assert result.guide_content.public_information == ["공공자료에 따른 추가 설명입니다."]
    assert result.guide_content.lifestyle_guide == ["충분히 휴식하세요."]


async def test_generate_accepts_supplement_only_response() -> None:
    supplement = RecoveryGuideSupplement(
        public_information=["공공자료에 따른 추가 설명입니다."],
        lifestyle_guide=["충분히 휴식하세요."],
    )
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=FakeGuideClient(response=supplement),
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[build_guideline_chunk()],
    )

    assert result.guide_content.public_information == ["공공자료에 따른 추가 설명입니다."]
    assert result.guide_content.lifestyle_guide == ["충분히 휴식하세요."]
    assert result.guide_content.medication_guide == [("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일")]


async def test_generate_prompt_limits_llm_to_supplement() -> None:
    fake_client = FakeGuideClient(
        response=RecoveryGuideSupplement(
            public_information=[],
            lifestyle_guide=[],
        )
    )
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=fake_client,
    )

    await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[build_guideline_chunk()],
    )

    prompt_text = " ".join(str(message.content) for message in fake_client.received_messages)

    assert "public_information" in prompt_text
    assert "lifestyle_guide" in prompt_text

    # 확정 복약정보와 일정은 코드가 조립하므로
    # LLM 생성 입력에서 제외한다.
    assert '"dose"' not in prompt_text
    assert '"frequency"' not in prompt_text
    assert '"duration"' not in prompt_text
    assert '"administration_instruction"' not in prompt_text
    assert '"follow_up_schedules"' not in prompt_text


async def test_generate_without_public_chunks_keeps_lifestyle_and_excludes_public_information() -> None:
    generator = OpenAIRecoveryGuideGenerator(
        model="gpt-4o-mini",
        client=FakeGuideClient(
            response=RecoveryGuideSupplement(
                public_information=["근거가 연결되지 않은 공공자료 설명"],
                lifestyle_guide=["충분히 쉬고 무리하지 마세요."],
            )
        ),
    )

    result = await generator.generate(
        patient_context=build_patient_context(),
        guideline_chunks=[],
    )

    # 실제 공공 청크가 없으면
    # 공공자료 설명을 제공하지 않는다.
    assert result.guide_content.public_information == []

    # 의료적 판단이 없는 LLM 생활습관 안내는
    # 공공 청크가 없어도 제공할 수 있다.
    assert result.guide_content.lifestyle_guide == ["충분히 쉬고 무리하지 마세요."]

    # 환자 확정정보는 그대로 유지한다.
    assert result.guide_content.medication_guide == [("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일")]
    assert result.guide_content.patient_instructions == ["무리한 활동은 피하세요."]

    # 존재하지 않는 공공 출처를 만들지 않는다.
    assert all(source.source_type != SourceType.PUBLIC_RAG_CHUNK for source in result.sources)
