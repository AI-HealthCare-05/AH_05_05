from datetime import datetime, time, timedelta

from fastapi import HTTPException, status
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.settings import NotifySettingsUpdateRequest
from app.models.enums import MealSlot
from app.models.users import User, UserSettings
from app.services.medication_schedule import SLOT_ORDER, MedicationScheduleService

_SETTING_FIELD_MAP = {
    "notify_medication": "is_notify_medication",
    "notify_supplement": "is_notify_supplement",
}
_TIME_FIELDS = {
    MealSlot.MORNING: "morning_medication_time",
    MealSlot.LUNCH: "lunch_medication_time",
    MealSlot.EVENING: "evening_medication_time",
    MealSlot.BEDTIME: "bedtime_medication_time",
}


def normalize_medication_time(value: time | timedelta) -> time:
    if isinstance(value, time):
        return value
    seconds = int(value.total_seconds()) % (24 * 60 * 60)
    hour, remainder = divmod(seconds, 60 * 60)
    minute, second = divmod(remainder, 60)
    return time(hour, minute, second)


def _merge_medication_times(
    settings: UserSettings,
    supplied: dict[str, object],
) -> dict[MealSlot, time]:
    meal_times = {
        slot: normalize_medication_time(getattr(settings, field_name)) for slot, field_name in _TIME_FIELDS.items()
    }
    for slot, field_name in _TIME_FIELDS.items():
        value = supplied.get(field_name)
        if isinstance(value, time):
            meal_times[slot] = value

    ordered_times = [meal_times[slot] for slot in SLOT_ORDER]
    if any(first >= second for first, second in zip(ordered_times, ordered_times[1:], strict=False)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Medication times must be ordered morning, lunch, evening, bedtime.",
        )
    return meal_times


def _apply_medication_times(
    settings: UserSettings,
    meal_times: dict[MealSlot, time],
) -> list[str]:
    update_fields: list[str] = []
    for slot, field_name in _TIME_FIELDS.items():
        current = normalize_medication_time(getattr(settings, field_name))
        if current != meal_times[slot]:
            setattr(settings, field_name, meal_times[slot])
            update_fields.append(field_name)
    return update_fields


class NotifySettingsService:
    async def get(self, user: User) -> UserSettings:
        settings, _ = await UserSettings.get_or_create(user=user)
        return settings

    async def update(self, user: User, data: NotifySettingsUpdateRequest) -> UserSettings:
        async with in_transaction() as connection:
            settings = await UserSettings.filter(user_id=user.id).using_db(connection).select_for_update().first()
            if settings is None:
                settings = await UserSettings.create(user_id=user.id, using_db=connection)

            update_fields: list[str] = []
            supplied = data.model_dump(exclude_unset=True)
            for request_field, model_field in _SETTING_FIELD_MAP.items():
                value = supplied.get(request_field)
                if value is not None and getattr(settings, model_field) != value:
                    setattr(settings, model_field, value)
                    update_fields.append(model_field)

            meal_times = _merge_medication_times(settings, supplied)
            time_update_fields = _apply_medication_times(settings, meal_times)
            update_fields.extend(time_update_fields)

            if settings.notify_consented_at is None:
                settings.notify_consented_at = datetime.now(config.TIMEZONE)
                update_fields.append("notify_consented_at")

            if update_fields:
                await settings.save(using_db=connection, update_fields=update_fields)
            if time_update_fields:
                await MedicationScheduleService._sync_medication_alarms(
                    user.id,
                    meal_times,
                    connection,
                )

        return settings
