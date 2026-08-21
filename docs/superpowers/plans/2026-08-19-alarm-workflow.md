# Alarm Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JWT 기반 알람 업무 API, 내부 BackgroundJob 관리 API, ARQ/Redis 스케줄러와 `pywebpush` 발송·재시도 흐름을 구현한다.

**Architecture:** FastAPI Router는 HTTP 계약만 담당하고 Service가 소유권·상태 전환·트랜잭션을 처리하며 Repository가 Tortoise ORM 접근을 캡슐화한다. 별도 `alarm-worker` 프로세스가 due alarm을 기기별 BackgroundJob으로 fan-out하고 Redis/ARQ에서 `pywebpush.webpush_async` 발송을 실행한다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, Tortoise ORM, MySQL 8, ARQ 0.28.0, Redis, pywebpush 2.4.0, python-dateutil, pytest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-08-19-alarm-workflow-design.md`

## Global Constraints

- 작업 루트는 `/Users/admin/PycharmProjects/FinalProject`다.
- 커밋을 생성하지 않는다. 각 Task 종료 시 `git diff --check`와 관련 테스트 결과만 기록한다.
- 사용자 API는 JWT를 요구하고 로그인 사용자의 Alarm, PushSubscription, CareEpisode, RecoveryGuide만 접근한다.
- 내부 작업 API는 `X-Internal-API-Key`를 `INTERNAL_API_KEY`와 상수 시간 비교한다.
- AlarmEvent와 BackgroundJob은 API로 물리 삭제하지 않는다.
- Alarm DELETE는 `CANCELLED`, PushSubscription DELETE는 `is_active=false`로 처리한다.
- 자동 재시도는 같은 BackgroundJob 행, 수동 재처리는 `FAILED` 원본을 가리키는 새 행을 사용한다.
- HTTP 404/410은 구독 만료, 네트워크·timeout·429·5xx는 일시 실패로 분류한다.
- 실제 secret과 개인 데이터는 저장소, 로그, 오류 메시지에 추가하지 않는다.
- 기존 사용자 변경과 관련 없는 파일은 수정하지 않는다.

---

## File Structure

### 신규 파일

- `app/apis/v1/alarm_router.py`: 사용자 알람·구독·이벤트 HTTP API
- `app/apis/v1/job_router.py`: 내부 BackgroundJob 조회·재처리·취소 API
- `app/dtos/alarms.py`: 알람·구독·이벤트 요청/응답 DTO
- `app/dtos/background_jobs.py`: 작업 필터·응답 DTO
- `app/repositories/alarm_repository.py`: 알람 도메인 DB 접근
- `app/repositories/background_job_repository.py`: BackgroundJob DB 접근
- `app/services/alarm_schedule.py`: timezone/RRULE/회차 계산 순수 함수
- `app/services/alarms.py`: 알람·구독·이벤트 업무 규칙과 트랜잭션
- `app/services/background_jobs.py`: 작업 생성·상태 전환·재처리·ARQ 등록
- `app/services/web_push.py`: payload 생성과 Web Push 결과 분류
- `app/workers/__init__.py`: Worker 패키지
- `app/workers/alarm_worker.py`: ARQ startup/shutdown, cron, 발송 함수
- `app/dependencies/internal_auth.py`: 내부 API 키 Dependency
- `app/tests/alarm_apis/helpers.py`: 회원 생성·로그인 테스트 helper
- `app/tests/alarm_apis/test_alarm_crud_api.py`: 알람 CRUD/상태 테스트
- `app/tests/alarm_apis/test_push_subscription_api.py`: 구독 API 테스트
- `app/tests/alarm_apis/test_alarm_event_api.py`: 이벤트 API 테스트
- `app/tests/job_apis/test_job_api.py`: 내부 작업 API 테스트
- `app/tests/services/test_alarm_schedule.py`: RRULE/timezone 테스트
- `app/tests/services/test_web_push.py`: 전송 결과 분류 테스트
- `app/tests/workers/test_alarm_worker.py`: 스케줄러/fan-out/재시도 테스트

### 수정 파일

- `app/apis/v1/__init__.py`: alarm_router와 job_router 등록
- `app/core/config.py`: Redis, VAPID, 내부 API, 알람 Worker 설정
- `pyproject.toml`, `uv.lock`: ARQ와 pywebpush 의존성
- `docker-compose.yml`: alarm-worker 서비스
- `infra/docker/docker-compose.prod.yml`: 운영 alarm-worker 서비스
- `envs/example.prod.env`: 비밀 값 없는 환경변수 예시

---

### Task 1: Dependencies, Configuration, and Internal Authentication

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `app/core/config.py`
- Modify: `envs/example.prod.env`
- Create: `app/dependencies/internal_auth.py`
- Create: `app/tests/job_apis/__init__.py`
- Create: `app/tests/job_apis/test_internal_auth.py`

**Interfaces:**
- Produces: `require_internal_api_key(x_internal_api_key: str | None) -> None`
- Produces config: `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `INTERNAL_API_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`, `ALARM_POLL_SECONDS`, `ALARM_MAX_RETRY_COUNT`, `ALARM_RETRY_BASE_SECONDS`, `ALARM_PUSH_TTL_SECONDS`, `ALARM_CLICK_URL`

- [ ] **Step 1: Write failing internal-auth tests**

```python
import pytest
from fastapi import HTTPException

from app.dependencies.internal_auth import require_internal_api_key


def test_internal_key_accepts_matching_value(monkeypatch):
    monkeypatch.setattr("app.dependencies.internal_auth.config.INTERNAL_API_KEY", "test-key")
    assert require_internal_api_key("test-key") is None


def test_internal_key_rejects_invalid_value(monkeypatch):
    monkeypatch.setattr("app.dependencies.internal_auth.config.INTERNAL_API_KEY", "test-key")
    with pytest.raises(HTTPException) as error:
        require_internal_api_key("wrong-key")
    assert error.value.status_code == 403
```

- [ ] **Step 2: Run the test and confirm the missing module failure**

Run: `uv run pytest app/tests/job_apis/test_internal_auth.py -q`

Expected: FAIL because `app.dependencies.internal_auth` does not exist.

- [ ] **Step 3: Add pinned app dependencies**

Run: `uv add --group app "arq==0.28.0" "pywebpush==2.4.0"`

Expected: `pyproject.toml` and `uv.lock` contain both packages and resolve for Python 3.13.

- [ ] **Step 4: Add typed configuration fields**

Add to `Config` with development-safe non-secret defaults only where safe:

```python
REDIS_HOST: str = "localhost"
REDIS_PORT: int = 6379
REDIS_DB: int = 0
INTERNAL_API_KEY: str = ""
VAPID_PRIVATE_KEY: str = ""
VAPID_PUBLIC_KEY: str = ""
VAPID_SUBJECT: str = "mailto:admin@example.com"
ALARM_POLL_SECONDS: int = 10
ALARM_MAX_RETRY_COUNT: int = 3
ALARM_RETRY_BASE_SECONDS: int = 30
ALARM_PUSH_TTL_SECONDS: int = 300
ALARM_CLICK_URL: str = "/"
```

`envs/example.prod.env`에는 변수명과 로컬 예시만 추가하고 실제 key를 넣지 않는다.

- [ ] **Step 5: Implement constant-time internal authentication**

```python
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core import config


def require_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header(alias="X-Internal-API-Key")] = None,
) -> None:
    expected = config.INTERNAL_API_KEY
    if not expected or not x_internal_api_key or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key.")
```

- [ ] **Step 6: Run tests and static checks**

Run: `uv run pytest app/tests/job_apis/test_internal_auth.py -q`

Expected: 2 tests PASS.

Run: `uv run ruff check app/core/config.py app/dependencies/internal_auth.py app/tests/job_apis/test_internal_auth.py`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 2: Alarm DTOs and Scheduling Rules

**Files:**
- Create: `app/dtos/alarms.py`
- Create: `app/services/alarm_schedule.py`
- Create: `app/tests/services/__init__.py`
- Create: `app/tests/services/test_alarm_schedule.py`

**Interfaces:**
- Produces: `AlarmCreateRequest`, `AlarmUpdateRequest`, `AlarmResponse`, `AlarmListResponse`
- Produces: `PushSubscriptionUpsertRequest`, `PushSubscriptionResponse`, `DeliveryAckRequest`, `AlarmEventResponse`
- Produces: `parse_timezone(name: str) -> ZoneInfo`
- Produces: `next_occurrence(rule: str, dtstart: datetime, after: datetime) -> datetime | None`
- Produces: `validate_alarm_shape(alarm_type: AlarmType, meal_slot: MealSlot | None) -> None`

- [ ] **Step 1: Write failing schedule and DTO tests**

```python
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.dtos.alarms import AlarmCreateRequest
from app.models.enums import AlarmType
from app.services.alarm_schedule import next_occurrence, parse_timezone


def test_medication_requires_meal_slot():
    with pytest.raises(ValidationError):
        AlarmCreateRequest(
            alarm_type=AlarmType.MEDICATION,
            title="아침약",
            scheduled_at="2026-08-20T08:00:00+09:00",
            timezone="Asia/Seoul",
        )


def test_rrule_returns_next_occurrence():
    start = datetime.fromisoformat("2026-08-20T08:00:00+09:00")
    result = next_occurrence("FREQ=DAILY", start, start)
    assert result == datetime.fromisoformat("2026-08-21T08:00:00+09:00")


def test_invalid_timezone_is_rejected():
    with pytest.raises(ValueError):
        parse_timezone("Not/AZone")
```

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/services/test_alarm_schedule.py -q`

Expected: FAIL on missing DTO and scheduling modules.

- [ ] **Step 3: Implement focused scheduling functions**

```python
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr


def parse_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Invalid timezone.") from exc


def next_occurrence(rule: str, dtstart: datetime, after: datetime) -> datetime | None:
    return rrulestr(rule, dtstart=dtstart).after(after, inc=False)
```

Add a separate `validate_alarm_shape` that raises `ValueError` for MEDICATION without meal slot and for non-MEDICATION with a meal slot.

- [ ] **Step 4: Implement DTO validation and serialized responses**

Use `BaseSerializerModel` for response models and Pydantic `model_validator(mode="after")` for the alarm type/meal slot relationship. Require timezone-aware datetimes, title length 1..255, message max 500, recurrence max 100, endpoint max 500, and key max 255.

```python
class AlarmCreateRequest(BaseModel):
    care_episode_id: int | None = None
    source_guide_id: int | None = None
    alarm_type: AlarmType = AlarmType.MEDICATION
    meal_slot: MealSlot | None = None
    title: Annotated[str, Field(min_length=1, max_length=255)]
    message: Annotated[str | None, Field(max_length=500)] = None
    scheduled_at: datetime
    recurrence_rule: Annotated[str | None, Field(max_length=100)] = None
    timezone: Annotated[str, Field(max_length=50)] = "Asia/Seoul"
```

- [ ] **Step 5: Run focused tests and Ruff**

Run: `uv run pytest app/tests/services/test_alarm_schedule.py -q`

Expected: PASS.

Run: `uv run ruff check app/dtos/alarms.py app/services/alarm_schedule.py app/tests/services/test_alarm_schedule.py`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 3: Alarm Repository and Business Service

**Files:**
- Create: `app/repositories/alarm_repository.py`
- Create: `app/services/alarms.py`
- Create: `app/tests/alarm_apis/__init__.py`
- Create: `app/tests/alarm_apis/helpers.py`
- Create: `app/tests/alarm_apis/test_alarm_service.py`

**Interfaces:**
- Consumes: DTOs and scheduling functions from Task 2
- Produces: `AlarmRepository.get_owned_alarm(alarm_id: int, user_id: int) -> Alarm | None`
- Produces: `AlarmRepository.list_owned_alarms(...) -> tuple[list[Alarm], int]`
- Produces: `AlarmService.create_alarm(user: User, data: AlarmCreateRequest) -> Alarm`
- Produces: `AlarmService.update_alarm(user: User, alarm_id: int, data: AlarmUpdateRequest) -> Alarm`
- Produces: `AlarmService.transition(user: User, alarm_id: int, action: AlarmAction) -> Alarm`

- [ ] **Step 1: Write failing service tests for ownership, creation, and transition**

```python
async def test_create_alarm_writes_scheduled_event(user):
    alarm = await AlarmService().create_alarm(user, medication_alarm_request())
    assert alarm.status == AlarmStatus.ACTIVE
    event = await AlarmEvent.get(alarm_id=alarm.id)
    assert event.event_type == AlarmEventType.SCHEDULED


async def test_other_user_cannot_read_alarm(user, other_user):
    alarm = await Alarm.create(user=user, **alarm_fields())
    with pytest.raises(HTTPException) as error:
        await AlarmService().get_alarm(other_user, alarm.id)
    assert error.value.status_code == 404


async def test_delete_soft_cancels_alarm(user):
    alarm = await Alarm.create(user=user, **alarm_fields())
    result = await AlarmService().cancel_alarm(user, alarm.id)
    assert result.status == AlarmStatus.CANCELLED
    assert result.cancelled_at is not None
```

The helper creates active users directly through existing models and builds timezone-aware request data; avoid repeating signup/login when testing Service behavior.

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/alarm_apis/test_alarm_service.py -q`

Expected: FAIL because repository and service do not exist.

- [ ] **Step 3: Implement repository queries with explicit ownership filters**

Repository methods must include:

```python
async def get_owned_alarm(self, alarm_id: int, user_id: int) -> Alarm | None:
    return await Alarm.get_or_none(id=alarm_id, user_id=user_id)

async def get_owned_subscription(self, subscription_id: int, user_id: int) -> PushSubscription | None: ...
async def get_subscription_by_endpoint(self, endpoint: str) -> PushSubscription | None: ...
async def list_active_subscriptions(self, user_id: int) -> list[PushSubscription]: ...
async def list_events(self, alarm_id: int, offset: int, limit: int) -> tuple[list[AlarmEvent], int]: ...
```

List filters are `status`, `alarm_type`, `care_episode_id`, `offset`, and `limit`, ordered by `next_trigger_at`, then `id`.

- [ ] **Step 4: Implement transactional creation and ownership checks**

`create_alarm` must:

1. Validate CareEpisode with `id` and `user_id`.
2. Validate RecoveryGuide through `care_episode__user_id` and, when both IDs are given, ensure guide belongs to that episode.
3. Parse timezone and RRULE before opening the transaction.
4. Create Alarm and SCHEDULED event in `in_transaction()`.
5. Convert Tortoise unique violations to HTTP 409.

- [ ] **Step 5: Implement explicit state transitions**

```python
class AlarmAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    COMPLETE = "complete"
    SKIP = "skip"
    CANCEL = "cancel"
```

Use a transition map. `COMPLETE` writes `completed_at` and a COMPLETED event. `SKIP` writes a SKIPPED event and consumes the current one-shot occurrence or advances a recurring occurrence. CANCEL is idempotent and never deletes rows.

- [ ] **Step 6: Run service tests and inspect DB state assertions**

Run: `uv run pytest app/tests/alarm_apis/test_alarm_service.py -q`

Expected: PASS for creation, ownership, validation, update, state transitions, and soft delete.

Run: `uv run ruff check app/repositories/alarm_repository.py app/services/alarms.py app/tests/alarm_apis`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 4: User Alarm, Subscription, and Event APIs

**Files:**
- Create: `app/apis/v1/alarm_router.py`
- Modify: `app/apis/v1/__init__.py`
- Modify: `app/services/alarms.py`
- Create: `app/tests/alarm_apis/test_alarm_crud_api.py`
- Create: `app/tests/alarm_apis/test_push_subscription_api.py`
- Create: `app/tests/alarm_apis/test_alarm_event_api.py`

**Interfaces:**
- Consumes: `AlarmService` from Task 3 and `get_request_user`
- Produces: all `/api/v1/alarms` endpoints in the spec
- Produces service methods: `upsert_subscription`, `deactivate_subscription`, `list_events`, `acknowledge_delivery`

- [ ] **Step 1: Write failing API tests using the existing ASGI client pattern**

```python
async def test_create_and_get_alarm(authenticated_client):
    response = await authenticated_client.post("/api/v1/alarms", json=alarm_payload())
    assert response.status_code == 201
    alarm_id = response.json()["id"]
    detail = await authenticated_client.get(f"/api/v1/alarms/{alarm_id}")
    assert detail.status_code == 200


async def test_subscription_delete_is_soft(authenticated_client):
    created = await authenticated_client.put("/api/v1/alarms/push-subscriptions", json=subscription_payload())
    response = await authenticated_client.delete(
        f"/api/v1/alarms/push-subscriptions/{created.json()['id']}"
    )
    assert response.status_code == 204
    assert await PushSubscription.filter(id=created.json()["id"], is_active=False).exists()
```

Also test 401 without JWT, 404 for another user's resource, filters, 409 transitions, public VAPID key, and duplicate delivery acknowledgement.

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/alarm_apis/test_alarm_crud_api.py app/tests/alarm_apis/test_push_subscription_api.py app/tests/alarm_apis/test_alarm_event_api.py -q`

Expected: FAIL because routes are not registered.

- [ ] **Step 3: Implement subscription business methods**

`PUT` is endpoint-based upsert:

- New endpoint: create for current user.
- Same user's endpoint: update keys/platform/user_agent and reactivate.
- Endpoint owned by another user: HTTP 409; never transfer ownership silently.
- DELETE: current user ownership check and `is_active=false`.

- [ ] **Step 4: Implement event query and acknowledgement**

`acknowledge_delivery` verifies the alarm and subscription are owned by the current user. If a matching DELIVERED event already exists for the same alarm/subscription, return it; otherwise append a new event. Do not expose generic event create/update/delete endpoints.

- [ ] **Step 5: Implement Router with static routes before `/{alarm_id}`**

Use `APIRouter(prefix="/alarms", tags=["alarms"])`. Return response models with `model_dump(mode="json")`. Register the router in `app/apis/v1/__init__.py`.

Key signatures:

```python
@alarm_router.put("/push-subscriptions", response_model=PushSubscriptionResponse)
async def upsert_push_subscription(...): ...

@alarm_router.post("/{alarm_id}/delivery-ack", response_model=AlarmEventResponse)
async def acknowledge_alarm_delivery(...): ...
```

- [ ] **Step 6: Run all alarm API tests**

Run: `uv run pytest app/tests/alarm_apis -q`

Expected: PASS.

Run: `uv run ruff check app/apis/v1/alarm_router.py app/apis/v1/__init__.py app/services/alarms.py app/tests/alarm_apis`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 5: BackgroundJob Repository and Service

**Files:**
- Create: `app/dtos/background_jobs.py`
- Create: `app/repositories/background_job_repository.py`
- Create: `app/services/background_jobs.py`
- Create: `app/tests/job_apis/test_background_job_service.py`

**Interfaces:**
- Produces: `BackgroundJobFilter`, `BackgroundJobResponse`, `BackgroundJobListResponse`
- Produces: `BackgroundJobService.create_alarm_job(...) -> tuple[BackgroundJob, bool]`
- Produces: `BackgroundJobService.cancel(job_id: int) -> BackgroundJob`
- Produces: `BackgroundJobService.retry_failed(job_id: int) -> BackgroundJob`
- Produces: `BackgroundJobService.enqueue(job: BackgroundJob, *, alarm_id: int, subscription_id: int, trigger_at: datetime, defer_seconds: int = 0) -> None`

- [ ] **Step 1: Write failing service tests**

```python
async def test_alarm_job_creation_is_idempotent(alarm, subscription):
    service = BackgroundJobService(redis_pool=AsyncMock())
    first, first_created = await service.create_alarm_job(alarm, subscription, alarm.next_trigger_at)
    second, second_created = await service.create_alarm_job(alarm, subscription, alarm.next_trigger_at)
    assert first.id == second.id
    assert first_created is True
    assert second_created is False


async def test_manual_retry_creates_child_of_failed_job(failed_alarm_job):
    retried = await BackgroundJobService(redis_pool=AsyncMock()).retry_failed(failed_alarm_job.id)
    assert retried.parent_job_id == failed_alarm_job.id
    assert retried.status == BackgroundJobStatus.QUEUED
```

Test cancellation only for QUEUED/RETRY_WAITING, 409 for PROCESSING, and 409 retry for non-FAILED jobs.

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/job_apis/test_background_job_service.py -q`

Expected: FAIL on missing DTO/repository/service modules.

- [ ] **Step 3: Implement BackgroundJob repository**

Required methods:

```python
async def get(self, job_id: int) -> BackgroundJob | None: ...
async def get_by_idempotency_key(self, key: str) -> BackgroundJob | None: ...
async def list(self, filters: BackgroundJobFilter) -> tuple[list[BackgroundJob], int]: ...
async def claim(self, job_id: int) -> bool: ...
async def find_recoverable(self, now: datetime, limit: int) -> list[BackgroundJob]: ...
```

`claim` updates QUEUED/RETRY_WAITING to PROCESSING only when the previous state matches.

- [ ] **Step 4: Implement idempotent creation and enqueue boundary**

Use key `alarm:{alarm_id}:{subscription_id}:{trigger_at.isoformat()}`. Catch unique constraint races, reload the existing row, and return `(existing, False)`. ARQ `_job_id` uses the same key.

```python
await redis_pool.enqueue_job(
    "send_alarm_push",
    job.id,
    alarm_id,
    subscription_id,
    trigger_at.isoformat(),
    _job_id=job.idempotency_key,
    _defer_by=timedelta(seconds=defer_seconds) if defer_seconds else None,
)
```

- [ ] **Step 5: Implement cancel and failed-job retry**

Manual retry loads the original FAILED AlarmEvent through `reference_table="alarm_events"` and `reference_id`, recovers `alarm_id` and `push_subscription_id`, creates a new key suffixed with `:manual:{uuid4().hex}`, sets `parent_job`, and enqueues the new job. Missing reference or subscription returns HTTP 409.

- [ ] **Step 6: Run service tests and static checks**

Run: `uv run pytest app/tests/job_apis/test_background_job_service.py -q`

Expected: PASS.

Run: `uv run ruff check app/dtos/background_jobs.py app/repositories/background_job_repository.py app/services/background_jobs.py app/tests/job_apis/test_background_job_service.py`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 6: Internal Job Router

**Files:**
- Create: `app/apis/v1/job_router.py`
- Modify: `app/apis/v1/__init__.py`
- Create: `app/tests/job_apis/test_job_api.py`

**Interfaces:**
- Consumes: Task 1 internal dependency and Task 5 service/DTOs
- Produces: `/api/v1/internal/jobs` list, detail, retry, cancel APIs

- [ ] **Step 1: Write failing API tests**

```python
async def test_job_list_requires_internal_key(client):
    response = await client.get("/api/v1/internal/jobs")
    assert response.status_code == 403


async def test_job_list_is_not_scoped_by_user(client, jobs_for_two_users, internal_headers):
    response = await client.get("/api/v1/internal/jobs", headers=internal_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2
```

Add detail 404, filter, successful retry, retry conflict, successful cancel, and processing cancel conflict tests.

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/job_apis/test_job_api.py -q`

Expected: FAIL because the Router is not registered.

- [ ] **Step 3: Implement internal Router dependency at router level**

```python
job_router = APIRouter(
    prefix="/internal/jobs",
    tags=["internal-jobs"],
    dependencies=[Depends(require_internal_api_key)],
)
```

Add query parameters for `job_type`, `status`, `user_id`, `requested_from`, `requested_to`, `offset >= 0`, and `1 <= limit <= 100`.

- [ ] **Step 4: Register Router and run tests**

Run: `uv run pytest app/tests/job_apis/test_internal_auth.py app/tests/job_apis/test_background_job_service.py app/tests/job_apis/test_job_api.py -q`

Expected: PASS.

Run: `uv run ruff check app/apis/v1/job_router.py app/apis/v1/__init__.py app/tests/job_apis`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 7: Web Push Service and Result Classification

**Files:**
- Create: `app/services/web_push.py`
- Create: `app/tests/services/test_web_push.py`

**Interfaces:**
- Produces: `PushResultKind(StrEnum): SUCCESS, EXPIRED, RETRYABLE, PERMANENT_FAILURE`
- Produces: `PushResult(kind: PushResultKind, status_code: int | None, error_code: str | None)`
- Produces: `WebPushService.send(subscription: PushSubscription, payload: dict[str, object]) -> PushResult`
- Produces: `WebPushService.build_payload(alarm: Alarm, medications: list[Medication]) -> dict[str, object]`

- [ ] **Step 1: Write failing classification tests**

```python
async def test_send_success(monkeypatch, subscription):
    monkeypatch.setattr("app.services.web_push.webpush_async", AsyncMock(return_value=FakeResponse(201)))
    result = await WebPushService().send(subscription, {"title": "복약 알림"})
    assert result.kind == PushResultKind.SUCCESS


@pytest.mark.parametrize("status_code", [404, 410])
async def test_expired_subscription(status_code, monkeypatch, subscription):
    monkeypatch.setattr(
        "app.services.web_push.webpush_async",
        AsyncMock(side_effect=web_push_error(status_code)),
    )
    result = await WebPushService().send(subscription, {})
    assert result.kind == PushResultKind.EXPIRED
```

Add 429/500/network timeout as RETRYABLE and 400/401/403 as PERMANENT_FAILURE.

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/services/test_web_push.py -q`

Expected: FAIL on missing service.

- [ ] **Step 3: Implement payload without leaking subscription keys**

Payload keys are `alarmId`, `title`, `body`, `clickUrl`, `alarmType`, `mealSlot`, and `triggerAt`. For MEDICATION, query active medication names for the alarm care episode and meal slot and build the body at send time; fall back to the Alarm message when there are no matching medications.

- [ ] **Step 4: Implement asynchronous send and deterministic classification**

```python
response = await webpush_async(
    subscription_info={
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
    },
    data=orjson.dumps(payload).decode(),
    vapid_private_key=config.VAPID_PRIVATE_KEY,
    vapid_claims={"sub": config.VAPID_SUBJECT},
    ttl=config.ALARM_PUSH_TTL_SECONDS,
    timeout=10,
)
```

Never include the private key, p256dh key, auth key, endpoint, or medical source text in returned errors.

- [ ] **Step 5: Run tests and Ruff**

Run: `uv run pytest app/tests/services/test_web_push.py -q`

Expected: PASS for all result classes.

Run: `uv run ruff check app/services/web_push.py app/tests/services/test_web_push.py`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 8: ARQ Alarm Scheduler, Sender, and Recovery

**Files:**
- Create: `app/workers/__init__.py`
- Create: `app/workers/alarm_worker.py`
- Modify: `app/repositories/alarm_repository.py`
- Modify: `app/services/background_jobs.py`
- Create: `app/tests/workers/__init__.py`
- Create: `app/tests/workers/test_alarm_worker.py`

**Interfaces:**
- Consumes: Task 3 Alarm repository, Task 5 job service, Task 7 WebPush service
- Produces: `startup(ctx: dict[str, object]) -> None`, `shutdown(ctx: dict[str, object]) -> None`
- Produces: `poll_due_alarms(ctx: dict[str, object]) -> None`
- Produces: `recover_background_jobs(ctx: dict[str, object]) -> None`
- Produces: `send_alarm_push(ctx, job_id, alarm_id, subscription_id, trigger_at) -> None`
- Produces: `WorkerSettings`

- [ ] **Step 1: Write failing worker tests**

```python
async def test_due_alarm_fans_out_one_job_per_active_subscription(due_alarm, subscriptions, redis_pool):
    await poll_due_alarms(worker_context(redis_pool))
    jobs = await BackgroundJob.filter(job_type=BackgroundJobType.ALARM)
    assert len(jobs) == len(subscriptions)
    assert redis_pool.enqueue_job.await_count == len(subscriptions)


async def test_retryable_failure_moves_job_to_retry_waiting(alarm_job, retryable_push_service):
    await send_alarm_push(worker_context(push=retryable_push_service), *job_args(alarm_job))
    await alarm_job.refresh_from_db()
    assert alarm_job.status == BackgroundJobStatus.RETRY_WAITING
    assert alarm_job.retry_count == 1
```

Add tests for duplicate cron execution, no active subscription, success/SENT, expired subscription, permanent failure, max retries, cancelled job, and recoverable queue rows.

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/workers/test_alarm_worker.py -q`

Expected: FAIL because Worker functions do not exist.

- [ ] **Step 3: Implement Worker lifecycle**

`startup` initializes Tortoise with `TORTOISE_ORM`, creates the ARQ Redis pool, and stores reusable `BackgroundJobService` and `WebPushService` instances in ctx. `shutdown` closes Tortoise connections and Redis.

- [ ] **Step 4: Implement locked due-alarm polling**

Add repository query for:

```python
Alarm.filter(
    status=AlarmStatus.ACTIVE,
    next_trigger_at__lte=now,
).filter(Q(last_triggered_at=None) | Q(last_triggered_at__lt=F("next_trigger_at")))
```

If Tortoise cannot express the field-to-field comparison portably, use a parameterized raw SQL repository method limited to IDs, then lock/reload those Alarm rows in a transaction. Do not interpolate values into SQL.

For each locked alarm, create one BackgroundJob per active subscription and enqueue it. Update `last_triggered_at` and recurrence exactly once. With no active subscription, append FAILED/NO_ACTIVE_SUBSCRIPTION and consume the occurrence.

- [ ] **Step 5: Implement sender state machine**

1. Atomically claim QUEUED/RETRY_WAITING as PROCESSING.
2. Re-read Alarm, subscription, and job status.
3. Skip delivery if cancelled/inactive/terminal.
4. Call WebPushService.
5. SUCCESS: append SENT, update `last_used_at`, complete and link job.
6. EXPIRED: deactivate subscription, append FAILED, fail and link job.
7. PERMANENT_FAILURE: append FAILED, fail and link job.
8. RETRYABLE: increment retry count; schedule exponential delay `base * 2 ** (retry_count - 1)` or fail at the maximum.

All terminal event/job/link changes use one DB transaction.

- [ ] **Step 6: Implement recovery cron**

Find stale QUEUED jobs using `requested_at <= now - recovery_grace`, and RETRY_WAITING jobs using `updated_at + (base * 2 ** (retry_count - 1)) <= now`. Because the current schema has no `retry_at`, every RETRY_WAITING transition must set `updated_at`; a RETRY_WAITING row with null `updated_at` is eligible immediately and is repaired during enqueue. Re-enqueue with the original idempotency key. If ARQ reports an existing job id, treat it as successfully recovered.

- [ ] **Step 7: Define WorkerSettings**

```python
class WorkerSettings:
    functions = [send_alarm_push]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
    cron_jobs = [
        cron(poll_due_alarms, second=set(range(0, 60, config.ALARM_POLL_SECONDS))),
        cron(recover_background_jobs, second={5, 35}),
    ]
```

Validate that `ALARM_POLL_SECONDS` divides 60 or construct a bounded second set without invalid values.

- [ ] **Step 8: Run Worker tests and all service tests**

Run: `uv run pytest app/tests/workers/test_alarm_worker.py app/tests/services app/tests/job_apis/test_background_job_service.py -q`

Expected: PASS.

Run: `uv run ruff check app/workers app/repositories/alarm_repository.py app/services/background_jobs.py app/tests/workers`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors; do not commit.

---

### Task 9: Docker Worker Integration and End-to-End Verification

**Files:**
- Modify: `docker-compose.yml`
- Modify: `infra/docker/docker-compose.prod.yml`
- Modify: `envs/example.prod.env`
- Test: all Python tests and Compose configuration

**Interfaces:**
- Consumes: `app.workers.alarm_worker.WorkerSettings`
- Produces: independently runnable `alarm-worker` Compose service

- [ ] **Step 1: Add a Compose contract test before editing**

Create `app/tests/test_alarm_worker_compose.py` without adding a YAML dependency:

```python
import json
import subprocess
from pathlib import Path


def test_alarm_worker_has_required_dependencies():
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    compose = json.loads(result.stdout)
    worker = compose["services"]["alarm-worker"]
    assert "app.workers.alarm_worker.WorkerSettings" in str(worker["command"])
    assert set(worker["depends_on"]) >= {"mysql", "redis"}
    assert "ws" in worker["networks"]
```

- [ ] **Step 2: Verify red state**

Run: `uv run pytest app/tests/test_alarm_worker_compose.py -q`

Expected: FAIL because `alarm-worker` does not exist.

- [ ] **Step 3: Add the development alarm-worker service**

Reuse the FastAPI build/image and override command:

```yaml
alarm-worker:
  container_name: alarm-worker
  build:
    context: .
    dockerfile: app/Dockerfile
  image: ${DOCKER_USER}/${DOCKER_REPOSITORY}:app-${APP_VERSION}
  env_file: .env
  command: uv run --no-sync arq app.workers.alarm_worker.WorkerSettings
  restart: always
  networks:
    - ws
  depends_on:
    mysql:
      condition: service_healthy
    redis:
      condition: service_healthy
```

Mount `./app:/app/app` in development to match FastAPI. Add the corresponding production service without source mount or reload behavior.

- [ ] **Step 4: Run Compose and import verification**

Run: `docker compose config --quiet`

Expected: exit 0.

Run: `uv run python -c "from app.workers.alarm_worker import WorkerSettings; print(WorkerSettings.__name__)"`

Expected: `WorkerSettings`.

Run: `uv run pytest app/tests/test_alarm_worker_compose.py -q`

Expected: PASS.

- [ ] **Step 5: Run focused feature verification**

Run: `uv run pytest app/tests/alarm_apis app/tests/job_apis app/tests/services app/tests/workers app/tests/test_alarm_worker_compose.py -q`

Expected: all alarm workflow tests PASS with no failures.

- [ ] **Step 6: Run full repository verification**

Run: `uv run pytest -q`

Expected: full Python suite PASS. If the existing MySQL test database is unavailable, report the environmental failure separately and still run pure unit tests.

Run: `uv run ruff check app`

Expected: exit 0.

Run: `docker compose config --quiet`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 7: Review final diff without committing**

Run: `git status --short`

Run: `git diff --stat`

Run: `git diff -- app/apis/v1 app/dtos app/repositories app/services app/workers app/dependencies app/core/config.py pyproject.toml docker-compose.yml infra/docker/docker-compose.prod.yml envs/example.prod.env`

Confirm only requested Alarm/BackgroundJob/Worker changes and the already approved Qdrant compose change are present. Do not stage or commit.
