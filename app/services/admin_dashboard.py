from datetime import date, datetime, time, timedelta
from typing import Any

from tortoise.expressions import RawSQL
from tortoise.functions import Avg, Count
from tortoise.models import Model

from app.core import config
from app.dtos.admin_dashboard import (
    ChatStats,
    DashboardPeriod,
    DashboardQuery,
    DashboardResponse,
    MemberStats,
    NotificationStats,
    OcrStats,
    SystemStats,
    TrendPoint,
)
from app.models.alarms import AlarmEvent
from app.models.background_jobs import BackgroundJob
from app.models.chat import ChatMessage
from app.models.enums import (
    AccountStatus,
    AlarmEventType,
    BackgroundJobStatus,
    BackgroundJobType,
    ChatMessageRole,
    ChatMessageStatus,
    OcrJobStatus,
)
from app.models.ocr import OcrJob
from app.models.users import User

# 기간 토글이 며칠을 뜻하는지. 오늘은 당일 하루다.
PERIOD_DAYS = {
    DashboardPeriod.TODAY: 1,
    DashboardPeriod.LAST_7_DAYS: 7,
    DashboardPeriod.LAST_30_DAYS: 30,
}

# 추이 그래프의 막대 개수는 화면 시안에 고정돼 있어 선택 기간을 따르지 않는다.
SIGNUP_TREND_DAYS = 14
NOTIFICATION_TREND_DAYS = 7


class AdminDashboardService:
    """REQ-DASH-001 운영 대시보드 집계."""

    async def get_dashboard(self, query: DashboardQuery) -> DashboardResponse:
        now = datetime.now(tz=config.TIMEZONE)
        days = PERIOD_DAYS[query.period]

        start_at = self._day_start(now.date() - timedelta(days=days - 1))
        # 증감률 기준이 되는 직전 동일 기간. [previous_start, start_at) 구간이다.
        previous_start = start_at - timedelta(days=days)

        return DashboardResponse(
            period=query.period,
            start_at=start_at,
            end_at=now,
            members=await self._members(now, start_at, previous_start),
            chat=await self._chat(now, start_at, previous_start),
            ocr=await self._ocr(now, start_at, previous_start),
            notifications=await self._notifications(now, start_at),
            system=await self._system(now, start_at),
        )

    async def _members(self, now: datetime, start_at: datetime, previous_start: datetime) -> MemberStats:
        by_status = await self._count_by(User, "status")
        total_count = sum(by_status.values())

        period_signup_count = await User.filter(created_at__gte=start_at, created_at__lte=now).count()
        previous_signup_count = await User.filter(created_at__gte=previous_start, created_at__lt=start_at).count()

        return MemberStats(
            total_count=total_count,
            active_count=by_status.get(AccountStatus.ACTIVE, 0),
            suspended_count=by_status.get(AccountStatus.SUSPENDED, 0),
            today_signup_count=await User.filter(created_at__gte=self._day_start(now.date())).count(),
            period_signup_count=period_signup_count,
            signup_change_rate=self._change_rate(period_signup_count, previous_signup_count),
            signup_trend=await self._daily_trend(User, "created_at", now, SIGNUP_TREND_DAYS),
        )

    async def _chat(self, now: datetime, start_at: datetime, previous_start: datetime) -> ChatStats:
        # 사용자 질문이 아니라 답변 시도를 센다. 그래야 성공·실패의 합이 전체와 맞는다.
        answered = {"role": ChatMessageRole.ASSISTANT}
        by_status = await self._count_by(
            ChatMessage, "status", **answered, created_at__gte=start_at, created_at__lte=now
        )
        total_count = sum(by_status.values())
        success_count = by_status.get(ChatMessageStatus.COMPLETED, 0)

        previous_count = await ChatMessage.filter(
            **answered, created_at__gte=previous_start, created_at__lt=start_at
        ).count()

        return ChatStats(
            total_count=total_count,
            success_count=success_count,
            failure_count=by_status.get(ChatMessageStatus.FAILED, 0),
            success_rate=self._rate(success_count, total_count),
            change_rate=self._change_rate(total_count, previous_count),
        )

    async def _ocr(self, now: datetime, start_at: datetime, previous_start: datetime) -> OcrStats:
        by_status = await self._count_by(OcrJob, "status", created_at__gte=start_at, created_at__lte=now)
        total_count = sum(by_status.values())
        success_count = by_status.get(OcrJobStatus.COMPLETE, 0)

        previous_count = await OcrJob.filter(created_at__gte=previous_start, created_at__lt=start_at).count()

        return OcrStats(
            total_count=total_count,
            # 사용자 확인을 기다리는 READY_FOR_REVIEW 는 운영 대기열이 아니라 제외한다.
            pending_count=by_status.get(OcrJobStatus.QUEUED, 0) + by_status.get(OcrJobStatus.PROCESSING, 0),
            success_count=success_count,
            failure_count=by_status.get(OcrJobStatus.FAILED, 0),
            success_rate=self._rate(success_count, total_count),
            change_rate=self._change_rate(total_count, previous_count),
        )

    async def _notifications(self, now: datetime, start_at: datetime) -> NotificationStats:
        by_type = await self._count_by(AlarmEvent, "event_type", event_at__gte=start_at, event_at__lte=now)

        sent_count = by_type.get(AlarmEventType.SENT, 0)
        failure_count = by_type.get(AlarmEventType.FAILED, 0)

        return NotificationStats(
            scheduled_count=by_type.get(AlarmEventType.SCHEDULED, 0),
            sent_count=sent_count,
            failure_count=failure_count,
            # 발송을 시도한 건들 중의 성공률이다. 예약 상태는 아직 시도 전이라 분모에서 뺀다.
            success_rate=self._rate(sent_count, sent_count + failure_count),
            daily_sent_trend=await self._daily_trend(
                AlarmEvent, "event_at", now, NOTIFICATION_TREND_DAYS, event_type=AlarmEventType.SENT
            ),
        )

    async def _system(self, now: datetime, start_at: datetime) -> SystemStats:
        # 지금 밀려 있는 양이라 기간을 적용하지 않는다. 재시도 대기도 처리되지 않은 작업이다.
        queued_job_count = await BackgroundJob.filter(
            status__in=[BackgroundJobStatus.QUEUED, BackgroundJobStatus.RETRY_WAITING]
        ).count()

        latency = (
            await BackgroundJob.filter(
                job_type=BackgroundJobType.LLM,
                status=BackgroundJobStatus.COMPLETED,
                completed_at__gte=start_at,
                completed_at__lte=now,
            )
            .annotate(average=Avg("duration_ms"))
            .values("average")
        )
        average = latency[0]["average"] if latency else None

        return SystemStats(
            queued_job_count=queued_job_count,
            llm_average_latency_ms=round(average) if average is not None else None,
        )

    @staticmethod
    async def _count_by(model: type[Model], field: str, **filters: Any) -> dict[str, int]:
        """한 컬럼으로 묶어 개수를 센다. 상태별로 따로 세면 쿼리가 상태 수만큼 늘어난다."""
        rows = await model.filter(**filters).annotate(total=Count("id")).group_by(field).values(field, "total")
        return {row[field]: row["total"] for row in rows}

    @classmethod
    async def _daily_trend(
        cls, model: type[Model], column: str, now: datetime, days: int, **filters: Any
    ) -> list[TrendPoint]:
        """최근 days 일의 일별 건수. 건수가 0인 날도 빠뜨리지 않고 채운다."""
        first_day = now.date() - timedelta(days=days - 1)
        window = {f"{column}__gte": cls._day_start(first_day), f"{column}__lte": now}

        rows = await (
            model.filter(**window, **filters)
            # 컬럼명은 코드가 정하는 고정값이라 사용자 입력이 섞이지 않는다.
            .annotate(day=RawSQL(f"DATE(`{column}`)"), total=Count("id"))
            .group_by("day")
            .values("day", "total")
        )
        counts = {cls._as_date(row["day"]): row["total"] for row in rows}

        return [
            TrendPoint(date=day, count=counts.get(day, 0))
            for day in (first_day + timedelta(days=offset) for offset in range(days))
        ]

    @staticmethod
    def _as_date(value: Any) -> date:
        """DATE() 결과는 드라이버에 따라 date 로도 문자열로도 온다."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    @staticmethod
    def _day_start(day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=config.TIMEZONE)

    @staticmethod
    def _rate(part: int, whole: int) -> float | None:
        """비율(%). 분모가 0이면 0% 가 아니라 null 이다. 0% 는 '전부 실패'로 읽힌다."""
        if whole == 0:
            return None
        return round(part / whole * 100, 1)

    @staticmethod
    def _change_rate(current: int, previous: int) -> float | None:
        """직전 동일 기간 대비 증감률(%). 직전이 0이면 증감률을 정의할 수 없어 null 이다."""
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)
