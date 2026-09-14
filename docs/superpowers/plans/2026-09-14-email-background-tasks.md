# Email Background Tasks Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dedicated ARQ `email-worker` with recoverable FastAPI Background Tasks while preserving encrypted payloads, job history, retries, cancellation, and existing API responses.

**Architecture:** Email producers persist an encrypted payload in `background_jobs`, then register a lightweight launcher with request-scoped FastAPI `BackgroundTasks`. That launcher quickly creates a process-scoped, lifespan-owned `asyncio.Task`; the manager tracks and deduplicates those tasks while database status and lease predicates provide cross-process ownership. FastAPI startup schedules every unfinished EMAIL job, and the executor sleeps until a future retry or lease becomes claimable.

**Tech Stack:** Python 3.13, FastAPI/Starlette BackgroundTasks, asyncio, Tortoise ORM, Aerich, Fernet, SMTP, pytest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-14-email-background-tasks-design.md`

## Global Constraints

- Keep `background_jobs` as the status source for EMAIL work.
- Never persist recipient addresses, verification codes, temporary passwords, or report bodies in plaintext.
- Preserve `EMAIL_MAX_RETRY_COUNT=3`, `EMAIL_RETRY_BASE_SECONDS=30`, and `EMAIL_PAYLOAD_ENCRYPTION_KEY`.
- Remove only `EMAIL_QUEUE_NAME`; Redis remains for ALARM, OCR, and other existing features.
- Preserve exponential retry delay: `EMAIL_RETRY_BASE_SECONDS * 2 ** (retry_count - 1)`.
- Clear `encrypted_payload`, `next_attempt_at`, and `lease_expires_at` on `COMPLETED`, `FAILED`, or `CANCELLED`.
- Recover only expired `PROCESSING` leases; never reset an unexpired lease owned by another FastAPI process.
- On startup, schedule every unfinished `RETRY_WAITING` EMAIL job, including future-due rows; otherwise a restart before `next_attempt_at` would strand the retry forever.
- On startup, also schedule every `PROCESSING` EMAIL job with payload; a future lease waits until expiry, then competes for the conditional claim. Scheduling does not permit an early takeover.
- Use an injectable clock and async sleeper in executor tests so retry and lease tests never wait for production delays.
- Do not run SMTP or retry sleeps directly inside Starlette's response Background Task: `ApiTimeoutMiddleware` wraps the whole ASGI call with a 3-second default. The response task may only launch a manager-owned coroutine and return immediately.
- Delivery is at-least-once; do not claim exactly-once SMTP delivery.
- Run only tests directly related to email, authentication/admin email APIs, migrations, and Compose.

---

## File Structure

- `app/models/background_jobs.py`: persistent encrypted email payload, retry due time, and execution lease.
- `app/core/db/migrations/models/46_20260914000000_email_background_tasks.py`: schema upgrade/downgrade and legacy unfinished EMAIL normalization.
- `app/services/email_background_tasks.py`: email job claim, delivery, state transitions, retry waiting, manager-owned task tracking, process-local deduplication, and recovery.
- `app/services/email_jobs.py`: producer-side job creation, payload encryption, persistence, and scheduling; no Redis/ARQ.
- `app/dependencies/email_background_tasks.py`: request-scoped scheduler bound to FastAPI `BackgroundTasks` and the app manager.
- `app/main.py`: manager lifecycle, unfinished job recovery, and shutdown cancellation.
- `app/apis/v1/auth_routers.py`, `app/apis/v1/admin_routers.py`, `app/apis/v1/intake_report_router.py`: inject and pass the scheduler.
- `app/services/email_verifications.py`, `app/services/auth.py`, `app/services/admins.py`: accept the scheduler at email-producing service boundaries.
- `docker-compose.yml`, `infra/docker/docker-compose.prod.yml`: remove the `email-worker` service.
- `app/workers/email_worker.py`: delete after its delivery behavior moves to the Background Task executor.
- `app/tests/email/test_email_background_tasks.py`: executor, retry, lease, recovery, and sensitive-payload cleanup.
- Existing email/auth/admin/intake/Compose tests: update contracts without broad unrelated rewrites.

---

### Task 1: Persist recoverable EMAIL task state

**Files:**
- Modify: `app/models/background_jobs.py`
- Create: `app/core/db/migrations/models/46_20260914000000_email_background_tasks.py`
- Create: `app/tests/models/test_email_background_task_migration.py`
- Modify: `app/tests/models/test_challenge_rejoin_aerich.py`

**Interfaces:**
- Produces: `BackgroundJob.encrypted_payload: str | None`, `next_attempt_at: datetime | None`, `lease_expires_at: datetime | None`.
- Produces indexes: `idx_email_job_retry_due(job_type, status, next_attempt_at)` and `idx_email_job_lease(job_type, status, lease_expires_at)`.

- [ ] **Step 1: Write the failing model and migration tests**

```python
def test_background_job_exposes_email_recovery_fields() -> None:
    fields = BackgroundJob._meta.fields_map
    assert fields["encrypted_payload"].null is True
    assert fields["next_attempt_at"].null is True
    assert fields["lease_expires_at"].null is True


async def test_email_background_task_migration_adds_recovery_columns_and_indexes() -> None:
    sql = await migration.upgrade(None)
    assert "encrypted_payload" in sql
    assert "next_attempt_at" in sql
    assert "lease_expires_at" in sql
    assert "idx_email_job_retry_due" in sql
    assert "idx_email_job_lease" in sql
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest app/tests/models/test_email_background_task_migration.py -q`

Expected: FAIL because the fields and migration module do not exist.

- [ ] **Step 3: Add model fields and named indexes**

```python
encrypted_payload = fields.TextField(null=True)
next_attempt_at = fields.DatetimeField(null=True)
lease_expires_at = fields.DatetimeField(null=True)

Index(fields=("job_type", "status", "next_attempt_at"), name="idx_email_job_retry_due")
Index(fields=("job_type", "status", "lease_expires_at"), name="idx_email_job_lease")
```

- [ ] **Step 4: Add the Aerich migration**

The upgrade must add all three nullable columns and both indexes. It must also mark legacy unfinished EMAIL rows without payload as terminal without touching completed history:

```sql
UPDATE background_jobs
SET status = 'FAILED',
    completed_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    error_code = 'EMAIL_PAYLOAD_UNAVAILABLE',
    error_message = 'EMAIL_PAYLOAD_UNAVAILABLE'
WHERE job_type = 'EMAIL'
  AND status IN ('QUEUED', 'PROCESSING', 'RETRY_WAITING')
  AND encrypted_payload IS NULL;
```

The downgrade drops `idx_email_job_lease`, `idx_email_job_retry_due`, `lease_expires_at`, `next_attempt_at`, and `encrypted_payload` in that order.

Build `MODELS_STATE` from migration 45 and update the `models.BackgroundJob` metadata with the three fields and two named indexes so Aerich's ledger matches the runtime model after upgrade.

Update the real Aerich-chain regression's latest-version constant, expected head/upgrade/downgrade lists, final state source, restored ledger slice, and success marker from 45 to 46. Add assertions against `SHOW COLUMNS`/`SHOW INDEX` for the three fields and two indexes after upgrade, and verify a single downgrade removes only migration 46 before the existing historical rollback checks continue.

- [ ] **Step 5: Verify GREEN and formatting**

Run: `uv run pytest app/tests/models/test_email_background_task_migration.py -q`

Run: `uv run pytest app/tests/models/test_challenge_rejoin_aerich.py -q`

Run: `uv run ruff check app/models/background_jobs.py app/core/db/migrations/models/46_20260914000000_email_background_tasks.py app/tests/models/test_email_background_task_migration.py app/tests/models/test_challenge_rejoin_aerich.py`

- [ ] **Step 6: Commit**

```bash
git add app/models/background_jobs.py app/core/db/migrations/models/46_20260914000000_email_background_tasks.py app/tests/models/test_email_background_task_migration.py app/tests/models/test_challenge_rejoin_aerich.py
git commit -m "feat: persist recoverable email tasks"
```

---

### Task 2: Move email delivery into a reusable Background Task executor

**Files:**
- Create: `app/services/email_background_tasks.py`
- Create: `app/tests/email/test_email_background_tasks.py`
- Reference: `app/workers/email_worker.py`
- Reference: `app/tests/workers/test_email_worker.py`

**Interfaces:**
- Produces: `EmailBackgroundTaskExecutor.run(job_id: int) -> None`.
- Produces: `EmailBackgroundTaskExecutor.recoverable_job_ids(now: datetime) -> list[int]`.
- Consumes: encrypted payload stored on `BackgroundJob`, existing `EmailPayloadCodec`, `EmailTemplateRenderer`, `SmtpSettingsService`, and `SmtpEmailSender`.
- Constructor test seams: injectable `now_provider` and async `sleep`; the production lease is a module constant longer than `SMTP_TIMEOUT_SECONDS` (use 60 seconds for the current 10-second SMTP timeout).

- [ ] **Step 1: Port the existing worker behavior into failing executor tests**

Create real database jobs and inject fake SMTP/settings dependencies. Cover observable state rather than ARQ calls:

```python
async def test_success_claims_sends_and_clears_sensitive_payload() -> None:
    job = await create_email_job(status=QUEUED, encrypted_payload=encrypted_payload())
    await executor.run(job.id)
    await job.refresh_from_db()
    assert job.status is BackgroundJobStatus.COMPLETED
    assert job.encrypted_payload is None
    assert job.next_attempt_at is None
    assert job.lease_expires_at is None
    sender.send.assert_called_once()


async def test_unexpired_processing_lease_cannot_be_claimed() -> None:
    job = await create_email_job(
        status=PROCESSING,
        lease_expires_at=now + timedelta(minutes=1),
    )
    run_task = asyncio.create_task(executor.run(job.id))
    await sleep.started.wait()
    sender.send.assert_not_called()
    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_task


async def test_future_retry_waits_until_due_then_claims() -> None:
    job = await create_email_job(
        status=RETRY_WAITING,
        next_attempt_at=now + timedelta(seconds=30),
    )
    await executor.run(job.id)
    sleep.assert_awaited_once_with(30)
    sender.send.assert_called_once()
```

For the future-retry test, the fake sleeper advances the fake clock by the requested delay. For the unexpired-lease test, use a blocking sleeper so the assertion observes the job before the lease becomes claimable and then cancel the test task cleanly.

Also port assertions for invalid payload, invalid SMTP configuration, permanent SMTP failure, signup verification expiration, missing/consumed verification, invalid password-reset target, invalid intake-report target, and post-delivery password update.

- [ ] **Step 2: Run the executor tests and verify RED**

Run: `uv run pytest app/tests/email/test_email_background_tasks.py -q`

Expected: FAIL because `EmailBackgroundTaskExecutor` does not exist.

- [ ] **Step 3: Implement atomic claim and terminal transitions**

Use conditional updates so only one caller owns a job. Before this update, `run()` sleeps until a future `next_attempt_at` or `lease_expires_at`; the claim predicate itself still permits only due rows:

```python
claimed = await BackgroundJob.filter(
    Q(id=job_id, job_type=BackgroundJobType.EMAIL, status=BackgroundJobStatus.QUEUED)
    | Q(
        id=job_id,
        job_type=BackgroundJobType.EMAIL,
        status=BackgroundJobStatus.RETRY_WAITING,
        next_attempt_at__lte=now,
    )
    | Q(
        id=job_id,
        job_type=BackgroundJobType.EMAIL,
        status=BackgroundJobStatus.PROCESSING,
        lease_expires_at__lte=now,
    )
).update(
    status=BackgroundJobStatus.PROCESSING,
    started_at=now,
    lease_expires_at=now + EMAIL_TASK_LEASE,
    updated_at=now,
)
```

Decrypt from `job.encrypted_payload`, apply the same sendability checks and post-delivery effects as the existing worker, and clear recovery fields in every terminal transition.

- [ ] **Step 4: Add retry-due behavior**

On retryable failure with attempts remaining:

```python
delay = config.EMAIL_RETRY_BASE_SECONDS * (2 ** (retry_count - 1))
job.status = BackgroundJobStatus.RETRY_WAITING
job.next_attempt_at = now + timedelta(seconds=delay)
job.lease_expires_at = None
```

For signup verification, cancel instead when `next_attempt_at >= payload.expires_at`. `run()` reloads a `RETRY_WAITING` job, sleeps until `next_attempt_at` when it is still in the future, and then attempts the same DB claim again. A retry scheduled during the current execution follows that same loop. It must not use or raise `arq.Retry`.

- [ ] **Step 5: Add recovery selection tests and implementation**

```python
ids = await executor.recoverable_job_ids(now)
assert ids == [queued.id, due_retry.id, future_retry.id, expired_lease.id, active_lease.id, payloadless_legacy.id]
assert completed.id not in ids
```

All `RETRY_WAITING` and `PROCESSING` EMAIL rows are recovery candidates; `run()` itself enforces `next_attempt_at` and `lease_expires_at`, so future retries and future lease recovery remain automatic after a restart. When `run()` encounters an unfinished legacy EMAIL job with no payload, terminate it as `FAILED/EMAIL_PAYLOAD_UNAVAILABLE` without calling SMTP.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest app/tests/email/test_email_background_tasks.py -q`

Run: `uv run ruff check app/services/email_background_tasks.py app/tests/email/test_email_background_tasks.py`

- [ ] **Step 7: Commit**

```bash
git add app/services/email_background_tasks.py app/tests/email/test_email_background_tasks.py
git commit -m "feat: execute email background tasks in api process"
```

---

### Task 3: Replace Redis enqueueing with persistent task scheduling

**Files:**
- Modify: `app/services/email_jobs.py`
- Modify: `app/tests/email/test_email_job_service.py`
- Create: `app/dependencies/email_background_tasks.py`
- Test: `app/tests/email/test_email_background_tasks.py`

**Interfaces:**
- Produces: `EmailTaskScheduler.schedule(job_id: int) -> None` protocol.
- Produces: `FastAPIEmailTaskScheduler.schedule(job_id: int) -> None`, implemented with `BackgroundTasks.add_task(manager.start, job_id)`; `start()` only creates a tracked asyncio task and returns.
- Changes each `EmailJobService.enqueue_*` method to require keyword-only `scheduler: EmailTaskScheduler`.
- Consumes: `EmailBackgroundTaskManager.run(job_id: int) -> None` from Task 4; use a protocol in this task so the manager implementation can follow.

- [ ] **Step 1: Rewrite producer tests to describe the new contract and verify RED**

```python
job = await service.enqueue_admin_temporary_password(
    admin_id=7,
    recipient_email="admin@example.com",
    recipient_name="관리자",
    temporary_password="Temp1234!",
    scheduler=scheduler,
)
assert job.status is BackgroundJobStatus.QUEUED
assert job.encrypted_payload is not None
assert "Temp1234!" not in job.encrypted_payload
assert scheduler.job_ids == [job.id]
```

Replace Redis enqueue assertions and `EMAIL_QUEUE_UNAVAILABLE` cases with encryption/persistence/scheduler assertions for all four email templates.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest app/tests/email/test_email_job_service.py -q`

Expected: FAIL because `scheduler` is unsupported and Redis is still called.

- [ ] **Step 3: Remove all Redis/ARQ producer dependencies**

Delete `ArqRedis`, `RedisSettings`, `create_pool`, `redis_pool`, `_queue_name`, and `enqueue_job` usage. After encrypting the payload, persist it before scheduling:

```python
job.encrypted_payload = encrypted_payload
job.next_attempt_at = datetime.now(config.TIMEZONE)
job.updated_at = job.next_attempt_at
await job.save(update_fields=["encrypted_payload", "next_attempt_at", "updated_at"])
scheduler.schedule(job.id)
```

If encryption or persistence fails, mark the job `FAILED`, clear recovery fields, and do not schedule it. Wrap `scheduler.schedule(job.id)` as well: if task registration raises, mark the persisted job `FAILED/EMAIL_TASK_SCHEDULING_FAILED`, clear the encrypted payload and recovery timestamps, and preserve the existing caller behavior that maps a failed job to its current API response.

- [ ] **Step 4: Implement the FastAPI scheduler dependency**

```python
class FastAPIEmailTaskScheduler:
    def __init__(self, background_tasks: BackgroundTasks, manager: EmailTaskRunner) -> None:
        self.background_tasks = background_tasks
        self.manager = manager

    def schedule(self, job_id: int) -> None:
        self.background_tasks.add_task(self.manager.start, job_id)
```

`get_email_task_scheduler(request: Request, background_tasks: BackgroundTasks)` reads `request.app.state.email_background_task_manager` and returns this scheduler.

Add a focused integration test around `ApiTimeoutMiddleware`: use a fake executor that remains blocked longer than the configured request timeout, assert the HTTP response completes without a post-response timeout log, and assert the manager still owns the running task until shutdown.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest app/tests/email/test_email_job_service.py app/tests/email/test_email_background_tasks.py -q`

Run: `uv run ruff check app/services/email_jobs.py app/dependencies/email_background_tasks.py app/tests/email/test_email_job_service.py`

- [ ] **Step 6: Commit**

```bash
git add app/services/email_jobs.py app/dependencies/email_background_tasks.py app/tests/email/test_email_job_service.py app/tests/email/test_email_background_tasks.py
git commit -m "refactor: schedule email jobs with background tasks"
```

---

### Task 4: Add process-local deduplication and lifespan recovery

**Files:**
- Modify: `app/services/email_background_tasks.py`
- Modify: `app/main.py`
- Modify: `app/tests/email/test_email_background_tasks.py`
- Create: `app/tests/test_email_background_task_lifespan.py`

**Interfaces:**
- Produces: `EmailBackgroundTaskManager.start(job_id: int) -> None`, which quickly creates a tracked task.
- Produces: `EmailBackgroundTaskManager.recover() -> None` and `shutdown() -> None`.
- Consumes: `EmailBackgroundTaskExecutor.run()` and `recoverable_job_ids()`.

- [ ] **Step 1: Write failing manager tests**

```python
async def test_manager_deduplicates_same_job_inside_one_process() -> None:
    await asyncio.gather(manager.start(17), manager.start(17))
    await manager.wait_until_idle()
    assert executor.run_calls == [17]


async def test_recover_schedules_only_recoverable_jobs() -> None:
    executor.recoverable_ids = [2, 5, 9]
    await manager.recover()
    await manager.wait_until_idle()
    assert sorted(executor.run_calls) == [2, 5, 9]
```

Include one future-due retry and one unexpired processing lease in `recoverable_ids`; use the injected sleeper to prove both remain scheduled until claimable. Also assert that shutdown cancels manager-owned sleeps without marking terminal state, allowing the next startup to recover them.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest app/tests/email/test_email_background_tasks.py app/tests/test_email_background_task_lifespan.py -q`

Expected: FAIL because the manager and lifespan integration do not exist.

- [ ] **Step 3: Implement the manager**

Protect a `_tasks_by_job_id: dict[int, asyncio.Task[None]]` with an `asyncio.Lock`. `start(job_id)` returns immediately when the ID already has a live task; otherwise it creates an asyncio task for a private runner that delegates to the executor and removes itself in `finally`. `recover()` calls `start()` for all returned IDs, including future-due retries and unexpired processing leases whose executor coroutine sleeps until claimable. `shutdown()` cancels and awaits every tracked task with `return_exceptions=True`, including tasks launched from requests.

- [ ] **Step 4: Integrate FastAPI lifespan**

Before `yield`:

```python
manager = EmailBackgroundTaskManager(EmailBackgroundTaskExecutor())
app.state.email_background_task_manager = manager
await manager.recover()
```

The recovery call must run only after Tortoise's registered lifespan has initialized the database. Add a lifespan integration test that enters the real merged app lifespan with the executor/manager factory patched and proves DB-ready recovery happens before request serving. After `yield`, call `await manager.shutdown()` before closing shared clients. Delete the state attribute after shutdown so tests do not reuse a closed manager.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest app/tests/email/test_email_background_tasks.py app/tests/test_email_background_task_lifespan.py app/tests/chat_apis/test_chat_api_integration.py::test_lifespan_closes_qdrant_before_chat_tracer -q`

Run: `uv run ruff check app/services/email_background_tasks.py app/main.py app/tests/test_email_background_task_lifespan.py`

- [ ] **Step 6: Commit**

```bash
git add app/services/email_background_tasks.py app/main.py app/tests/email/test_email_background_tasks.py app/tests/test_email_background_task_lifespan.py
git commit -m "feat: recover email tasks on api startup"
```

---

### Task 5: Pass the scheduler through every email-producing API

**Files:**
- Modify: `app/apis/v1/auth_routers.py`
- Modify: `app/apis/v1/admin_routers.py`
- Modify: `app/apis/v1/intake_report_router.py`
- Modify: `app/services/email_verifications.py`
- Modify: `app/services/auth.py`
- Modify: `app/services/admins.py`
- Modify: `app/tests/auth_apis/test_email_verification_api.py`
- Modify: `app/tests/auth_apis/test_password_reset_api.py`
- Modify: `app/tests/email/test_email_verification_service.py`
- Modify: `app/tests/admin_apis/test_admin_email.py`
- Modify: `app/tests/admin_apis/test_admin_password_reset_api.py`
- Modify: `app/tests/admin_apis/test_admin_write_apis.py`
- Modify: `app/tests/intake_report_apis/test_intake_report_email.py`

**Interfaces:**
- Consumes: `EmailTaskScheduler` and `get_email_task_scheduler` from Task 3.
- Changes service boundaries to accept keyword-only `scheduler: EmailTaskScheduler` only on methods that create email work.

- [ ] **Step 1: Add failing API tests for response-before-send scheduling**

For each flow, override the scheduler dependency with a recorder and assert one job ID was scheduled while preserving current response contracts. Update the email-verification service tests to pass the same recorder explicitly, and give administrator-create API tests the override because their `ASGITransport` helper does not enter application lifespan:

```python
response = await request("POST", "/api/v1/auth/email-verifications", json={"email": "new@example.com"})
assert response.status_code == 202
assert len(scheduler.job_ids) == 1
job = await BackgroundJob.get(id=scheduler.job_ids[0])
assert job.status is BackgroundJobStatus.QUEUED
assert smtp_sender.call_count == 0
```

Cover signup verification, user password reset, administrator creation, administrator password reset, and intake report email.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest app/tests/auth_apis/test_email_verification_api.py app/tests/auth_apis/test_password_reset_api.py app/tests/email/test_email_verification_service.py app/tests/admin_apis/test_admin_email.py app/tests/admin_apis/test_admin_password_reset_api.py app/tests/admin_apis/test_admin_write_apis.py app/tests/intake_report_apis/test_intake_report_email.py -q`

Expected: FAIL because the scheduler dependency is not passed to producers.

- [ ] **Step 3: Update route and service signatures**

Use the same pattern in each route:

```python
async def request_email_verification(
    data: EmailVerificationRequest,
    scheduler: Annotated[EmailTaskScheduler, Depends(get_email_task_scheduler)],
    service: Annotated[EmailVerificationService, Depends(get_email_verification_service)],
) -> EmailVerificationRequestResponse:
    result = await service.request(str(data.email), scheduler=scheduler)
```

Propagate `scheduler` unchanged through `AuthService.request_password_reset`, `AdminQueryService.create_admin`, `AdminQueryService.reset_password`, and the intake-report route into the corresponding `EmailJobService.enqueue_*` method. Do not alter verification expiration, password mutation, or response DTO behavior.

- [ ] **Step 4: Update API documentation strings**

Replace statements saying a dedicated worker/queue handles email with “FastAPI 응답 후 Background Task가 처리한다.” Keep `emailJobId` and `emailJobStatus` descriptions.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest app/tests/auth_apis/test_email_verification_api.py app/tests/auth_apis/test_password_reset_api.py app/tests/email/test_email_verification_service.py app/tests/admin_apis/test_admin_email.py app/tests/admin_apis/test_admin_password_reset_api.py app/tests/admin_apis/test_admin_write_apis.py app/tests/intake_report_apis/test_intake_report_email.py -q`

Run: `uv run ruff check app/apis/v1/auth_routers.py app/apis/v1/admin_routers.py app/apis/v1/intake_report_router.py app/services/email_verifications.py app/services/auth.py app/services/admins.py`

- [ ] **Step 6: Commit**

```bash
git add app/apis/v1/auth_routers.py app/apis/v1/admin_routers.py app/apis/v1/intake_report_router.py app/services/email_verifications.py app/services/auth.py app/services/admins.py app/tests/auth_apis/test_email_verification_api.py app/tests/auth_apis/test_password_reset_api.py app/tests/email/test_email_verification_service.py app/tests/admin_apis/test_admin_email.py app/tests/admin_apis/test_admin_password_reset_api.py app/tests/admin_apis/test_admin_write_apis.py app/tests/intake_report_apis/test_intake_report_email.py
git commit -m "feat: dispatch email from fastapi background tasks"
```

---

### Task 6: Remove the dedicated email worker and queue configuration

**Files:**
- Delete: `app/workers/email_worker.py`
- Delete: `app/tests/workers/test_email_worker.py`
- Modify: `docker-compose.yml`
- Modify: `infra/docker/docker-compose.prod.yml`
- Modify: `app/core/config.py`
- Modify: `app/services/admin_settings.py`
- Modify: `envs/example.local.env`
- Modify: `envs/example.prod.env`
- Modify: `app/tests/test_env_examples.py`
- Modify: `app/tests/test_alarm_worker_compose.py`
- Modify: `app/tests/test_custom_challenge_worker_compose.py`
- Modify: `app/tests/test_medication_guide_ocr_worker_compose.py`
- Create: `app/tests/test_email_background_task_compose.py`

**Interfaces:**
- Removes: `config.EMAIL_QUEUE_NAME` and `app.workers.email_worker.WorkerSettings`.
- Preserves: retry, payload encryption, verification, and SMTP settings on FastAPI.

- [ ] **Step 1: Write failing configuration and Compose assertions**

```python
def test_compose_removes_email_worker_and_keeps_fastapi_email_settings() -> None:
    compose = load_compose(ROOT / "docker-compose.yml")
    assert "email-worker" not in compose["services"]
    fastapi = compose["services"]["fastapi"]
    assert "EMAIL_PAYLOAD_ENCRYPTION_KEY" in fastapi["environment"]
    assert "EMAIL_QUEUE_NAME" not in fastapi["environment"]


def test_env_examples_keep_retry_and_encryption_without_queue_name() -> None:
    values = read_env(EXAMPLE_LOCAL_ENV)
    assert "EMAIL_QUEUE_NAME" not in values
    assert values["EMAIL_MAX_RETRY_COUNT"] == "3"
    assert values["EMAIL_RETRY_BASE_SECONDS"] == "30"
    assert values["EMAIL_PAYLOAD_ENCRYPTION_KEY"] == ""
```

Apply the same Compose assertion to the production file and update existing service-set tests to exclude `email-worker` while retaining `alarm-worker`, `ocr-worker`, and `ai-worker`.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest app/tests/test_email_background_task_compose.py app/tests/test_env_examples.py app/tests/test_alarm_worker_compose.py app/tests/test_custom_challenge_worker_compose.py app/tests/test_medication_guide_ocr_worker_compose.py -q`

Expected: FAIL because the worker and queue settings still exist.

- [ ] **Step 3: Remove worker services and queue-only settings**

Delete the full `email-worker` service blocks from both Compose files. Remove `EMAIL_QUEUE_NAME` from config and the two tracked environment examples. Do not edit the untracked local secret file `envs/.local.env`. Keep `EMAIL_MAX_RETRY_COUNT`, `EMAIL_RETRY_BASE_SECONDS`, `EMAIL_PAYLOAD_ENCRYPTION_KEY`, SMTP settings, and verification settings on FastAPI.

- [ ] **Step 4: Remove worker module and update wording**

Delete `app/workers/email_worker.py` only after Task 2 tests cover every migrated state transition. Delete its old test file because behavior now lives in `test_email_background_tasks.py`. Change:

```python
raise RuntimeError(f"email-worker 필수 설정이 비어 있습니다: {name}")
```

to:

```python
raise RuntimeError(f"이메일 발송 필수 설정이 비어 있습니다: {name}")
```

- [ ] **Step 5: Verify GREEN and stale references**

Run: `uv run pytest app/tests/test_email_background_task_compose.py app/tests/test_env_examples.py app/tests/test_alarm_worker_compose.py app/tests/test_custom_challenge_worker_compose.py app/tests/test_medication_guide_ocr_worker_compose.py -q`

Run: `rg -n "EMAIL_QUEUE_NAME|app\.workers\.email_worker|email-worker" app docker-compose.yml infra/docker envs --glob '!app/core/db/migrations/**'`

Expected: no runtime/config matches; historical migrations are excluded.

- [ ] **Step 6: Commit**

```bash
git add app/workers/email_worker.py app/tests/workers/test_email_worker.py docker-compose.yml infra/docker/docker-compose.prod.yml app/core/config.py app/services/admin_settings.py envs/example.local.env envs/example.prod.env app/tests/test_env_examples.py app/tests/test_alarm_worker_compose.py app/tests/test_custom_challenge_worker_compose.py app/tests/test_medication_guide_ocr_worker_compose.py app/tests/test_email_background_task_compose.py
git commit -m "chore: remove dedicated email worker"
```

---

### Task 7: Run focused end-to-end verification

**Files:**
- Verify only; modify a listed implementation/test file only if its focused test exposes a regression.

**Interfaces:**
- Consumes all outputs from Tasks 1–6.
- Produces a verified implementation with no dedicated email worker or email Redis queue.

- [ ] **Step 1: Run the focused email and API suite**

```bash
uv run pytest \
  app/tests/models/test_email_background_task_migration.py \
  app/tests/email \
  app/tests/auth_apis/test_email_verification_api.py \
  app/tests/auth_apis/test_password_reset_api.py \
  app/tests/email/test_email_verification_service.py \
  app/tests/admin_apis/test_admin_email.py \
  app/tests/admin_apis/test_admin_password_reset_api.py \
  app/tests/admin_apis/test_admin_write_apis.py \
  app/tests/intake_report_apis/test_intake_report_email.py \
  app/tests/test_email_background_task_lifespan.py \
  app/tests/test_email_background_task_compose.py \
  app/tests/test_env_examples.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run focused static checks**

```bash
uv run ruff check \
  app/models/background_jobs.py \
  app/services/email_jobs.py \
  app/services/email_background_tasks.py \
  app/dependencies/email_background_tasks.py \
  app/main.py \
  app/apis/v1/auth_routers.py \
  app/apis/v1/admin_routers.py \
  app/apis/v1/intake_report_router.py \
  app/services/email_verifications.py \
  app/services/auth.py \
  app/services/admins.py

uv run ruff format --check \
  app/models/background_jobs.py \
  app/services/email_jobs.py \
  app/services/email_background_tasks.py \
  app/dependencies/email_background_tasks.py \
  app/main.py
```

Expected: both commands exit 0.

- [ ] **Step 3: Validate Compose and migration SQL**

Run: `docker compose config --services`

Expected: no `email-worker`; existing `fastapi`, `mysql`, `redis`, `alarm-worker`, `ocr-worker`, `ai-worker`, `nginx`, `qdrant`, and `ocr-images` remain.

Run: `uv run aerich upgrade`

Expected: migration 46 applies and `background_jobs` contains the three nullable fields and two named indexes.

- [ ] **Step 4: Confirm no sensitive plaintext or stale runtime references**

Run: `rg -n "EMAIL_QUEUE_NAME|app\.workers\.email_worker|email-worker" app docker-compose.yml infra/docker envs --glob '!app/core/db/migrations/**'`

Expected: no matches.

Run: `git diff --check`

Expected: exit 0.

- [ ] **Step 5: Commit verification-only fixes if needed**

If the focused checks required a code correction, stage only those directly related files and commit:

```bash
git commit -m "test: verify email background task migration"
```

If no correction was necessary, do not create an empty commit.
