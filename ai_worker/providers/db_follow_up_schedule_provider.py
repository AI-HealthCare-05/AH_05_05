from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tortoise.timezone import now

from ai_worker.schemas.patient import FollowUpSchedule
from app.models.care import FollowUpVisit

_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")


def _service_today() -> date:
    return now().date()


class DbFollowUpScheduleProvider:
    """사용자가 등록한 예정 진료일정을 사용자 범위 안에서만 읽는다."""

    def __init__(
        self,
        *,
        today_provider: Callable[[], date] = _service_today,
    ) -> None:
        self._today_provider = today_provider

    async def list_upcoming_schedules(
        self,
        *,
        user_id: int,
        limit: int,
    ) -> list[FollowUpSchedule]:
        if limit < 1:
            return []

        visits = await (
            FollowUpVisit.filter(
                user_id=user_id,
                visit_date__gte=self._today_provider(),
            )
            .order_by("visit_date", "visit_time", "id")
            .limit(limit)
        )
        return [
            FollowUpSchedule(
                follow_up_visit_id=visit.id,
                visit_at=self._combine_visit_at(
                    visit_date=visit.visit_date,
                    visit_time=self._normalize_visit_time(visit.visit_time),
                ),
                visit_time=self._normalize_visit_time(visit.visit_time),
                hospital=visit.hospital,
            )
            for visit in visits
        ]

    @staticmethod
    def _normalize_visit_time(
        visit_time: time | timedelta | None,
    ) -> time | None:
        if not isinstance(visit_time, timedelta):
            return visit_time

        total_seconds = int(visit_time.total_seconds())
        hours, remainder = divmod(total_seconds, 60 * 60)
        minutes, seconds = divmod(remainder, 60)
        return time(
            hour=hours,
            minute=minutes,
            second=seconds,
            microsecond=visit_time.microseconds,
        )

    @staticmethod
    def _combine_visit_at(
        *,
        visit_date: date,
        visit_time: time | timedelta | None,
    ) -> datetime:
        visit_time = DbFollowUpScheduleProvider._normalize_visit_time(visit_time)
        return datetime.combine(
            visit_date,
            visit_time or time.min,
            tzinfo=_KOREA_TIME_ZONE,
        )
