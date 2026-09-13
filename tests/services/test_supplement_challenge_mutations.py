"""Approved #456 policies exercised through real services and disposable SQLite."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.dtos.settings import NotifySettingsUpdateRequest
from app.dtos.user_supplement_nutrients import UserSupplementNutrientUpdateRequest, UserSupplementNutrientUpsertRequest
from app.models.custom_challenges import (
    CustomChallengeBadgeAward,
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
)
from app.models.enums import ChallengeParticipationStatus, CustomChallengeType, MealSlot, SupplementStatus
from app.models.supplement_nutrients import SupplementDose, UserSupplementNutrient, UserSupplementNutrientSlot
from app.models.users import UserSettings
from app.services.custom_challenge_schedule_reconciler import CustomChallengeScheduleReconciler
from app.services.custom_challenges import CustomChallengeService
from app.services.settings import NotifySettingsService
from app.services.user_supplement_nutrients import UserSupplementNutrientService
from app.tests.custom_challenge_apis.test_custom_challenge_schedule_reconciliation import (
    CHANGED_AT,
    JOINED_AT,
    _aware,
    _join,
    _occurrences,
    _standard_supplement,
    _supplement,
    _templates,
    _user,
)
from app.tests.custom_challenge_apis.test_custom_challenge_schedule_reconciliation import (
    initialized_db as initialized_db,
)


async def _taken(registration, day, slot):
    return await SupplementDose.create(registration=registration, dose_date=day, slot=slot)


async def test_removing_one_target_keeps_sibling_and_completed_history_then_last_removal_cancels():
    owner = await _user("remove-owner@example.com")
    other = await _user("remove-other@example.com")
    _, template = await _templates()
    removed = await _supplement(owner, name="삭제 대상")
    sibling = await _supplement(owner, name="유지 대상")
    foreign_source = await _supplement(other)
    participation = await _join(owner, template, [removed.id, sibling.id], "remove-multiple")
    foreign = await _join(other, template, [foreign_source.id], "foreign")
    for day in (JOINED_AT.date(), CHANGED_AT.date()):
        await _taken(removed, day, MealSlot.MORNING)
    before = await CustomChallengeService(now_provider=lambda: CHANGED_AT).get(owner, participation.id)
    foreign_before = await CustomChallengeService(now_provider=lambda: CHANGED_AT).get(other, foreign.id)
    removed_target = next(target for target in before.targets if target.source_id == removed.id)
    sibling_target = next(target for target in before.targets if target.source_id == sibling.id)
    service = UserSupplementNutrientService(mutation_time_provider=lambda: CHANGED_AT)

    await service.complete(owner, removed.id)

    challenges = CustomChallengeService(now_provider=lambda: CHANGED_AT)
    detail = await challenges.get(owner, participation.id)
    assert detail.status is ChallengeParticipationStatus.ACTIVE
    assert [o for o in detail.occurrences if o.target_id == sibling_target.id] == [
        o for o in before.occurrences if o.target_id == sibling_target.id
    ]
    assert [o for o in detail.occurrences if o.target_id == removed_target.id] == [
        o for o in before.occurrences if o.target_id == removed_target.id and o.is_completed
    ]
    assert detail.completed_count == 2
    assert detail.target_count == 9
    assert detail.progress_rate == Decimal("22.22")
    assert await challenges.get(other, foreign.id) == foreign_before
    await service.complete(owner, removed.id)
    assert await challenges.get(owner, participation.id) == detail

    await service.complete(owner, sibling.id)

    frozen = await challenges.get(owner, participation.id)
    assert frozen.status is ChallengeParticipationStatus.CANCELLED
    assert frozen.completed_count == 2
    assert frozen.target_count == 3  # Two completed removed goals + sibling's prior-day history.
    assert frozen.progress_rate == Decimal("66.67")
    assert await SupplementDose.filter(registration_id=removed.id).count() == 2
    assert await CustomChallengeBadgeAward.all().count() == 0
    await SupplementDose.filter(registration_id=removed.id).delete()
    await service.complete(owner, sibling.id)
    assert await challenges.get(owner, participation.id) == frozen
    assert (await challenges.list(owner)).items == [frozen]


async def test_last_target_removed_before_first_goal_keeps_cancelled_empty_history():
    user = await _user("remove-empty@example.com")
    _, template = await _templates()
    source = await _supplement(user)
    participation = await _join(user, template, [source.id], "empty")

    await UserSupplementNutrientService(mutation_time_provider=lambda: JOINED_AT).complete(user, source.id)

    detail = await CustomChallengeService(now_provider=lambda: JOINED_AT).get(user, participation.id)
    assert detail.status is ChallengeParticipationStatus.CANCELLED
    assert detail.target_count == detail.completed_count == 0
    assert detail.progress_rate == Decimal("0.00")
    assert detail.occurrences == []
    assert len(detail.targets) == 1


async def test_removed_target_is_excluded_but_retains_snapshot_identity_and_name_in_response():
    user = await _user("excluded-label@example.com")
    _, template = await _templates()
    removed = await _supplement(user, name="기록에 남는 이름")
    sibling = await _supplement(user, name="현재 참여 대상")
    participation = await _join(user, template, [removed.id, sibling.id], "labels")
    challenges = CustomChallengeService(now_provider=lambda: CHANGED_AT)

    await UserSupplementNutrientService(mutation_time_provider=lambda: CHANGED_AT).complete(user, removed.id)

    detail = (await challenges.get(user, participation.id)).model_dump(by_alias=True)
    removed_response = next(target for target in detail["targets"] if target["sourceId"] == removed.id)
    sibling_response = next(target for target in detail["targets"] if target["sourceId"] == sibling.id)
    assert removed_response.get("isExcluded") is True
    assert removed_response["name"] == "기록에 남는 이름"
    assert sibling_response.get("isExcluded") is False


@pytest.mark.parametrize("operation", ["update", "upsert"])
@pytest.mark.parametrize("completed_today", [False, True])
async def test_slot_change_reconciles_elapsed_pending_today_but_preserves_completed_and_prior_days(
    operation, completed_today
):
    user = await _user("change-slots@example.com")
    _, template = await _templates()
    source = await _standard_supplement(user)
    participation = await _join(user, template, [source.id], "slots")
    if completed_today:
        await _taken(source, CHANGED_AT.date(), MealSlot.MORNING)
    before = await _occurrences(participation)
    yesterday = next(o for o in before if o.scheduled_date == JOINED_AT.date())
    today = next(o for o in before if o.scheduled_date == CHANGED_AT.date())
    service = UserSupplementNutrientService(mutation_time_provider=lambda: CHANGED_AT)

    if operation == "update":
        await service.update(user, source.id, UserSupplementNutrientUpdateRequest(slots=[MealSlot.EVENING]))
    else:
        await service.upsert(
            user,
            source.supplement_nutrient_id,
            UserSupplementNutrientUpsertRequest(
                dose_amount=Decimal("1"), dose_unit="정", start_date=JOINED_AT.date(), slots=[MealSlot.EVENING]
            ),
        )

    after = await _occurrences(participation)
    assert await CustomChallengeOccurrence.filter(id=today.id).exists() is completed_today
    assert _aware((await CustomChallengeOccurrence.get(id=yesterday.id)).scheduled_at) == _aware(yesterday.scheduled_at)
    assert {(o.scheduled_date, o.slot) for o in after if o.scheduled_date >= CHANGED_AT.date()} == {
        (CHANGED_AT.date() + timedelta(days=offset), MealSlot.EVENING) for offset in range(6)
    } | ({(CHANGED_AT.date(), MealSlot.MORNING)} if completed_today else set())
    detail = await CustomChallengeService(now_provider=lambda: CHANGED_AT).get(user, participation.id)
    assert detail.completed_count == int(completed_today)
    assert detail.target_count == 7 + int(completed_today)


async def test_early_completed_evening_survives_slot_removal_and_clock_changes():
    user = await _user("early-complete@example.com")
    _, template = await _templates()
    source = await _supplement(user)
    await UserSupplementNutrientSlot.create(user_suppl_nutrient=source, slot=MealSlot.EVENING)
    participation = await _join(user, template, [source.id], "early")
    await _taken(source, CHANGED_AT.date(), MealSlot.EVENING)
    before = await _occurrences(participation)
    evening = next(o for o in before if o.scheduled_date == CHANGED_AT.date() and o.slot is MealSlot.EVENING)

    await NotifySettingsService(mutation_time_provider=lambda: CHANGED_AT).update(
        user, NotifySettingsUpdateRequest(evening_medication_time=time(21))
    )
    assert _aware((await CustomChallengeOccurrence.get(id=evening.id)).scheduled_at) == _aware(evening.scheduled_at)
    await UserSupplementNutrientService(mutation_time_provider=lambda: CHANGED_AT).update(
        user, source.id, UserSupplementNutrientUpdateRequest(slots=[MealSlot.LUNCH])
    )

    detail = await CustomChallengeService(now_provider=lambda: CHANGED_AT).get(user, participation.id)
    assert next(o for o in detail.occurrences if o.id == evening.id).is_completed
    assert not [o for o in detail.occurrences if o.scheduled_date > CHANGED_AT.date() and o.slot is MealSlot.EVENING]
    assert detail.completed_count == 1


async def test_elapsed_pending_clock_change_moves_today_and_new_elapsed_slot_is_reconciled():
    user = await _user("elapsed-clock@example.com")
    _, template = await _templates()
    source = await _supplement(user)
    participation = await _join(user, template, [source.id], "clock")
    before = await _occurrences(participation)
    today = next(o for o in before if o.scheduled_date == CHANGED_AT.date())

    await NotifySettingsService(mutation_time_provider=lambda: CHANGED_AT).update(
        user, NotifySettingsUpdateRequest(morning_medication_time=time(10))
    )

    assert _aware((await CustomChallengeOccurrence.get(id=today.id)).scheduled_at) == datetime(
        2026, 9, 10, 10, tzinfo=config.TIMEZONE
    )
    await UserSupplementNutrientService(mutation_time_provider=lambda: CHANGED_AT.replace(hour=20)).update(
        user, source.id, UserSupplementNutrientUpdateRequest(slots=[MealSlot.LUNCH])
    )
    detail = await CustomChallengeService(now_provider=lambda: CHANGED_AT.replace(hour=20)).get(user, participation.id)
    assert [(o.slot, o.is_completed) for o in detail.occurrences if o.scheduled_date == CHANGED_AT.date()] == [
        (MealSlot.LUNCH, False)
    ]


@pytest.mark.parametrize(
    ("changed_clock", "expected_slots"),
    [
        (time(20, 1), [MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME]),
        (time(23, 57, 59), [MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME]),
        (time(23, 58), [MealSlot.EVENING, MealSlot.BEDTIME]),
        (time(23, 59, 59), [MealSlot.EVENING, MealSlot.BEDTIME]),
    ],
)
async def test_join_day_clock_change_recomputes_current_slot_at_change_time(changed_clock, expected_slots):
    user, source, participation, joined_at = await _late_join_supplement()
    changed_at = datetime.combine(joined_at.date(), changed_clock, tzinfo=config.TIMEZONE)
    before = await _occurrences(participation)
    today_before = [o for o in before if o.scheduled_date == joined_at.date()]
    assert [o.slot for o in today_before] == [MealSlot.EVENING, MealSlot.BEDTIME]

    service = NotifySettingsService(mutation_time_provider=lambda: changed_at)
    request = NotifySettingsUpdateRequest(evening_medication_time=time(23, 58))
    await service.update(user, request)

    detail = await CustomChallengeService(now_provider=lambda: changed_at).get(user, participation.id)
    today = [o for o in detail.occurrences if o.scheduled_date == joined_at.date()]
    assert [o.slot for o in today] == expected_slots
    assert not any(o.is_completed for o in today)
    assert {o.id for o in today_before} <= {o.id for o in today}
    assert [o.scheduled_at.time() for o in today if o.slot is not MealSlot.LUNCH] == [time(23, 58), time(23, 59)]
    await service.update(user, request)
    assert await CustomChallengeService(now_provider=lambda: changed_at).get(user, participation.id) == detail

    if MealSlot.LUNCH in expected_slots:
        dose = await _taken(source, joined_at.date(), MealSlot.LUNCH)
        await SupplementDose.filter(id=dose.id).update(taken_at=changed_at)
        completed = await CustomChallengeService(now_provider=lambda: changed_at).get(user, participation.id)
        assert completed.completed_count == 1
        await dose.delete()
        undone = await CustomChallengeService(now_provider=lambda: changed_at).get(user, participation.id)
        assert undone.completed_count == 0
        assert [o.id for o in undone.occurrences] == [o.id for o in detail.occurrences]


async def _late_join_supplement(*, lunch_taken_before_join=False):
    user = await _user("late-clock@example.com")
    _, template = await _templates()
    source = await _supplement(user)
    await UserSupplementNutrientSlot.filter(user_suppl_nutrient_id=source.id).delete()
    for slot in (MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME):
        await UserSupplementNutrientSlot.create(user_suppl_nutrient=source, slot=slot)
    await UserSettings.create(
        user=user,
        lunch_medication_time=time(13),
        evening_medication_time=time(18),
        bedtime_medication_time=time(23, 59),
    )
    joined_at = JOINED_AT.replace(hour=20, minute=0)
    if lunch_taken_before_join:
        dose = await _taken(source, joined_at.date(), MealSlot.LUNCH)
        await SupplementDose.filter(id=dose.id).update(taken_at=joined_at - timedelta(hours=1))
    joined = await CustomChallengeService(now_provider=lambda: joined_at).join(
        user, template.id, CustomChallengeJoinRequest(target_ids=[source.id], idempotency_key="late-clock")
    )
    return user, source, await CustomChallengeParticipation.get(id=joined.id), joined_at


async def test_join_day_clock_change_does_not_restore_prejoin_completion_or_move_completed_goal():
    user, source, participation, joined_at = await _late_join_supplement(lunch_taken_before_join=True)
    dose = await _taken(source, joined_at.date(), MealSlot.EVENING)
    await SupplementDose.filter(id=dose.id).update(taken_at=joined_at + timedelta(seconds=1))
    before = await CustomChallengeService(now_provider=lambda: joined_at).get(user, participation.id)
    evening = next(o for o in before.occurrences if o.scheduled_date == joined_at.date() and o.slot is MealSlot.EVENING)
    changed_at = joined_at + timedelta(minutes=1)

    await NotifySettingsService(mutation_time_provider=lambda: changed_at).update(
        user, NotifySettingsUpdateRequest(evening_medication_time=time(23, 58))
    )

    detail = await CustomChallengeService(now_provider=lambda: changed_at).get(user, participation.id)
    today = [o for o in detail.occurrences if o.scheduled_date == joined_at.date()]
    assert [o.slot for o in today] == [MealSlot.EVENING, MealSlot.BEDTIME]
    assert next(o for o in today if o.slot is MealSlot.EVENING) == evening
    assert evening.is_completed
    assert detail.completed_count == 1


async def test_midnight_clock_change_keeps_prior_day_and_full_new_day():
    user, _, participation, joined_at = await _late_join_supplement()
    before = await _occurrences(participation)
    changed_at = (joined_at + timedelta(days=1)).replace(hour=0, minute=0)

    await NotifySettingsService(mutation_time_provider=lambda: changed_at).update(
        user, NotifySettingsUpdateRequest(evening_medication_time=time(23, 58))
    )

    after = await _occurrences(participation)
    assert [(o.id, o.slot, o.scheduled_at) for o in after if o.scheduled_date == joined_at.date()] == [
        (o.id, o.slot, o.scheduled_at) for o in before if o.scheduled_date == joined_at.date()
    ]
    assert [(o.slot, _aware(o.scheduled_at).time()) for o in after if o.scheduled_date == changed_at.date()] == [
        (MealSlot.LUNCH, time(13)),
        (MealSlot.EVENING, time(23, 58)),
        (MealSlot.BEDTIME, time(23, 59)),
    ]


@pytest.mark.parametrize(
    ("changed_clock", "expected_slots"),
    [
        (time(23, 57, 59), [MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME]),
        (time(23, 58), [MealSlot.EVENING, MealSlot.BEDTIME]),
    ],
)
async def test_join_day_reconciliation_handles_existing_equal_clock_data(changed_clock, expected_slots):
    user, source, participation, joined_at = await _late_join_supplement()
    changed_at = datetime.combine(joined_at.date(), changed_clock, tzinfo=config.TIMEZONE)
    # The settings API rejects equal clocks. Exercise legacy/imported data at
    # the real reconciliation boundary without relaxing that validation.
    await UserSettings.filter(user_id=user.id).update(
        evening_medication_time=time(23, 58), bedtime_medication_time=time(23, 58)
    )
    async with in_transaction() as connection:
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.SUPPLEMENT,
            source_ids=[source.id],
            changed_at=changed_at,
            connection=connection,
            refresh_join_day_slot=True,
        )
    detail = await CustomChallengeService(now_provider=lambda: changed_at).get(user, participation.id)
    today = [o for o in detail.occurrences if o.scheduled_date == joined_at.date()]
    assert {o.slot for o in today} == set(expected_slots)
    assert [o.scheduled_at.time() for o in today if o.slot is not MealSlot.LUNCH] == [time(23, 58), time(23, 58)]


async def _morning_only_late_join(*, evening_taken_before_join=False, joined_at=None):
    user = await _user("add-slots@example.com")
    _, template = await _templates()
    source = await _standard_supplement(user)
    await UserSettings.create(
        user=user,
        morning_medication_time=time(8),
        lunch_medication_time=time(13),
        evening_medication_time=time(18, 52),
        bedtime_medication_time=time(23, 59),
    )
    joined_at = joined_at or JOINED_AT.replace(hour=20, minute=0)
    if evening_taken_before_join:
        dose = await _taken(source, joined_at.date(), MealSlot.EVENING)
        await SupplementDose.filter(id=dose.id).update(taken_at=joined_at - timedelta(minutes=1))
    joined = await CustomChallengeService(now_provider=lambda: joined_at).join(
        user, template.id, CustomChallengeJoinRequest(target_ids=[source.id], idempotency_key="add-slots")
    )
    return user, source, joined, joined_at


async def _save_supplement_slots(operation, user, source, slots, changed_at):
    service = UserSupplementNutrientService(mutation_time_provider=lambda: changed_at)
    if operation == "update":
        await service.update(user, source.id, UserSupplementNutrientUpdateRequest(slots=slots))
    else:
        await service.upsert(
            user,
            source.supplement_nutrient_id,
            UserSupplementNutrientUpsertRequest(
                dose_amount=Decimal("1"),
                dose_unit="정",
                start_date=source.start_date,
                slots=slots,
            ),
        )


@pytest.mark.parametrize("operation", ["update", "upsert"])
@pytest.mark.parametrize(
    ("changed_clock", "expected_slots"),
    [
        (time(20, 5), [MealSlot.EVENING, MealSlot.BEDTIME]),
        (time(23, 59), [MealSlot.BEDTIME]),
    ],
)
async def test_adding_slots_on_join_day_starts_at_current_slot(operation, changed_clock, expected_slots):
    user, source, joined, joined_at = await _morning_only_late_join()
    assert not [o for o in joined.occurrences if o.scheduled_date == joined_at.date()]
    changed_at = datetime.combine(joined_at.date(), changed_clock, tzinfo=config.TIMEZONE)

    await _save_supplement_slots(operation, user, source, list(MealSlot), changed_at)

    challenges = CustomChallengeService(now_provider=lambda: changed_at)
    detail = await challenges.get(user, joined.id)
    assert [o.slot for o in detail.occurrences if o.scheduled_date == joined_at.date()] == expected_slots
    assert not any(o.is_completed for o in detail.occurrences)
    assert detail.end_at == joined.end_at
    assert len([o for o in detail.occurrences if o.scheduled_date > joined_at.date()]) == 24
    await _save_supplement_slots(operation, user, source, list(MealSlot), changed_at + timedelta(seconds=1))
    assert await challenges.get(user, joined.id) == detail
    if MealSlot.EVENING in expected_slots:
        dose = await _taken(source, joined_at.date(), MealSlot.EVENING)
        await SupplementDose.filter(id=dose.id).update(taken_at=changed_at)
        assert (await challenges.get(user, joined.id)).completed_count == 1
        await dose.delete()
        assert await challenges.get(user, joined.id) == detail


@pytest.mark.parametrize("operation", ["update", "upsert"])
async def test_adding_slots_does_not_restore_prejoin_taken_current_slot(operation):
    user, source, joined, joined_at = await _morning_only_late_join(evening_taken_before_join=True)
    changed_at = joined_at + timedelta(minutes=5)
    await _save_supplement_slots(operation, user, source, list(MealSlot), changed_at)
    detail = await CustomChallengeService(now_provider=lambda: changed_at).get(user, joined.id)
    assert [o.slot for o in detail.occurrences if o.scheduled_date == joined_at.date()] == [MealSlot.BEDTIME]
    assert detail.completed_count == 0


@pytest.mark.parametrize("operation", ["update", "upsert"])
async def test_adding_slots_after_midnight_preserves_prior_day_and_includes_full_today(operation):
    user, source, joined, joined_at = await _morning_only_late_join(joined_at=JOINED_AT)
    dose = await _taken(source, joined_at.date(), MealSlot.MORNING)
    await SupplementDose.filter(id=dose.id).update(taken_at=joined_at + timedelta(hours=1))
    before = await CustomChallengeService(now_provider=lambda: joined_at).get(user, joined.id)
    changed_at = (joined_at + timedelta(days=1)).replace(hour=0, minute=0)

    await _save_supplement_slots(operation, user, source, list(MealSlot), changed_at)

    detail = await CustomChallengeService(now_provider=lambda: changed_at).get(user, joined.id)
    assert [o for o in detail.occurrences if o.scheduled_date == joined_at.date()] == [
        o for o in before.occurrences if o.scheduled_date == joined_at.date()
    ]
    assert [o.slot for o in detail.occurrences if o.scheduled_date == changed_at.date()] == list(MealSlot)
    assert detail.completed_count == 1


@pytest.mark.parametrize("operation", ["update", "upsert", "quantity_only"])
async def test_saving_unchanged_slots_does_not_repair_absent_join_day_history(operation):
    user, source, joined, joined_at = await _morning_only_late_join()
    # Simulate an existing registration with the previously strict join-day snapshot.
    for slot in (MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME):
        await UserSupplementNutrientSlot.create(user_suppl_nutrient=source, slot=slot)
    changed_at = joined_at + timedelta(minutes=5)
    if operation == "quantity_only":
        await UserSupplementNutrientService(mutation_time_provider=lambda: changed_at).update(
            user, source.id, UserSupplementNutrientUpdateRequest(dose_amount=Decimal("2"))
        )
    else:
        await _save_supplement_slots(operation, user, source, list(MealSlot), changed_at)
    detail = await CustomChallengeService(now_provider=lambda: changed_at).get(user, joined.id)
    assert [o.slot for o in detail.occurrences if o.scheduled_date == joined_at.date()] == [MealSlot.BEDTIME]


async def test_foreign_removal_rejected_and_reconciliation_failure_rolls_back_source_and_goals():
    class FailingReconciler(CustomChallengeScheduleReconciler):
        async def reconcile(self, **kwargs):
            await super().reconcile(**kwargs)
            raise RuntimeError("reconcile failed")

    user = await _user("rollback-owner@example.com")
    other = await _user("rollback-other@example.com")
    _, template = await _templates()
    source = await _supplement(user)
    participation = await _join(user, template, [source.id], "rollback")
    challenges = CustomChallengeService(now_provider=lambda: CHANGED_AT)
    before = await challenges.get(user, participation.id)
    service = UserSupplementNutrientService(reconciler=FailingReconciler(), mutation_time_provider=lambda: CHANGED_AT)

    with pytest.raises(HTTPException) as error:
        await service.complete(other, source.id)
    assert error.value.status_code == 404
    with pytest.raises(RuntimeError, match="reconcile failed"):
        await service.complete(user, source.id)

    assert (await UserSupplementNutrient.get(id=source.id)).status is SupplementStatus.ACTIVE
    assert (await CustomChallengeParticipation.get(id=participation.id)).finalized_at is None
    assert await challenges.get(user, participation.id) == before


async def test_readding_same_product_does_not_restore_removed_target_or_rewrite_its_completion():
    user = await _user("readd@example.com")
    _, template = await _templates()
    removed = await _standard_supplement(user)
    sibling = await _supplement(user)
    participation = await _join(user, template, [removed.id, sibling.id], "original")
    await _taken(removed, CHANGED_AT.date(), MealSlot.MORNING)
    service = UserSupplementNutrientService(mutation_time_provider=lambda: CHANGED_AT)
    challenges = CustomChallengeService(now_provider=lambda: CHANGED_AT)

    await service.complete(user, removed.id)
    before = await challenges.get(user, participation.id)
    await SupplementDose.filter(registration_id=removed.id).delete()
    readded = await service.upsert(
        user,
        removed.supplement_nutrient_id,
        UserSupplementNutrientUpsertRequest(
            dose_amount=Decimal("1"), dose_unit="정", start_date=CHANGED_AT.date(), slots=[MealSlot.EVENING]
        ),
    )

    assert readded.id == removed.id
    assert await challenges.get(user, participation.id) == before
    recommended = await challenges.recommendations(user)
    target = next(target for item in recommended.items for target in item.targets if target.id == removed.id)
    assert target.existing_participation_id is None
    fresh = await challenges.join(
        user, template.id, CustomChallengeJoinRequest(target_ids=[removed.id], idempotency_key="readded")
    )
    assert fresh.id != participation.id
    await service.update(user, removed.id, UserSupplementNutrientUpdateRequest(slots=[MealSlot.LUNCH]))
    assert await challenges.get(user, participation.id) == before
    await service.complete(user, sibling.id)
    frozen = await challenges.get(user, participation.id)
    assert frozen.status is ChallengeParticipationStatus.CANCELLED
    assert frozen.completed_count == before.completed_count == 1
    assert (await challenges.get(user, fresh.id)).status is ChallengeParticipationStatus.ACTIVE
