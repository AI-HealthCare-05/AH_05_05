from datetime import datetime, time, timedelta
from itertools import count as counter
from typing import Any

from starlette import status
from tortoise import Tortoise
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.jwt.tokens import AccessToken
from app.models.background_jobs import BackgroundJob
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import (
    AccountStatus,
    AdminRole,
    BackgroundJobStatus,
    BackgroundJobType,
    ChatMessageRole,
    ChatMessageStatus,
    OcrJobStatus,
)
from app.models.ocr import OcrJob
from app.models.users import User
from app.tests.admin_apis.conftest import auth_header, create_admin, create_user, request

DASHBOARD_SUMMARY_URL = "/api/v1/admin/dashboard/summary"
TREND_DAYS = 14
_sequence = counter(1)


def unique_email(prefix: str = "u") -> str:
    return f"{prefix}{next(_sequence)}@example.com"


def now_kst() -> datetime:
    return datetime.now(tz=config.TIMEZONE)


def at(day_offset: int, hour: int | None = None, minute: int = 0, second: int = 0) -> datetime:
    """day_offset 일 전의 시각(KST).

    hour 를 생략하면 '지금'에서 그만큼 뺀 시각을 쓴다. 정오 같은 고정 시각을 기본값으로
    두면 오전에 테스트를 돌릴 때 미래 시각이 되어 집계에서 빠진다(집계는 now 까지만 센다).
    """
    if hour is None:
        return now_kst() - timedelta(days=day_offset)
    day = now_kst().date() - timedelta(days=day_offset)
    return datetime.combine(day, time(hour, minute, second), tzinfo=config.TIMEZONE)


def before_9am_today() -> datetime:
    """KST 00:00~09:00 사이의 과거 시각. UTC 로는 '어제'에 해당한다.

    아직 09시 전이면 08:59:59 가 미래가 되므로 자정과 지금 사이를 쓴다.
    """
    now = now_kst()
    candidate = at(0, 8, 59, 59)
    if candidate < now:
        return candidate
    midnight = at(0, 0, 0, 0)
    return midnight + (now - midnight) / 2


async def signup_at(when: datetime, *, user_status: AccountStatus = AccountStatus.ACTIVE) -> User:
    """created_at 이 auto_now_add 라 생성 후 소급해서 덮어쓴다."""
    user = await create_user(name="회원", email=unique_email(), status=user_status)
    await User.filter(id=user.id).update(created_at=when)
    return user


class DashboardTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.headers = auth_header(self.admin.id)

    async def fetch(self, period: str | None = None) -> dict[str, Any]:
        params = {"period": period} if period else None
        response = await request("GET", DASHBOARD_SUMMARY_URL, headers=self.headers, params=params)
        assert response.status_code == status.HTTP_200_OK, response.text
        return response.json()

    async def members(self, period: str | None = None) -> dict[str, Any]:
        return (await self.fetch(period))["members"]


class TestSessionTimezoneRegression(TestCase):
    """대시보드 집계 전체가 DB 세션 타임존에 의존한다.

    Tortoise 는 커넥션마다 세션 타임존을 databases.py 의 timezone 값으로 세팅한다.
    이 값이 바뀌면 created_at 의 저장 기준과 DATE() 결과가 함께 바뀌어,
    에러 없이 대시보드 숫자만 조용히 틀어진다. 그래서 여기서 고정한다.
    """

    HINT = (
        "app/core/db/databases.py 의 timezone 설정을 확인하세요. "
        "이 값이 바뀌면 created_at 저장 기준과 DATE() 결과가 함께 바뀌어 "
        "대시보드 집계가 조용히 틀려집니다."
    )

    @staticmethod
    def connection() -> Any:
        # 커넥션 라벨이 앱은 "default", 테스트는 "models" 라 모델에 붙은 값을 그대로 쓴다.
        return Tortoise.get_connection(User._meta.default_connection or "models")

    async def test_session_timezone_offset_is_kst(self) -> None:
        rows = await self.connection().execute_query_dict("SELECT @@session.time_zone AS offset")

        assert rows[0]["offset"] == "+09:00", f"MySQL 세션 타임존이 +09:00 이 아닙니다. {self.HINT}"

    async def test_database_now_matches_kst_wall_clock(self) -> None:
        """오프셋 문자열이 같아도 실제 시각이 어긋나면 집계가 틀어진다."""
        rows = await self.connection().execute_query_dict("SELECT NOW() AS now")

        drift = abs((rows[0]["now"].replace(tzinfo=None) - now_kst().replace(tzinfo=None)).total_seconds())
        assert drift < 60, f"DB 시각이 KST 벽시계와 {drift:.0f}초 차이납니다. {self.HINT}"

    async def test_created_at_is_stored_as_kst_not_utc(self) -> None:
        """저장이 KST 라서 집계에 +9시간 보정을 넣으면 안 된다.

        보정을 넣으면 오후 3시 이후 가입이 다음 날로 넘어간다.
        """
        user = await create_user(name="회원", email=unique_email())

        rows = await self.connection().execute_query_dict(
            "SELECT created_at, DATE(created_at) AS day FROM user WHERE id=%s", [user.id]
        )
        kst = now_kst()
        drift = abs((rows[0]["created_at"].replace(tzinfo=None) - kst.replace(tzinfo=None)).total_seconds())

        assert drift < 60, f"created_at 이 KST 로 저장되지 않았습니다. {self.HINT}"
        assert str(rows[0]["day"]) == str(kst.date()), f"DATE(created_at) 이 KST 날짜와 다릅니다. {self.HINT}"


class TestDashboardStatusCounts(DashboardTestBase):
    async def test_counts_each_status(self) -> None:
        for _ in range(3):
            await signup_at(at(0), user_status=AccountStatus.ACTIVE)
        await signup_at(at(0), user_status=AccountStatus.PENDING)
        for _ in range(2):
            await signup_at(at(0), user_status=AccountStatus.SUSPENDED)
        await signup_at(at(0), user_status=AccountStatus.WITHDRAWN)

        members = await self.members()

        assert members["active"] == 3
        assert members["pending"] == 1
        assert members["suspended"] == 2
        assert members["withdrawn"] == 1

    async def test_total_is_active_plus_suspended_only(self) -> None:
        """화면이 활성 + 정지 = 100% 로 표시하므로 PENDING·WITHDRAWN 은 total 에서 뺀다."""
        await signup_at(at(0), user_status=AccountStatus.ACTIVE)
        await signup_at(at(0), user_status=AccountStatus.SUSPENDED)
        await signup_at(at(0), user_status=AccountStatus.PENDING)
        await signup_at(at(0), user_status=AccountStatus.WITHDRAWN)

        members = await self.members()

        assert members["total"] == 2
        assert members["total"] == members["active"] + members["suspended"]

    async def test_absent_status_is_reported_as_zero(self) -> None:
        """GROUP BY 는 0건인 상태를 아예 돌려주지 않는다. 응답에서는 0이어야 한다."""
        await signup_at(at(0), user_status=AccountStatus.ACTIVE)

        members = await self.members()

        assert members["pending"] == 0
        assert members["suspended"] == 0
        assert members["withdrawn"] == 0

    async def test_all_zero_when_no_users(self) -> None:
        members = await self.members()

        assert members["total"] == 0
        assert members["active"] == 0
        assert members["newSignups"] == 0


class TestDashboardPeriod(DashboardTestBase):
    async def test_new_signups_changes_but_snapshot_counts_do_not(self) -> None:
        """period 는 newSignups 에만 적용된다. total 등은 현재 시점 값이라 그대로다."""
        await signup_at(at(0))
        await signup_at(at(3))
        await signup_at(at(20))

        today = await self.members("TODAY")
        week = await self.members("LAST_7_DAYS")
        month = await self.members("LAST_30_DAYS")

        assert (today["newSignups"], week["newSignups"], month["newSignups"]) == (1, 2, 3)
        assert today["total"] == week["total"] == month["total"] == 3
        assert today["active"] == week["active"] == month["active"] == 3

    async def test_defaults_to_today(self) -> None:
        await signup_at(at(0))
        await signup_at(at(3))

        body = await self.fetch()

        assert body["period"] == "TODAY"
        assert body["members"]["newSignups"] == 1

    async def test_last_7_days_includes_today_and_excludes_day_seven_back(self) -> None:
        await signup_at(at(6))  # 경계 안쪽 (오늘 포함 7일)
        await signup_at(at(7))  # 경계 바깥

        assert (await self.members("LAST_7_DAYS"))["newSignups"] == 1

    async def test_rejects_unknown_period(self) -> None:
        response = await request("GET", DASHBOARD_SUMMARY_URL, headers=self.headers, params={"period": "LAST_YEAR"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "지원하지 않는 집계 기간" in body["message"]


class TestDashboardDateBoundary(DashboardTestBase):
    async def test_yesterday_last_second_is_excluded_from_today(self) -> None:
        await signup_at(at(1, 23, 59, 59))

        assert (await self.members("TODAY"))["newSignups"] == 0

    async def test_today_midnight_is_included(self) -> None:
        await signup_at(at(0, 0, 0, 0))

        assert (await self.members("TODAY"))["newSignups"] == 1

    async def test_before_9am_is_counted_as_today(self) -> None:
        """KST 00~09시는 UTC 로는 어제다. UTC 기준으로 집계하면 오늘에서 누락된다."""
        await signup_at(before_9am_today())

        assert (await self.members("TODAY"))["newSignups"] == 1

    async def test_afternoon_signup_stays_on_its_own_day(self) -> None:
        """저장이 이미 KST 라 +9시간 보정을 넣으면 15시 이후 가입이 다음 날로 밀린다.

        오늘 오후는 실행 시각에 따라 미래가 될 수 있어 이틀 전 15:30 으로 검증한다.
        """
        target = now_kst().date() - timedelta(days=2)
        await signup_at(at(2, 15, 30))

        trend = {point["date"]: point["count"] for point in (await self.members())["signupTrend"]}

        assert trend[target.isoformat()] == 1
        assert trend[(target + timedelta(days=1)).isoformat()] == 0

    async def test_trend_buckets_follow_the_same_boundary(self) -> None:
        """DATE() 그룹핑도 필터와 같은 날짜 경계를 써야 한다."""
        await signup_at(at(0, 0, 0, 0))
        await signup_at(before_9am_today())
        await signup_at(at(1, 23, 59, 59))

        trend = {point["date"]: point["count"] for point in (await self.members())["signupTrend"]}
        today = now_kst().date()

        assert trend[today.isoformat()] == 2
        assert trend[(today - timedelta(days=1)).isoformat()] == 1


class TestSignupTrend(DashboardTestBase):
    async def test_always_returns_14_ascending_days_ending_today(self) -> None:
        trend = (await self.members())["signupTrend"]
        today = now_kst().date()

        assert len(trend) == TREND_DAYS
        dates = [point["date"] for point in trend]
        assert dates == sorted(dates)
        assert dates[-1] == today.isoformat()
        assert dates[0] == (today - timedelta(days=TREND_DAYS - 1)).isoformat()

    async def test_days_without_signups_are_zero_filled(self) -> None:
        """날짜가 빠지면 차트가 그날을 건너뛰어 추이가 왜곡된다."""
        await signup_at(at(2))

        trend = (await self.members())["signupTrend"]

        assert len(trend) == TREND_DAYS
        assert sum(point["count"] for point in trend) == 1
        assert len([point for point in trend if point["count"] == 0]) == TREND_DAYS - 1

    async def test_length_is_independent_of_period(self) -> None:
        for period in ("TODAY", "LAST_7_DAYS", "LAST_30_DAYS"):
            assert len((await self.members(period))["signupTrend"]) == TREND_DAYS

    async def test_ignores_signups_older_than_14_days(self) -> None:
        await signup_at(at(TREND_DAYS))

        assert sum(point["count"] for point in (await self.members())["signupTrend"]) == 0


class TestChangeRate(DashboardTestBase):
    async def test_new_signups_change_rate_compares_previous_window(self) -> None:
        """LAST_7_DAYS 는 직전 7일과 비교한다. 2건 -> 3건이면 +50%."""
        for offset in (8, 9):
            await signup_at(at(offset))
        for offset in (0, 1, 2):
            await signup_at(at(offset))

        members = await self.members("LAST_7_DAYS")

        assert members["newSignups"] == 3
        assert members["newSignupsChangeRate"] == 50.0

    async def test_today_compares_with_same_time_yesterday(self) -> None:
        """어제 하루 전체가 아니라 어제 같은 시각까지와 비교해야 한다.

        어제 늦은 밤 건이 비교 구간에 들어가면 오전에는 증감률이 항상 마이너스로 나온다.
        """
        await signup_at(at(1))  # 어제 지금 시각 — 비교 구간 안
        await signup_at(at(1, 23, 59, 59))  # 어제 늦은 밤 — 비교 구간 밖
        await signup_at(at(0))
        await signup_at(at(0))

        members = await self.members("TODAY")

        assert members["newSignups"] == 2
        # 어제 같은 시각까지는 1건이므로 2건 대비 +100%
        assert members["newSignupsChangeRate"] == 100.0

    async def test_change_rate_is_null_without_previous_data(self) -> None:
        await signup_at(at(0))

        members = await self.members("TODAY")

        assert members["newSignupsChangeRate"] is None
        assert members["totalChangeRate"] is None

    async def test_total_change_rate_uses_previous_boundary(self) -> None:
        await signup_at(at(5))  # 직전 구간 이전부터 존재
        await signup_at(at(0))  # 오늘 신규

        members = await self.members("TODAY")

        assert members["total"] == 2
        assert members["totalChangeRate"] == 100.0


class TestAlertStatus(DashboardTestBase):
    async def _with_ratio(self, active: int, suspended: int) -> str:
        for _ in range(active):
            await signup_at(at(0), user_status=AccountStatus.ACTIVE)
        for _ in range(suspended):
            await signup_at(at(0), user_status=AccountStatus.SUSPENDED)
        return (await self.members())["status"]

    async def test_normal_below_threshold(self) -> None:
        assert await self._with_ratio(active=19, suspended=1) == "NORMAL"  # 5%

    async def test_normal_at_10_percent_boundary(self) -> None:
        """10%는 NORMAL 에 포함된다(이하)."""
        assert await self._with_ratio(active=27, suspended=3) == "NORMAL"

    async def test_warning_just_above_10_percent(self) -> None:
        assert await self._with_ratio(active=8, suspended=1) == "WARNING"  # 11.1%

    async def test_warning_at_20_percent_boundary(self) -> None:
        """20%는 WARNING 에 포함된다(이하)."""
        assert await self._with_ratio(active=8, suspended=2) == "WARNING"

    async def test_danger_above_20_percent(self) -> None:
        assert await self._with_ratio(active=7, suspended=3) == "DANGER"  # 30%

    async def test_normal_when_no_members(self) -> None:
        assert (await self.members())["status"] == "NORMAL"

    async def test_pending_and_withdrawn_do_not_dilute_the_ratio(self) -> None:
        """total 이 활성+정지라 분모에 PENDING·WITHDRAWN 이 끼면 안 된다."""
        for _ in range(7):
            await signup_at(at(0), user_status=AccountStatus.ACTIVE)
        for _ in range(3):
            await signup_at(at(0), user_status=AccountStatus.SUSPENDED)
        for _ in range(50):
            await signup_at(at(0), user_status=AccountStatus.WITHDRAWN)

        assert (await self.members())["status"] == "DANGER"


class TestDashboardContract(DashboardTestBase):
    async def test_generated_at_carries_kst_offset(self) -> None:
        body = await self.fetch()

        assert body["generatedAt"].endswith("+09:00")
        assert datetime.fromisoformat(body["generatedAt"]).utcoffset() == timedelta(hours=9)

    async def test_response_has_dashboard_stat_blocks(self) -> None:
        body = await self.fetch()

        assert set(body) == {
            "period",
            "generatedAt",
            "members",
            "alarmNotifications",
            "ocrDocuments",
            "chatResponses",
        }

    async def test_member_block_fields(self) -> None:
        assert set(await self.members()) == {
            "total",
            "newSignups",
            "active",
            "pending",
            "suspended",
            "withdrawn",
            "totalChangeRate",
            "newSignupsChangeRate",
            "signupTrend",
            "status",
        }


class TestDashboardAlarmNotifications(DashboardTestBase):
    async def create_job(
        self,
        job_status: BackgroundJobStatus,
        *,
        job_type: BackgroundJobType = BackgroundJobType.ALARM,
        completed_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> BackgroundJob:
        job = await BackgroundJob.create(
            idempotency_key=f"dashboard-alarm-{next(_sequence)}",
            job_type=job_type,
            status=job_status,
            completed_at=completed_at,
        )
        if created_at is not None:
            await BackgroundJob.filter(id=job.id).update(created_at=created_at)
            job.created_at = created_at
        return job

    async def test_counts_only_alarm_jobs_in_requested_statuses(self) -> None:
        await self.create_job(BackgroundJobStatus.QUEUED)
        await self.create_job(BackgroundJobStatus.COMPLETED, completed_at=at(0))
        await self.create_job(BackgroundJobStatus.FAILED)
        await self.create_job(
            BackgroundJobStatus.COMPLETED,
            job_type=BackgroundJobType.EMAIL,
            completed_at=at(0),
        )

        notifications = (await self.fetch())["alarmNotifications"]

        assert notifications["queued"] == 1
        assert notifications["completed"] == 1
        assert notifications["failed"] == 1

    async def test_status_counts_include_only_jobs_created_in_selected_period(self) -> None:
        await self.create_job(BackgroundJobStatus.QUEUED, created_at=at(0))
        await self.create_job(BackgroundJobStatus.COMPLETED, completed_at=at(0), created_at=at(6))
        await self.create_job(BackgroundJobStatus.FAILED, created_at=at(7))

        notifications = (await self.fetch("LAST_7_DAYS"))["alarmNotifications"]

        assert notifications["queued"] == 1
        assert notifications["completed"] == 1
        assert notifications["failed"] == 0

    async def test_completed_trend_is_fixed_to_fourteen_days_and_uses_completed_at(self) -> None:
        await self.create_job(BackgroundJobStatus.COMPLETED, completed_at=at(0))
        await self.create_job(BackgroundJobStatus.COMPLETED, completed_at=at(2))
        await self.create_job(BackgroundJobStatus.COMPLETED, completed_at=at(7))
        await self.create_job(BackgroundJobStatus.COMPLETED, completed_at=at(14))
        await self.create_job(BackgroundJobStatus.FAILED, completed_at=at(1))

        today = now_kst().date()
        for period in ("TODAY", "LAST_7_DAYS", "LAST_30_DAYS"):
            trend = (await self.fetch(period))["alarmNotifications"]["completedTrend"]

            assert len(trend) == 14
            assert [point["date"] for point in trend] == sorted(point["date"] for point in trend)
            assert trend[-1]["date"] == today.isoformat()
            assert trend[0]["date"] == (today - timedelta(days=13)).isoformat()
            assert sum(point["count"] for point in trend) == 3


class TestDashboardOcrDocuments(DashboardTestBase):
    async def create_ocr_job(
        self,
        job_status: OcrJobStatus,
        user: User,
        *,
        structured_result: dict[str, object] | None = None,
        created_at: datetime | None = None,
    ) -> OcrJob:
        job = await OcrJob.create(
            user=user,
            status=job_status,
            idempotency_key=f"dashboard-ocr-{next(_sequence)}",
            input_manifest={},
            structured_result=structured_result,
            ocr_model="clova-template",
            structuring_model="rule-based",
            prompt_version="v1",
            schema_version="v1",
        )
        if created_at is not None:
            await OcrJob.filter(id=job.id).update(created_at=created_at)
            job.created_at = created_at
        return job

    async def test_total_includes_every_status_and_cards_count_selected_statuses(self) -> None:
        user = await create_user(name="OCR 회원", email=unique_email("ocr"))
        statuses = [
            OcrJobStatus.QUEUED,
            OcrJobStatus.PROCESSING,
            OcrJobStatus.READY_FOR_REVIEW,
            OcrJobStatus.COMPLETE,
            OcrJobStatus.COMPLETE,
            OcrJobStatus.FAILED,
            OcrJobStatus.CANCELLED,
        ]
        for job_status in statuses:
            await self.create_ocr_job(job_status, user)

        documents = (await self.fetch())["ocrDocuments"]

        assert documents == {
            "total": 7,
            "queued": 1,
            "completed": 2,
            "failed": 1,
            "avgFieldConfidence": None,
        }

    async def test_counts_include_only_jobs_created_in_selected_period(self) -> None:
        user = await create_user(name="OCR 회원", email=unique_email("ocr-period"))
        await self.create_ocr_job(OcrJobStatus.QUEUED, user, created_at=at(0))
        await self.create_ocr_job(OcrJobStatus.COMPLETE, user, created_at=at(6))
        await self.create_ocr_job(OcrJobStatus.FAILED, user, created_at=at(7))

        documents = (await self.fetch("LAST_7_DAYS"))["ocrDocuments"]

        assert documents["total"] == 2
        assert documents["queued"] == 1
        assert documents["completed"] == 1
        assert documents["failed"] == 0

    async def test_field_confidence_averages_jobs_in_selected_created_at_period(self) -> None:
        user = await create_user(name="OCR 회원", email=unique_email("ocr-confidence"))
        await self.create_ocr_job(
            OcrJobStatus.COMPLETE,
            user,
            structured_result={"ocrFields": [{"confidence": 1.0}, {"confidence": 0.8}]},
            created_at=at(0),
        )
        await self.create_ocr_job(
            OcrJobStatus.COMPLETE,
            user,
            structured_result={"ocrFields": [{"confidence": 0.6}]},
            created_at=at(3),
        )
        await self.create_ocr_job(
            OcrJobStatus.COMPLETE,
            user,
            structured_result={"ocrFields": []},
            created_at=at(1),
        )
        await self.create_ocr_job(
            OcrJobStatus.COMPLETE,
            user,
            structured_result={"ocrFields": [{"confidence": 0.0}]},
            created_at=at(8),
        )

        documents = (await self.fetch("LAST_7_DAYS"))["ocrDocuments"]

        assert documents["avgFieldConfidence"] == 0.75


class TestDashboardChatResponses(DashboardTestBase):
    async def create_session(self, *, is_like: bool | None = None, created_at: datetime | None = None) -> ChatSession:
        user = await create_user(name="챗봇 회원", email=unique_email("chat"))
        session = await ChatSession.create(user=user, is_like=is_like)
        if created_at is not None:
            await ChatSession.filter(id=session.id).update(created_at=created_at)
            session.created_at = created_at
        return session

    @staticmethod
    async def create_message(
        session: ChatSession,
        *,
        role: ChatMessageRole = ChatMessageRole.ASSISTANT,
        message_status: ChatMessageStatus,
        completed_at: datetime | None,
    ) -> ChatMessage:
        return await ChatMessage.create(
            chat_session=session,
            sequence_no=1,
            role=role,
            content="테스트 메시지",
            status=message_status,
            completed_at=completed_at,
        )

    async def test_counts_only_terminal_assistant_responses_in_selected_period(self) -> None:
        await self.create_message(
            await self.create_session(),
            message_status=ChatMessageStatus.COMPLETED,
            completed_at=at(0),
        )
        await self.create_message(
            await self.create_session(),
            message_status=ChatMessageStatus.FAILED,
            completed_at=at(2),
        )
        await self.create_message(
            await self.create_session(),
            message_status=ChatMessageStatus.PENDING,
            completed_at=None,
        )
        await self.create_message(
            await self.create_session(),
            role=ChatMessageRole.USER,
            message_status=ChatMessageStatus.COMPLETED,
            completed_at=at(0),
        )
        await self.create_message(
            await self.create_session(),
            message_status=ChatMessageStatus.COMPLETED,
            completed_at=at(8),
        )

        responses = (await self.fetch("LAST_7_DAYS"))["chatResponses"]

        assert responses == {"total": 2, "completed": 1, "failed": 1, "likeRate": None}

    async def test_like_rate_uses_only_evaluated_sessions_created_in_selected_period(self) -> None:
        await self.create_session(is_like=True, created_at=at(0))
        await self.create_session(is_like=True, created_at=at(1))
        await self.create_session(is_like=False, created_at=at(2))
        await self.create_session(is_like=None, created_at=at(0))
        await self.create_session(is_like=False, created_at=at(8))

        responses = (await self.fetch("LAST_7_DAYS"))["chatResponses"]

        assert responses["likeRate"] == 66.7


class TestDashboardPermissions(DashboardTestBase):
    async def test_staff_is_allowed(self) -> None:
        """대시보드는 역할을 가리지 않는다."""
        staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request("GET", DASHBOARD_SUMMARY_URL, headers=auth_header(staff.id))

        assert response.status_code == status.HTTP_200_OK

    async def test_requires_authentication(self) -> None:
        response = await request("GET", DASHBOARD_SUMMARY_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"

    async def test_pending_admin_is_allowed(self) -> None:
        """비밀번호 변경이 선택제가 되면서 PENDING 도 열렸다(예전에는 403 이었다)."""
        pending = await create_admin(
            name="대기", email="pending@ozcoding.ai", role=AdminRole.ADMIN, status=AccountStatus.PENDING
        )

        response = await request("GET", DASHBOARD_SUMMARY_URL, headers=auth_header(pending.id))

        assert response.status_code == status.HTTP_200_OK

    async def test_suspended_admin_is_forbidden(self) -> None:
        suspended = await create_admin(
            name="정지", email="susp@ozcoding.ai", role=AdminRole.ADMIN, status=AccountStatus.SUSPENDED
        )

        response = await request("GET", DASHBOARD_SUMMARY_URL, headers=auth_header(suspended.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_non_admin_token_is_forbidden(self) -> None:
        """사용자 토큰에는 scope=admin 이 없다. id 가 겹쳐도 통과하면 안 된다."""
        user = await create_user(name="회원", email=unique_email())
        token = AccessToken()
        token["sub"] = str(user.id)

        response = await request("GET", DASHBOARD_SUMMARY_URL, headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"
