# Alarm Background Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dedicated ARQ `alarm-worker` and run scheduled alarm polling, Web Push delivery, retries, and restart recovery inside the FastAPI process.

**Architecture:** A lifespan-owned `AlarmBackgroundTaskManager` runs a periodic database poller and tracks one local asyncio delivery task per ALARM job. `AlarmBackgroundTaskExecutor` persists retry and lease state in the existing `background_jobs.next_attempt_at` and `lease_expires_at` columns, while conditional database updates and alarm-row locks remain authoritative across multiple API processes.

**Tech Stack:** Python 3.13, FastAPI lifespan, asyncio, Tortoise ORM/MySQL, aiohttp/pywebpush, pytest, Docker Compose, Ruff

**Spec:** `docs/superpowers/specs/2026-09-14-alarm-background-tasks-design.md`

## Global Constraints

- Work only in `/Users/admin/PycharmProjects/FinalProject` on the current feature branch.
- Run only alarm/background-task, job API, lifespan, Compose, and task-monitoring tests; do not run the repository-wide pytest suite.
- Preserve scheduled delivery without requiring incoming HTTP traffic.
- Preserve exponential retry, startup recovery, subscription deactivation, and existing Push payloads/error codes.
- Keep `PUSH_DELIVERY_UNKNOWN` terminal and non-retryable when Push acceptance is ambiguous.
- Use the database lock/write order `BackgroundJob -> PushSubscription -> AlarmEvent` for Push result persistence.
- Do not remove Redis; OCR and other subsystems still depend on it.
- Do not add a migration: ALARM reuses the existing nullable `next_attempt_at` and `lease_expires_at` columns.
- Do not rename the existing `idx_email_job_retry_due` or `idx_email_job_lease` indexes in this change; their indexed columns already support ALARM queries.

---

### Task 1: Move ALARM delivery and recovery into a database-backed executor

**Files:**
- Create: `app/services/alarm_background_tasks.py`
- Create: `app/tests/alarm/test_alarm_background_tasks.py`
- Reference during RED only: `app/workers/alarm_worker.py`

**Interfaces:**
- Consumes: `Alarm`, `AlarmEvent`, `PushSubscription`, `BackgroundJob`, `WebPushService`, `next_occurrence`, and existing alarm configuration.
- Produces: `AlarmBackgroundTaskExecutor.poll_due_alarm_job_ids() -> list[int]`, `recoverable_job_ids(now: datetime) -> list[int]`, `recover_stalled_processing(now: datetime) -> None`, and `run(job_id: int) -> None`.

- [ ] **Step 1: Write executor contract tests before creating the module**

Create tests that import the wished-for class and preserve the existing behavior. Start with these state-transition cases:

```python
async def test_retryable_push_persists_next_attempt_without_arq_retry(self):
    executor = self.executor(now_provider=lambda: self.now)
    job = await self.create_job(self.subscription)
    self.push_service.send.return_value = PushResult(
        PushResultKind.RETRYABLE,
        503,
        "PUSH_TEMPORARY_ERROR",
    )

    await executor.run(job.id)

    await job.refresh_from_db()
    assert job.status == BackgroundJobStatus.RETRY_WAITING
    assert job.retry_count == 1
    assert job.next_attempt_at == self.now + timedelta(seconds=config.ALARM_RETRY_BASE_SECONDS)
    assert job.lease_expires_at is None


async def test_expired_processing_lease_becomes_unknown_without_push(self):
    job = await self.create_job(self.subscription)
    await BackgroundJob.filter(id=job.id).update(
        status=BackgroundJobStatus.PROCESSING,
        started_at=self.now - timedelta(minutes=10),
        lease_expires_at=self.now - timedelta(seconds=1),
    )

    await self.executor(now_provider=lambda: self.now).recover_stalled_processing(self.now)

    await job.refresh_from_db()
    assert job.status == BackgroundJobStatus.FAILED
    assert job.error_code == "PUSH_DELIVERY_UNKNOWN"
    self.push_service.send.assert_not_awaited()
```

Add focused cases for:

- a successful Push creating exactly one SENT event and completing the job;
- retry exhaustion creating one FAILED event and incrementing `retry_count`;
- an expired subscription being deactivated with `PUSH_SUBSCRIPTION_EXPIRED`;
- inactive users and disabled notification settings cancelling without Push;
- missing nutrient/follow-up context cancelling without Push;
- legacy PROCESSING rows with null lease using the existing timeout plus grace period;
- two concurrent `run(job.id)` calls causing only one Push call;
- completion/failure persistence retrying database errors without repeating Push.

- [ ] **Step 2: Run the new executor tests and verify RED**

Run:

```bash
uv run pytest app/tests/alarm/test_alarm_background_tasks.py -q
```

Expected: collection fails because `app.services.alarm_background_tasks` does not exist.

- [ ] **Step 3: Implement the executor without ARQ or Redis**

Create the module with these public constants and interfaces:

```python
ALARM_TASK_LEASE = timedelta(seconds=360)
_UNFINISHED_ALARM_STATUSES = (
    BackgroundJobStatus.QUEUED,
    BackgroundJobStatus.PROCESSING,
    BackgroundJobStatus.RETRY_WAITING,
)


class AlarmTaskExecutor(Protocol):
    async def poll_due_alarm_job_ids(self) -> list[int]: ...
    async def recoverable_job_ids(self, now: datetime) -> list[int]: ...
    async def recover_stalled_processing(self, now: datetime) -> None: ...
    async def run(self, job_id: int) -> None: ...
```

Implement the claim as one conditional update:

```python
claimable = Q(status=BackgroundJobStatus.QUEUED)
claimable |= Q(status=BackgroundJobStatus.RETRY_WAITING) & (
    Q(next_attempt_at__lte=now) | Q(next_attempt_at=None)
)
updated = await BackgroundJob.filter(
    Q(id=job_id, job_type=BackgroundJobType.ALARM) & claimable
).update(
    status=BackgroundJobStatus.PROCESSING,
    started_at=now,
    updated_at=now,
    next_attempt_at=None,
    lease_expires_at=now + ALARM_TASK_LEASE,
)
```

Do not claim PROCESSING ALARM rows for delivery. `recover_stalled_processing()` must close an expired or legacy-stale PROCESSING row as `FAILED/PUSH_DELIVERY_UNKNOWN` without invoking `WebPushService.send()`.

Replace ARQ `Retry` with persisted retry state:

```python
delay = config.ALARM_RETRY_BASE_SECONDS * (2 ** (retry_count - 1))
job.status = BackgroundJobStatus.RETRY_WAITING
job.retry_count = retry_count
job.next_attempt_at = now + timedelta(seconds=delay)
job.lease_expires_at = None
job.error_code = result.error_code
job.updated_at = now
```

In every COMPLETED, FAILED, or CANCELLED path, clear `next_attempt_at` and `lease_expires_at`.

Keep the Push persistence order inside one transaction:

```python
locked_job = await BackgroundJob.filter(id=job.id).using_db(connection).select_for_update().first()
locked_subscription = (
    await PushSubscription.filter(id=subscription.id).using_db(connection).select_for_update().first()
)
event = await AlarmEvent.create(
    using_db=connection,
    alarm_id=alarm.id,
    event_type=event_type,
    push_subscription_id=locked_subscription.id,
    event_at=now,
    payload=event_payload,
    error_code=error_code,
)
locked_job.reference_table = "alarm_events"
locked_job.reference_id = event.id
await locked_job.save(
    using_db=connection,
    update_fields=["status", "completed_at", "updated_at", "duration_ms", "reference_table", "reference_id"],
)
```

Call the Push provider once, then retry only the database persistence section on `OperationalError` or `DBConnectionError`.

- [ ] **Step 4: Move and adapt the existing behavior tests**

Port every scenario from `app/tests/workers/test_alarm_worker.py` into `app/tests/alarm/test_alarm_background_tasks.py` by replacing:

```python
await send_alarm_push(ctx, job.id, alarm.id, subscription.id, trigger_at.isoformat())
```

with:

```python
await executor.run(job.id)
```

Replace Redis enqueue assertions with returned job-ID or persisted state assertions. Preserve the test proving MEDICATION, NUTRIENT, and FOLLOW_UP_VISIT alarms at the same timestamp create three independent jobs:

```python
job_ids = await executor.poll_due_alarm_job_ids()
jobs = await BackgroundJob.filter(id__in=job_ids)
assert len(jobs) == 3
assert {job.reference_id for job in jobs} == {
    medication_alarm.id,
    nutrient_alarm.id,
    follow_up_alarm.id,
}
```

- [ ] **Step 5: Run executor tests and verify GREEN**

Run:

```bash
uv run pytest app/tests/alarm/test_alarm_background_tasks.py -q
uv run ruff check app/services/alarm_background_tasks.py app/tests/alarm/test_alarm_background_tasks.py
```

Expected: all tests pass and no ARQ/Redis import exists in the new service.

- [ ] **Step 6: Commit the executor**

```bash
git add app/services/alarm_background_tasks.py app/tests/alarm/test_alarm_background_tasks.py
git commit -m "feat: execute alarm delivery in api process"
```

---

### Task 2: Add the lifespan-owned poller and task manager

**Files:**
- Modify: `app/services/alarm_background_tasks.py`
- Modify: `app/tests/alarm/test_alarm_background_tasks.py`

**Interfaces:**
- Consumes: `AlarmTaskExecutor` from Task 1 and `config.ALARM_POLL_SECONDS`.
- Produces: `AlarmBackgroundTaskManager.start()`, `start_job(job_id)`, `shutdown()`, `active_job_ids`, and `build_alarm_background_task_manager()`.

- [ ] **Step 1: Write manager tests**

Add tests using an in-memory recording executor:

```python
async def test_manager_recovers_then_polls_without_http_requests():
    executor = RecordingExecutor(recoverable=[11], due=[12])
    manager = AlarmBackgroundTaskManager(executor, poll_seconds=0.01)

    await manager.start()
    await asyncio.wait_for(executor.polled.wait(), timeout=0.1)
    await manager.shutdown()

    assert executor.recovered is True
    assert {11, 12} <= set(executor.run_ids)


async def test_manager_deduplicates_local_job_start():
    executor = BlockingExecutor()
    manager = AlarmBackgroundTaskManager(executor)

    await asyncio.gather(manager.start_job(31), manager.start_job(31))
    await asyncio.wait_for(executor.started.wait(), timeout=0.1)

    assert executor.run_ids == [31]
    await manager.shutdown()
```

Add a shutdown test proving the polling loop stops promptly and active tasks are cancelled without erasing their PROCESSING DB state.

- [ ] **Step 2: Run manager tests and verify RED**

Run:

```bash
uv run pytest app/tests/alarm/test_alarm_background_tasks.py -k manager -q
```

Expected: fails because the manager API is not implemented.

- [ ] **Step 3: Implement the manager**

Use a lock-protected task dictionary and stop event:

```python
class AlarmBackgroundTaskManager:
    def __init__(self, executor: AlarmTaskExecutor, *, poll_seconds: float = config.ALARM_POLL_SECONDS):
        self.executor = executor
        self.poll_seconds = poll_seconds
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._tasks_by_job_id: dict[int, asyncio.Task[None]] = {}
        self._poll_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._tick()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def start_job(self, job_id: int) -> None:
        async with self._lock:
            current = self._tasks_by_job_id.get(job_id)
            if current is not None and not current.done():
                return
            self._tasks_by_job_id[job_id] = asyncio.create_task(self._run(job_id))
```

Each `_tick()` performs, in order:

1. `recover_stalled_processing(now)`;
2. `recoverable_job_ids(now)`;
3. `poll_due_alarm_job_ids()`;
4. `start_job()` for the de-duplicated union of returned IDs.

Implement the poll wait with `asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)` so shutdown does not wait for a full interval.

- [ ] **Step 4: Verify manager GREEN**

```bash
uv run pytest app/tests/alarm/test_alarm_background_tasks.py -k manager -q
uv run pytest app/tests/alarm/test_alarm_background_tasks.py -q
```

- [ ] **Step 5: Commit the manager**

```bash
git add app/services/alarm_background_tasks.py app/tests/alarm/test_alarm_background_tasks.py
git commit -m "feat: manage scheduled alarms in fastapi lifespan"
```

---

### Task 3: Wire alarm management into FastAPI lifespan

**Files:**
- Modify: `app/main.py`
- Create: `app/tests/test_alarm_background_task_lifespan.py`
- Modify: `app/tests/test_email_background_task_lifespan.py`

**Interfaces:**
- Consumes: `build_alarm_background_task_manager()` from Task 2.
- Produces: `app.state.alarm_background_task_manager` for the active lifespan.

- [ ] **Step 1: Write failing lifespan tests**

```python
@pytest.mark.asyncio
async def test_lifespan_starts_and_shuts_down_alarm_manager(monkeypatch):
    manager = RecordingAlarmManager()
    monkeypatch.setattr(main_module, "build_alarm_background_task_manager", lambda: manager)
    test_app = SimpleNamespace(state=SimpleNamespace())

    async with lifespan(test_app):
        assert manager.started is True
        assert test_app.state.alarm_background_task_manager is manager

    assert manager.shutdown_called is True
    assert not hasattr(test_app.state, "alarm_background_task_manager")
```

The recording email manager in the existing lifespan tests must remain active so the test verifies both managers are initialized and cleaned up.

- [ ] **Step 2: Run lifespan tests and verify RED**

```bash
uv run pytest app/tests/test_alarm_background_task_lifespan.py app/tests/test_email_background_task_lifespan.py -q
```

Expected: alarm manager attributes and builder are missing.

- [ ] **Step 3: Integrate the manager**

Update lifespan setup and cleanup:

```python
email_manager = build_email_background_task_manager()
alarm_manager = build_alarm_background_task_manager()
app.state.email_background_task_manager = email_manager
app.state.alarm_background_task_manager = alarm_manager
await email_manager.recover()
await alarm_manager.start()
try:
    yield
finally:
    await alarm_manager.shutdown()
    await email_manager.shutdown()
    del app.state.alarm_background_task_manager
    del app.state.email_background_task_manager
```

Keep the existing Qdrant and tracer cleanup after both background managers stop.

- [ ] **Step 4: Verify lifespan GREEN**

```bash
uv run pytest app/tests/test_alarm_background_task_lifespan.py app/tests/test_email_background_task_lifespan.py -q
uv run ruff check app/main.py app/tests/test_alarm_background_task_lifespan.py
```

- [ ] **Step 5: Commit lifespan integration**

```bash
git add app/main.py app/tests/test_alarm_background_task_lifespan.py app/tests/test_email_background_task_lifespan.py
git commit -m "feat: recover alarm tasks on api startup"
```

---

### Task 4: Route manual retries through the alarm manager

**Files:**
- Modify: `app/services/background_jobs.py`
- Modify: `app/apis/v1/job_router.py`
- Modify: `app/tests/job_apis/test_background_job_service.py`
- Modify: `app/tests/job_apis/test_job_api.py`

**Interfaces:**
- Consumes: an `AlarmTaskScheduler` with `async start_job(job_id: int) -> None`.
- Produces: `BackgroundJobService.retry_failed(job_id, *, scheduler)` with no Redis dependency.

- [ ] **Step 1: Write failing service and endpoint tests**

Replace the Redis mock in `TestBackgroundJobService` with:

```python
class RecordingAlarmScheduler:
    def __init__(self):
        self.job_ids: list[int] = []

    async def start_job(self, job_id: int) -> None:
        self.job_ids.append(job_id)
```

Assert manual retry schedules the child row:

```python
retried = await self.service.retry_failed(failed.id, scheduler=self.scheduler)
assert self.scheduler.job_ids == [retried.id]
```

Add an endpoint dependency override that returns the recording scheduler and assert the retry response remains 200 with a QUEUED child job.

- [ ] **Step 2: Run job tests and verify RED**

```bash
uv run pytest app/tests/job_apis/test_background_job_service.py app/tests/job_apis/test_job_api.py -q
```

Expected: fails because `retry_failed` and the route do not accept a scheduler.

- [ ] **Step 3: Remove alarm Redis enqueue code and inject the manager**

Delete `ArqRedis`, `RedisSettings`, and `create_pool` imports, `redis_pool` constructor state, and `BackgroundJobService.enqueue()`.

Define the scheduler protocol without importing the concrete manager:

```python
class AlarmTaskScheduler(Protocol):
    async def start_job(self, job_id: int) -> None: ...
```

Change manual retry to:

```python
async def retry_failed(self, job_id: int, *, scheduler: AlarmTaskScheduler) -> BackgroundJob:
    original = await self.get(job_id)
    if original.status != BackgroundJobStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed jobs can be retried.")
    if original.error_code == "PUSH_DELIVERY_UNKNOWN":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="발송 결과가 불명확하여 재발송할 수 없습니다. 중복 알림 여부를 먼저 확인해주세요.",
        )
    if original.job_type != BackgroundJobType.ALARM or original.reference_table != "alarm_events":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job retry handler is not available.")
    event = await AlarmEvent.get_or_none(id=original.reference_id)
    if event is None or event.push_subscription_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm retry context is missing.")
    alarm = await Alarm.get_or_none(id=event.alarm_id)
    subscription = await PushSubscription.get_or_none(id=event.push_subscription_id)
    if alarm is None or subscription is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm retry target is missing.")
    retried = await self.repository.create(
        {
            "idempotency_key": f"{original.idempotency_key}:manual:{uuid4().hex}",
            "job_type": original.job_type,
            "status": BackgroundJobStatus.QUEUED,
            "user_id": original.user_id,
            "retry_count": 0,
            "max_retry_count": original.max_retry_count,
            "parent_job_id": original.id,
        }
    )
    await scheduler.start_job(retried.id)
    return retried
```

Add a request-state dependency in `job_router.py`:

```python
def get_alarm_task_scheduler(request: Request) -> AlarmTaskScheduler:
    return request.app.state.alarm_background_task_manager
```

Inject it into `retry_background_job()` and update the docstring from ARQ queue registration to FastAPI-managed background execution.

- [ ] **Step 4: Verify manual retry GREEN**

```bash
uv run pytest app/tests/job_apis/test_background_job_service.py app/tests/job_apis/test_job_api.py -q
uv run ruff check app/services/background_jobs.py app/apis/v1/job_router.py
```

- [ ] **Step 5: Commit retry routing**

```bash
git add app/services/background_jobs.py app/apis/v1/job_router.py app/tests/job_apis/test_background_job_service.py app/tests/job_apis/test_job_api.py
git commit -m "refactor: schedule alarm retries without redis"
```

---

### Task 5: Remove the dedicated Docker worker and stale UI wording

**Files:**
- Delete: `app/workers/alarm_worker.py`
- Delete: `app/tests/workers/test_alarm_worker.py`
- Modify: `docker-compose.yml`
- Modify: `infra/docker/docker-compose.prod.yml`
- Replace: `app/tests/test_alarm_worker_compose.py` with `app/tests/test_alarm_background_task_compose.py`
- Modify: `app/tests/test_custom_challenge_worker_compose.py`
- Modify: `app/static/templates/screen-5-task-management.html`
- Modify: `app/tests/static_ui/task-management.test.mjs`

**Interfaces:**
- Consumes: FastAPI lifespan ownership from Task 3.
- Produces: Compose service sets without `alarm-worker` and task-monitoring help text independent of ARQ/worker names.

- [ ] **Step 1: Write failing Compose and UI contract tests**

```python
@pytest.mark.parametrize(
    "compose_path",
    [PROJECT_ROOT / "docker-compose.yml", PROJECT_ROOT / "infra/docker/docker-compose.prod.yml"],
)
def test_compose_runs_alarm_tasks_in_fastapi_without_alarm_worker(compose_path):
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert "fastapi" in compose["services"]
    assert "alarm-worker" not in compose["services"]
```

Add a static UI assertion:

```javascript
test("task status help describes persisted background tasks without worker names", () => {
  const html = readFileSync(templatePath, "utf8");
  assert.doesNotMatch(html, /Redis|ARQ|alarm-worker/);
  assert.match(html, /백그라운드 작업이 실행을 시작했을 때/);
});
```

- [ ] **Step 2: Run and verify RED**

```bash
uv run pytest app/tests/test_alarm_background_task_compose.py app/tests/test_custom_challenge_worker_compose.py -q
node --test app/tests/static_ui/task-management.test.mjs
```

Expected: Compose still contains `alarm-worker` and the template still names Redis/ARQ and `alarm-worker`.

- [ ] **Step 3: Remove worker services and update the service set**

Delete the complete `alarm-worker` blocks from both Compose files. Keep `redis`, `REDIS_HOST`, `REDIS_PORT`, and `REDIS_DB` for remaining consumers.

Update expected services to include:

```python
{"fastapi", "mysql", "redis", "ocr-worker", "ai-worker", "ocr-images", "qdrant", "nginx"}
```

and explicitly exclude both `alarm-worker` and `email-worker`.

- [ ] **Step 4: Replace stale task-monitoring help text**

Use these generic descriptions:

```text
진행 대기: 백그라운드 작업이 등록되어 실행을 기다릴 때
진행중: 백그라운드 작업이 실행을 시작했을 때
성공: 백그라운드 작업이 정상적으로 완료되었을 때
실패: 영구 오류 또는 최대 재시도 횟수를 초과했을 때
재시도 대기: 일시 오류 후 다음 실행 시각을 기다릴 때
취소: 관리자 취소 또는 실행 대상이 더 이상 유효하지 않을 때
```

- [ ] **Step 5: Delete legacy worker code after migrated tests are green**

Delete `app/workers/alarm_worker.py` and `app/tests/workers/test_alarm_worker.py`. Confirm the new executor test file contains every unique scenario from the deleted test file before staging the deletion.

- [ ] **Step 6: Verify Compose and UI GREEN**

```bash
uv run pytest app/tests/test_alarm_background_task_compose.py app/tests/test_custom_challenge_worker_compose.py app/tests/test_medication_guide_ocr_worker_compose.py -q
node --test app/tests/static_ui/task-management.test.mjs
docker compose config --services
rg -n "alarm-worker|app\.workers\.alarm_worker|send_alarm_push|poll_due_alarms" app docker-compose.yml infra/docker --glob '!docs/**'
```

Expected: tests pass; service output contains no `alarm-worker`; stale runtime references return no matches.

- [ ] **Step 7: Commit worker removal**

```bash
git add app/workers/alarm_worker.py app/tests/workers/test_alarm_worker.py docker-compose.yml infra/docker/docker-compose.prod.yml app/tests/test_alarm_worker_compose.py app/tests/test_alarm_background_task_compose.py app/tests/test_custom_challenge_worker_compose.py app/static/templates/screen-5-task-management.html app/tests/static_ui/task-management.test.mjs
git commit -m "chore: remove dedicated alarm worker"
```

---

### Task 6: Run focused end-to-end verification

**Files:**
- Verify only; modify a directly related implementation or test file only if a focused check exposes a regression.

**Interfaces:**
- Consumes: all outputs from Tasks 1–5.
- Produces: a verified FastAPI-owned alarm scheduler with no alarm ARQ runtime.

- [ ] **Step 1: Run the focused alarm and job suite**

```bash
uv run pytest \
  app/tests/alarm \
  app/tests/job_apis/test_background_job_service.py \
  app/tests/job_apis/test_job_api.py \
  app/tests/test_alarm_background_task_lifespan.py \
  app/tests/test_email_background_task_lifespan.py \
  app/tests/test_alarm_background_task_compose.py \
  app/tests/test_custom_challenge_worker_compose.py \
  app/tests/test_medication_guide_ocr_worker_compose.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run focused static checks**

```bash
uv run ruff check \
  app/services/alarm_background_tasks.py \
  app/services/background_jobs.py \
  app/apis/v1/job_router.py \
  app/main.py \
  app/tests/alarm/test_alarm_background_tasks.py \
  app/tests/test_alarm_background_task_lifespan.py \
  app/tests/test_alarm_background_task_compose.py

uv run ruff format --check \
  app/services/alarm_background_tasks.py \
  app/services/background_jobs.py \
  app/apis/v1/job_router.py \
  app/main.py
```

Expected: both commands exit 0.

- [ ] **Step 3: Validate Compose and stale references**

```bash
docker compose config --services
rg -n "alarm-worker|app\.workers\.alarm_worker|from arq import Retry|send_alarm_push|poll_due_alarms" \
  app docker-compose.yml infra/docker envs --glob '!docs/**'
git diff --check
git status --short
```

Expected:

- Compose retains `fastapi`, `mysql`, `redis`, `ocr-worker`, `ai-worker`, `ocr-images`, `qdrant`, and `nginx`.
- No alarm-worker or alarm ARQ runtime references remain.
- The worktree contains only deliberate changes or is clean after commits.

- [ ] **Step 4: Verify the unchanged schema contract**

```bash
uv run python -c 'from app.models.background_jobs import BackgroundJob; fields=BackgroundJob._meta.fields_map; assert fields["next_attempt_at"].null; assert fields["lease_expires_at"].null; print("alarm recovery fields available")'
```

Expected: `alarm recovery fields available`. Do not create an Aerich migration for this task.

- [ ] **Step 5: Commit verification-only corrections if needed**

If a focused check required a correction, stage only the directly related files and commit:

```bash
git commit -m "test: verify alarm background task migration"
```

If no correction was required, do not create an empty commit.
