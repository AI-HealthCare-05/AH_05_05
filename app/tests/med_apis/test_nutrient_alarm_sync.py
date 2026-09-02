from datetime import datetime, timedelta

from tortoise.contrib.test import TestCase

from app.core import config
from app.dtos.user_supplement_nutrients import (
    ManualSupplementNutrientCreateRequest,
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
from app.models.alarms import Alarm
from app.models.enums import AccountStatus, AlarmStatus, AlarmType, MealSlot
from app.models.users import User
from app.services.user_supplement_nutrients import UserSupplementNutrientService
from app.tests.med_apis.helpers import create_supplement


class TestNutrientAlarmSync(TestCase):
    async def test_upsert_creates_indefinite_alarm_for_each_active_slot(self) -> None:
        user = await User.create(
            email="nutrient-alarm@example.com",
            hashed_password="hashed-password",
            status=AccountStatus.ACTIVE,
            name="영양제 알람 사용자",
        )
        product = await create_supplement("ALARM-SUPPL-001", "비타민 D")
        today = datetime.now(config.TIMEZONE).date()

        await UserSupplementNutrientService().upsert(
            user,
            product.id,
            UserSupplementNutrientUpsertRequest(
                dose_amount="1.000",
                dose_unit="정",
                start_date=today - timedelta(days=1),
                slots=[MealSlot.MORNING, MealSlot.EVENING],
            ),
        )

        alarms = await Alarm.filter(user=user, alarm_type=AlarmType.NUTRIENT).order_by("meal_slot")
        assert {alarm.meal_slot for alarm in alarms} == {MealSlot.MORNING, MealSlot.EVENING}
        assert all(alarm.status == AlarmStatus.ACTIVE for alarm in alarms)
        assert all(alarm.recurrence_rule == "FREQ=DAILY" for alarm in alarms)
        assert all(alarm.care_episode_id is None for alarm in alarms)

    async def test_manual_registration_creates_nutrient_alarm(self) -> None:
        user = await User.create(
            email="manual-nutrient-alarm@example.com",
            hashed_password="hashed-password",
            status=AccountStatus.ACTIVE,
            name="직접 입력 영양제 사용자",
        )
        today = datetime.now(config.TIMEZONE).date()

        await UserSupplementNutrientService().create_manual(
            user,
            ManualSupplementNutrientCreateRequest(
                custom_name="직접 입력 영양제",
                dose_amount="1.000",
                dose_unit="정",
                start_date=today - timedelta(days=1),
                slots=[MealSlot.BEDTIME],
            ),
        )

        alarm = await Alarm.get(
            user=user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.BEDTIME,
        )
        assert alarm.status == AlarmStatus.ACTIVE
        assert alarm.recurrence_rule == "FREQ=DAILY"

    async def test_update_cancels_alarm_for_removed_slot(self) -> None:
        user = await User.create(
            email="update-nutrient-alarm@example.com",
            hashed_password="hashed-password",
            status=AccountStatus.ACTIVE,
            name="영양제 슬롯 변경 사용자",
        )
        product = await create_supplement("ALARM-SUPPL-002", "철분")
        today = datetime.now(config.TIMEZONE).date()
        service = UserSupplementNutrientService()
        registration = await service.upsert(
            user,
            product.id,
            UserSupplementNutrientUpsertRequest(
                dose_amount="1.000",
                dose_unit="정",
                start_date=today - timedelta(days=1),
                slots=[MealSlot.MORNING, MealSlot.EVENING],
            ),
        )

        await service.update(
            user,
            registration.id,
            UserSupplementNutrientUpdateRequest(slots=[MealSlot.MORNING]),
        )

        morning = await Alarm.get(
            user=user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.MORNING,
        )
        evening = await Alarm.get(
            user=user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.EVENING,
        )
        assert morning.status == AlarmStatus.ACTIVE
        assert evening.status == AlarmStatus.CANCELLED

    async def test_complete_cancels_all_nutrient_alarms(self) -> None:
        user = await User.create(
            email="complete-nutrient-alarm@example.com",
            hashed_password="hashed-password",
            status=AccountStatus.ACTIVE,
            name="영양제 완료 사용자",
        )
        product = await create_supplement("ALARM-SUPPL-003", "오메가3")
        today = datetime.now(config.TIMEZONE).date()
        service = UserSupplementNutrientService()
        registration = await service.upsert(
            user,
            product.id,
            UserSupplementNutrientUpsertRequest(
                dose_amount="1.000",
                dose_unit="캡슐",
                start_date=today - timedelta(days=1),
                slots=[MealSlot.LUNCH],
            ),
        )

        await service.complete(user, registration.id)

        alarm = await Alarm.get(
            user=user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.LUNCH,
        )
        assert alarm.status == AlarmStatus.CANCELLED

    async def test_finite_registration_uses_exact_daily_count(self) -> None:
        user = await User.create(
            email="finite-nutrient-alarm@example.com",
            hashed_password="hashed-password",
            status=AccountStatus.ACTIVE,
            name="기간 영양제 사용자",
        )
        product = await create_supplement("ALARM-SUPPL-004", "칼슘")
        tomorrow = datetime.now(config.TIMEZONE).date() + timedelta(days=1)

        await UserSupplementNutrientService().upsert(
            user,
            product.id,
            UserSupplementNutrientUpsertRequest(
                dose_amount="1.000",
                dose_unit="정",
                start_date=tomorrow,
                end_date=tomorrow + timedelta(days=2),
                slots=[MealSlot.LUNCH],
            ),
        )

        alarm = await Alarm.get(
            user=user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.LUNCH,
        )
        assert alarm.next_trigger_at.date() == tomorrow
        assert alarm.scheduled_at == alarm.next_trigger_at
        assert alarm.recurrence_rule == "FREQ=DAILY;COUNT=3"
