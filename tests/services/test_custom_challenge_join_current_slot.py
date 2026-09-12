"""Join policy regression tests: real planner/service with disposable SQLite only."""

import sqlite3
from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exceptions import CustomChallengeInvalidTargetsError
from app.dtos.custom_challenges import CustomChallengeJoinRequest
from app.models.care import CareEpisode
from app.models.challenges import CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import CustomChallengeOccurrence, CustomChallengeTarget
from app.models.enums import AccountStatus, CareEpisodeStatus, CustomChallengeType, MealSlot
from app.models.medications import Medication, MedicationDose, MedicationSlot
from app.models.supplement_nutrients import SupplementDose, UserSupplementNutrient, UserSupplementNutrientSlot
from app.models.users import User, UserSettings
from app.services.custom_challenge_goal_planner import KST, GoalWindow, plan_goals, seven_day_end
from app.services.custom_challenge_schedule_reconciler import CustomChallengeScheduleReconciler
from app.services.custom_challenges import CustomChallengeService

DAY = date(2026, 9, 12)
TIMES = dict(zip(MealSlot, (time(8), time(13), time(18), time(22)), strict=True))
JOIN = datetime(2026, 9, 12, 18, 0, 1, tzinfo=KST)


@pytest.mark.parametrize(
    ("joined", "expected"),
    [
        (datetime(2026, 9, 12, 7, 59, 59, tzinfo=KST), list(MealSlot)),
        (datetime(2026, 9, 12, 18, tzinfo=KST), [MealSlot.EVENING, MealSlot.BEDTIME]),
        (JOIN, [MealSlot.EVENING, MealSlot.BEDTIME]),
        (datetime(2026, 9, 12, 9, 0, 1, tzinfo=UTC), [MealSlot.EVENING, MealSlot.BEDTIME]),
        (datetime(2026, 9, 12, 23, 59, 59, tzinfo=KST), [MealSlot.BEDTIME]),
        (datetime(2026, 9, 12, 15, 0, tzinfo=UTC), []),  # KST next midnight: no previous-day goal
    ],
)
def test_join_boundary_keeps_only_latest_configured_slot_and_future(joined, expected):
    goals = plan_goals(
        windows=[GoalWindow(1, slot, DAY, DAY) for slot in MealSlot],
        meal_times=TIMES,
        joined_at=joined,
        end_at=seven_day_end(joined),
        include_join_slot=True,
    )
    assert [goal.slot for goal in goals] == expected


def test_unselected_current_slot_does_not_fall_back_to_older_selected_slot():
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, DAY, DAY)],
        meal_times=TIMES,
        joined_at=JOIN,
        end_at=seven_day_end(JOIN),
        include_join_slot=True,
    )
    assert goals == []


def test_tied_latest_slots_use_clock_time_not_enum_order_and_completed_keys_never_fall_back():
    goals = plan_goals(
        windows=[GoalWindow(1, slot, DAY, DAY) for slot in MealSlot],
        meal_times={**TIMES, MealSlot.MORNING: time(18), MealSlot.EVENING: time(13)},
        joined_at=JOIN,
        end_at=seven_day_end(JOIN),
        include_join_slot=True,
        excluded_keys={(1, DAY, MealSlot.MORNING)},
    )
    assert [goal.slot for goal in goals] == [MealSlot.BEDTIME]


def test_equal_latest_times_all_remain_eligible():
    goals = plan_goals(
        windows=[GoalWindow(1, slot, DAY, DAY) for slot in MealSlot],
        meal_times={**TIMES, MealSlot.LUNCH: time(18)},
        joined_at=JOIN,
        end_at=seven_day_end(JOIN),
        include_join_slot=True,
    )
    assert [goal.slot for goal in goals] == [MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME]


def test_future_start_full_later_days_and_exclusive_end_stay_unchanged():
    goals = plan_goals(
        windows=[GoalWindow(1, slot, DAY + timedelta(days=1), None) for slot in MealSlot],
        meal_times=TIMES,
        joined_at=JOIN,
        end_at=seven_day_end(JOIN),
        include_join_slot=True,
    )
    assert len(goals) == 24
    assert {goal.scheduled_date for goal in goals} == {date(2026, 9, day) for day in range(13, 19)}
    assert goals[-1].scheduled_at == datetime(2026, 9, 18, 22, tzinfo=KST)


@pytest_asyncio.fixture
async def database():
    sqlite3.register_adapter(time, lambda value: value.isoformat())
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


async def setup_source(kind, *, start=DAY, slots=tuple(MealSlot), email="join@example.com"):
    user = await User.create(email=email, hashed_password="unused", name="fixture", status=AccountStatus.ACTIVE)
    await UserSettings.create(
        user=user, **{f"{slot.value.lower()}_medication_time": value for slot, value in TIMES.items()}
    )
    group, _ = await CommonCodeGroup.get_or_create(
        category="CHL", group_code="CST_CHL_TYPE", defaults={"group_name": "type"}
    )
    code, _ = await CommonCode.get_or_create(group=group, detail_code=kind.value, defaults={"detail_name": kind.value})
    check_group, _ = await CommonCodeGroup.get_or_create(
        category="CHL", group_code="CST_CHK_TYPE", defaults={"group_name": "check"}
    )
    check, _ = await CommonCode.get_or_create(group=check_group, detail_code="AUTO", defaults={"detail_name": "auto"})
    template = await CustomChallengeTemplate.create(
        name="fixture", challenge_type=code, check_type=check, is_active=True
    )
    if kind is CustomChallengeType.MEDICATION:
        source = await CareEpisode.create(
            user=user,
            alias="fixture",
            status=CareEpisodeStatus.ACTIVE,
            medication_start_date=start,
            medication_start_slot=MealSlot.MORNING,
            medication_days=7,
        )
        med = await Medication.create(care_episode=source, name="fixture", times_per_day=len(slots), days=7)
        for slot in slots:
            await MedicationSlot.create(medication=med, slot=slot)
    else:
        source = await UserSupplementNutrient.create(
            user=user, custom_name="fixture", dose_amount=1, dose_unit="정", start_date=start
        )
        for slot in slots:
            await UserSupplementNutrientSlot.create(user_suppl_nutrient=source, slot=slot)
    return user, source, template


async def dose(kind, user, source, slot, taken_at):
    if kind is CustomChallengeType.MEDICATION:
        row = await MedicationDose.create(user=user, care_episode=source, dose_date=DAY, slot=slot)
    else:
        row = await SupplementDose.create(registration=source, dose_date=DAY, slot=slot)
    row.taken_at = taken_at
    await row.save(update_fields=["taken_at"])
    return row


async def join(user, source, template, now=JOIN):
    return await CustomChallengeService(now_provider=lambda: now).join(
        user, template.id, CustomChallengeJoinRequest(target_ids=[source.id], idempotency_key=f"join-{source.id}")
    )


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.usefixtures("database")
async def test_real_join_adds_pending_current_slot_and_completion_undo_tracks_that_goal(kind):
    user, source, template = await setup_source(kind)
    result = await join(user, source, template)
    today = [o for o in result.occurrences if o.scheduled_date == DAY]
    assert [o.slot for o in today] == [MealSlot.EVENING, MealSlot.BEDTIME]
    assert result.target_count == 26
    assert result.completed_count == 0
    assert result.end_at == datetime(2026, 9, 19, tzinfo=KST)
    row = await dose(kind, user, source, MealSlot.EVENING, JOIN + timedelta(seconds=1))
    service = CustomChallengeService(now_provider=lambda: JOIN + timedelta(seconds=2))
    completed = await service.get(user, result.id)
    assert completed.completed_count == 1
    await row.delete()
    undone = await service.get(user, result.id)
    assert undone.completed_count == 0
    assert [(o.id, o.slot) for o in undone.occurrences] == [(o.id, o.slot) for o in result.occurrences]


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.parametrize("taken_at", [JOIN - timedelta(seconds=2), JOIN])
@pytest.mark.usefixtures("database")
async def test_prejoin_current_and_early_future_doses_excluded_and_reconcile_does_not_recreate(kind, taken_at):
    user, source, template = await setup_source(kind)
    for slot in [MealSlot.EVENING, MealSlot.BEDTIME]:
        await dose(kind, user, source, slot, taken_at)
    result = await join(user, source, template)
    assert [o for o in result.occurrences if o.scheduled_date == DAY] == []
    assert result.completed_count == 0
    assert result.target_count == 24
    async with in_transaction() as connection:
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=kind,
            source_ids=[source.id],
            changed_at=JOIN + timedelta(minutes=20),
            connection=connection,
        )
    refreshed = await CustomChallengeService(now_provider=lambda: JOIN + timedelta(minutes=21)).get(user, result.id)
    assert [o for o in refreshed.occurrences if o.scheduled_date == DAY] == []
    assert refreshed.completed_count == 0


@pytest.mark.usefixtures("database")
async def test_partial_medication_means_other_episode_dose_does_not_complete_selected_episode():
    user, source, template = await setup_source(CustomChallengeType.MEDICATION)
    other = await CareEpisode.create(user=user, alias="other")
    await MedicationDose.create(user=user, care_episode=other, dose_date=DAY, slot=MealSlot.EVENING)
    result = await join(user, source, template)
    assert [o.slot for o in result.occurrences if o.scheduled_date == DAY] == [MealSlot.EVENING, MealSlot.BEDTIME]
    assert result.completed_count == 0


@pytest.mark.usefixtures("database")
async def test_reconcile_preserves_new_past_goal_and_does_not_backfill_old_participation():
    user, source, template = await setup_source(CustomChallengeType.SUPPLEMENT)
    result = await join(user, source, template)
    current = next(o for o in result.occurrences if o.scheduled_date == DAY and o.slot == MealSlot.EVENING)
    async with in_transaction() as connection:
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.SUPPLEMENT,
            source_ids=[source.id],
            changed_at=JOIN + timedelta(minutes=1),
            connection=connection,
        )
    assert await CustomChallengeOccurrence.filter(id=current.id).exists()
    # Simulate an old strict-policy snapshot missing the past goal: reconciliation must not repair history.
    await CustomChallengeOccurrence.filter(id=current.id).delete()
    async with in_transaction() as connection:
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=CustomChallengeType.SUPPLEMENT,
            source_ids=[source.id],
            changed_at=JOIN + timedelta(minutes=2),
            connection=connection,
        )
    target = await CustomChallengeTarget.get(participation_id=result.id)
    assert not await CustomChallengeOccurrence.filter(
        target_id=target.id, scheduled_date=DAY, slot=MealSlot.EVENING
    ).exists()


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.usefixtures("database")
async def test_undo_prejoin_dose_can_readd_only_still_future_pending_goal(kind):
    user, source, template = await setup_source(kind)
    rows = [
        await dose(kind, user, source, slot, JOIN - timedelta(seconds=1))
        for slot in [MealSlot.EVENING, MealSlot.BEDTIME]
    ]
    result = await join(user, source, template)
    for row in rows:
        await row.delete()
    async with in_transaction() as connection:
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=kind,
            source_ids=[source.id],
            changed_at=JOIN + timedelta(minutes=1),
            connection=connection,
        )
    refreshed = await CustomChallengeService(now_provider=lambda: JOIN + timedelta(minutes=2)).get(user, result.id)
    today = [o for o in refreshed.occurrences if o.scheduled_date == DAY]
    assert [(o.slot, o.is_completed) for o in today] == [(MealSlot.BEDTIME, False)]
    assert refreshed.completed_count == 0


@pytest.mark.parametrize("taken", [False, True])
@pytest.mark.usefixtures("database")
async def test_last_prescription_day_recommendation_and_join_depend_on_current_pending_slot(taken):
    user, source, template = await setup_source(CustomChallengeType.MEDICATION, slots=(MealSlot.EVENING,))
    source.medication_days = 1
    await source.save(update_fields=["medication_days"])
    await Medication.filter(care_episode=source).update(days=1)
    if taken:
        await dose(CustomChallengeType.MEDICATION, user, source, MealSlot.EVENING, JOIN - timedelta(seconds=1))
    service = CustomChallengeService(now_provider=lambda: JOIN)
    recommended = await service.recommendations(user)
    assert [target.id for item in recommended.items for target in item.targets] == ([] if taken else [source.id])
    if taken:
        with pytest.raises(CustomChallengeInvalidTargetsError):
            await join(user, source, template)
    else:
        result = await join(user, source, template)
        assert [(o.scheduled_date, o.slot) for o in result.occurrences] == [(DAY, MealSlot.EVENING)]
        assert result.end_at == datetime(2026, 9, 13, tzinfo=KST)
        retried = await join(user, source, template, now=JOIN + timedelta(hours=1))
        assert retried.id == result.id
        assert [o.id for o in retried.occurrences] == [o.id for o in result.occurrences]


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.usefixtures("database")
async def test_actual_utc_join_future_registration_has_no_today_goal(kind):
    user, source, template = await setup_source(kind, start=DAY + timedelta(days=1))
    result = await join(user, source, template, now=datetime(2026, 9, 12, 9, 0, 1, tzinfo=UTC))
    assert not [o for o in result.occurrences if o.scheduled_date == DAY]
    assert result.occurrences[0].scheduled_at == datetime(2026, 9, 13, 8, tzinfo=KST)
    assert result.target_count == (28 if kind is CustomChallengeType.MEDICATION else 24)


@pytest.mark.usefixtures("database")
async def test_supplement_completion_is_per_selected_registration_not_global_slot():
    user, source, template = await setup_source(CustomChallengeType.SUPPLEMENT)
    other = await UserSupplementNutrient.create(
        user=user, custom_name="other", dose_amount=1, dose_unit="정", start_date=DAY
    )
    await UserSupplementNutrientSlot.create(user_suppl_nutrient=other, slot=MealSlot.EVENING)
    await dose(CustomChallengeType.SUPPLEMENT, user, other, MealSlot.EVENING, JOIN - timedelta(seconds=1))
    result = await CustomChallengeService(now_provider=lambda: JOIN).join(
        user, template.id, CustomChallengeJoinRequest(target_ids=sorted([source.id, other.id]), idempotency_key="multi")
    )
    today = [o for o in result.occurrences if o.scheduled_date == DAY]
    selected_target = next(target for target in result.targets if target.source_id == source.id)
    assert [(o.target_id, o.slot) for o in today] == [
        (selected_target.id, MealSlot.EVENING),
        (selected_target.id, MealSlot.BEDTIME),
    ]
    assert result.completed_count == 0


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.usefixtures("database")
async def test_existing_future_goal_keeps_same_timestamp_postjoin_completion_and_undo(kind):
    user, source, template = await setup_source(kind)
    result = await join(user, source, template)
    original = next(o for o in result.occurrences if o.scheduled_date == DAY and o.slot == MealSlot.BEDTIME)
    # Persisted after join, but timestamp is indistinguishable at DB precision.
    row = await dose(kind, user, source, MealSlot.BEDTIME, JOIN)
    async with in_transaction() as connection:
        await CustomChallengeScheduleReconciler().reconcile(
            user_id=user.id,
            source_kind=kind,
            source_ids=[source.id],
            changed_at=JOIN + timedelta(minutes=1),
            connection=connection,
        )
    service = CustomChallengeService(now_provider=lambda: JOIN + timedelta(minutes=2))
    refreshed = await service.get(user, result.id)
    same_goal = next(o for o in refreshed.occurrences if o.id == original.id)
    assert same_goal.is_completed
    assert refreshed.completed_count == 1
    await row.delete()
    undone = await service.get(user, result.id)
    assert not next(o for o in undone.occurrences if o.id == original.id).is_completed
    assert undone.completed_count == 0
