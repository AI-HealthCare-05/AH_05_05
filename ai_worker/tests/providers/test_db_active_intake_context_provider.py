from datetime import date, datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.domain.errors import (
    PatientContextNotFoundError,
    UnconfirmedPatientContextError,
)
from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, SupplementStatus
from app.models.medications import Medication
from app.models.supplement_nutrients import (
    SupplementNutrient,
    UserSupplementNutrient,
)
from app.models.users import User


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def _create_user(user_id: int, email: str) -> User:
    return await User.create(
        id=user_id,
        email=email,
        hashed_password="hashed-password",
        name=f"사용자 {user_id}",
    )


async def _create_confirmed_episode(
    *,
    episode_id: int,
    user: User,
    status: CareEpisodeStatus = CareEpisodeStatus.ACTIVE,
) -> CareEpisode:
    return await CareEpisode.create(
        id=episode_id,
        user=user,
        title="약봉투 확인 기록",
        status=status,
        confirmation_hash="a" * 64,
        confirmed_at=datetime(2026, 8, 24, 9, 0),
    )


@pytest.mark.asyncio
async def test_provider_returns_only_current_user_active_intakes(
    initialized_db: None,
) -> None:
    user = await _create_user(1, "patient@example.com")
    other = await _create_user(2, "other@example.com")
    active_episode = await _create_confirmed_episode(episode_id=100, user=user)
    completed_episode = await _create_confirmed_episode(
        episode_id=200,
        user=user,
        status=CareEpisodeStatus.COMPLETED,
    )
    other_episode = await _create_confirmed_episode(episode_id=300, user=other)

    await Medication.create(
        id=10,
        care_episode=active_episode,
        name="아스피린",
        dose_quantity="1정",
        days=30,
        prescribed_at=date(2026, 8, 1),
    )
    await Medication.create(
        id=20,
        care_episode=active_episode,
        name="종료된 단기약",
        days=3,
        prescribed_at=date(2026, 7, 1),
    )
    await Medication.create(
        id=30,
        care_episode=completed_episode,
        name="과거 처방약",
    )
    await Medication.create(
        id=40,
        care_episode=other_episode,
        name="다른 사용자 약",
    )

    omega3 = await SupplementNutrient.create(
        id=1,
        food_code="SUP-001",
        name="오메가3",
        basis_qty="500mg",
        energy_kcal=0,
        protein_g="0",
        carb_g="0",
        serving_desc="1정",
        serving_size="500mg",
        daily_freq="1회",
    )
    vitamin = await SupplementNutrient.create(
        id=2,
        food_code="SUP-002",
        name="비타민 C",
        basis_qty="500mg",
        energy_kcal=0,
        protein_g="0",
        carb_g="0",
        serving_desc="1정",
        serving_size="500mg",
        daily_freq="1회",
    )
    future_supplement = await SupplementNutrient.create(
        id=3,
        food_code="SUP-003",
        name="미래 복용 영양제",
        basis_qty="500mg",
        energy_kcal=0,
        protein_g="0",
        carb_g="0",
        serving_desc="1정",
        serving_size="500mg",
        daily_freq="1회",
    )
    await UserSupplementNutrient.create(
        id=50,
        user=user,
        supplement_nutrient=omega3,
        dose_amount="1",
        dose_unit="캡슐",
        start_date=date(2026, 8, 1),
        status=SupplementStatus.ACTIVE,
    )
    await UserSupplementNutrient.create(
        id=60,
        user=user,
        supplement_nutrient=vitamin,
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 7, 1),
        status=SupplementStatus.PAUSED,
    )
    await UserSupplementNutrient.create(
        id=70,
        user=user,
        supplement_nutrient=future_supplement,
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 9, 1),
        status=SupplementStatus.ACTIVE,
    )

    context = await DbActiveIntakeContextProvider(
        today_provider=lambda: date(2026, 8, 25),
    ).get_active_context(
        user_id=user.id,
        care_episode_id=active_episode.id,
    )

    assert [item.name for item in context.medications] == ["아스피린"]
    assert [item.name for item in context.supplements] == ["오메가3"]
    assert context.preferred_care_episode_id == active_episode.id


@pytest.mark.asyncio
async def test_ai_context_excludes_manual_registrations(
    initialized_db: None,
) -> None:
    user = await _create_user(1, "manual-supplement@example.com")
    await UserSupplementNutrient.create(
        user=user,
        supplement_nutrient_id=None,
        custom_name="직접 입력 영양제",
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 8, 1),
        status=SupplementStatus.ACTIVE,
    )

    context = await DbActiveIntakeContextProvider(
        today_provider=lambda: date(2026, 8, 25),
    ).get_active_context(
        user_id=user.id,
        care_episode_id=None,
    )

    assert context.supplements == []


@pytest.mark.asyncio
async def test_provider_rejects_unowned_episode(
    initialized_db: None,
) -> None:
    owner = await _create_user(1, "owner@example.com")
    other = await _create_user(2, "other@example.com")
    episode = await _create_confirmed_episode(episode_id=100, user=owner)

    with pytest.raises(PatientContextNotFoundError, match="찾을 수 없습니다"):
        await DbActiveIntakeContextProvider().get_active_context(
            user_id=other.id,
            care_episode_id=episode.id,
        )


@pytest.mark.asyncio
async def test_provider_rejects_unconfirmed_episode(
    initialized_db: None,
) -> None:
    user = await _create_user(1, "patient@example.com")
    episode = await CareEpisode.create(
        id=100,
        user=user,
        title="확정 전 약봉투",
        status=CareEpisodeStatus.ACTIVE,
    )

    with pytest.raises(UnconfirmedPatientContextError, match="확정"):
        await DbActiveIntakeContextProvider().get_active_context(
            user_id=user.id,
            care_episode_id=episode.id,
        )
