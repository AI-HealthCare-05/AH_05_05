from ai_worker.schemas.enums import (
    ConflictStatus,
    SafetyStatus,
)
from ai_worker.schemas.guide import (
    RecoveryGuideContent,
    RecoveryGuideResult,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.safety import (
    ConflictCheckResult,
    SafetyResult,
)
from ai_worker.use_cases.generate_recovery_guide import (
    GenerateRecoveryGuideUseCase,
)


class FakePatientContextProvider:
    def __init__(
        self,
        patient_context: PatientContext,
    ) -> None:
        self._patient_context = patient_context
        self.received_user_id: int | None = None
        self.received_care_episode_id: int | None = None

    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext:
        self.received_user_id = user_id
        self.received_care_episode_id = care_episode_id
        return self._patient_context


class FakeQueryBuilder:
    def __init__(
        self,
        search_query: GuidelineSearchQuery,
    ) -> None:
        self._search_query = search_query
        self.received_patient_context: PatientContext | None = None

    def build(
        self,
        patient_context: PatientContext,
        condition: str,
        topic: str,
        care_phase: str = "POST_DISCHARGE",
        limit: int = 5,
    ) -> GuidelineSearchQuery:
        self.received_patient_context = patient_context
        return self._search_query


class FakeRetriever:
    def __init__(
        self,
        chunks: list[RetrievedGuidelineChunk],
    ) -> None:
        self._chunks = chunks
        self.received_search_query: GuidelineSearchQuery | None = None

    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        self.received_search_query = search_query
        return self._chunks


class FakeConflictResolver:
    def __init__(
        self,
        result: ConflictCheckResult,
    ) -> None:
        self._result = result
        self.received_chunks: list[RetrievedGuidelineChunk] = []

    async def resolve(
        self,
        patient_context: PatientContext,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ConflictCheckResult:
        self.received_chunks = guideline_chunks
        return self._result


class FakeGuideGenerator:
    def __init__(
        self,
        result: RecoveryGuideResult,
    ) -> None:
        self._result = result
        self.received_chunks: list[RetrievedGuidelineChunk] = []

    async def generate(
        self,
        patient_context: PatientContext,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> RecoveryGuideResult:
        self.received_chunks = guideline_chunks
        return self._result


class FakeSafetyValidator:
    def __init__(
        self,
        result: SafetyResult,
    ) -> None:
        self._result = result

    async def validate(
        self,
        patient_context: PatientContext,
        result: RecoveryGuideResult,
    ) -> SafetyResult:
        return self._result


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=1,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
    )


def build_search_query() -> GuidelineSearchQuery:
    return GuidelineSearchQuery(
        query="STROKE 뇌졸중 퇴원 후 생활관리",
        condition="STROKE",
        care_phase="POST_DISCHARGE",
        topic="LIFESTYLE",
        limit=5,
    )


def build_chunk() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="chunk-1",
        content="퇴원 후 생활관리 안내",
        similarity_score=0.9,
        metadata=GuidelineMetadata(
            document_id="stroke-guideline",
            title="Stroke Guideline",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="LIFESTYLE",
        ),
    )


def build_guide(
    *,
    medication_text: str = ("처방받은 방법대로 복용하세요."),
) -> RecoveryGuideResult:
    return RecoveryGuideResult(
        care_episode_id=100,
        patient_context_hash="a" * 64,
        model_name="gpt-4o-mini",
        model_version=None,
        prompt_version=("recovery-guide-prompt-v1"),
        schema_version=("recovery-guide-result-v1"),
        guide_content=RecoveryGuideContent(
            medication_guide=[medication_text],
            patient_instructions=[],
            public_information=[],
            lifestyle_guide=[],
            warning_signs=[],
            follow_up_schedule=[],
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        ),
        safety_status=SafetyStatus.PENDING,
    )


def build_use_case(
    *,
    conflict_result: ConflictCheckResult,
    guide_result: RecoveryGuideResult,
    safety_result: SafetyResult,
) -> tuple[
    GenerateRecoveryGuideUseCase,
    FakeGuideGenerator,
]:
    patient_context = build_patient_context()
    chunk = build_chunk()
    generator = FakeGuideGenerator(result=guide_result)

    use_case = GenerateRecoveryGuideUseCase(
        patient_context_provider=(FakePatientContextProvider(patient_context)),
        query_builder=FakeQueryBuilder(build_search_query()),
        retriever=FakeRetriever([chunk]),
        conflict_resolver=(FakeConflictResolver(conflict_result)),
        guide_generator=generator,
        safety_validator=(FakeSafetyValidator(safety_result)),
    )

    return use_case, generator


async def test_execute_returns_safe_guide() -> None:
    chunk = build_chunk()
    use_case, generator = build_use_case(
        conflict_result=ConflictCheckResult(
            status=ConflictStatus.NO_CONFLICT,
            usable_guideline_chunks=[chunk],
        ),
        guide_result=build_guide(),
        safety_result=SafetyResult(
            status=SafetyStatus.SAFE,
        ),
    )

    result = await use_case.execute(
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        topic="LIFESTYLE",
    )

    assert result.safety_status == SafetyStatus.SAFE
    assert result.safety_reason_codes == []
    assert generator.received_chunks == [chunk]


async def test_execute_replaces_blocked_content() -> None:
    chunk = build_chunk()
    use_case, _ = build_use_case(
        conflict_result=ConflictCheckResult(
            status=ConflictStatus.NO_CONFLICT,
            usable_guideline_chunks=[chunk],
        ),
        guide_result=build_guide(medication_text=("오늘부터 약 복용을 중단하세요.")),
        safety_result=SafetyResult(
            status=SafetyStatus.BLOCKED,
            reason_codes=["MEDICATION_CHANGE_INSTRUCTION"],
        ),
    )

    result = await use_case.execute(
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        topic="LIFESTYLE",
    )

    assert result.safety_status == SafetyStatus.BLOCKED
    assert result.guide_content.medication_guide == []
    assert result.guide_content.lifestyle_guide == []
    assert "제공할 수 없습니다" in result.guide_content.safety_notice
    assert result.safety_reason_codes == ["MEDICATION_CHANGE_INSTRUCTION"]


async def test_execute_restricts_review_required_result() -> None:
    chunk = build_chunk()
    use_case, generator = build_use_case(
        conflict_result=ConflictCheckResult(
            status=(ConflictStatus.REVIEW_REQUIRED),
            usable_guideline_chunks=[],
            excluded_guideline_chunks=[chunk],
        ),
        guide_result=build_guide(),
        safety_result=SafetyResult(
            status=SafetyStatus.SAFE,
        ),
    )

    result = await use_case.execute(
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        topic="LIFESTYLE",
    )

    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "GUIDELINE_REVIEW_REQUIRED" in result.safety_reason_codes
    assert generator.received_chunks == []


async def test_execute_restricted_keeps_only_confirmed_content() -> None:
    guide_result = RecoveryGuideResult(
        care_episode_id=100,
        patient_context_hash="a" * 64,
        model_name="gpt-4o-mini",
        model_version=None,
        prompt_version=("recovery-guide-prompt-v1"),
        schema_version=("recovery-guide-result-v1"),
        guide_content=RecoveryGuideContent(
            medication_guide=["아스피린 · 1정 · 1일 1회"],
            patient_instructions=["무리한 활동은 피하세요."],
            public_information=["LLM이 설명한 공공자료 내용"],
            lifestyle_guide=["매일 30분씩 운동하세요."],
            warning_signs=["LLM이 생성한 위험 신호"],
            follow_up_schedule=["2026-08-20 10:00 · 신경과"],
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        ),
        safety_status=SafetyStatus.PENDING,
    )

    use_case, _ = build_use_case(
        conflict_result=ConflictCheckResult(
            status=ConflictStatus.NO_CONFLICT,
            usable_guideline_chunks=[build_chunk()],
        ),
        guide_result=guide_result,
        safety_result=SafetyResult(
            status=SafetyStatus.RESTRICTED,
            reason_codes=["MISSING_MEDICAL_DISCLAIMER"],
        ),
    )

    result = await use_case.execute(
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        topic="LIFESTYLE",
    )

    assert result.safety_status == SafetyStatus.RESTRICTED

    # 환자 확정정보는 유지한다.
    assert result.guide_content.medication_guide == ["아스피린 · 1정 · 1일 1회"]
    assert result.guide_content.patient_instructions == ["무리한 활동은 피하세요."]
    assert result.guide_content.follow_up_schedule == ["2026-08-20 10:00 · 신경과"]

    # LLM·공공자료 기반 추가정보는 제거한다.
    assert result.guide_content.public_information == []
    assert result.guide_content.lifestyle_guide == []
    assert result.guide_content.warning_signs == []

    assert "추가 안내를 제한" in result.guide_content.safety_notice
