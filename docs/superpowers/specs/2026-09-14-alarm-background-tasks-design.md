# Alarm Background Tasks Design

## Goal

Remove the dedicated ARQ `alarm-worker` container and execute alarm polling, Web Push delivery, retries, and recovery inside the FastAPI process without weakening the existing delivery-safety guarantees.

## Scope

Included:

- due-alarm polling while no HTTP request is being served;
- per-subscription `background_jobs` creation and execution;
- Web Push payload construction and delivery;
- retryable, permanent, and expired-subscription result handling;
- restart recovery and multi-process duplicate-claim prevention;
- manual retry of failed ALARM jobs;
- FastAPI lifespan integration;
- removal of the Docker `alarm-worker` service and alarm-only ARQ code;
- correction of stale task-monitoring help text;
- focused tests for the migrated behavior.

Excluded:

- changes to alarm message copy or scheduling rules;
- changes to Push subscription registration;
- removal of Redis, because OCR and other runtime paths still use it;
- new database columns or a redesign of `alarm_events`;
- automatic resend when a Push provider may already have accepted a notification.

## Current Responsibilities

`app/workers/alarm_worker.py` currently owns four responsibilities:

1. An ARQ cron job polls active alarms whose `next_trigger_at` is due.
2. It creates one ALARM `background_jobs` row per active Push subscription and enqueues an ARQ delivery job.
3. The delivery job validates the user, notification setting, alarm target, and subscription before calling Web Push.
4. It records `AlarmEvent`, retries temporary failures, deactivates expired subscriptions, and recovers interrupted jobs.

Deleting only the container would stop scheduled notifications entirely. All four responsibilities therefore move into an application-owned background manager.

## Architecture

### AlarmBackgroundTaskManager

Create `app/services/alarm_background_tasks.py` with an `AlarmBackgroundTaskManager`. The manager is owned by the FastAPI lifespan and has two kinds of managed asyncio tasks:

- one polling loop, active for the lifetime of the FastAPI process;
- one tracked delivery task per `background_jobs.id`.

The manager exposes:

- `start()`: recover unfinished work, then start the polling loop;
- `start_job(job_id)`: create at most one local asyncio task for a job ID;
- `shutdown()`: stop the poller, cancel or await managed tasks, and leave claimed jobs recoverable;
- test-only state/wait helpers equivalent to the email manager's helpers where useful.

Local task deduplication prevents React/API duplication inside one process. Database claims remain the authority across multiple FastAPI processes.

### AlarmBackgroundTaskExecutor

The executor contains the behavior migrated from `alarm_worker.py`:

- `poll_due_alarms()` selects at most 100 due active alarms;
- `run(job_id)` waits until a retry is due, conditionally claims the job, validates its delivery context, sends Web Push, and persists the result;
- `recover()` schedules QUEUED and RETRY_WAITING jobs and resolves expired PROCESSING leases;
- result persistence keeps the existing lock order and event semantics.

The executor accepts clock, sleep, Push service, and manager/scheduler boundaries in a testable form. It must not import ARQ or Redis.

### FastAPI lifespan

`app/main.py` creates both the email and alarm managers. The alarm manager starts after the database lifespan is available and is shut down before application resources are closed. The manager is stored on `app.state.alarm_background_task_manager` for dependency injection and manual retries.

The alarm poller is application-owned rather than a Starlette request `BackgroundTasks` callback. This is required because alarms must fire even when the API receives no request.

## Data Flow

### Due-alarm polling

1. Every `ALARM_POLL_SECONDS`, query active alarms with `next_trigger_at <= now`.
2. For each candidate, lock the `alarms` row in a transaction and re-check status and due time.
3. Check account status, notification preference, and active Push subscriptions.
4. Create one ALARM `background_jobs` row per subscription using the existing unique idempotency key:
   `alarm:{alarm_id}:{subscription_id}:{trigger_at.isoformat()}`.
5. Advance `last_triggered_at` and the recurring `next_trigger_at` in the same protected flow.
6. After commit, call `manager.start_job(job.id)` for every queued delivery.

The alarm row lock, due-time re-check, and unique job key prevent duplicate job creation when multiple API instances poll simultaneously.

### Delivery state transitions

ALARM jobs use the existing recovery columns introduced for in-process background work:

- `next_attempt_at`: time at which a RETRY_WAITING job becomes claimable;
- `lease_expires_at`: upper bound for an in-flight PROCESSING claim.

No new migration is required. Existing composite indexes beginning with `(job_type, status, ...)` support ALARM recovery queries even though their current names contain `email`.

Normal flow:

```text
QUEUED -> PROCESSING -> COMPLETED
```

Temporary provider failure:

```text
PROCESSING -> RETRY_WAITING -> PROCESSING
```

Terminal flows:

```text
PROCESSING -> FAILED
QUEUED/PROCESSING/RETRY_WAITING -> CANCELLED when the target is no longer sendable
```

Claiming is a conditional database update. QUEUED is immediately claimable; RETRY_WAITING is claimable only when `next_attempt_at <= now`. A successful claim sets `started_at`, clears `next_attempt_at`, and sets `lease_expires_at`.

### Retry

ARQ `Retry` is removed. A retryable Push result increments `retry_count`, stores the provider error, computes exponential backoff from `ALARM_RETRY_BASE_SECONDS`, sets `next_attempt_at`, clears the lease, and returns the job to `RETRY_WAITING`.

The owning manager task may sleep until the due time and attempt the conditional claim again. On restart, startup recovery finds the same persisted job. If multiple processes wait for it, only one conditional claim succeeds.

### Interrupted delivery

Web Push acceptance and database commit cannot be made atomic. If a process stops with a PROCESSING job, the notification may already have reached the provider. After `lease_expires_at`, recovery marks the job `FAILED` with `PUSH_DELIVERY_UNKNOWN` and does not automatically resend it.

For PROCESSING rows created by the legacy worker before deployment, `lease_expires_at` may be null. Recovery applies the existing `started_at`/`requested_at` timeout plus grace period to those rows and then uses the same `PUSH_DELIVERY_UNKNOWN` terminal result.

This preserves the current at-most-once safety decision. Manual retry remains prohibited for `PUSH_DELIVERY_UNKNOWN`.

### Manual retry

The existing internal retry endpoint continues to create a child ALARM job linked through `parent_job_id`. Instead of enqueueing ARQ, it invokes the alarm manager's scheduler interface with the new job ID. Context recovery continues to use the parent `AlarmEvent` or the original idempotency key.

## Concurrency and Locking

Database state is authoritative. In-process task dictionaries are only an optimization.

For Push result persistence, all paths use this lock/write order:

```text
BackgroundJob -> PushSubscription -> AlarmEvent
```

This matches the currently stabilized failure path and prevents concurrent notifications sharing one subscription from acquiring conflicting foreign-key and update locks in opposite orders.

Completion persistence retries database-only failures up to the existing bounded count. It never repeats the provider call after the provider has accepted a Push.

## Validation and Error Handling

The migrated executor preserves these checks immediately before delivery:

- the user account is ACTIVE;
- the matching notification setting is enabled;
- the alarm is ACTIVE;
- the Push subscription exists and is active;
- medication, nutrient, or follow-up-visit context is still valid.

Existing error codes remain stable, including:

- `NO_ACTIVE_SUBSCRIPTION`;
- `PUSH_TEMPORARY_ERROR`;
- `PUSH_SUBSCRIPTION_EXPIRED`;
- `PUSH_REJECTED`;
- `PUSH_DELIVERY_UNKNOWN`;
- cancellation reasons such as inactive users or disabled notifications.

Expired subscriptions are deactivated in the same result transaction. The task-monitoring API continues to read the same `background_jobs` and `alarm_events` rows.

## Docker and Configuration

Delete `alarm-worker` from:

- `docker-compose.yml`;
- `infra/docker/docker-compose.prod.yml`.

Delete `app/workers/alarm_worker.py` after its behavior is covered by executor tests. Keep:

- `ALARM_POLL_SECONDS`;
- `ALARM_MAX_RETRY_COUNT`;
- `ALARM_RETRY_BASE_SECONDS`;
- Push TTL and VAPID settings;
- Redis services and FastAPI Redis settings needed by other subsystems.

Update Compose tests so the service set retains `fastapi`, `mysql`, `redis`, `ocr-worker`, `ai-worker`, `ocr-images`, `qdrant`, and `nginx`, but not `alarm-worker` or `email-worker`.

## Task Monitoring UI

The list and counters need no new API fields because ALARM jobs retain the same statuses and error codes. Update only stale help text that currently describes `Redis/ARQ`, `alarm-worker`, or Web Push as if every background job were an alarm job. The replacement text describes generic DB-persisted background task states.

## Testing

Migrate existing worker tests before deleting the worker module. Focused coverage must include:

- due alarms create one delivery job per active subscription;
- medication, nutrient, follow-up visit, and guide payloads remain unchanged;
- three alarm types scheduled at the same time create independent jobs;
- local and cross-process duplicate claims execute once;
- temporary failure persists RETRY_WAITING and the exact next-attempt time;
- retry exhaustion persists FAILED;
- expired subscriptions are deactivated;
- disabled notifications and invalid domain targets are cancelled/skipped;
- startup recovery schedules QUEUED and due RETRY_WAITING jobs;
- unexpired retries wait rather than execute early;
- expired PROCESSING leases become `PUSH_DELIVERY_UNKNOWN` without resend;
- manual retry schedules through the manager without Redis;
- FastAPI lifespan starts, recovers, and shuts down the manager;
- both Compose files omit `alarm-worker`;
- task-monitoring UI contains no stale worker/ARQ explanation.

Run only alarm/background-task, lifespan, job API, Compose, and task-monitoring tests, followed by focused Ruff checks and `docker compose config --services`.

## Rollout Notes

Deploy the FastAPI image and Compose changes together. Before removing the old container, ensure no old ARQ alarm jobs are actively running. Persisted QUEUED and RETRY_WAITING rows are recovered by FastAPI; Redis-only jobs without a corresponding recoverable database row are outside the supported handoff contract.

After deployment, verify that:

- only FastAPI owns ALARM delivery;
- `alarm-worker` is absent from Compose;
- due alarms advance `next_trigger_at`;
- ALARM jobs progress through the monitoring screen;
- no increase occurs in `PUSH_DELIVERY_UNKNOWN` or duplicate delivery reports.
