import sqlite3
from collections.abc import Collection
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exceptions import MedicationRecordForbiddenError, MedicationScheduleNotFoundError
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.dtos.medication_schedule import SaveMedicationScheduleRequest
from app.dtos.settings import NotifySettingsUpdateRequest
from app.dtos.user_supplement_nutrients import (
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
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
from app.models.supplement_nutrients import (
    SupplementNutrient,
    UserSupplementNutrient,
    UserSupplementNutrientSlot,
)
from app.models.users import User, UserSettings
from app.services.custom_challenge_schedule_reconciler import CustomChallengeScheduleReconciler
from app.services.custom_challenges import CustomChallengeService
from app.services.medication_schedule import MedicationScheduleService
from app.services.medications import MedicationService
from app.services.settings import NotifySettingsService
from app.services.user_supplement_nutrients import UserSupplementNutrientService

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
        group_code="CST_CHK_TYPE",
        group_name="미래 목표 재계산 테스트",
    )
    check_type = await CommonCode.create(
        group=group,
        detail_code="AUTO",
        detail_name="자동",
    )
    type_group = await CommonCodeGroup.create(category="CHL", group_code="CST_CHL_TYPE", group_name="맞춤 챌린지 유형")
    medication_type = await CommonCode.create(group=type_group, detail_code="MEDICATION", detail_name="복약")
    supplement_type = await CommonCode.create(group=type_group, detail_code="SUPPLEMENT", detail_name="영양제")
    medication = await CustomChallengeTemplate.create(
        name="7일 복약",
        check_type=check_type,
        challenge_type=medication_type,
        is_active=True,
    )
    supplement = await CustomChallengeTemplate.create(
        name="7일 영양제",
        check_type=check_type,
        challenge_type=supplement_type,
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


async def _standard_supplement(
    user: User,
    *,
    name: str = "표준 재계산 영양제",
) -> UserSupplementNutrient:
    product = await SupplementNutrient.create(
        food_code=f"RECON-{name}",
        name=name,
        basis_qty="1정",
        energy_kcal=0,
        protein_g=Decimal("0"),
        carb_g=Decimal("0"),
        serving_desc="1정",
        serving_size="1정",
        daily_freq="1회",
    )
    registration = await UserSupplementNutrient.create(
        user=user,
        supplement_nutrient=product,
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


def _schedule_request(
    medication_id: int,
    *,
    slots: list[str],
    morning: str = "08:00",
) -> SaveMedicationScheduleRequest:
    return SaveMedicationScheduleRequest.model_validate(
        {
            "start": {"date": JOINED_AT.date().isoformat(), "slot": "morning"},
            "mealTimes": {
                "morning": morning,
                "lunch": "13:00",
                "evening": "19:00",
                "bedtime": "22:00",
            },
            "medications": [{"medicationId": medication_id, "slots": slots}],
        }
    )


async def test_reconcile_updates_inserts_and_deletes_only_future_occurrences() -> None:
    user = await _user("future-diff@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(user)
    participation = await _join(user, medication_template, [episode.id], "future-diff")
    before = await _occurrences(participation)
    past = next(row for row in before if row.scheduled_date == CHANGED_AT.date() and row.slot is MealSlot.MORNING)
    retained = next(row for row in before if row.scheduled_date == date(2026, 9, 11) and row.slot is MealSlot.MORNING)
    removed = next(row for row in before if row.scheduled_date == CHANGED_AT.date() and row.slot is MealSlot.EVENING)
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
    original = next(row for row in before if row.scheduled_date == changed_at.date() and row.slot is MealSlot.MORNING)

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


async def test_ending_source_before_first_goal_keeps_empty_participation_readable() -> None:
    user = await _user("empty-goals@example.com")
    _, template = await _templates()
    registration = await _supplement(user, name="첫 목표 전 종료")
    participation = await _join(user, template, [registration.id], "empty-goals")
    service = UserSupplementNutrientService(mutation_time_provider=lambda: JOINED_AT)

    await service.complete(user, registration.id)

    challenges = CustomChallengeService(now_provider=lambda: JOINED_AT)
    detail = await challenges.get(user, participation.id)
    listing = await challenges.list(user)
    assert detail.target_count == detail.completed_count == 0
    assert detail.progress_rate == Decimal("0.00")
    assert detail.actual_end_date is None
    assert detail.status is ChallengeParticipationStatus.ACTIVE
    assert detail.occurrences == []
    assert listing.items == [detail]
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


@pytest.mark.parametrize("source_kind", ["MEDICATION", CustomChallengeType.VISIT])
async def test_reconcile_rejects_non_enum_and_unsupported_source_kinds(source_kind: object) -> None:
    user = await _user(f"invalid-kind-{source_kind!s}@example.com")

    async with in_transaction() as connection:
        with pytest.raises(ValueError, match="only medication and supplement"):
            await CustomChallengeScheduleReconciler().reconcile(
                user_id=user.id,
                source_kind=source_kind,  # type: ignore[arg-type]
                source_ids=None,
                changed_at=CHANGED_AT,
                connection=connection,
            )


async def test_medication_schedule_save_reconciles_only_changed_episode_when_times_match() -> None:
    user = await _user("schedule-target@example.com")
    medication_template, _ = await _templates()
    changed = await _episode(user, alias="변경 처방")
    untouched = await _episode(user, alias="유지 처방")
    changed_participation = await _join(user, medication_template, [changed.id], "schedule-changed")
    untouched_participation = await _join(user, medication_template, [untouched.id], "schedule-untouched")
    untouched_before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at))
        for row in await _occurrences(untouched_participation)
    ]
    medication = await Medication.get(care_episode_id=changed.id)
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    await MedicationScheduleService(mutation_time_provider=lambda: mutation_at).save(
        user,
        changed.id,
        _schedule_request(medication.id, slots=["morning", "lunch"]),
    )

    changed_after = await _occurrences(changed_participation)
    assert any(
        row.scheduled_date == mutation_at.date()
        and row.slot is MealSlot.MORNING
        and _aware(row.scheduled_at) < mutation_at
        for row in changed_after
    )
    assert any(row.slot is MealSlot.LUNCH and _aware(row.scheduled_at) >= mutation_at for row in changed_after)
    assert not any(row.slot is MealSlot.EVENING and _aware(row.scheduled_at) >= mutation_at for row in changed_after)
    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at))
        for row in await _occurrences(untouched_participation)
    ] == untouched_before


async def test_medication_duration_extension_moves_the_participation_end_to_the_episode_end() -> None:
    user = await _user("duration-extension@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(user, alias="기간 연장 처방")
    participation = await _join(user, medication_template, [episode.id], "duration-extension")
    medication = await Medication.get(care_episode_id=episode.id)

    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        await CareEpisode.filter(id=episode.id).using_db(connection).select_for_update().get()
        medication = await Medication.filter(id=medication.id).using_db(connection).select_for_update().get()
        medication.days = 30
        await medication.save(using_db=connection, update_fields=["days"])
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.MEDICATION,
            source_ids=(episode.id,),
            changed_at=CHANGED_AT,
            connection=connection,
        )

    await participation.refresh_from_db()
    assert _aware(participation.end_at) == datetime(2026, 10, 9, tzinfo=config.TIMEZONE)
    occurrences = await _occurrences(participation)
    assert occurrences[-1].scheduled_date == date(2026, 10, 8)


async def test_late_reconciliation_cannot_extend_an_already_due_participation() -> None:
    user = await _user("late-extension@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(user, alias="이미 종료된 처방")
    participation = await _join(user, medication_template, [episode.id], "late-extension")
    original_end_at = _aware(participation.end_at)
    medication = await Medication.get(care_episode_id=episode.id)
    changed_at = original_end_at + timedelta(days=1)

    async with in_transaction() as connection:
        await User.filter(id=user.id).using_db(connection).select_for_update().get()
        await CareEpisode.filter(id=episode.id).using_db(connection).select_for_update().get()
        medication = await Medication.filter(id=medication.id).using_db(connection).select_for_update().get()
        medication.days = 30
        await medication.save(using_db=connection, update_fields=["days"])
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.MEDICATION,
            source_ids=(episode.id,),
            changed_at=changed_at,
            connection=connection,
        )

    await participation.refresh_from_db()
    assert participation.status is ChallengeParticipationStatus.EXPIRED
    assert _aware(participation.end_at) == original_end_at
    assert _aware(participation.finalized_at) == changed_at


async def test_medication_schedule_global_time_change_reconciles_all_owned_types() -> None:
    owner = await _user("global-time-owner@example.com")
    other = await _user("global-time-other@example.com")
    medication_template, supplement_template = await _templates()
    first_episode = await _episode(owner, alias="첫 처방")
    second_episode = await _episode(owner, alias="둘째 처방")
    supplement = await _supplement(owner)
    other_supplement = await _supplement(other)
    first = await _join(owner, medication_template, [first_episode.id], "global-first")
    second = await _join(owner, medication_template, [second_episode.id], "global-second")
    nutrient = await _join(owner, supplement_template, [supplement.id], "global-supplement")
    foreign = await _join(other, supplement_template, [other_supplement.id], "global-foreign")
    foreign_before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(foreign)
    ]
    medication = await Medication.get(care_episode_id=first_episode.id)
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    await MedicationScheduleService(mutation_time_provider=lambda: mutation_at).save(
        owner,
        first_episode.id,
        _schedule_request(medication.id, slots=["morning", "evening"], morning="09:00"),
    )

    for participation in (first, second, nutrient):
        future_mornings = [
            row
            for row in await _occurrences(participation)
            if row.slot is MealSlot.MORNING and _aware(row.scheduled_at) >= mutation_at
        ]
        assert future_mornings
        assert {_aware(row.scheduled_at).time() for row in future_mornings} == {time(9, 0)}
    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(foreign)
    ] == foreign_before


async def test_medication_schedule_uses_one_post_lock_boundary_for_all_source_types() -> None:
    class RecordingReconciler(CustomChallengeScheduleReconciler):
        def __init__(self) -> None:
            self.changed_ats: list[datetime] = []

        async def reconcile(
            self,
            *,
            user_id: int,
            source_kind: CustomChallengeType,
            source_ids: Collection[int] | None,
            changed_at: datetime,
            connection: BaseDBAsyncClient,
        ) -> None:
            self.changed_ats.append(changed_at)
            await super().reconcile(
                user_id=user_id,
                source_kind=source_kind,
                source_ids=source_ids,
                changed_at=changed_at,
                connection=connection,
            )

    user = await _user("schedule-boundary@example.com")
    medication_template, supplement_template = await _templates()
    episode = await _episode(user)
    registration = await _supplement(user)
    medication_participation = await _join(
        user,
        medication_template,
        [episode.id],
        "schedule-boundary-med",
    )
    supplement_participation = await _join(
        user,
        supplement_template,
        [registration.id],
        "schedule-boundary-supp",
    )
    changed_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)
    just_before = changed_at - timedelta(microseconds=1)
    medication_row = next(
        row
        for row in await _occurrences(medication_participation)
        if row.scheduled_date == changed_at.date() and row.slot is MealSlot.MORNING
    )
    supplement_row = next(
        row
        for row in await _occurrences(supplement_participation)
        if row.scheduled_date == changed_at.date() and row.slot is MealSlot.MORNING
    )
    medication_row.scheduled_at = just_before
    supplement_row.scheduled_at = changed_at
    await medication_row.save(update_fields=["scheduled_at"])
    await supplement_row.save(update_fields=["scheduled_at"])
    provider_calls = 0

    def mutation_time() -> datetime:
        nonlocal provider_calls
        provider_calls += 1
        return changed_at

    reconciler = RecordingReconciler()
    medication = await Medication.get(care_episode_id=episode.id)
    await MedicationScheduleService(
        reconciler=reconciler,
        mutation_time_provider=mutation_time,
    ).save(
        user,
        episode.id,
        _schedule_request(medication.id, slots=["morning", "evening"], morning="09:30"),
    )

    assert provider_calls == 1
    assert reconciler.changed_ats == [changed_at, changed_at]
    assert _aware((await CustomChallengeOccurrence.get(id=medication_row.id)).scheduled_at) == just_before
    assert await CustomChallengeOccurrence.filter(id=supplement_row.id).exists() is False
    for participation in (medication_participation, supplement_participation):
        future_mornings = [
            row
            for row in await _occurrences(participation)
            if row.slot is MealSlot.MORNING and _aware(row.scheduled_at) >= changed_at
        ]
        assert future_mornings
        assert {_aware(row.scheduled_at).time() for row in future_mornings} == {time(9, 30)}


async def test_medication_schedule_and_cancel_preserve_owner_error_contracts() -> None:
    owner = await _user("med-owner@example.com")
    other = await _user("med-other@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(owner)
    participation = await _join(owner, medication_template, [episode.id], "med-owner")
    medication = await Medication.get(care_episode_id=episode.id)
    before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(participation)
    ]
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    with pytest.raises(MedicationScheduleNotFoundError):
        await MedicationScheduleService(mutation_time_provider=lambda: mutation_at).save(
            other,
            episode.id,
            _schedule_request(medication.id, slots=["morning", "lunch"]),
        )
    with pytest.raises(MedicationRecordForbiddenError):
        await MedicationService(mutation_time_provider=lambda: mutation_at).cancel(other, episode.id)

    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(participation)
    ] == before
    assert (await CareEpisode.get(id=episode.id)).status is CareEpisodeStatus.ACTIVE


async def test_medication_cancel_ends_and_finalizes_the_episode_challenge() -> None:
    user = await _user("cancel-goals@example.com")
    medication_template, _ = await _templates()
    episode = await _episode(user)
    participation = await _join(user, medication_template, [episode.id], "cancel-goals")
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    await MedicationService(mutation_time_provider=lambda: mutation_at).cancel(user, episode.id)

    remaining = await _occurrences(participation)
    assert len(remaining) == 1
    assert all(_aware(row.scheduled_at) < mutation_at for row in remaining)
    assert (await CareEpisode.get(id=episode.id)).status is CareEpisodeStatus.CANCELLED
    stored = await CustomChallengeParticipation.get(id=participation.id)
    assert stored.status is ChallengeParticipationStatus.EXPIRED
    assert _aware(stored.end_at) == mutation_at
    assert _aware(stored.finalized_at) == mutation_at
    assert await UserBadge.all().count() == 0


async def test_supplement_update_reconciles_only_selected_registration() -> None:
    owner = await _user("supp-update-owner@example.com")
    other = await _user("supp-update-other@example.com")
    _, supplement_template = await _templates()
    changed = await _supplement(owner, name="변경 영양제")
    sibling = await _supplement(owner, name="유지 영양제")
    foreign_registration = await _supplement(other, name="타인 영양제")
    participation = await _join(owner, supplement_template, [changed.id, sibling.id], "supp-update")
    foreign = await _join(other, supplement_template, [foreign_registration.id], "supp-update-other")
    sibling_target = await CustomChallengeTarget.get(
        participation_id=participation.id,
        source_id_snapshot=sibling.id,
    )
    sibling_before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at))
        for row in await CustomChallengeOccurrence.filter(target_id=sibling_target.id).order_by("id")
    ]
    foreign_before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(foreign)
    ]
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    await UserSupplementNutrientService(mutation_time_provider=lambda: mutation_at).update(
        owner,
        changed.id,
        UserSupplementNutrientUpdateRequest(slots=[MealSlot.LUNCH]),
    )

    changed_target = await CustomChallengeTarget.get(
        participation_id=participation.id,
        source_id_snapshot=changed.id,
    )
    changed_after = await CustomChallengeOccurrence.filter(target_id=changed_target.id)
    assert any(row.slot is MealSlot.MORNING and _aware(row.scheduled_at) < mutation_at for row in changed_after)
    assert not any(row.slot is MealSlot.MORNING and _aware(row.scheduled_at) >= mutation_at for row in changed_after)
    assert any(row.slot is MealSlot.LUNCH and _aware(row.scheduled_at) >= mutation_at for row in changed_after)
    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at))
        for row in await CustomChallengeOccurrence.filter(target_id=sibling_target.id).order_by("id")
    ] == sibling_before
    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(foreign)
    ] == foreign_before


async def test_supplement_upsert_reconciles_reused_registration() -> None:
    user = await _user("supp-upsert@example.com")
    _, supplement_template = await _templates()
    registration = await _standard_supplement(user)
    participation = await _join(user, supplement_template, [registration.id], "supp-upsert")
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    response = await UserSupplementNutrientService(mutation_time_provider=lambda: mutation_at).upsert(
        user,
        registration.supplement_nutrient_id,
        UserSupplementNutrientUpsertRequest(
            dose_amount=Decimal("2"),
            dose_unit="정",
            start_date=JOINED_AT.date(),
            slots=[MealSlot.EVENING],
        ),
    )

    assert response.id == registration.id
    rows = await _occurrences(participation)
    assert any(row.slot is MealSlot.MORNING and _aware(row.scheduled_at) < mutation_at for row in rows)
    assert not any(row.slot is MealSlot.MORNING and _aware(row.scheduled_at) >= mutation_at for row in rows)
    assert any(row.slot is MealSlot.EVENING and _aware(row.scheduled_at) >= mutation_at for row in rows)


async def test_supplement_complete_preserves_history_without_completion_or_award() -> None:
    user = await _user("supp-complete@example.com")
    _, supplement_template = await _templates()
    registration = await _supplement(user)
    participation = await _join(user, supplement_template, [registration.id], "supp-complete")
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    await UserSupplementNutrientService(mutation_time_provider=lambda: mutation_at).complete(
        user,
        registration.id,
    )

    rows = await _occurrences(participation)
    assert len(rows) == 1
    assert all(_aware(row.scheduled_at) < mutation_at for row in rows)
    assert (await CustomChallengeParticipation.get(id=participation.id)).status is ChallengeParticipationStatus.ACTIVE
    assert await ChallengeProgress.all().count() == 0
    assert await UserBadge.all().count() == 0


async def test_supplement_complete_reconciles_legacy_future_when_already_completed() -> None:
    user = await _user("supp-already-complete@example.com")
    _, supplement_template = await _templates()
    registration = await _supplement(user)
    participation = await _join(user, supplement_template, [registration.id], "supp-already-complete")
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)
    registration.status = SupplementStatus.COMPLETED
    registration.end_date = mutation_at.date()
    await registration.save(update_fields=["status", "end_date"])
    assert any(_aware(row.scheduled_at) >= mutation_at for row in await _occurrences(participation))

    await UserSupplementNutrientService(mutation_time_provider=lambda: mutation_at).complete(
        user,
        registration.id,
    )

    remaining = await _occurrences(participation)
    assert len(remaining) == 1
    assert all(_aware(row.scheduled_at) < mutation_at for row in remaining)
    assert (await CustomChallengeParticipation.get(id=participation.id)).status is ChallengeParticipationStatus.ACTIVE
    assert await ChallengeProgress.all().count() == 0
    assert await UserBadge.all().count() == 0


async def test_supplement_update_rejects_foreign_registration_without_goal_writes() -> None:
    owner = await _user("supp-foreign-owner@example.com")
    other = await _user("supp-foreign-other@example.com")
    _, supplement_template = await _templates()
    registration = await _supplement(owner)
    participation = await _join(owner, supplement_template, [registration.id], "supp-foreign")
    before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(participation)
    ]
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    with pytest.raises(HTTPException) as exc_info:
        await UserSupplementNutrientService(mutation_time_provider=lambda: mutation_at).update(
            other,
            registration.id,
            UserSupplementNutrientUpdateRequest(slots=[MealSlot.LUNCH]),
        )

    assert exc_info.value.status_code == 404
    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(participation)
    ] == before


async def test_notify_time_change_reconciles_all_owned_medication_and_supplement_goals() -> None:
    owner = await _user("notify-owner@example.com")
    other = await _user("notify-other@example.com")
    medication_template, supplement_template = await _templates()
    episode = await _episode(owner)
    supplement = await _supplement(owner)
    foreign_registration = await _supplement(other)
    medication = await _join(owner, medication_template, [episode.id], "notify-med")
    nutrient = await _join(owner, supplement_template, [supplement.id], "notify-supp")
    foreign = await _join(other, supplement_template, [foreign_registration.id], "notify-foreign")
    foreign_before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(foreign)
    ]
    mutation_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)

    await NotifySettingsService(mutation_time_provider=lambda: mutation_at).update(
        owner,
        NotifySettingsUpdateRequest(morning_medication_time=time(9, 30)),
    )

    for participation in (medication, nutrient):
        future_mornings = [
            row
            for row in await _occurrences(participation)
            if row.slot is MealSlot.MORNING and _aware(row.scheduled_at) >= mutation_at
        ]
        assert future_mornings
        assert {_aware(row.scheduled_at).time() for row in future_mornings} == {time(9, 30)}
    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(foreign)
    ] == foreign_before


async def test_notify_toggle_only_update_does_not_change_occurrences() -> None:
    class FailIfCalledReconciler(CustomChallengeScheduleReconciler):
        async def reconcile(self, **_: object) -> None:
            raise AssertionError("toggle-only updates must not reconcile custom challenges")

    user = await _user("notify-toggle@example.com")
    _, supplement_template = await _templates()
    registration = await _supplement(user)
    participation = await _join(user, supplement_template, [registration.id], "notify-toggle")
    before = [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(participation)
    ]

    await NotifySettingsService(
        reconciler=FailIfCalledReconciler(),
        mutation_time_provider=lambda: datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE),
    ).update(
        user,
        NotifySettingsUpdateRequest(notify_medication=True),
    )

    assert [
        (row.id, row.scheduled_date, row.slot, _aware(row.scheduled_at)) for row in await _occurrences(participation)
    ] == before


async def test_notify_time_change_uses_one_post_lock_boundary_for_all_source_types() -> None:
    class RecordingReconciler(CustomChallengeScheduleReconciler):
        def __init__(self) -> None:
            self.changed_ats: list[datetime] = []

        async def reconcile(
            self,
            *,
            user_id: int,
            source_kind: CustomChallengeType,
            source_ids: Collection[int] | None,
            changed_at: datetime,
            connection: BaseDBAsyncClient,
        ) -> None:
            self.changed_ats.append(changed_at)
            await super().reconcile(
                user_id=user_id,
                source_kind=source_kind,
                source_ids=source_ids,
                changed_at=changed_at,
                connection=connection,
            )

    user = await _user("notify-boundary@example.com")
    medication_template, supplement_template = await _templates()
    episode = await _episode(user)
    registration = await _supplement(user)
    medication = await _join(user, medication_template, [episode.id], "notify-boundary-med")
    nutrient = await _join(user, supplement_template, [registration.id], "notify-boundary-supp")
    changed_at = datetime(2026, 9, 9, 12, 0, tzinfo=config.TIMEZONE)
    just_before = changed_at - timedelta(microseconds=1)
    medication_row = next(
        row
        for row in await _occurrences(medication)
        if row.scheduled_date == changed_at.date() and row.slot is MealSlot.MORNING
    )
    supplement_row = next(
        row
        for row in await _occurrences(nutrient)
        if row.scheduled_date == changed_at.date() and row.slot is MealSlot.MORNING
    )
    medication_row.scheduled_at = just_before
    supplement_row.scheduled_at = changed_at
    await medication_row.save(update_fields=["scheduled_at"])
    await supplement_row.save(update_fields=["scheduled_at"])
    provider_calls = 0

    def mutation_time() -> datetime:
        nonlocal provider_calls
        provider_calls += 1
        return changed_at

    reconciler = RecordingReconciler()
    await NotifySettingsService(
        reconciler=reconciler,
        mutation_time_provider=mutation_time,
    ).update(
        user,
        NotifySettingsUpdateRequest(morning_medication_time=time(9, 30)),
    )

    assert provider_calls == 1
    assert reconciler.changed_ats == [changed_at, changed_at]
    assert _aware((await CustomChallengeOccurrence.get(id=medication_row.id)).scheduled_at) == just_before
    assert await CustomChallengeOccurrence.filter(id=supplement_row.id).exists() is False
    for participation in (medication, nutrient):
        future_mornings = [
            row
            for row in await _occurrences(participation)
            if row.slot is MealSlot.MORNING and _aware(row.scheduled_at) >= changed_at
        ]
        assert future_mornings
        assert {_aware(row.scheduled_at).time() for row in future_mornings} == {time(9, 30)}


def test_settings_routes_register_without_service_constructor_parameters() -> None:
    from app.main import app

    operations = app.openapi()["paths"]["/api/v1/me/settings"]
    assert {"get", "patch"} <= operations.keys()
    for method in ("get", "patch"):
        parameter_names = {parameter["name"] for parameter in operations[method].get("parameters", [])}
        assert parameter_names.isdisjoint({"reconciler", "mutation_time_provider"})
