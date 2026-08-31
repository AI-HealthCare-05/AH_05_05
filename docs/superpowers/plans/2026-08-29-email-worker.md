# Dedicated Email Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synchronous administrator temporary-password email delivery with an encrypted Redis/ARQ job processed by a dedicated Docker `email-worker`.

**Architecture:** FastAPI commits the administrator change, creates an `EMAIL` row in `background_jobs`, encrypts the template context, and enqueues it on `arq:email`. The dedicated worker claims the row, decrypts and validates the payload, renders text and HTML bodies, sends multipart SMTP mail, and records completion or exponential-backoff retry status.

**Tech Stack:** Python 3.13, FastAPI, Tortoise ORM/Aerich, ARQ/Redis, `cryptography.fernet`, Jinja2, stdlib `smtplib`, Docker Compose, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-29-email-worker-design.md`

## Global Constraints

- Do not commit any changes; the user explicitly requested work without commits.
- `EMAIL` internal manual retry remains unsupported and returns the existing 409 response.
- Do not add an email outbox table or a payload column to `background_jobs`.
- Store no recipient, email body, or temporary password plaintext in MySQL or logs.
- Put only a Fernet-encrypted email payload in the Redis/ARQ job arguments.
- Use JSON `emailJobId` and `emailJobStatus` in administrator API responses, following `CamelModel`.
- Render the approved Korean content from an HTML template and include an equivalent `text/plain` fallback.
- Keep alarm, OCR, AI worker behavior and queues unchanged.

---

## File Map

### Create

- `app/core/email/payload.py`: email template enum, validated encrypted payload schema, Fernet codec.
- `app/core/email/renderer.py`: Jinja2 HTML and plain-text rendering into `EmailMessage`.
- `app/core/email/smtp_sender.py`: SMTP-only multipart sender and retryability-aware errors.
- `app/static/templates/emails/admin_temporary_password.html`: approved administrator temporary-password HTML.
- `app/services/email_jobs.py`: `background_jobs` creation and dedicated ARQ enqueue producer.
- `app/workers/email_worker.py`: worker lifecycle, claim, decrypt, render, send, retry, and final state transitions.
- `app/core/db/migrations/models/12_20260829090000_add_email_background_job_type.py`: update `job_type` metadata comment/model state without changing its length.
- `app/tests/email/test_email_payload.py`: codec validation and plaintext-leak tests.
- `app/tests/email/test_email_renderer.py`: template and multipart body tests.
- `app/tests/email/test_smtp_sender.py`: SMTP success and error classification tests.
- `app/tests/email/test_email_job_service.py`: job creation, queue routing, and enqueue failure tests.
- `app/tests/workers/test_email_worker.py`: worker state transition and retry tests.
- `app/tests/test_email_worker_compose.py`: Compose service contract.

### Modify

- `app/models/enums.py`: add `BackgroundJobType.EMAIL`.
- `app/core/config.py`: add email queue/retry/encryption settings and remove `EMAIL_BACKEND`.
- `envs/example.local.env`: remove console backend and document worker SMTP/encryption variables.
- `envs/example.prod.env`: document worker SMTP/encryption variables without secrets.
- `app/services/admin_credentials.py`: remove synchronous `send_to`; expose plaintext only for immediate encrypted enqueue.
- `app/services/admins.py`: enqueue email jobs and return job ID/status.
- `app/dtos/admins.py`: replace `email_sent` with `email_job_id` and `email_job_status`.
- `app/apis/v1/admin_routers.py`: update endpoint documentation for asynchronous email jobs.
- `app/services/background_jobs.py`: preserve ALARM-only manual retry and make the EMAIL rejection explicit in tests.
- `app/static/js/admin-management.js`: replace `emailSent` handling with queued/failed job-state messaging.
- `app/tests/static_ui/admin-management.test.mjs`: assert queued/failed email-job response handling.
- `app/static/templates/screen-5-task-management.html`: add the visible `EMAIL` job-type option.
- `app/static/js/task-management.js`: map the `EMAIL` option to the API enum value.
- `app/tests/static_ui/task-management.test.mjs`: assert the EMAIL filter mapping.
- `docker-compose.yml`: add the dedicated `email-worker` service.
- `app/tests/admin_apis/test_admin_email.py`: replace synchronous backend assertions with queued-job API assertions.
- `app/tests/admin_apis/test_admin_password_reset_api.py`: assert asynchronous job response.
- `app/tests/test_env_examples.py`: validate worker configuration instead of `EMAIL_BACKEND`.
- `app/tests/test_root_logging.py`: remove console-email logging tests while retaining unrelated root logging tests.
- `app/tests/job_apis/test_background_job_service.py`: verify EMAIL manual retry is rejected.

### Delete

- `app/core/email/backends.py`: replaced by the SMTP-only worker sender and focused message contract.
- `app/core/email/state.py`: remove import-time global backend.
- `app/services/admin_email.py`: replace synchronous builder/sender with worker renderer and template.

---

### Task 1: Email job type, configuration, and migration metadata

**Files:**
- Modify: `app/models/enums.py`
- Modify: `app/core/config.py`
- Modify: `envs/example.local.env`
- Modify: `envs/example.prod.env`
- Create: `app/core/db/migrations/models/12_20260829090000_add_email_background_job_type.py`
- Modify/Test: `app/tests/models/test_model_metadata.py`
- Modify/Test: `app/tests/test_env_examples.py`

**Interfaces:**
- Produces: `BackgroundJobType.EMAIL`
- Produces: `config.EMAIL_QUEUE_NAME`, `config.EMAIL_MAX_RETRY_COUNT`, `config.EMAIL_RETRY_BASE_SECONDS`, `config.EMAIL_PAYLOAD_ENCRYPTION_KEY`

- [ ] **Step 1: Write failing enum and configuration tests**

Add assertions equivalent to:

```python
assert BackgroundJobType.EMAIL.value == "EMAIL"
assert config.EMAIL_QUEUE_NAME == "arq:email"
assert config.EMAIL_MAX_RETRY_COUNT == 3
assert config.EMAIL_RETRY_BASE_SECONDS == 30
```

Update environment example tests to require `EMAIL_QUEUE_NAME`, retry settings, SMTP settings, and an empty secret placeholder while rejecting the removed `EMAIL_BACKEND` key.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest app/tests/models/test_model_metadata.py app/tests/test_env_examples.py -q
```

Expected: failure because `EMAIL` and worker settings do not exist.

- [ ] **Step 3: Add the enum and settings**

Implement:

```python
class BackgroundJobType(StrEnum):
    OCR = "OCR"
    LLM = "LLM"
    CHAT = "CHAT"
    ALARM = "ALARM"
    EMAIL = "EMAIL"
    DATA_DELETION = "DATA_DELETION"
```

Add settings with validation:

```python
EMAIL_QUEUE_NAME: str = "arq:email"
EMAIL_MAX_RETRY_COUNT: int = Field(default=3, ge=0)
EMAIL_RETRY_BASE_SECONDS: int = Field(default=30, gt=0)
EMAIL_PAYLOAD_ENCRYPTION_KEY: SecretStr | None = None
```

Keep SMTP fields, remove `EMAIL_BACKEND`, and update both environment examples. Never put a real key or SMTP password in an example file.

- [ ] **Step 4: Add and inspect the Aerich migration**

The migration must retain `VARCHAR(13)` and existing data while updating the column comment to include `EMAIL`. Its downgrade restores the old comment. Copy the current complete `MODELS_STATE` and change only the enum description metadata required by the model state.

- [ ] **Step 5: Run GREEN checks**

Run:

```bash
uv run pytest app/tests/models/test_model_metadata.py app/tests/test_env_examples.py -q
uv run ruff check app/models/enums.py app/core/config.py app/core/db/migrations/models/12_20260829090000_add_email_background_job_type.py app/tests/models/test_model_metadata.py app/tests/test_env_examples.py
```

Expected: all pass.

### Task 2: Encrypted payload, HTML renderer, and SMTP sender

**Files:**
- Create: `app/core/email/payload.py`
- Create: `app/core/email/renderer.py`
- Create: `app/core/email/smtp_sender.py`
- Create: `app/static/templates/emails/admin_temporary_password.html`
- Create: `app/tests/email/test_email_payload.py`
- Create: `app/tests/email/test_email_renderer.py`
- Create: `app/tests/email/test_smtp_sender.py`

**Interfaces:**
- Produces: `EmailTemplate.ADMIN_TEMPORARY_PASSWORD`
- Produces: `EmailJobPayload(recipient_email, recipient_name, temporary_password, template)`
- Produces: `EmailPayloadCodec.encrypt(payload) -> str` and `decrypt(token) -> EmailJobPayload`
- Produces: `EmailMessage(to, subject, text_body, html_body)`
- Produces: `EmailTemplateRenderer.render(payload) -> EmailMessage`
- Produces: `SmtpEmailSender.send(message) -> None` and `EmailDeliveryError(code, retryable)`

- [ ] **Step 1: Write failing codec tests**

Cover round-trip encryption, invalid/missing Fernet key, corrupt token, Pydantic payload validation, and this security assertion:

```python
token = codec.encrypt(payload)
assert payload.temporary_password not in token
assert payload.recipient_email not in token
```

- [ ] **Step 2: Implement the payload contract and codec**

Use a Pydantic model and compact JSON. Resolve `SecretStr` safely and translate Fernet/configuration failures into focused exceptions that do not include token contents.

- [ ] **Step 3: Write failing renderer tests**

Assert that rendered text and HTML contain:

```text
홍길동 님 안녕하세요.
임시비밀번호 : Temp1234!
시스템 로그인 후 비밀번호를 변경해 주세요.
감사합니다.
```

Also pass a name such as `<script>alert(1)</script>` and assert the raw tag is absent from HTML while escaped text is present.

- [ ] **Step 4: Implement the HTML template and renderer**

Create a simple table-based HTML document with inline styles and no JavaScript or external CSS. Configure Jinja2 with `select_autoescape(["html", "xml"])`. Render the approved plain-text fallback in Python from the same validated payload.

- [ ] **Step 5: Write failing SMTP tests**

Mock `smtplib.SMTP` and assert STARTTLS, login, and `send_message`. Inspect the sent MIME object and assert it has both `text/plain` and `text/html` parts. Cover:

- `OSError`/timeout -> retryable `EMAIL_CONNECTION_ERROR`
- SMTP 4xx -> retryable `EMAIL_SMTP_TEMPORARY_ERROR`
- authentication failure -> permanent `EMAIL_AUTH_FAILED`
- recipient refusal -> permanent `EMAIL_RECIPIENT_REJECTED`
- SMTP 5xx -> permanent `EMAIL_SMTP_PERMANENT_ERROR`

- [ ] **Step 6: Implement SMTP-only sending**

The sender accepts explicit host, port, username, password, and from address. It must never log message bodies or authentication values.

- [ ] **Step 7: Run GREEN checks**

Run:

```bash
uv run pytest app/tests/email/test_email_payload.py app/tests/email/test_email_renderer.py app/tests/email/test_smtp_sender.py -q
uv run ruff check app/core/email app/tests/email
```

Expected: all pass.

### Task 3: EMAIL background-job producer

**Files:**
- Create: `app/services/email_jobs.py`
- Create: `app/tests/email/test_email_job_service.py`
- Modify: `app/repositories/background_job_repository.py` only if a focused state-update helper is needed.

**Interfaces:**
- Consumes: `EmailJobPayload`, `EmailPayloadCodec`, `BackgroundJobType.EMAIL`
- Produces: `EmailJobService.enqueue_admin_temporary_password(admin_id: int, recipient_email: str, recipient_name: str, temporary_password: str) -> BackgroundJob`

- [ ] **Step 1: Write failing producer tests**

Using an injected `AsyncMock` ARQ pool and deterministic codec, verify:

- a new job is `EMAIL/QUEUED`
- `reference_table == "admin"` and `reference_id == admin_id`
- `max_retry_count == config.EMAIL_MAX_RETRY_COUNT`
- `enqueue_job` uses function `send_email`, `_queue_name=config.EMAIL_QUEUE_NAME`, `_job_id=job.idempotency_key`
- ARQ arguments contain no recipient, name, or password plaintext
- enqueue exception changes the job to `FAILED` with `EMAIL_QUEUE_UNAVAILABLE`
- encryption/configuration failure changes the job to `FAILED` with `EMAIL_PAYLOAD_ENCRYPTION_FAILED`

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest app/tests/email/test_email_job_service.py -q
```

Expected: import or behavior failure because `EmailJobService` does not exist.

- [ ] **Step 3: Implement the producer**

Use a unique key such as `email:admin-temporary-password:{admin_id}:{uuid4().hex}`. Create the DB row before encryption and enqueueing so configuration and queue failures remain observable. Close only Redis pools created inside the service; never close an injected/shared pool. On encryption or enqueue failure, set `completed_at`, `updated_at`, `error_code`, and a sanitized `error_message`, then return the failed job rather than raising into the administrator API.

- [ ] **Step 4: Run GREEN checks**

Run:

```bash
uv run pytest app/tests/email/test_email_job_service.py -q
uv run ruff check app/services/email_jobs.py app/tests/email/test_email_job_service.py
```

Expected: all pass.

### Task 4: Dedicated ARQ email worker

**Files:**
- Create: `app/workers/email_worker.py`
- Create: `app/tests/workers/test_email_worker.py`

**Interfaces:**
- Consumes: `send_email(ctx, job_id, encrypted_payload)` ARQ arguments from Task 3.
- Consumes: codec, renderer, SMTP sender, `BackgroundJobRepository.claim`.
- Produces: `WorkerSettings` with `functions=[send_email]`, `queue_name=config.EMAIL_QUEUE_NAME`, and `max_tries=config.EMAIL_MAX_RETRY_COUNT + 1`.

- [ ] **Step 1: Write failing lifecycle and settings tests**

Verify startup initializes Tortoise and creates codec, renderer, and SMTP sender in `ctx`; shutdown closes Tortoise connections; settings expose only the email function and dedicated queue.

- [ ] **Step 2: Write failing state-transition tests**

Cover:

- claim failure returns without sending
- success: `PROCESSING -> COMPLETED`, timestamps and duration recorded
- retryable failure with retries left: `RETRY_WAITING`, count increment, sanitized code, ARQ `Retry`
- retryable failure after limit: `FAILED`
- permanent failure: immediate `FAILED`
- invalid encrypted payload: immediate `FAILED`
- completed/cancelled job is never sent
- logs and `error_message` do not contain the plaintext password or encrypted token

- [ ] **Step 3: Run the worker tests and verify RED**

Run:

```bash
uv run pytest app/tests/workers/test_email_worker.py -q
```

Expected: import failure because the worker does not exist.

- [ ] **Step 4: Implement startup, shutdown, and worker settings**

Validate required SMTP settings and `EMAIL_PAYLOAD_ENCRYPTION_KEY` in worker startup, not in FastAPI module import. Use `asyncio.to_thread(sender.send, message)` so synchronous `smtplib` does not block the ARQ event loop.

- [ ] **Step 5: Implement processing and retry transitions**

Use the same timestamp and duration conventions as `alarm_worker`. Store only stable error codes and safe summaries. Raise `Retry(defer=timedelta(seconds=config.EMAIL_RETRY_BASE_SECONDS * 2 ** (retry_count - 1)))` after persisting `RETRY_WAITING`.

- [ ] **Step 6: Run GREEN checks**

Run:

```bash
uv run pytest app/tests/workers/test_email_worker.py -q
uv run ruff check app/workers/email_worker.py app/tests/workers/test_email_worker.py
```

Expected: all pass.

### Task 5: Administrator API integration and synchronous-path removal

**Files:**
- Modify: `app/services/admin_credentials.py`
- Modify: `app/services/admins.py`
- Modify: `app/dtos/admins.py`
- Modify: `app/apis/v1/admin_routers.py`
- Modify: `app/tests/admin_apis/test_admin_email.py`
- Modify: `app/tests/admin_apis/test_admin_password_reset_api.py`
- Modify: `app/static/js/admin-management.js`
- Modify: `app/tests/static_ui/admin-management.test.mjs`
- Delete: `app/core/email/backends.py`
- Delete: `app/core/email/state.py`
- Delete: `app/services/admin_email.py`
- Modify: `app/tests/test_root_logging.py`

**Interfaces:**
- Consumes: `EmailJobService.enqueue_admin_temporary_password(admin_id: int, recipient_email: str, recipient_name: str, temporary_password: str) -> BackgroundJob`
- Produces: `AdminCreateResponse.email_job_id`, `AdminCreateResponse.email_job_status`
- Produces: `AdminPasswordResetResponse.email_job_id`, `AdminPasswordResetResponse.email_job_status`

- [ ] **Step 1: Rewrite API tests for the asynchronous contract**

Inject or monkeypatch the job producer and expect JSON fields:

```json
{"emailJobId": 123, "emailJobStatus": "QUEUED"}
```

Cover the queue-failure response with `emailJobStatus: "FAILED"` while proving the administrator or changed password remains stored.

- [ ] **Step 2: Run focused API tests and verify RED**

Run:

```bash
uv run pytest app/tests/admin_apis/test_admin_email.py app/tests/admin_apis/test_admin_password_reset_api.py -q
```

Expected: failures because responses still contain `emailSent` and SMTP is called inline.

- [ ] **Step 3: Refactor temporary credentials and administrator service**

Remove `send_to()`. Provide a narrowly named method/property that supplies the temporary plaintext only to the immediate enqueue call and keeps it excluded from `repr`. Add injectable `EmailJobService` construction to `AdminQueryService`, enqueue after the administrator transaction/save, and map the returned job into both response DTOs.

- [ ] **Step 4: Update API documentation and frontend behavior**

Replace `emailSent` documentation and UI branches. For `QUEUED`, show that the email was queued; for `FAILED`, show that account/password storage succeeded but email queue registration failed and the operator must retry password issuance.

- [ ] **Step 5: Remove the synchronous and console sources**

Delete the three obsolete files after all imports have moved. Remove console-specific tests from `test_root_logging.py` without removing unrelated logging coverage. Confirm with:

```bash
rg -n 'ConsoleEmailBackend|EMAIL_BACKEND|email_backend|send_temporary_password|emailSent' app envs
```

Expected: no matches in `app` or `envs`.

- [ ] **Step 6: Run GREEN checks**

Run:

```bash
uv run pytest app/tests/admin_apis/test_admin_email.py app/tests/admin_apis/test_admin_password_reset_api.py app/tests/test_root_logging.py -q
node --test app/tests/static_ui/*.test.mjs
uv run ruff check app/services/admin_credentials.py app/services/admins.py app/dtos/admins.py app/apis/v1/admin_routers.py app/tests/admin_apis app/tests/test_root_logging.py
```

Expected: all pass.

### Task 6: Docker Compose and job monitoring integration

**Files:**
- Modify: `docker-compose.yml`
- Create: `app/tests/test_email_worker_compose.py`
- Modify: `app/tests/job_apis/test_background_job_service.py`
- Modify: `app/static/templates/screen-5-task-management.html`
- Modify: `app/static/js/task-management.js`
- Modify: `app/tests/static_ui/task-management.test.mjs`

**Interfaces:**
- Consumes: `app.workers.email_worker.WorkerSettings`
- Produces: Docker service `email-worker` and job-type filter option `EMAIL`.

- [ ] **Step 1: Write failing Compose and retry-contract tests**

Parse `docker compose config --format json` from a temporary directory with an empty `.env`, following existing Compose tests. Assert:

- service name/container name is `email-worker`
- command contains `app.workers.email_worker.WorkerSettings`
- it depends on healthy `mysql` and `redis`
- DB/Redis environment uses Compose service names
- it mounts `./app:/app/app`

Create a failed `EMAIL` job and assert `BackgroundJobService.retry_failed()` raises HTTP 409 with `Job retry handler is not available.`

- [ ] **Step 2: Write failing UI test for the EMAIL filter**

Assert the work-type select contains visible label `EMAIL` with value `EMAIL` and forwards that value to the administrator jobs API.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run pytest app/tests/test_email_worker_compose.py app/tests/job_apis/test_background_job_service.py -q
node --test app/tests/static_ui/*.test.mjs
```

Expected: failure because service/filter/enum integration is absent.

- [ ] **Step 4: Add Compose service and UI option**

Reuse `app/Dockerfile`, add the dedicated ARQ command, DB/Redis environment, app source mount, restart policy, network, and healthy dependency conditions. Do not add Qdrant or AI dependencies.

- [ ] **Step 5: Run GREEN checks**

Run:

```bash
uv run pytest app/tests/test_email_worker_compose.py app/tests/job_apis/test_background_job_service.py -q
node --test app/tests/static_ui/*.test.mjs
docker compose config --format json
```

Expected: all tests pass and Compose config exits zero.

### Task 7: Full cleanup and verification

**Files:**
- Review: all modified files from Tasks 1-6.

**Interfaces:**
- Produces: verified end-to-end implementation with no synchronous email path.

- [ ] **Step 1: Scan for obsolete and plaintext-sensitive paths**

Run:

```bash
rg -n 'ConsoleEmailBackend|EMAIL_BACKEND|email_backend|send_temporary_password|emailSent' app envs docker-compose.yml
rg -n 'temporary_password|SMTP_PASSWORD' app/workers app/services app/core/email
```

Expected: the first scan has no production matches; the second contains only payload field access and configuration, never logging interpolation.

- [ ] **Step 2: Run formatting and lint checks**

Run:

```bash
uv run ruff format . --check
uv run ruff check .
git diff --check
```

Expected: all exit zero.

- [ ] **Step 3: Run the email/admin/job test slice**

Run:

```bash
uv run pytest app/tests/email app/tests/workers/test_email_worker.py app/tests/admin_apis/test_admin_email.py app/tests/admin_apis/test_admin_password_reset_api.py app/tests/job_apis/test_background_job_service.py app/tests/test_email_worker_compose.py -q
node --test app/tests/static_ui/*.test.mjs
```

Expected: all pass.

- [ ] **Step 4: Run the complete automated test suite**

Run:

```bash
uv run pytest -q
```

Expected: zero failures.

- [ ] **Step 5: Inspect the final diff without committing**

Run:

```bash
git status --short
git diff --stat
git diff -- app/models/enums.py app/core/config.py app/core/email app/services/email_jobs.py app/workers/email_worker.py app/services/admins.py app/dtos/admins.py app/apis/v1/admin_routers.py docker-compose.yml envs
```

Confirm that unrelated user changes remain untouched and report that no commit was created.
