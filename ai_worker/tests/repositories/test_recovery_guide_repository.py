from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from tortoise import Tortoise
from tortoise.exceptions import IntegrityError

from ai_worker.repositories.recovery_guide_repository import (
    RecoveryGuideRepository,
)
from ai_worker.schemas.enums import (
    PatientSourceKind,
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guide import (
    GuideSource,
    RecoveryGuideContent,
    RecoveryGuideResult,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import (
    CareAdvice,
    CareEpisode,
    FollowUpVisit,
)
from app.models.enums import (
    CareAdviceCategory,
    ChatSafetyStatus,
    RecoveryGuideStatus,
)
from app.models.medications import Medication
from app.models.recovery import (
    RecoveryGuide,
    RecoveryGuideSource,
)
from app.models.users import User


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={
            "models": TORTOISE_APP_MODELS,
        },
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()

    yield

    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_save_creates_recovery_guide(
    initialized_db: None,
) -> None:
    user = await User.create(
        id=1,
        email="patient@example.com",
        hashed_password="hashed-password",
        name="테스트 환자",
    )
    care_episode = await CareEpisode.create(
        id=100,
        user=user,
        title="뇌졸중 퇴원 후 관리",
        diagnosis="뇌졸중",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(
            2026,
            8,
            11,
            10,
            30,
            tzinfo=ZoneInfo("Asia/Seoul"),
        ),
    )

    result = RecoveryGuideResult(
        care_episode_id=care_episode.id,
        guide_content=RecoveryGuideContent(
            medication_guide=[
                "아스피린 · 1정 · 1일 1회",
            ],
            patient_instructions=[
                "퇴원 후 무리한 활동을 피하세요.",
            ],
            public_information=[],
            lifestyle_guide=[
                "충분한 휴식을 취하세요.",
            ],
            warning_signs=[],
            follow_up_schedule=[],
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        ),
        patient_context_hash="b" * 64,
        model_name="gpt-4o-mini",
        model_version=None,
        prompt_version="recovery-guide-prompt-v1",
        schema_version="recovery-guide-result-v1",
        safety_status=SafetyStatus.SAFE,
        safety_reason_codes=[],
    )
    repository = RecoveryGuideRepository()

    recovery_guide_id = await repository.save(
        result=result,
    )

    saved_guide = await RecoveryGuide.get(
        id=recovery_guide_id,
    )

    assert saved_guide.care_episode_id == 100
    assert saved_guide.status == RecoveryGuideStatus.COMPLETED
    assert saved_guide.guide_content["medication_guide"] == ["아스피린 · 1정 · 1일 1회"]
    assert saved_guide.guide_content["lifestyle_guide_label"] == "AI 생성 일반 안내"
    assert saved_guide.patient_context_hash == "b" * 64
    assert saved_guide.model_name == "gpt-4o-mini"
    assert saved_guide.prompt_version == "recovery-guide-prompt-v1"
    assert saved_guide.schema_version == "recovery-guide-result-v1"
    assert saved_guide.safety_status == ChatSafetyStatus.SAFE
    assert saved_guide.safety_reason_codes == []
    assert saved_guide.completed_at is not None


@pytest.mark.asyncio
async def test_save_creates_patient_and_public_sources(
    initialized_db: None,
) -> None:
    user = await User.create(
        id=1,
        email="source-patient@example.com",
        hashed_password="hashed-password",
        name="출처 테스트 환자",
    )
    care_episode = await CareEpisode.create(
        id=100,
        user=user,
        title="뇌졸중 퇴원 후 관리",
        diagnosis="뇌졸중",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(
            2026,
            8,
            11,
            10,
            30,
            tzinfo=ZoneInfo("Asia/Seoul"),
        ),
    )
    medication = await Medication.create(
        id=1001,
        care_episode=care_episode,
        name="아스피린",
        dose="1정",
        times_per_day=1,
        days=7,
    )

    result = RecoveryGuideResult(
        care_episode_id=care_episode.id,
        guide_content=RecoveryGuideContent(
            medication_guide=[
                "아스피린 · 1정 · 1일 1회",
            ],
            public_information=[
                "공공 가이드라인 추가 설명",
            ],
            lifestyle_guide=[],
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        ),
        patient_context_hash="b" * 64,
        model_name="gpt-4o-mini",
        prompt_version="recovery-guide-prompt-v1",
        schema_version="recovery-guide-result-v1",
        sources=[
            GuideSource(
                source_type=(SourceType.PATIENT_SAVED_FIELD),
                patient_source_kind=(PatientSourceKind.MEDICATION),
                medication_id=medication.id,
                citation_order=1,
            ),
            GuideSource(
                source_type=(SourceType.PUBLIC_RAG_CHUNK),
                public_dataset_key=("PUBLIC_GUIDELINE"),
                dataset_version="2020",
                vector_chunk_id="chunk-001",
                source_record_key=("canadian-stroke-2020-page-10"),
                source_title=("Canadian Stroke Guideline"),
                source_organization=("Heart and Stroke Foundation"),
                source_page_number=10,
                source_license="CC BY-NC-ND 4.0",
                similarity_score=0.91,
                citation_order=2,
            ),
        ],
        safety_status=SafetyStatus.SAFE,
        safety_reason_codes=[],
    )
    repository = RecoveryGuideRepository()

    recovery_guide_id = await repository.save(
        result=result,
    )

    saved_sources = await RecoveryGuideSource.filter(
        recovery_guide_id=recovery_guide_id,
    ).order_by("citation_order")

    assert len(saved_sources) == 2

    patient_source = saved_sources[0]
    assert patient_source.source_type.value == ("PATIENT_SAVED_FIELD")
    assert patient_source.patient_source_kind.value == ("MEDICATION")
    assert patient_source.medication_id == 1001
    assert patient_source.citation_order == 1

    public_source = saved_sources[1]
    assert public_source.source_type.value == ("PUBLIC_RAG_CHUNK")
    assert public_source.public_dataset_key == "PUBLIC_GUIDELINE"
    assert public_source.vector_chunk_id == "chunk-001"
    assert public_source.source_record_key == "canadian-stroke-2020-page-10"
    assert public_source.source_page_number == 10
    assert public_source.similarity_score == Decimal("0.9100")
    assert public_source.citation_order == 2


@pytest.mark.asyncio
async def test_save_rolls_back_when_source_save_fails(
    initialized_db: None,
) -> None:
    user = await User.create(
        id=1,
        email="rollback@example.com",
        hashed_password="hashed-password",
        name="롤백 테스트 환자",
    )
    care_episode = await CareEpisode.create(
        id=100,
        user=user,
        title="트랜잭션 테스트",
        diagnosis="뇌졸중",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(
            2026,
            8,
            11,
            10,
            30,
            tzinfo=ZoneInfo("Asia/Seoul"),
        ),
    )

    result = RecoveryGuideResult(
        care_episode_id=care_episode.id,
        guide_content=RecoveryGuideContent(
            public_information=[
                "공공자료 추가 설명",
            ],
            lifestyle_guide=[],
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        ),
        patient_context_hash="b" * 64,
        model_name="gpt-4o-mini",
        prompt_version="recovery-guide-prompt-v1",
        schema_version="recovery-guide-result-v1",
        sources=[
            GuideSource(
                source_type=(SourceType.PUBLIC_RAG_CHUNK),
                public_dataset_key=("PUBLIC_GUIDELINE"),
                dataset_version="2020",
                vector_chunk_id="chunk-001",
                source_record_key="record-001",
                citation_order=1,
            ),
            GuideSource(
                source_type=(SourceType.PUBLIC_RAG_CHUNK),
                public_dataset_key=("PUBLIC_GUIDELINE"),
                dataset_version="2020",
                vector_chunk_id="chunk-002",
                source_record_key="record-002",
                citation_order=1,
            ),
        ],
        safety_status=SafetyStatus.SAFE,
        safety_reason_codes=[],
    )
    repository = RecoveryGuideRepository()

    with pytest.raises(IntegrityError):
        await repository.save(
            result=result,
        )

    assert await RecoveryGuide.all().count() == 0
    assert await RecoveryGuideSource.all().count() == 0


@pytest.mark.parametrize(
    (
        "patient_source_kind",
        "source_id_field",
    ),
    [
        (
            PatientSourceKind.MEDICATION,
            "medication_id",
        ),
        (
            PatientSourceKind.CARE_ADVICE,
            "care_advice_id",
        ),
        (
            PatientSourceKind.FOLLOW_UP_VISIT,
            "follow_up_visit_id",
        ),
    ],
)
@pytest.mark.asyncio
async def test_save_rejects_patient_source_from_other_episode(
    initialized_db: None,
    patient_source_kind: PatientSourceKind,
    source_id_field: str,
) -> None:
    user = await User.create(
        id=1,
        email="owner@example.com",
        hashed_password="hashed-password",
        name="가이드 소유자",
    )
    other_user = await User.create(
        id=2,
        email="other@example.com",
        hashed_password="hashed-password",
        name="다른 환자",
    )
    care_episode = await CareEpisode.create(
        id=100,
        user=user,
        title="가이드 생성 대상",
        diagnosis="뇌졸중",
        confirmation_hash="a" * 64,
        confirmed_at=datetime(
            2026,
            8,
            11,
            10,
            30,
            tzinfo=ZoneInfo("Asia/Seoul"),
        ),
    )
    other_episode = await CareEpisode.create(
        id=200,
        user=other_user,
        title="다른 환자의 케어 에피소드",
        diagnosis="고관절 골절",
        confirmation_hash="c" * 64,
        confirmed_at=datetime(
            2026,
            8,
            11,
            11,
            0,
            tzinfo=ZoneInfo("Asia/Seoul"),
        ),
    )

    other_medication = await Medication.create(
        id=1001,
        care_episode=other_episode,
        name="다른 환자의 약",
    )
    other_advice = await CareAdvice.create(
        id=2001,
        care_episode=other_episode,
        category=CareAdviceCategory.OTHER,
        text="다른 환자의 권고사항",
        display_order=1,
    )
    other_follow_up = await FollowUpVisit.create(
        id=3001,
        care_episode=other_episode,
        visit_date=date(2026, 8, 20),
        visit_time=time(10, 0),
    )

    source_ids = {
        "medication_id": other_medication.id,
        "care_advice_id": other_advice.id,
        "follow_up_visit_id": other_follow_up.id,
    }

    patient_source = GuideSource(
        source_type=(SourceType.PATIENT_SAVED_FIELD),
        patient_source_kind=patient_source_kind,
        citation_order=1,
        **{source_id_field: source_ids[source_id_field]},
    )
    result = RecoveryGuideResult(
        care_episode_id=care_episode.id,
        guide_content=RecoveryGuideContent(
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        ),
        patient_context_hash="b" * 64,
        model_name="gpt-4o-mini",
        prompt_version="recovery-guide-prompt-v1",
        schema_version="recovery-guide-result-v1",
        sources=[patient_source],
        safety_status=SafetyStatus.SAFE,
        safety_reason_codes=[],
    )
    repository = RecoveryGuideRepository()

    with pytest.raises(
        ValueError,
        match="케어 에피소드",
    ):
        await repository.save(
            result=result,
        )

    assert await RecoveryGuide.all().count() == 0
    assert await RecoveryGuideSource.all().count() == 0
