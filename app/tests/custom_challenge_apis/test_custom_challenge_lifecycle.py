import sqlite3
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest_asyncio
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dtos.medications import SaveMedicationDoseRequest
from app.dtos.supplement_doses import SupplementDoseRequest
from app.models.care import CareEpisode
from app.models.challenges import Badge, CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import (
    CustomChallengeBadgeAward,
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import (
    AccountStatus,
    ChallengeParticipationStatus,
    CustomChallengeType,
    MealSlot,
)
from app.models.medications import MedicationDose
from app.models.supplement_nutrients import (
    SupplementDose,
    UserSupplementNutrient,
    UserSupplementNutrientSlot,
)
from app.models.users import User
from app.services.custom_challenge_lifecycle import CustomChallengeLifecycleService
from app.services.custom_challenges import CustomChallengeService
from app.services.medications import MedicationService
from app.services.supplement_doses import SupplementDoseService

END_AT = datetime(2026, 9, 17, tzinfo=config.TIMEZONE)


@pytest_asyncio.fixture(autouse=True)
async def initialized_db() -> None:
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


async def _user(email: str = "lifecycle@example.com") -> User:
    return await User.create(
        email=email,
        hashed_password="unused",
        name="생명주기 사용자",
        status=AccountStatus.ACTIVE,
    )


async def _template_with_badge() -> tuple[CustomChallengeTemplate, Badge]:
    check_group = await CommonCodeGroup.create(
        category="CHL",
        group_code="CST_CHK_TYPE",
        group_name="맞춤 인증",
    )
    type_group = await CommonCodeGroup.create(
        category="CHL",
        group_code="CST_CHL_TYPE",
        group_name="맞춤 유형",
    )
    check_type = await CommonCode.create(
        group=check_group,
        detail_code="AUTO",
        detail_name="자동",
    )
    challenge_type = await CommonCode.create(
        group=type_group,
        detail_code="MEDICATION",
        detail_name="복약",
    )
    badge = await Badge.create(
        name="7일 복약 완료",
        image_path="media/badges/medication-7.png",
    )
    template = await CustomChallengeTemplate.create(
        name="7일 복약",
        check_type=check_type,
        challenge_type=challenge_type,
        reward_badge=badge,
    )
    return template, badge


async def test_full_progress_finalizes_only_at_prescribed_end_and_awards_once() -> None:
    user = await _user()
    template, badge = await _template_with_badge()
    episode = await CareEpisode.create(user=user, alias="완료 처방")
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.MEDICATION,
        challenge_name=template.name,
        idempotency_key="complete-at-end",
        end_at=END_AT,
    )
    target = await CustomChallengeTarget.create(
        participation=participation,
        care_episode=episode,
        source_id_snapshot=episode.id,
        target_name_snapshot="완료 처방",
    )
    occurrences = [
        await CustomChallengeOccurrence.create(
            target=target,
            scheduled_date=date(2026, 9, 10),
            slot=slot,
            scheduled_at=datetime(2026, 9, 10, hour, tzinfo=config.TIMEZONE),
        )
        for slot, hour in ((MealSlot.MORNING, 8), (MealSlot.EVENING, 19))
    ]
    for occurrence in occurrences:
        await MedicationDose.create(
            user=user,
            care_episode=episode,
            dose_date=occurrence.scheduled_date,
            slot=occurrence.slot,
        )

    lifecycle = CustomChallengeLifecycleService()
    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        await CareEpisode.filter(id=episode.id).using_db(connection).select_for_update().get()
        finalized_before_end = await lifecycle.finalize_due_for_user(
            user_id=user.id,
            now=END_AT - timedelta(microseconds=1),
            connection=connection,
        )

    await participation.refresh_from_db()
    assert finalized_before_end == 0
    assert participation.status is ChallengeParticipationStatus.ACTIVE
    assert await CustomChallengeBadgeAward.all().count() == 0

    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        await CareEpisode.filter(id=episode.id).using_db(connection).select_for_update().get()
        first = await lifecycle.finalize_due_for_user(
            user_id=user.id,
            now=END_AT,
            connection=connection,
        )
        second = await lifecycle.finalize_due_for_user(
            user_id=user.id,
            now=END_AT,
            connection=connection,
        )

    await participation.refresh_from_db()
    stored_occurrences = await CustomChallengeOccurrence.filter(target_id=target.id).order_by("id")
    awards = await CustomChallengeBadgeAward.filter(participation_id=participation.id)
    assert (first, second) == (1, 0)
    assert participation.status is ChallengeParticipationStatus.COMPLETED
    assert participation.target_count == 2
    assert participation.completed_count == 2
    assert participation.progress_rate == 100
    assert participation.completed_at == END_AT
    assert participation.finalized_at == END_AT
    assert [occurrence.is_completed for occurrence in stored_occurrences] == [True, True]
    assert len(awards) == 1
    assert awards[0].badge_id == badge.id

    await MedicationDose.filter(user_id=user.id, care_episode_id=episode.id).delete()
    badge.name = "나중에 바뀐 배지"
    badge.image_path = "media/badges/changed-after-award.png"
    await badge.save(update_fields=["name", "image_path"])
    frozen = await CustomChallengeService().get(user, participation.id)
    assert frozen.status is ChallengeParticipationStatus.COMPLETED
    assert frozen.target_count == frozen.completed_count == 2
    assert frozen.progress_rate == 100
    assert [occurrence.is_completed for occurrence in frozen.occurrences] == [True, True]
    assert frozen.reward_badge is not None
    assert frozen.reward_badge.name == "7일 복약 완료"
    assert frozen.reward_badge.image_path == "media/badges/medication-7.png"


async def test_empty_or_partial_goal_set_expires_without_award() -> None:
    user = await _user("expired-lifecycle@example.com")
    template, badge = await _template_with_badge()
    episode = await CareEpisode.create(user=user, alias="미완료 처방")
    empty = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.MEDICATION,
        challenge_name="빈 목표",
        idempotency_key="empty-at-end",
        end_at=END_AT,
    )
    partial = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.MEDICATION,
        challenge_name="부분 목표",
        idempotency_key="partial-at-end",
        end_at=END_AT,
    )
    target = await CustomChallengeTarget.create(
        participation=partial,
        care_episode=episode,
        source_id_snapshot=episode.id,
        target_name_snapshot="미완료 처방",
    )
    first = await CustomChallengeOccurrence.create(
        target=target,
        scheduled_date=date(2026, 9, 10),
        slot=MealSlot.MORNING,
        scheduled_at=datetime(2026, 9, 10, 8, tzinfo=config.TIMEZONE),
    )
    await CustomChallengeOccurrence.create(
        target=target,
        scheduled_date=date(2026, 9, 10),
        slot=MealSlot.EVENING,
        scheduled_at=datetime(2026, 9, 10, 19, tzinfo=config.TIMEZONE),
    )
    await MedicationDose.create(
        user=user,
        care_episode=episode,
        dose_date=first.scheduled_date,
        slot=first.slot,
    )

    async with in_transaction() as connection:
        finalized = await CustomChallengeLifecycleService().finalize_due_for_user(
            user_id=user.id,
            now=END_AT,
            connection=connection,
        )

    await empty.refresh_from_db()
    await partial.refresh_from_db()
    assert finalized == 2
    assert empty.status is ChallengeParticipationStatus.EXPIRED
    assert (empty.target_count, empty.completed_count, empty.progress_rate) == (0, 0, 0)
    assert partial.status is ChallengeParticipationStatus.EXPIRED
    assert (partial.target_count, partial.completed_count, partial.progress_rate) == (2, 1, 50)
    assert await CustomChallengeBadgeAward.filter(user_id=user.id).count() == 0


async def test_detail_read_finalizes_a_due_challenge_when_the_worker_is_delayed() -> None:
    user = await _user("read-fallback@example.com")
    template, badge = await _template_with_badge()
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.MEDICATION,
        challenge_name=template.name,
        idempotency_key="read-fallback",
        end_at=END_AT,
    )

    detail = await CustomChallengeService(now_provider=lambda: END_AT).get(user, participation.id)

    assert detail.status is ChallengeParticipationStatus.EXPIRED
    await participation.refresh_from_db()
    assert participation.finalized_at == END_AT


async def test_medication_undo_at_end_finalizes_before_mutating_the_dose() -> None:
    now = datetime.now(config.TIMEZONE)
    user = await _user("medication-race@example.com")
    template, badge = await _template_with_badge()
    episode = await CareEpisode.create(user=user, alias="종료 경계 처방")
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.MEDICATION,
        challenge_name=template.name,
        idempotency_key="medication-race",
        end_at=now,
    )
    target = await CustomChallengeTarget.create(
        participation=participation,
        care_episode=episode,
        source_id_snapshot=episode.id,
        target_name_snapshot="종료 경계 처방",
    )
    occurrence = await CustomChallengeOccurrence.create(
        target=target,
        scheduled_date=now.date(),
        slot=MealSlot.MORNING,
        scheduled_at=datetime.combine(now.date(), time(8), tzinfo=config.TIMEZONE),
    )
    await MedicationDose.create(
        user=user,
        care_episode=episode,
        dose_date=occurrence.scheduled_date,
        slot=occurrence.slot,
    )

    await MedicationService(mutation_time_provider=lambda: now).save_dose(
        user,
        SaveMedicationDoseRequest(
            date=now.date(),
            slot="morning",
            taken=False,
            record_id=episode.id,
        ),
    )

    assert await MedicationDose.filter(care_episode_id=episode.id).count() == 0
    frozen = await CustomChallengeService().get(user, participation.id)
    assert frozen.status is ChallengeParticipationStatus.COMPLETED
    assert (frozen.target_count, frozen.completed_count) == (1, 1)
    assert frozen.occurrences[0].is_completed is True
    assert await CustomChallengeBadgeAward.filter(participation_id=participation.id).count() == 1


async def test_supplement_undo_at_end_finalizes_before_mutating_the_dose() -> None:
    now = datetime.now(config.TIMEZONE)
    user = await _user("supplement-race@example.com")
    template, badge = await _template_with_badge()
    registration = await UserSupplementNutrient.create(
        user=user,
        custom_name="종료 경계 영양제",
        dose_amount=Decimal("1"),
        dose_unit="정",
        start_date=now.date(),
    )
    await UserSupplementNutrientSlot.create(
        user_suppl_nutrient=registration,
        slot=MealSlot.MORNING,
    )
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        reward_badge=badge,
        challenge_type=CustomChallengeType.SUPPLEMENT,
        challenge_name=template.name,
        idempotency_key="supplement-race",
        end_at=now,
    )
    target = await CustomChallengeTarget.create(
        participation=participation,
        supplement_registration=registration,
        source_id_snapshot=registration.id,
        target_name_snapshot="종료 경계 영양제",
    )
    occurrence = await CustomChallengeOccurrence.create(
        target=target,
        scheduled_date=now.date(),
        slot=MealSlot.MORNING,
        scheduled_at=datetime.combine(now.date(), time(8), tzinfo=config.TIMEZONE),
    )
    await SupplementDose.create(
        registration=registration,
        dose_date=occurrence.scheduled_date,
        slot=occurrence.slot,
    )

    await SupplementDoseService().save(
        user,
        SupplementDoseRequest(
            supplement_id=registration.id,
            date=now.date(),
            slot="morning",
            taken=False,
        ),
    )

    assert await SupplementDose.filter(registration_id=registration.id).count() == 0
    frozen = await CustomChallengeService().get(user, participation.id)
    assert frozen.status is ChallengeParticipationStatus.COMPLETED
    assert (frozen.target_count, frozen.completed_count) == (1, 1)
    assert frozen.occurrences[0].is_completed is True
