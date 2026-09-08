from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.domain.errors import (
    PatientContextNotFoundError,
    UnconfirmedPatientContextError,
)
from ai_worker.providers.db_patient_context_provider import (
    DbPatientContextProvider,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import (
    CareEpisode,
    FollowUpVisit,
)
from app.models.enums import (
    MealSlot,
)
from app.models.medications import Medication
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
async def test_get_patient_context_reads_confirmed_erd_data(
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
        alias="확정 복약",
        medication_days=7,
        medication_start_date=date(2026, 8, 11),
        medication_start_slot=MealSlot.MORNING,
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
    await Medication.create(
        id=1001,
        care_episode=care_episode,
        name="아스피린",
        dose_quantity="1정",
        times_per_day=1,
        note="아침 식후 복용",
        days=7,
        prescribed_at=date(2026, 8, 10),
    )
    await FollowUpVisit.create(
        id=3001,
        user=user,
        visit_date=date(2026, 8, 20),
        visit_time=time(10, 0),
        hospital="테스트병원",
    )

    provider = DbPatientContextProvider()

    result = await provider.get_patient_context(
        user_id=1,
        care_episode_id=100,
    )

    assert result.user_id == 1
    assert result.care_episode_id == 100
    assert result.diagnoses == []
    assert result.surgery is None
    assert result.discharge_date is None
    assert result.medication_start_slot == "MORNING"
    assert result.confirmation_hash == "a" * 64

    assert len(result.medications) == 1
    assert result.medications[0].medication_id == 1001
    assert result.medications[0].name == "아스피린"

    assert result.instructions == []

    assert len(result.follow_up_schedules) == 1
    assert result.follow_up_schedules[0].follow_up_visit_id == 3001
    assert result.follow_up_schedules[0].visit_at == datetime(
        2026,
        8,
        20,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Seoul"),
    )
    assert result.follow_up_schedules[0].hospital == "테스트병원"


@pytest.mark.asyncio
async def test_get_patient_context_rejects_unconfirmed_data(
    initialized_db: None,
) -> None:
    user = await User.create(
        id=1,
        email="unconfirmed@example.com",
        hashed_password="hashed-password",
        name="미확정 환자",
    )
    await CareEpisode.create(
        id=100,
        user=user,
        alias="사용자 확인 전 데이터",
        confirmation_hash=None,
        confirmed_at=None,
    )

    provider = DbPatientContextProvider()

    with pytest.raises(
        UnconfirmedPatientContextError,
        match="확정",
    ):
        await provider.get_patient_context(
            user_id=1,
            care_episode_id=100,
        )


@pytest.mark.asyncio
async def test_get_patient_context_rejects_other_users_episode(
    initialized_db: None,
) -> None:
    owner = await User.create(
        id=1,
        email="owner@example.com",
        hashed_password="hashed-password",
        name="소유자",
    )
    other_user = await User.create(
        id=2,
        email="other@example.com",
        hashed_password="hashed-password",
        name="다른 사용자",
    )
    await CareEpisode.create(
        id=100,
        user=owner,
        alias="소유자의 케어 에피소드",
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

    provider = DbPatientContextProvider()

    with pytest.raises(
        PatientContextNotFoundError,
        match="찾을 수 없습니다",
    ):
        await provider.get_patient_context(
            user_id=other_user.id,
            care_episode_id=100,
        )
