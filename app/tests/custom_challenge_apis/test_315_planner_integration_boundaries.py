import sqlite3
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from pydantic import ValidationError
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exceptions import (
    CustomChallengeAlreadyActiveError,
    CustomChallengeInvalidTargetsError,
    CustomChallengeParticipationNotFoundError,
)
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.models.care import CareEpisode
from app.models.challenges import CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import CustomChallengeParticipation
from app.models.enums import AccountStatus, CareEpisodeStatus, MealSlot, SupplementStatus
from app.models.medications import Medication, MedicationDose, MedicationSlot
from app.models.supplement_nutrients import (
    SupplementDose,
    UserSupplementNutrient,
    UserSupplementNutrientSlot,
)
from app.models.users import User
from app.services.custom_challenges import CustomChallengeService

JOINED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=config.TIMEZONE)
JOINED_DATE = JOINED_AT.date()


@pytest_asyncio.fixture(autouse=True)
async def initialized_sqlite() -> None:
    sqlite3.register_adapter(time, lambda value: value.isoformat())
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def _user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password="unused",
        name="315 planner QA",
        status=AccountStatus.ACTIVE,
    )


async def _templates() -> tuple[CustomChallengeTemplate, CustomChallengeTemplate]:
    check_group = await CommonCodeGroup.create(
        category="CHL",
        group_code="CST_CHK_TYPE",
        group_name="맞춤 인증 방식",
    )
    check_type = await CommonCode.create(
        group=check_group,
        detail_code="AUTO",
        detail_name="자동",
    )
    type_group = await CommonCodeGroup.create(
        category="CHL",
        group_code="CST_CHL_TYPE",
        group_name="맞춤 챌린지 유형",
    )
    medication_type = await CommonCode.create(
        group=type_group,
        detail_code="MEDICATION",
        detail_name="복약",
    )
    supplement_type = await CommonCode.create(
        group=type_group,
        detail_code="SUPPLEMENT",
        detail_name="영양제",
    )
    return (
        await CustomChallengeTemplate.create(
            name="7일 복약",
            check_type=check_type,
            challenge_type=medication_type,
        ),
        await CustomChallengeTemplate.create(
            name="7일 영양제",
            check_type=check_type,
            challenge_type=supplement_type,
        ),
    )


async def _episode(
    user: User,
    alias: str,
    *,
    start_date: date = JOINED_DATE,
    medication_days: int = 7,
) -> CareEpisode:
    episode = await CareEpisode.create(
        user=user,
        alias=alias,
        status=CareEpisodeStatus.ACTIVE,
        medication_start_date=start_date,
        medication_start_slot=MealSlot.MORNING,
        medication_days=medication_days,
    )
    for name, days in (("단기약", 2), ("장기약", medication_days)):
        medication = await Medication.create(
            care_episode=episode,
            name=name,
            times_per_day=1,
            days=days,
        )
        await MedicationSlot.create(medication=medication, slot=MealSlot.MORNING)
    return episode


async def test_medication_participation_uses_remaining_prescription_period_without_a_seven_day_cap() -> None:
    user = await _user("long-prescription@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(
        user,
        "30일 처방",
        start_date=JOINED_AT.date() - timedelta(days=9),
        medication_days=30,
    )

    joined = await CustomChallengeService(now_provider=lambda: JOINED_AT).join(
        user,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[episode.id], idempotency_key="long-prescription"),
    )

    assert joined.end_at == datetime(2026, 10, 1, tzinfo=config.TIMEZONE)
    assert joined.actual_end_date == date(2026, 9, 30)
    assert joined.target_count == 21
    assert joined.occurrences[0].scheduled_at == datetime(2026, 9, 10, 8, tzinfo=config.TIMEZONE)
    assert joined.occurrences[-1].scheduled_at == datetime(2026, 9, 30, 8, tzinfo=config.TIMEZONE)


async def _supplement(user: User, name: str) -> UserSupplementNutrient:
    registration = await UserSupplementNutrient.create(
        user=user,
        custom_name=name,
        dose_amount=Decimal("1"),
        dose_unit="정",
        start_date=JOINED_AT.date(),
        status=SupplementStatus.ACTIVE,
    )
    await UserSupplementNutrientSlot.create(
        user_suppl_nutrient=registration,
        slot=MealSlot.MORNING,
    )
    return registration


async def test_many_active_medication_episodes_are_independent_one_episode_participations() -> None:
    user = await _user("many-episodes@example.com")
    medication_template, _ = await _templates()
    first = await _episode(user, "첫 처방")
    second = await _episode(user, "둘째 처방")
    service = CustomChallengeService(now_provider=lambda: JOINED_AT)

    recommendation = (await service.recommendations(user)).items[0]
    assert [(target.id, target.name) for target in recommendation.targets] == [
        (first.id, "첫 처방"),
        (second.id, "둘째 처방"),
    ]
    with pytest.raises(CustomChallengeInvalidTargetsError):
        await service.join(
            user,
            medication_template.id,
            CustomChallengeJoinRequest(
                target_ids=[first.id, second.id],
                idempotency_key="combined-episodes",
            ),
        )

    first_join = await service.join(
        user,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[first.id], idempotency_key="first-episode"),
    )
    second_join = await service.join(
        user,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[second.id], idempotency_key="second-episode"),
    )

    assert first_join.id != second_join.id
    assert [item.scheduled_date for item in first_join.occurrences] == [
        date(2026, 9, day) for day in range(10, 17)
    ]
    assert first_join.target_count == second_join.target_count == 7


async def test_medication_progress_is_episode_scoped_even_when_slots_match() -> None:
    owner = await _user("episode-owner@example.com")
    other = await _user("episode-other@example.com")
    medication_template, _ = await _templates()
    first = await _episode(owner, "첫 처방")
    second = await _episode(owner, "둘째 처방")
    service = CustomChallengeService(now_provider=lambda: JOINED_AT)
    first_join = await service.join(
        owner,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[first.id], idempotency_key="progress-first"),
    )
    second_join = await service.join(
        owner,
        medication_template.id,
        CustomChallengeJoinRequest(target_ids=[second.id], idempotency_key="progress-second"),
    )
    await MedicationDose.create(
        user=owner,
        care_episode=first,
        dose_date=JOINED_AT.date(),
        slot=MealSlot.MORNING,
    )

    assert (await service.get(owner, first_join.id)).completed_count == 1
    assert (await service.get(owner, second_join.id)).completed_count == 0
    with pytest.raises(CustomChallengeParticipationNotFoundError):
        await service.get(other, first_join.id)


async def test_two_supplements_have_distinct_daily_goals_and_canonical_idempotency() -> None:
    user = await _user("two-supplements@example.com")
    _, supplement_template = await _templates()
    first = await _supplement(user, "비타민")
    second = await _supplement(user, "오메가3")
    service = CustomChallengeService(now_provider=lambda: JOINED_AT)
    request = CustomChallengeJoinRequest(
        target_ids=[second.id, first.id],
        idempotency_key="two-supplements",
    )

    joined = await service.join(user, supplement_template.id, request)
    replayed = await service.join(user, supplement_template.id, request)

    assert replayed == joined
    assert [target.source_id for target in joined.targets] == [first.id, second.id]
    assert joined.target_count == 14
    assert len({(item.target_id, item.scheduled_date, item.slot) for item in joined.occurrences}) == 14
    with pytest.raises(CustomChallengeAlreadyActiveError):
        await service.join(
            user,
            supplement_template.id,
            CustomChallengeJoinRequest(
                target_ids=[first.id, second.id],
                idempotency_key="same-set-new-key",
            ),
        )
    with pytest.raises(ValidationError):
        CustomChallengeJoinRequest(
            target_ids=[first.id, first.id],
            idempotency_key="duplicate-target",
        )

    await SupplementDose.create(
        registration=second,
        dose_date=JOINED_AT.date(),
        slot=MealSlot.MORNING,
    )
    progress = await service.get(user, joined.id)
    assert progress.completed_count == 1
    assert [item.target_id for item in progress.occurrences if item.is_completed] == [joined.targets[1].id]


async def test_source_end_and_seven_day_end_are_both_exclusive_time_boundaries() -> None:
    user = await _user("intersection@example.com")
    _, supplement_template = await _templates()
    registration = await _supplement(user, "종료일 있는 영양제")
    registration.end_date = JOINED_AT.date() + timedelta(days=10)
    await registration.save(update_fields=["end_date"])
    service = CustomChallengeService(now_provider=lambda: JOINED_AT)

    joined = await service.join(
        user,
        supplement_template.id,
        CustomChallengeJoinRequest(target_ids=[registration.id], idempotency_key="end-intersection"),
    )

    assert joined.end_at == datetime(2026, 9, 17, tzinfo=config.TIMEZONE)
    assert joined.actual_end_date == date(2026, 9, 16)
    assert not any(item.scheduled_at >= joined.end_at for item in joined.occurrences)
    assert await CustomChallengeParticipation.all().count() == 1
