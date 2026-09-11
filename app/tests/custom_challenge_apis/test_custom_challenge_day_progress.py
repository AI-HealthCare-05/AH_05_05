"""Run with --noconftest: every row lives only in this file's in-memory SQLite database."""

import sqlite3
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dtos.medications import SaveMedicationDoseRequest
from app.dtos.supplement_doses import SupplementDoseRequest
from app.models.care import CareEpisode
from app.models.challenges import CustomChallengeTemplate
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.custom_challenges import CustomChallengeOccurrence, CustomChallengeParticipation, CustomChallengeTarget
from app.models.enums import AccountStatus, ChallengeParticipationStatus, CustomChallengeType, MealSlot
from app.models.medications import MedicationDose
from app.models.supplement_nutrients import SupplementDose, UserSupplementNutrient
from app.models.users import User
from app.services.custom_challenges import CustomChallengeService
from app.services.medications import MedicationService
from app.services.supplement_doses import SupplementDoseService

NOW = datetime(2026, 9, 10, 7, tzinfo=config.TIMEZONE)
END = datetime(2026, 9, 20, tzinfo=config.TIMEZONE)
FIRST = date(2026, 9, 10)
LAST = date(2026, 9, 14)
MORNING, LUNCH, EVENING = MealSlot.MORNING, MealSlot.LUNCH, MealSlot.EVENING
Goal = tuple[int, date, MealSlot, bool]


@pytest_asyncio.fixture(autouse=True)
async def initialized_db():
    sqlite3.register_adapter(time, lambda value: value.isoformat())
    await Tortoise.init(
        db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul", use_tz=False
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def fixture(kind: CustomChallengeType, goals: list[Goal]):
    user = await User.create(
        email="day-progress@example.invalid", hashed_password="unused", name="일 단위", status=AccountStatus.ACTIVE
    )
    check_group = await CommonCodeGroup.create(category="CHL", group_code="CST_CHK_TYPE", group_name="인증")
    type_group = await CommonCodeGroup.create(category="CHL", group_code="CST_CHL_TYPE", group_name="유형")
    check = await CommonCode.create(group=check_group, detail_code="AUTO", detail_name="자동")
    challenge_type = await CommonCode.create(group=type_group, detail_code=kind.value, detail_name="유형")
    template = await CustomChallengeTemplate.create(
        name="일 단위 챌린지", check_type=check, challenge_type=challenge_type
    )
    participation = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        challenge_type=kind,
        challenge_name=template.name,
        idempotency_key="day-progress",
        end_at=END,
    )
    sources = {}
    targets = {}
    for index, goal_date, slot, completed in goals:
        if index not in sources:
            source = (
                (await CareEpisode.create(user=user, alias=f"처방 {index}"))
                if kind is CustomChallengeType.MEDICATION
                else (
                    await UserSupplementNutrient.create(
                        user=user,
                        custom_name=f"영양제 {index}",
                        start_date=FIRST,
                        dose_amount=Decimal("1"),
                        dose_unit="정",
                    )
                )
            )
            sources[index] = source
            relation = (
                {"care_episode_id": source.id}
                if kind is CustomChallengeType.MEDICATION
                else {"supplement_registration_id": source.id}
            )
            targets[index] = await CustomChallengeTarget.create(
                participation=participation,
                source_id_snapshot=source.id,
                target_name_snapshot=f"대상 {index}",
                **relation,
            )
        await CustomChallengeOccurrence.create(
            target=targets[index],
            scheduled_date=goal_date,
            slot=slot,
            scheduled_at=datetime.combine(goal_date, time(8), tzinfo=config.TIMEZONE),
        )
        if completed:
            if kind is CustomChallengeType.MEDICATION:
                await MedicationDose.create(user=user, care_episode=sources[index], dose_date=goal_date, slot=slot)
            else:
                await SupplementDose.create(registration=sources[index], dose_date=goal_date, slot=slot)
    return user, participation


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
async def test_get_and_list_count_fully_completed_days_not_variable_dose_counts(kind):
    user, participation = await fixture(
        kind, [(0, FIRST, MORNING, True), (0, FIRST, LUNCH, True), (0, FIRST, EVENING, True), (0, LAST, MORNING, False)]
    )
    service = CustomChallengeService(now_provider=lambda: NOW)
    detail = await service.get(user, participation.id)
    listing = await service.list(user)
    for response in [detail, listing.items[0]]:
        payload = response.model_dump(mode="json", by_alias=True)
        assert payload.get("targetDayCount") == 2
        assert payload.get("completedDayCount") == 1
        assert payload.get("dayProgressRate") == "50.00"
        # Existing occurrence-level contract remains unchanged for lifecycle/badge compatibility.
        assert (response.target_count, response.completed_count, response.progress_rate) == (4, 3, Decimal("75.00"))
        assert response.status is ChallengeParticipationStatus.ACTIVE


async def test_a_partially_completed_day_does_not_count_as_an_achieved_day():
    user, participation = await fixture(
        CustomChallengeType.MEDICATION, [(0, FIRST, MORNING, True), (0, FIRST, EVENING, False)]
    )
    response = await CustomChallengeService(now_provider=lambda: NOW).get(user, participation.id)
    assert response.model_dump(by_alias=True).get("completedDayCount") == 0
    assert response.model_dump(by_alias=True).get("dayProgressRate") == Decimal("0.00")
    assert response.progress_rate == Decimal("50.00")


async def test_gap_dates_without_goals_are_excluded_from_the_denominator():
    user, participation = await fixture(
        CustomChallengeType.MEDICATION, [(0, FIRST, MORNING, True), (0, LAST, MORNING, True)]
    )
    payload = (await CustomChallengeService(now_provider=lambda: NOW).get(user, participation.id)).model_dump(
        by_alias=True
    )
    assert (payload.get("targetDayCount"), payload.get("completedDayCount"), payload.get("dayProgressRate")) == (
        2,
        2,
        Decimal("100.00"),
    )


async def test_all_targets_on_the_same_date_must_complete_before_the_day_counts():
    user, participation = await fixture(
        CustomChallengeType.SUPPLEMENT,
        [(0, FIRST, MORNING, True), (1, FIRST, MORNING, False), (0, LAST, MORNING, True)],
    )
    response = await CustomChallengeService(now_provider=lambda: NOW).get(user, participation.id)
    payload = response.model_dump(by_alias=True)
    assert (payload.get("targetDayCount"), payload.get("completedDayCount"), payload.get("dayProgressRate")) == (
        2,
        1,
        Decimal("50.00"),
    )
    assert response.progress_rate == Decimal("66.67")


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
async def test_active_dose_service_undo_updates_occurrence_and_decrements_achieved_days(kind):
    now = datetime.now(config.TIMEZONE)
    today = now.date()
    yesterday = today - timedelta(days=1)
    user, participation = await fixture(
        kind,
        [(0, yesterday, MORNING, True), (0, today, MORNING, True), (0, today, EVENING, True)],
    )
    # Keep this genuine mutation inside the active period independently of the test run date.
    participation.end_at = now + timedelta(days=2)
    await participation.save(update_fields=["end_at"])
    target = await CustomChallengeTarget.get(participation_id=participation.id)
    service = CustomChallengeService(now_provider=lambda: now)
    before = await service.get(user, participation.id)
    assert (before.target_day_count, before.completed_day_count, before.day_progress_rate) == (
        2,
        2,
        Decimal("100.00"),
    )
    assert all(item.is_completed for item in before.occurrences)

    if kind is CustomChallengeType.MEDICATION:
        result = await MedicationService(mutation_time_provider=lambda: now).save_dose(
            user,
            SaveMedicationDoseRequest(date=today, slot="morning", taken=False, record_id=target.care_episode_id),
        )
    else:
        result = await SupplementDoseService().save(
            user,
            SupplementDoseRequest(
                date=today, slot="morning", taken=False, supplement_id=target.supplement_registration_id
            ),
        )
    assert result.taken is False

    detail = await service.get(user, participation.id)
    listing = await service.list(user)
    for response in [detail, listing.items[0]]:
        assert response.status is ChallengeParticipationStatus.ACTIVE
        assert (response.target_day_count, response.completed_day_count, response.day_progress_rate) == (
            2,
            1,
            Decimal("50.00"),
        )
        assert (response.target_count, response.completed_count, response.progress_rate) == (3, 2, Decimal("66.67"))
        assert {(item.scheduled_date, item.slot): item.is_completed for item in response.occurrences} == {
            (yesterday, MORNING): True,
            (today, MORNING): False,
            (today, EVENING): True,
        }
    await participation.refresh_from_db()
    assert participation.finalized_at is None


@pytest.mark.parametrize("kind", [CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT])
@pytest.mark.parametrize(
    "status",
    [
        ChallengeParticipationStatus.COMPLETED,
        ChallengeParticipationStatus.EXPIRED,
        ChallengeParticipationStatus.CANCELLED,
    ],
)
async def test_finalized_day_progress_stays_frozen_after_source_record_undo(kind, status):
    all_done = status is ChallengeParticipationStatus.COMPLETED
    user, participation = await fixture(
        kind, [(0, FIRST, MORNING, True), (0, FIRST, EVENING, True), (0, LAST, MORNING, all_done)]
    )
    service = CustomChallengeService(
        now_provider=lambda: NOW if status is ChallengeParticipationStatus.CANCELLED else END
    )
    before = (
        await service.cancel(user, participation.id)
        if status is ChallengeParticipationStatus.CANCELLED
        else await service.get(user, participation.id)
    )
    assert before.status is status
    await MedicationDose.all().delete()
    await SupplementDose.all().delete()
    after = await service.get(user, participation.id)
    payload = after.model_dump(by_alias=True)
    expected = (2, 2, Decimal("100.00")) if all_done else (2, 1, Decimal("50.00"))
    assert (payload.get("targetDayCount"), payload.get("completedDayCount"), payload.get("dayProgressRate")) == expected
    assert (after.target_count, after.completed_count, after.progress_rate) == (
        before.target_count,
        before.completed_count,
        before.progress_rate,
    )
    assert [item.is_completed for item in after.occurrences] == [True, True, all_done]


@pytest.mark.parametrize("now", [NOW, END])
async def test_no_actual_goals_returns_zero_days_and_zero_progress(now):
    user, participation = await fixture(CustomChallengeType.MEDICATION, [])
    response = await CustomChallengeService(now_provider=lambda: now).get(user, participation.id)
    payload = response.model_dump(by_alias=True)
    assert (payload.get("targetDayCount"), payload.get("completedDayCount"), payload.get("dayProgressRate")) == (
        0,
        0,
        Decimal("0.00"),
    )
    assert (response.target_count, response.completed_count, response.progress_rate) == (0, 0, Decimal("0.00"))
