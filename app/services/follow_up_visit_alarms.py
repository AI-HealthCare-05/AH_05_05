from datetime import datetime, time, timedelta

from tortoise.backends.base.client import BaseDBAsyncClient

from app.core import config
from app.models.alarms import Alarm
from app.models.care import FollowUpVisit
from app.models.enums import AlarmStatus, AlarmType

FOLLOW_UP_ALARM_TITLE = "진료 일정 알림"
FOLLOW_UP_ALARM_MESSAGE = "내일 진료 일정이 있어요"


class FollowUpVisitAlarmService:
    @classmethod
    async def sync_future_alarms(
        cls,
        user_id: int,
        evening_time: time | timedelta,
        connection: BaseDBAsyncClient,
    ) -> None:
        today = datetime.now(config.TIMEZONE).date()
        visits = await FollowUpVisit.filter(user_id=user_id, visit_date__gte=today).using_db(connection)
        for visit in visits:
            await cls.sync_alarm(visit, evening_time, connection)

    @staticmethod
    async def sync_alarm(
        visit: FollowUpVisit,
        evening_time: time | timedelta,
        connection: BaseDBAsyncClient,
    ) -> None:
        now = datetime.now(config.TIMEZONE)
        scheduled_at = datetime.combine(
            visit.visit_date - timedelta(days=1),
            normalize_time(evening_time),
            tzinfo=config.TIMEZONE,
        )
        alarm = (
            await Alarm.filter(
                user_id=visit.user_id,
                alarm_type=AlarmType.FOLLOW_UP_VISIT,
                follow_up_visit_id=visit.id,
            )
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if scheduled_at <= now:
            if alarm is not None and alarm.status != AlarmStatus.CANCELLED:
                alarm.status = AlarmStatus.CANCELLED
                alarm.cancelled_at = now
                alarm.updated_at = now
                await alarm.save(
                    using_db=connection,
                    update_fields=["status", "cancelled_at", "updated_at"],
                )
            return

        values = {
            "title": FOLLOW_UP_ALARM_TITLE,
            "message": FOLLOW_UP_ALARM_MESSAGE,
            "scheduled_at": scheduled_at,
            "recurrence_rule": None,
            "timezone": str(config.TIMEZONE),
            "next_trigger_at": scheduled_at,
            "status": AlarmStatus.ACTIVE,
            "last_triggered_at": None,
            "completed_at": None,
            "cancelled_at": None,
            "updated_at": now,
        }
        if alarm is None:
            await Alarm.create(
                using_db=connection,
                user_id=visit.user_id,
                follow_up_visit_id=visit.id,
                care_episode_id=None,
                alarm_type=AlarmType.FOLLOW_UP_VISIT,
                meal_slot=None,
                **values,
            )
            return

        for field_name, value in values.items():
            setattr(alarm, field_name, value)
        await alarm.save(using_db=connection, update_fields=list(values))


def follow_up_message(visit: FollowUpVisit) -> str:
    parts = ["내일"]
    if visit.visit_time is not None:
        parts.append(normalize_time(visit.visit_time).strftime("%H:%M"))
    if visit.hospital:
        parts.append(visit.hospital)
    if len(parts) == 1:
        return "내일 진료 일정이 있어요"
    return f"{' '.join(parts)} 진료가 있어요"


def normalize_time(value: time | timedelta) -> time:
    if isinstance(value, time):
        return value
    seconds = int(value.total_seconds()) % (24 * 60 * 60)
    hour, remainder = divmod(seconds, 60 * 60)
    minute, second = divmod(remainder, 60)
    return time(hour, minute, second)
