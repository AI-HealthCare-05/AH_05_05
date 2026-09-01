from datetime import date, datetime, time, timedelta
from typing import Any

from tortoise.expressions import RawSQL
from tortoise.functions import Count

from app.core import config
from app.dtos.admin_dashboard import (
    AlarmNotificationStats,
    DashboardPeriod,
    DashboardSummaryQuery,
    DashboardSummaryResponse,
    MemberAlertStatus,
    MemberStats,
    OcrDocumentStats,
    SignupTrendPoint,
)
from app.models.background_jobs import BackgroundJob
from app.models.enums import AccountStatus, BackgroundJobStatus, BackgroundJobType, OcrJobStatus
from app.models.ocr import OcrJob
from app.models.users import User

# 기간 토글이 며칠을 뜻하는지. 오늘을 끝으로 하는 롤링 구간이며 캘린더 주·월이 아니다.
PERIOD_DAYS = {
    DashboardPeriod.TODAY: 1,
    DashboardPeriod.LAST_7_DAYS: 7,
    DashboardPeriod.LAST_30_DAYS: 30,
}

# 화면의 "14일간 가입 추이" 차트는 고정 길이라 선택한 기간을 따르지 않는다.
SIGNUP_TREND_DAYS = 14
ALARM_TREND_DAYS = 7

# total 로 세는 상태. 화면이 활성 95% + 정지 5% = 100% 로 표시하므로 둘만 넣는다.
TOTAL_STATUSES = (AccountStatus.ACTIVE, AccountStatus.SUSPENDED)


def now_kst() -> datetime:
    """앱 컨테이너가 UTC 여도 KST 기준으로 '지금'을 잡는다."""
    return datetime.now(tz=config.TIMEZONE)


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=config.TIMEZONE)


def day_range(first: date, last: date) -> tuple[datetime, datetime]:
    """[first 00:00, last+1일 00:00) 반열린 구간.

    끝을 `<= last` 로 잡으면 종료일 당일 가입자가 통째로 누락된다.
    경계 규칙을 여기 한 곳에만 두고 호출부는 gte/lt 로만 쓴다.
    """
    return day_start(first), day_start(last + timedelta(days=1))


class AdminDashboardService:
    """REQ-DASH-001 대시보드 집계.

    회원 현황, ALARM 백그라운드 작업 기반 알림 발송 현황과 OCR 작업 현황을 제공한다.
    챗봇·보안 지표는 담당 데이터가 아직 없어 응답에 넣지 않는다.
    """

    async def get_summary(self, query: DashboardSummaryQuery) -> DashboardSummaryResponse:
        now = now_kst()
        window = timedelta(days=PERIOD_DAYS[query.period])

        # 현재 구간 [start, now] 과 직전 구간 [start-window, now-window].
        # 끝을 경과 시간까지 맞춰야 한다. TODAY 를 어제 "하루 전체"와 비교하면
        # 오전에는 항상 마이너스가 나온다.
        start = day_start(now.date()) - window + timedelta(days=1)
        previous_start, previous_end = start - window, now - window

        return DashboardSummaryResponse(
            period=query.period,
            generated_at=now,
            members=await self._members(now, start, previous_start, previous_end),
            alarm_notifications=await self._alarm_notifications(now.date()),
            ocr_documents=await self._ocr_documents(),
        )

    @staticmethod
    async def _ocr_documents() -> OcrDocumentStats:
        """OCR 모든 상태의 합계와 화면에 노출하는 주요 상태를 한 번에 집계한다."""
        rows: list[dict[str, Any]] = (
            await OcrJob.all().annotate(total=Count("id")).group_by("status").values("status", "total")
        )
        counts = {OcrJobStatus(row["status"]): row["total"] for row in rows}

        return OcrDocumentStats(
            total=sum(counts.values()),
            queued=counts.get(OcrJobStatus.QUEUED, 0),
            completed=counts.get(OcrJobStatus.COMPLETE, 0),
            failed=counts.get(OcrJobStatus.FAILED, 0),
        )

    @staticmethod
    async def _alarm_notifications(today: date) -> AlarmNotificationStats:
        """ALARM 작업 상태와 최근 7일 성공 발송 수를 집계한다."""
        displayed_statuses = (
            BackgroundJobStatus.QUEUED,
            BackgroundJobStatus.COMPLETED,
            BackgroundJobStatus.FAILED,
        )
        rows: list[dict[str, Any]] = (
            await BackgroundJob.filter(job_type=BackgroundJobType.ALARM, status__in=list(displayed_statuses))
            .annotate(total=Count("id"))
            .group_by("status")
            .values("status", "total")
        )
        counts = {job_status: 0 for job_status in displayed_statuses}
        for row in rows:
            counts[BackgroundJobStatus(row["status"])] = row["total"]

        first = today - timedelta(days=ALARM_TREND_DAYS - 1)
        start, end = day_range(first, today)
        trend_rows: list[dict[str, Any]] = (
            await BackgroundJob.filter(
                job_type=BackgroundJobType.ALARM,
                status=BackgroundJobStatus.COMPLETED,
                completed_at__gte=start,
                completed_at__lt=end,
            )
            .annotate(day=RawSQL("DATE(`completed_at`)"), total=Count("id"))
            .group_by("day")
            .values("day", "total")
        )
        completed_by_day = {AdminDashboardService._as_date(row["day"]): row["total"] for row in trend_rows}

        return AlarmNotificationStats(
            queued=counts[BackgroundJobStatus.QUEUED],
            completed=counts[BackgroundJobStatus.COMPLETED],
            failed=counts[BackgroundJobStatus.FAILED],
            completed_trend=[
                SignupTrendPoint(date=day, count=completed_by_day.get(day, 0))
                for day in (first + timedelta(days=offset) for offset in range(ALARM_TREND_DAYS))
            ],
        )

    async def _members(
        self, now: datetime, start: datetime, previous_start: datetime, previous_end: datetime
    ) -> MemberStats:
        # 상태별 카운트는 한 번의 GROUP BY 로 가져온다. 상태마다 count() 를 돌리면
        # 4번 왕복하고, 그 사이에 가입·정지가 일어나면 합이 서로 어긋난다.
        by_status = await self._count_by_status()
        total = sum(by_status[status] for status in TOTAL_STATUSES)

        new_signups = await User.filter(created_at__gte=start, created_at__lte=now).count()
        previous_signups = await User.filter(created_at__gte=previous_start, created_at__lte=previous_end).count()

        return MemberStats(
            total=total,
            new_signups=new_signups,
            active=by_status[AccountStatus.ACTIVE],
            pending=by_status[AccountStatus.PENDING],
            suspended=by_status[AccountStatus.SUSPENDED],
            withdrawn=by_status[AccountStatus.WITHDRAWN],
            total_change_rate=self._change_rate(total, await self._total_as_of(previous_end)),
            new_signups_change_rate=self._change_rate(new_signups, previous_signups),
            signup_trend=await self._signup_trend(now.date()),
            status=self._alert_status(by_status[AccountStatus.SUSPENDED], total),
        )

    @staticmethod
    async def _count_by_status() -> dict[AccountStatus, int]:
        """상태별 회원 수. GROUP BY 는 0건인 상태를 아예 돌려주지 않으므로 먼저 0으로 채운다."""
        counts = dict.fromkeys(AccountStatus, 0)

        rows: list[dict[str, Any]] = (
            await User.all().annotate(total=Count("id")).group_by("status").values("status", "total")
        )
        for row in rows:
            counts[AccountStatus(row["status"])] = row["total"]
        return counts

    @staticmethod
    async def _total_as_of(moment: datetime) -> int:
        """과거 한 시점의 전체 회원 수(= 활성 + 정지).

        상태 변경 이력 테이블이 없어 '그때의 상태'는 알 수 없고 현재 상태로 근사한다.
        과거에 활성이었다가 지금 탈퇴한 회원은 이 값에서도 빠지므로,
        증감률은 추세를 보는 용도이지 정확한 과거 재현이 아니다.
        """
        return await User.filter(created_at__lte=moment, status__in=list(TOTAL_STATUSES)).count()

    @staticmethod
    async def _signup_trend(today: date) -> list[SignupTrendPoint]:
        """최근 14일 일별 가입 수. 가입자가 없는 날도 0 으로 채운다.

        날짜가 빠지면 차트가 그날을 건너뛰고 그려 추이가 왜곡된다.
        """
        first = today - timedelta(days=SIGNUP_TREND_DAYS - 1)
        start, end = day_range(first, today)

        # created_at 은 이미 KST 로 저장된다(use_tz=False + timezone="Asia/Seoul",
        # MySQL 세션 @@time_zone='+09:00'). 그래서 DATE() 가 그대로 KST 날짜를 준다.
        # CONVERT_TZ 는 mysql.time_zone 테이블이 비면 NULL 을 돌려줘 쓰지 않고,
        # +9시간 보정도 넣으면 안 된다. 이미 KST 인 값을 한 번 더 밀어 15시 이후
        # 가입이 다음 날로 넘어간다. 이 동작은 테스트로 고정해 두었다.
        rows: list[dict[str, Any]] = (
            await User.filter(created_at__gte=start, created_at__lt=end)
            .annotate(day=RawSQL("DATE(`created_at`)"), total=Count("id"))
            .group_by("day")
            .values("day", "total")
        )
        counts = {AdminDashboardService._as_date(row["day"]): row["total"] for row in rows}

        return [
            SignupTrendPoint(date=day, count=counts.get(day, 0))
            for day in (first + timedelta(days=offset) for offset in range(SIGNUP_TREND_DAYS))
        ]

    @staticmethod
    def _alert_status(suspended: int, total: int) -> MemberAlertStatus:
        """정지 비율로 경보 단계를 판정한다. 임계치는 config 에서 바꾼다."""
        if total == 0:
            return MemberAlertStatus.NORMAL

        # 나눗셈 대신 양변에 total 을 곱해 비교한다.
        # suspended/total*100 은 3/30 같은 값에서 부동소수 오차로 경계가 흔들린다.
        ratio = suspended * 100
        if ratio <= config.DASHBOARD_SUSPENDED_WARNING_PERCENT * total:
            return MemberAlertStatus.NORMAL
        if ratio <= config.DASHBOARD_SUSPENDED_DANGER_PERCENT * total:
            return MemberAlertStatus.WARNING
        return MemberAlertStatus.DANGER

    @staticmethod
    def _change_rate(current: int, previous: int) -> float | None:
        """직전 동일 기간 대비 증감률(%). 분모가 0이면 계산할 수 없어 null 이다."""
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    @staticmethod
    def _as_date(value: Any) -> date:
        """DATE() 결과는 드라이버에 따라 date 로도 문자열로도 온다."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))
