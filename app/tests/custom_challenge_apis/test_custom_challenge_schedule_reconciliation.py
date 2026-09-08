import sqlite3
from datetime import date, datetime, time
from decimal import Decimal

import pytest_asyncio
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.models.care import CareEpisode
from app.models.challenges import ChallengeProgress, CustomChallengeTemplate, UserBadge
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import (
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import (
    AccountStatus,
    CareEpisodeStatus,
    ChallengeParticipationStatus,
    CustomChallengeType,
    MealSlot,
    SupplementStatus,
)
from app.models.medications import Medication, MedicationSlot
from app.models.supplement_nutrients import UserSupplementNutrient, UserSupplementNutrientSlot
from app.models.users import User, UserSettings
from app.services.custom_challenge_schedule_reconciler import CustomChallengeScheduleReconciler
from app.services.custom_challenges import CustomChallengeService

JOINED_AT = datetime(2026, 9, 9, 7, 30, tzinfo=config.TIMEZONE)
CHANGED_AT = datetime(2026, 9, 10, 12, 0, tzinfo=config.TIMEZONE)


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
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES = {}
    yield
    await Tortoise.close_connections()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=config.TIMEZONE)
    return value.astimezone(config.TIMEZONE)


async def _user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password="unused",
        name="일정 재계산 사용자",
        status=AccountStatus.ACTIVE,
    )


async def _templates() -> tuple[CustomChallengeTemplate, CustomChallengeTemplate]:
    group = await CommonCodeGroup.create(
        category="CHL",
        group_code="RECONCILE_TEST",
        group_name="미래 목표 재계산 테스트",
    )
    check_type = await CommonCode.create(
        group=group,
        detail_code="AUTO",
        detail_name="자동",
    )
    medication = await CustomChallengeTemplate.create(
        name="7일 복약",
        check_type=check_type,
        is_active=True,
    )
    supplement = await CustomChallengeTemplate.create(
        name="7일 영양제",
        check_type=check_type,
        is_active=True,
    )
    config.CUSTOM_CHALLENGE_TEMPLATE_TYPES = {
        medication.id: CustomChallengeType.MEDICATION,
        supplement.id: CustomChallengeType.SUPPLEMENT,
    }
    return medication, supplement


async def _episode(user: User, *, alias: str = "재계산 처방") -> CareEpisode:
    episode = await CareEpisode.create(
        user=user,
        alias=alias,
        status=CareEpisodeStatus.ACTIVE,
        medication_start_date=JOINED_AT.date(),
        medication_start_slot=MealSlot.MORNING,
        medication_days=7,
    )
    medication = await Medication.create(
        care_episode=episode,
        name="재계산 약",
        times_per_day=2,
        days=7,
    )
    await MedicationSlot.create(medication=medication, slot=MealSlot.MORNING)
    await MedicationSlot.create(medication=medication, slot=MealSlot.EVENING)
    return episode


async def _supplement(user: User, *, name: str = "재계산 영양제") -> UserSupplementNutrient:
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


async def _join(
    user: User,
    template: CustomChallengeTemplate,
    source_ids: list[int],
    key: str,
) -> CustomChallengeParticipation:
    response = await CustomChallengeService(now_provider=lambda: JOINED_AT).join(
        user,
        template.id,
        CustomChallengeJoinRequest(target_ids=source_ids, idempotency_key=key),
    )
    return await CustomChallengeParticipation.get(id=response.id)


async def _occurrences(participation: CustomChallengeParticipation) -> list[CustomChallengeOccurrence]:
    return await CustomChallengeOccurrence.filter(
        target__participation_id=participation.id,
    ).order_by("scheduled_at", "id")


async def test_reconcile_updates_inserts_and_deletes_only_future_occurrences() -> None:
    user = await _user("future-diff@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(user)
    participation = await _join(user, medication_template, [episode.id], "future-diff")
    before = await _occurrences(participation)
    past = next(
        row
        for row in before
        if row.scheduled_date == CHANGED_AT.date() and row.slot is MealSlot.MORNING
    )
    retained = next(
        row
        for row in before
        if row.scheduled_date == date(2026, 9, 11) and row.slot is MealSlot.MORNING
    )
    removed = next(
        row
        for row in before
        if row.scheduled_date == CHANGED_AT.date() and row.slot is MealSlot.EVENING
    )
    past_snapshot = (past.id, past.scheduled_date, past.slot, _aware(past.scheduled_at))

    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        await CareEpisode.filter(id=episode.id).using_db(connection).select_for_update().get()
        settings = await UserSettings.filter(user_id=user.id).using_db(connection).select_for_update().get()
        settings.morning_medication_time = time(9, 0)
        await settings.save(using_db=connection, update_fields=["morning_medication_time"])
        medication = await Medication.filter(care_episode_id=episode.id).using_db(connection).get()
        await MedicationSlot.filter(medication_id=medication.id).using_db(connection).delete()
        await MedicationSlot.bulk_create(
            [
                MedicationSlot(medication_id=medication.id, slot=MealSlot.MORNING),
                MedicationSlot(medication_id=medication.id, slot=MealSlot.LUNCH),
            ],
            using_db=connection,
        )
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.MEDICATION,
            source_ids=(episode.id,),
            changed_at=CHANGED_AT,
            connection=connection,
        )

    after = await _occurrences(participation)
    preserved = await CustomChallengeOccurrence.get(id=past.id)
    updated = await CustomChallengeOccurrence.get(id=retained.id)
    assert (preserved.id, preserved.scheduled_date, preserved.slot, _aware(preserved.scheduled_at)) == past_snapshot
    assert _aware(updated.scheduled_at) == datetime(2026, 9, 11, 9, 0, tzinfo=config.TIMEZONE)
    assert not any(row.id == removed.id for row in after)
    assert any(
        row.scheduled_date == CHANGED_AT.date()
        and row.slot is MealSlot.LUNCH
        and _aware(row.scheduled_at) == datetime(2026, 9, 10, 13, 0, tzinfo=config.TIMEZONE)
        for row in after
    )
    assert not any(row.slot is MealSlot.EVENING and _aware(row.scheduled_at) >= CHANGED_AT for row in after)


async def test_reconcile_does_not_recreate_past_key_moved_after_changed_at() -> None:
    user = await _user("past-key@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(user)
    participation = await _join(user, medication_template, [episode.id], "past-key")
    changed_at = datetime(2026, 9, 9, 9, 0, tzinfo=config.TIMEZONE)
    before = await _occurrences(participation)
    original = next(
        row
        for row in before
        if row.scheduled_date == changed_at.date() and row.slot is MealSlot.MORNING
    )

    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        await CareEpisode.filter(id=episode.id).using_db(connection).select_for_update().get()
        settings = await UserSettings.filter(user_id=user.id).using_db(connection).select_for_update().get()
        settings.morning_medication_time = time(10, 0)
        await settings.save(using_db=connection, update_fields=["morning_medication_time"])
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.MEDICATION,
            source_ids=(episode.id,),
            changed_at=changed_at,
            connection=connection,
        )

    same_key = await CustomChallengeOccurrence.filter(
        target__participation_id=participation.id,
        scheduled_date=changed_at.date(),
        slot=MealSlot.MORNING,
    )
    assert [(row.id, _aware(row.scheduled_at)) for row in same_key] == [
        (original.id, datetime(2026, 9, 9, 8, 0, tzinfo=config.TIMEZONE))
    ]


async def test_reconcile_is_owner_scoped_and_zero_future_does_not_complete_or_award() -> None:
    owner = await _user("zero-owner@example.com")
    other = await _user("zero-other@example.com")
    _, supplement_template = await _templates()
    owned_registration = await _supplement(owner, name="완료 영양제")
    other_registration = await _supplement(other, name="타인 영양제")
    owned = await _join(owner, supplement_template, [owned_registration.id], "zero-owner")
    foreign = await _join(other, supplement_template, [other_registration.id], "zero-other")
    foreign_before = [(row.id, _aware(row.scheduled_at)) for row in await _occurrences(foreign)]

    async with in_transaction() as connection:
        await User.filter(id=owner.id).using_db(connection).select_for_update().get()
        registration = (
            await UserSupplementNutrient.filter(id=owned_registration.id, user_id=owner.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        await UserSettings.filter(user_id=owner.id).using_db(connection).select_for_update().get()
        registration.status = SupplementStatus.COMPLETED
        registration.end_date = CHANGED_AT.date()
        await registration.save(using_db=connection, update_fields=["status", "end_date"])
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=owner.id,
            source_kind=CustomChallengeType.SUPPLEMENT,
            source_ids=(owned_registration.id,),
            changed_at=CHANGED_AT,
            connection=connection,
        )

    owned_after = await _occurrences(owned)
    assert len(owned_after) == 2
    assert all(_aware(row.scheduled_at) < CHANGED_AT for row in owned_after)
    assert [(row.id, _aware(row.scheduled_at)) for row in await _occurrences(foreign)] == foreign_before
    assert (await CustomChallengeParticipation.get(id=owned.id)).status is ChallengeParticipationStatus.ACTIVE
    assert (await CustomChallengeParticipation.get(id=foreign.id)).status is ChallengeParticipationStatus.ACTIVE
    assert await ChallengeProgress.all().count() == 0
    assert await UserBadge.all().count() == 0


async def test_reconcile_null_source_fk_never_reattaches_reused_snapshot_id() -> None:
    user = await _user("deleted-source@example.com")
    _, supplement_template = await _templates()
    registration = await _supplement(user, name="삭제 영양제")
    participation = await _join(user, supplement_template, [registration.id], "deleted-source")
    target = await CustomChallengeTarget.get(participation_id=participation.id)

    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        locked = (
            await UserSupplementNutrient.filter(id=registration.id, user_id=user.id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        await UserSettings.filter(user_id=user.id).using_db(connection).select_for_update().get()
        await locked.delete(using_db=connection)
        replacement = await UserSupplementNutrient.create(
            id=registration.id,
            user_id=user.id,
            custom_name="재사용 ID 영양제",
            dose_amount=Decimal("1"),
            dose_unit="정",
            start_date=JOINED_AT.date(),
            status=SupplementStatus.ACTIVE,
            using_db=connection,
        )
        await UserSupplementNutrientSlot.create(
            user_suppl_nutrient_id=replacement.id,
            slot=MealSlot.EVENING,
            using_db=connection,
        )
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.SUPPLEMENT,
            source_ids=(registration.id,),
            changed_at=CHANGED_AT,
            connection=connection,
        )

    await target.refresh_from_db()
    remaining = await _occurrences(participation)
    assert target.supplement_registration_id is None
    assert len(remaining) == 2
    assert all(_aware(row.scheduled_at) < CHANGED_AT for row in remaining)
    assert not any(row.slot is MealSlot.EVENING for row in remaining)
