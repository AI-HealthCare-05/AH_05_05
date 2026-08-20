from datetime import datetime, time, timedelta
from itertools import count

from starlette import status
from tortoise.contrib.test import TestCase
from tortoise.models import Model

from app.core import config
from app.models.alarms import Alarm, AlarmEvent
from app.models.background_jobs import BackgroundJob
from app.models.care import CareEpisode
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import (
    AccountStatus,
    AdminRole,
    AlarmEventType,
    AlarmType,
    BackgroundJobStatus,
    BackgroundJobType,
    ChatMessageRole,
    ChatMessageStatus,
    MealSlot,
    OcrJobStatus,
)
from app.models.ocr import OcrJob
from app.models.users import User
from app.tests.admin_apis.conftest import auth_header, create_admin, create_user, request

DASHBOARD_URL = "/api/v1/admin/dashboard"

# id(object()) 는 해제된 주소를 재사용해 값이 겹친다. 단조 증가 카운터를 쓴다.
_sequence = count(1)


def unique(prefix: str) -> str:
    return f"{prefix}{next(_sequence)}@example.com"


def now() -> datetime:
    return datetime.now(tz=config.TIMEZONE)


def days_ago(count: int) -> datetime:
    """count 일 전 정오. 자정 경계에 걸려 테스트가 흔들리지 않도록 한낮으로 잡는다."""
    return datetime.combine(now().date() - timedelta(days=count), time(12, 0), tzinfo=config.TIMEZONE)


async def backdate(model: type[Model], pk: int, column: str, when: datetime) -> None:
    """auto_now_add 필드는 create 로 지정할 수 없어 저장 후 덮어쓴다."""
    await model.filter(id=pk).update(**{column: when})


async def create_episode() -> CareEpisode:
    user = await create_user(name="환자", email=unique("patient"))
    return await CareEpisode.create(user=user, title="테스트 케어")


async def create_ocr_job(*, job_status: OcrJobStatus, created_days_ago: int = 0) -> OcrJob:
    job = await OcrJob.create(
        care_episode=await create_episode(),
        status=job_status,
        idempotency_key=unique("key"),
        input_manifest={},
        ocr_model="test",
        structuring_model="test",
        prompt_version="v1",
        schema_version="v1",
    )
    await backdate(OcrJob, job.id, "created_at", days_ago(created_days_ago))
    return job


async def create_chat_message(*, message_status: ChatMessageStatus, role: ChatMessageRole, created_days_ago: int = 0):
    session = await ChatSession.create(care_episode=await create_episode())
    message = await ChatMessage.create(
        chat_session=session, sequence_no=1, role=role, content="q", status=message_status
    )
    await backdate(ChatMessage, message.id, "created_at", days_ago(created_days_ago))
    return message


async def create_alarm_event(*, event_type: AlarmEventType, event_days_ago: int = 0) -> AlarmEvent:
    user = await create_user(name="환자", email=unique("alarm"))
    alarm = await Alarm.create(
        user=user,
        alarm_type=AlarmType.MEDICATION,
        meal_slot=MealSlot.MORNING,
        title="복약",
        scheduled_at=now(),
        next_trigger_at=now(),
    )
    event = await AlarmEvent.create(alarm=alarm, event_type=event_type)
    await backdate(AlarmEvent, event.id, "event_at", days_ago(event_days_ago))
    return event


class DashboardTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.headers = auth_header(self.admin.id)

    async def fetch(self, period: str | None = None) -> dict:
        params = {"period": period} if period else None
        response = await request("GET", DASHBOARD_URL, headers=self.headers, params=params)
        assert response.status_code == status.HTTP_200_OK, response.text
        return response.json()


class TestDashboardMembers(DashboardTestBase):
    async def test_counts_users_by_status(self) -> None:
        await create_user(name="활성1", email="a1@example.com")
        await create_user(name="활성2", email="a2@example.com")
        await create_user(name="정지", email="s1@example.com", status=AccountStatus.SUSPENDED)
        await create_user(name="탈퇴", email="w1@example.com", status=AccountStatus.WITHDRAWN)

        members = (await self.fetch())["members"]

        assert members["totalCount"] == 4
        assert members["activeCount"] == 2
        assert members["suspendedCount"] == 1

    async def test_today_signup_ignores_older_users(self) -> None:
        today = await create_user(name="오늘", email="today@example.com")
        old = await create_user(name="예전", email="old@example.com")
        await backdate(User, old.id, "created_at", days_ago(3))

        members = (await self.fetch())["members"]

        assert members["todaySignupCount"] == 1
        assert today.id  # 오늘 가입자만 세어야 한다

    async def test_period_signup_respects_selected_range(self) -> None:
        for offset in (0, 3, 10):
            user = await create_user(name=f"u{offset}", email=f"u{offset}@example.com")
            await backdate(User, user.id, "created_at", days_ago(offset))

        assert (await self.fetch("TODAY"))["members"]["periodSignupCount"] == 1
        assert (await self.fetch("7D"))["members"]["periodSignupCount"] == 2
        assert (await self.fetch("30D"))["members"]["periodSignupCount"] == 3

    async def test_signup_trend_has_14_points_including_empty_days(self) -> None:
        user = await create_user(name="이틀전", email="t@example.com")
        await backdate(User, user.id, "created_at", days_ago(2))

        trend = (await self.fetch())["members"]["signupTrend"]

        assert len(trend) == 14
        assert [point["date"] for point in trend] == sorted(point["date"] for point in trend)
        assert sum(point["count"] for point in trend) == 1
        target = (now().date() - timedelta(days=2)).isoformat()
        assert next(p["count"] for p in trend if p["date"] == target) == 1

    async def test_change_rate_compares_previous_window(self) -> None:
        """7일 선택이면 그 직전 7일과 비교한다. 2건 -> 3건이면 +50%."""
        for offset in (8, 9):
            user = await create_user(name=f"prev{offset}", email=f"prev{offset}@example.com")
            await backdate(User, user.id, "created_at", days_ago(offset))
        for offset in (0, 1, 2):
            user = await create_user(name=f"cur{offset}", email=f"cur{offset}@example.com")
            await backdate(User, user.id, "created_at", days_ago(offset))

        members = (await self.fetch("7D"))["members"]

        assert members["periodSignupCount"] == 3
        assert members["signupChangeRate"] == 50.0

    async def test_change_rate_is_null_when_previous_window_is_empty(self) -> None:
        """직전 기간이 0건이면 증감률을 정의할 수 없다. 0으로 내리면 '변화 없음'으로 오독된다."""
        await create_user(name="오늘", email="today@example.com")

        assert (await self.fetch("7D"))["members"]["signupChangeRate"] is None


class TestDashboardOcr(DashboardTestBase):
    async def test_counts_jobs_by_status(self) -> None:
        await create_ocr_job(job_status=OcrJobStatus.COMPLETE)
        await create_ocr_job(job_status=OcrJobStatus.COMPLETE)
        await create_ocr_job(job_status=OcrJobStatus.FAILED)
        await create_ocr_job(job_status=OcrJobStatus.QUEUED)
        await create_ocr_job(job_status=OcrJobStatus.PROCESSING)

        ocr = (await self.fetch())["ocr"]

        assert ocr["totalCount"] == 5
        assert ocr["successCount"] == 2
        assert ocr["failureCount"] == 1
        assert ocr["pendingCount"] == 2
        assert ocr["successRate"] == 40.0

    async def test_review_waiting_is_not_counted_as_pending(self) -> None:
        """READY_FOR_REVIEW 는 사용자 확인 대기라 운영 대기열이 아니다."""
        await create_ocr_job(job_status=OcrJobStatus.READY_FOR_REVIEW)

        ocr = (await self.fetch())["ocr"]

        assert ocr["totalCount"] == 1
        assert ocr["pendingCount"] == 0

    async def test_success_rate_is_null_without_jobs(self) -> None:
        assert (await self.fetch())["ocr"]["successRate"] is None


class TestDashboardChat(DashboardTestBase):
    async def test_counts_only_assistant_messages(self) -> None:
        """사용자 질문까지 세면 성공·실패의 합이 전체와 맞지 않는다."""
        await create_chat_message(message_status=ChatMessageStatus.COMPLETED, role=ChatMessageRole.ASSISTANT)
        await create_chat_message(message_status=ChatMessageStatus.COMPLETED, role=ChatMessageRole.ASSISTANT)
        await create_chat_message(message_status=ChatMessageStatus.FAILED, role=ChatMessageRole.ASSISTANT)
        await create_chat_message(message_status=ChatMessageStatus.COMPLETED, role=ChatMessageRole.USER)

        chat = (await self.fetch())["chat"]

        assert chat["totalCount"] == 3
        assert chat["successCount"] == 2
        assert chat["failureCount"] == 1
        assert chat["successRate"] == 66.7


class TestDashboardNotifications(DashboardTestBase):
    async def test_counts_events_by_type(self) -> None:
        await create_alarm_event(event_type=AlarmEventType.SCHEDULED)
        await create_alarm_event(event_type=AlarmEventType.SENT)
        await create_alarm_event(event_type=AlarmEventType.SENT)
        await create_alarm_event(event_type=AlarmEventType.FAILED)

        notifications = (await self.fetch())["notifications"]

        assert notifications["scheduledCount"] == 1
        assert notifications["sentCount"] == 2
        assert notifications["failureCount"] == 1
        # 예약은 아직 시도 전이라 성공률 분모에서 뺀다.
        assert notifications["successRate"] == 66.7

    async def test_daily_trend_has_7_points_and_only_counts_sent(self) -> None:
        await create_alarm_event(event_type=AlarmEventType.SENT, event_days_ago=1)
        await create_alarm_event(event_type=AlarmEventType.FAILED, event_days_ago=1)

        trend = (await self.fetch())["notifications"]["dailySentTrend"]

        assert len(trend) == 7
        assert sum(point["count"] for point in trend) == 1


class TestDashboardSystem(DashboardTestBase):
    async def test_counts_waiting_jobs_including_retries(self) -> None:
        for index, job_status in enumerate(
            [
                BackgroundJobStatus.QUEUED,
                BackgroundJobStatus.RETRY_WAITING,
                BackgroundJobStatus.COMPLETED,
            ]
        ):
            await BackgroundJob.create(
                idempotency_key=f"job-{index}", job_type=BackgroundJobType.LLM, status=job_status
            )

        assert (await self.fetch())["system"]["queuedJobCount"] == 2

    async def test_averages_llm_latency(self) -> None:
        for index, duration in enumerate([1000, 2000, 3000]):
            job = await BackgroundJob.create(
                idempotency_key=f"llm-{index}",
                job_type=BackgroundJobType.LLM,
                status=BackgroundJobStatus.COMPLETED,
                duration_ms=duration,
                completed_at=now(),
            )
            assert job.id

        assert (await self.fetch())["system"]["llmAverageLatencyMs"] == 2000

    async def test_latency_is_null_without_completed_jobs(self) -> None:
        assert (await self.fetch())["system"]["llmAverageLatencyMs"] is None


class TestDashboardContract(DashboardTestBase):
    async def test_defaults_to_7_days(self) -> None:
        body = await self.fetch()

        assert body["period"] == "7D"
        start = datetime.fromisoformat(body["startAt"]).date()
        assert start == now().date() - timedelta(days=6)

    async def test_today_period_starts_at_midnight(self) -> None:
        body = await self.fetch("TODAY")

        start = datetime.fromisoformat(body["startAt"])
        assert body["period"] == "TODAY"
        assert (start.date(), start.hour, start.minute) == (now().date(), 0, 0)

    async def test_returns_all_five_cards(self) -> None:
        body = await self.fetch()

        assert set(body) >= {"members", "chat", "ocr", "notifications", "system"}

    async def test_rejects_unknown_period(self) -> None:
        response = await request("GET", DASHBOARD_URL, headers=self.headers, params={"period": "1Y"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"


class TestDashboardPermissions(DashboardTestBase):
    async def test_staff_can_read_dashboard(self) -> None:
        """대시보드는 조회라 STAFF 도 허용한다(사용자·관리자 목록과 같은 기준)."""
        staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request("GET", DASHBOARD_URL, headers=auth_header(staff.id))

        assert response.status_code == status.HTTP_200_OK

    async def test_requires_authentication(self) -> None:
        response = await request("GET", DASHBOARD_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"

    async def test_suspended_admin_is_rejected(self) -> None:
        suspended = await create_admin(
            name="정지", email="susp@ozcoding.ai", role=AdminRole.ADMIN, status=AccountStatus.SUSPENDED
        )

        response = await request("GET", DASHBOARD_URL, headers=auth_header(suspended.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN
