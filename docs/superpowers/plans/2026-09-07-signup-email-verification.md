# Signup Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모바일 웹 회원가입에서 1분 유효한 6자리 이메일 인증번호를 기존 `email-worker`로 발송·검증하고, 일회성 인증 토큰이 있어야 최종 회원가입이 완료되도록 구현한다.

**Architecture:** 인증 수명주기와 시도 횟수는 신규 `email_verifications` 테이블이 관리하고, 실제 발송 이력과 재시도 상태는 기존 `background_jobs`의 `EMAIL` 작업으로 관리한다. 인증번호 원문은 Fernet으로 암호화된 ARQ payload에만 두고 DB에는 HMAC-SHA256 digest만 저장하며, 인증 성공 후 발급하는 서명 토큰은 회원 생성 트랜잭션 안에서 한 번만 소비한다. 프론트는 전용 이메일 인증 API 모듈을 통해 요청·확인·재발송을 수행하고 서버가 반환한 인증 토큰을 React 메모리 상태에만 보관한다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Tortoise ORM, Aerich, MySQL 8, Redis/ARQ, cryptography/Fernet, PyJWT, Jinja2, SMTP, React 19, TypeScript, Vite, Playwright, Docker Compose, dbdiagram.io DBML

**Spec:** `docs/superpowers/specs/2026-09-07-signup-email-verification-design.md`

## Global Constraints

- 프로젝트 루트는 `/Users/admin/PycharmProjects/FinalProject`이며 모든 명령은 이 경로에서 실행한다.
- 인증번호는 `secrets.randbelow(1_000_000)`으로 생성하고 `f"{value:06d}"`로 앞자리 0을 보존한다.
- 인증번호 유효시간은 60초, 재발송 제한은 60초, 인증 토큰 유효시간은 600초, 최대 실패 횟수는 5회다.
- 인증번호 원문과 digest는 DB·API 응답·애플리케이션 로그에 노출하지 않는다.
- 같은 이메일의 최신 `SIGNUP` 인증 건만 확인할 수 있고, 재발송 시 앞선 미사용 인증 건을 즉시 만료한다.
- 이메일 발송은 기존 전용 `email-worker`와 `arq:email` 큐를 사용하고 `background_jobs`에 `job_type=EMAIL`로 기록한다.
- `background_jobs.reference_table="email_verifications"`, `reference_id=email_verifications.id`로 논리 연결하며 물리 FK는 추가하지 않는다.
- 최종 회원가입은 검증된 일회성 토큰을 필수로 받고, 사용자 생성·`UserSettings` 생성·`consumed_at` 기록을 하나의 DB 트랜잭션으로 처리한다.
- HTML 메일 제목은 `RxVita 회원가입 이메일 인증번호`이고 RxVita PNG 로고를 CID 인라인 이미지로 첨부한다.
- Mock 모드는 메일을 발송하지 않고 인증번호 `123456`을 사용한다.
- dbdiagram.io 저장 직전 별도 승인을 다시 요청하지 않는다.
- 기존 작업 트리의 사용자 변경을 보존하며 이 계획 실행 중 Git 커밋은 생성하지 않는다.

---

### Task 1: 이메일 인증 설정과 ORM 모델

**Files:**
- Create: `app/models/email_verifications.py`
- Modify: `app/models/enums.py`
- Modify: `app/models/__init__.py`
- Modify: `app/core/db/databases.py`
- Modify: `app/core/config.py`
- Test: `app/tests/models/test_email_verification_model.py`

**Interfaces:**
- Produces: `EmailVerificationPurpose.SIGNUP`, `EmailVerification`, 설정값 `EMAIL_VERIFICATION_SECRET`, `EMAIL_VERIFICATION_TTL_SECONDS`, `EMAIL_VERIFICATION_TOKEN_TTL_SECONDS`, `EMAIL_VERIFICATION_MAX_ATTEMPTS`, `EMAIL_VERIFICATION_RESEND_SECONDS`.
- Produces model fields: `id`, `email`, `purpose`, `code_digest`, `expires_at`, `attempt_count`, `verified_at`, `consumed_at`, `created_at`, `updated_at`.

- [ ] **Step 1: 모델 메타데이터 실패 테스트 작성**

```python
from app.models.email_verifications import EmailVerification
from app.models.enums import EmailVerificationPurpose


def test_email_verification_model_contract() -> None:
    assert EmailVerification._meta.db_table == "email_verifications"
    assert EmailVerification._meta.fields_map["email"].max_length == 255
    assert EmailVerification._meta.fields_map["purpose"].enum_type is EmailVerificationPurpose
    assert EmailVerification._meta.fields_map["code_digest"].max_length == 64
    assert EmailVerification._meta.fields_map["attempt_count"].default == 0
    index_fields = {tuple(index.fields) for index in EmailVerification._meta.indexes}
    assert ("email", "purpose", "created_at") in index_fields
    assert ("expires_at",) in index_fields
    assert ("verified_at", "consumed_at") in index_fields
```

- [ ] **Step 2: 테스트가 모델 미정의로 실패하는지 확인**

Run: `uv run pytest app/tests/models/test_email_verification_model.py -q`

Expected: `ModuleNotFoundError: No module named 'app.models.email_verifications'`.

- [ ] **Step 3: enum과 모델 최소 구현**

```python
class EmailVerificationPurpose(StrEnum):
    SIGNUP = "SIGNUP"
```

```python
from tortoise import fields, models
from tortoise.indexes import Index
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import EmailVerificationPurpose


class EmailVerification(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255)
    purpose = fields.CharEnumField(EmailVerificationPurpose, max_length=30)
    code_digest = fields.CharField(max_length=64)
    expires_at = fields.DatetimeField()
    attempt_count = fields.IntField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    verified_at = fields.DatetimeField(null=True)
    consumed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "email_verifications"
        indexes = (
            Index(fields=("email", "purpose", "created_at"), name="idx_email_verification_lookup"),
            Index(fields=("expires_at",), name="idx_email_verification_expiry"),
            Index(fields=("verified_at", "consumed_at"), name="idx_email_verification_state"),
        )
```

Export both new classes from `app/models/__init__.py` and append `"app.models.email_verifications"` to `TORTOISE_APP_MODELS`.

- [ ] **Step 4: 검증 제한이 있는 설정 필드 추가**

```python
EMAIL_VERIFICATION_SECRET: SecretStr | None = None
EMAIL_VERIFICATION_TTL_SECONDS: int = Field(default=60, gt=0)
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS: int = Field(default=600, gt=0)
EMAIL_VERIFICATION_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
EMAIL_VERIFICATION_RESEND_SECONDS: int = Field(default=60, gt=0)
```

- [ ] **Step 5: 모델 테스트 통과 및 정적 검사**

Run: `uv run pytest app/tests/models/test_email_verification_model.py -q`

Expected: PASS.

Run: `uv run ruff check app/models/email_verifications.py app/models/enums.py app/models/__init__.py app/core/db/databases.py app/core/config.py app/tests/models/test_email_verification_model.py`

Expected: `All checks passed!`.

---

### Task 2: 인증번호 digest와 일회성 토큰 코덱

**Files:**
- Create: `app/core/email/verification.py`
- Test: `app/tests/email/test_email_verification_security.py`

**Interfaces:**
- Consumes: `EmailVerificationPurpose`와 `config.EMAIL_VERIFICATION_SECRET`.
- Produces: `generate_verification_code() -> str`, `digest_verification_code(*, secret: str | SecretStr, verification_id: int, email: str, purpose: EmailVerificationPurpose, code: str) -> str`, `EmailVerificationTokenClaims`, `EmailVerificationTokenCodec.issue(...) -> str`, `EmailVerificationTokenCodec.verify(token: str) -> EmailVerificationTokenClaims`.
- Produces exceptions: `EmailVerificationConfigurationError`, `InvalidEmailVerificationTokenError`.

- [ ] **Step 1: 보안 유틸 실패 테스트 작성**

```python
def test_generated_code_is_six_digits(monkeypatch) -> None:
    monkeypatch.setattr(secrets, "randbelow", lambda _limit: 42)
    assert generate_verification_code() == "000042"


def test_digest_is_bound_to_verification_identity() -> None:
    first = digest_verification_code(
        secret="secret",
        verification_id=1,
        email="user@example.com",
        purpose=EmailVerificationPurpose.SIGNUP,
        code="123456",
    )
    second = digest_verification_code(
        secret="secret",
        verification_id=2,
        email="user@example.com",
        purpose=EmailVerificationPurpose.SIGNUP,
        code="123456",
    )
    assert len(first) == 64
    assert first != second


def test_token_rejects_tampering_and_expiry() -> None:
    codec = EmailVerificationTokenCodec("secret", algorithm="HS256", ttl_seconds=600)
    token = codec.issue(verification_id=7, email="user@example.com", purpose=EmailVerificationPurpose.SIGNUP)
    claims = codec.verify(token)
    assert claims.verification_id == 7
    assert claims.email == "user@example.com"
    with pytest.raises(InvalidEmailVerificationTokenError):
        codec.verify(token + "tampered")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest app/tests/email/test_email_verification_security.py -q`

Expected: import failure for `app.core.email.verification`.

- [ ] **Step 3: HMAC digest 구현**

```python
def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def digest_verification_code(*, secret, verification_id, email, purpose, code) -> str:
    secret_value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    if not secret_value:
        raise EmailVerificationConfigurationError("EMAIL_VERIFICATION_SECRET가 설정되지 않았습니다.")
    message = f"{verification_id}:{email.casefold()}:{purpose.value}:{code}".encode()
    return hmac.new(secret_value.encode(), message, hashlib.sha256).hexdigest()
```

- [ ] **Step 4: PyJWT 기반 토큰 코덱 구현**

`issue()`는 `sub="email-verification"`, `verification_id`, `email`, `purpose`, `iat`, `exp`를 HS256으로 서명한다. `verify()`는 서명·만료·`sub`·필수 claim을 검사해 `EmailVerificationTokenClaims`를 반환하고, 모든 PyJWT/validation 오류를 `InvalidEmailVerificationTokenError` 하나로 변환한다. 토큰이나 secret을 오류 메시지에 포함하지 않는다.

- [ ] **Step 5: 단위 테스트와 Ruff 실행**

Run: `uv run pytest app/tests/email/test_email_verification_security.py -q`

Expected: PASS.

Run: `uv run ruff check app/core/email/verification.py app/tests/email/test_email_verification_security.py`

Expected: `All checks passed!`.

---

### Task 3: 인증 요청·확인 서비스와 오류 계약

**Files:**
- Create: `app/repositories/email_verification_repository.py`
- Create: `app/services/email_verifications.py`
- Modify: `app/core/exceptions.py`
- Test: `app/tests/email/test_email_verification_service.py`

**Interfaces:**
- Consumes: Task 1 모델/설정, Task 2 digest/token 코덱, `UserRepository.exists_by_email`.
- Produces: `EmailVerificationService.request(email: str) -> EmailVerificationRequestResult`, `EmailVerificationService.verify(verification_id: int, code: str) -> EmailVerificationVerifyResult`, `EmailVerificationService.validate_signup_token(token: str, email: str, using_db) -> EmailVerification`.
- Produces: `SignupVerificationEmailEnqueuer` protocol with `enqueue_signup_verification(*, verification_id: int, recipient_email: str, verification_code: str, expires_at: datetime) -> BackgroundJob`; Task 4의 `EmailJobService`가 이를 구현한다.
- Produces result types: `EmailVerificationRequestResult(verification_id: int, expires_in: int, resend_available_in: int)` and `EmailVerificationVerifyResult(verification_token: str, expires_in: int)`.
- Produces AppErrors matching the spec error codes and status values.

- [ ] **Step 1: 서비스 상태 전이 실패 테스트 작성**

Cover these named cases with frozen `now` and injected `EmailJobService` mock:

```python
async def test_request_creates_digest_only_and_email_job(): ...
async def test_request_rejects_existing_user_with_409(): ...
async def test_request_rate_limits_within_60_seconds(): ...
async def test_resend_expires_previous_unconsumed_record(): ...
async def test_verify_accepts_only_latest_record_and_returns_token(): ...
async def test_verify_increments_attempt_count_for_wrong_code(): ...
async def test_verify_rejects_expired_record(): ...
async def test_verify_locks_after_five_failures(): ...
async def test_validate_signup_token_rejects_email_mismatch_and_reuse(): ...
```

Assertions must verify that `code_digest != "123456"`, no result contains the code/digest, and the enqueue call receives the plaintext code only as an in-memory argument.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest app/tests/email/test_email_verification_service.py -q`

Expected: missing repository/service errors.

- [ ] **Step 3: 명시된 AppError 클래스 추가**

Implement exact `status_code`, `code`, `message`, and `field="email"` where applicable:

```python
class EmailVerificationRateLimitedError(AppError): ...  # 429 EMAIL_VERIFICATION_RATE_LIMITED
class InvalidEmailVerificationCodeError(AppError): ...  # 400, message="인증번호를 확인해주세요."
class EmailVerificationExpiredError(AppError): ...      # 410 EMAIL_VERIFICATION_EXPIRED
class EmailVerificationAttemptsExceededError(AppError): ...  # 429
class EmailDeliveryUnavailableError(AppError): ...      # 503 EMAIL_DELIVERY_UNAVAILABLE
class EmailVerificationInvalidError(AppError): ...      # 400 EMAIL_VERIFICATION_INVALID
```

- [ ] **Step 4: 최신 건 조회와 행 잠금 repository 구현**

Repository methods are:

```python
async def get_latest(self, *, email: str, purpose: EmailVerificationPurpose, using_db=None) -> EmailVerification | None
async def get_for_update(self, verification_id: int, *, using_db) -> EmailVerification | None
async def expire_open(self, *, email: str, purpose: EmailVerificationPurpose, now: datetime, using_db) -> int
```

Use `select_for_update()` only inside a transaction and order latest query by `-created_at`, `-id`.

- [ ] **Step 5: 요청 서비스 구현**

Within one transaction: normalize email with `str(EmailStr).casefold()`, reject an existing user, lock/read latest record, enforce the 60-second resend boundary, expire prior open records, create a row with a temporary 64-character zero digest, calculate the final digest using its generated ID, then update `code_digest` before commit. After commit call `enqueue_signup_verification(verification_id, recipient_email, verification_code, expires_at)`. If the job ends `FAILED`, invalidate the verification row and raise `EmailDeliveryUnavailableError`. The service constructor receives `email_job_service: SignupVerificationEmailEnqueuer | None`; production defaults to `EmailJobService`, while unit tests inject a mock.

- [ ] **Step 6: 확인과 가입 토큰 검증 구현**

`verify()` locks the ID, rejects a non-latest ID, expired/consumed/already exhausted row, uses `hmac.compare_digest`, increments and persists failures atomically, and on success sets `verified_at` then issues the 600-second token. `validate_signup_token()` verifies claims, locks the row using the caller transaction, and validates ID/email/purpose/verified/not-consumed before returning the row; it does not set `consumed_at` itself.

- [ ] **Step 7: 서비스 테스트 실행**

Run: `uv run pytest app/tests/email/test_email_verification_service.py -q`

Expected: PASS including concurrent confirm serialization test.

---

### Task 4: 이메일 payload, 6칸 HTML 템플릿, CID 첨부 및 작업 등록

**Files:**
- Create: `app/static/templates/emails/signup_verification_code.html`
- Modify: `app/core/email/payload.py`
- Modify: `app/core/email/renderer.py`
- Modify: `app/core/email/smtp_sender.py`
- Modify: `app/services/email_jobs.py`
- Test: `app/tests/email/test_email_payload.py`
- Test: `app/tests/email/test_email_renderer.py`
- Test: `app/tests/email/test_smtp_sender.py`
- Test: `app/tests/email/test_email_job_service.py`

**Interfaces:**
- Consumes: `app/static/images/rxvita-logo-ai-chat-teal.png`, `EmailVerification.id/expires_at`.
- Produces: `EmailTemplate.SIGNUP_VERIFICATION_CODE`, discriminated optional payload fields `verification_id`, `verification_code`, `expires_at`; `InlineAttachment(content_id: str, filename: str, content_type: str, data: bytes)`; `EmailMessage.inline_attachments: tuple[InlineAttachment, ...]`.
- Produces: `EmailJobService.enqueue_signup_verification(*, verification_id: int, recipient_email: str, verification_code: str, expires_at: datetime) -> BackgroundJob`.

- [ ] **Step 1: payload와 렌더러 실패 테스트 작성**

Assert the new template round-trips through `EmailPayloadCodec`; renderer subject equals `RxVita 회원가입 이메일 인증번호`; text mentions 1 minute; HTML contains six separate code cells, `cid:rxvita-logo`, and never concatenates user-controlled HTML unsafely; one inline PNG attachment is returned.

- [ ] **Step 2: SMTP MIME 실패 테스트 작성**

Patch `smtplib.SMTP`, send a message with one inline PNG, capture `server.send_message` argument, and assert the MIME tree has plain text, related HTML, and an image part whose `Content-ID` is `<rxvita-logo>`.

- [ ] **Step 3: EmailJobService 실패 테스트 작성**

Assert the signup job has `job_type=EMAIL`, `reference_table="email_verifications"`, matching `reference_id`, idempotency prefix `email:signup-verification:`, queue `arq:email`, and an encrypted payload that does not contain email/code as plaintext.

- [ ] **Step 4: 테스트 실패 확인**

Run: `uv run pytest app/tests/email/test_email_payload.py app/tests/email/test_email_renderer.py app/tests/email/test_smtp_sender.py app/tests/email/test_email_job_service.py -q`

Expected: failures for the new enum/template/attachment/enqueue method.

- [ ] **Step 5: payload를 템플릿별 검증 구조로 확장**

Keep the existing admin password contract intact. Add optional fields, then a Pydantic `model_validator(mode="after")` that requires `recipient_name` and `temporary_password` only for `ADMIN_TEMPORARY_PASSWORD`, and requires `verification_id`, six numeric `verification_code`, and `expires_at` only for `SIGNUP_VERIFICATION_CODE`.

- [ ] **Step 6: 템플릿과 렌더러 구현**

HTML uses Jinja iteration over `verification_code` to create six fixed-size digit cells. Renderer reads the existing PNG bytes, returns CID `rxvita-logo`, and constructs this exact plain text:

```text
RxVita 회원가입 이메일 인증번호입니다.

인증번호: 123456

인증번호는 1분 동안 유효합니다.
본인이 요청하지 않았다면 이 메일을 무시해 주세요.
```

- [ ] **Step 7: CID MIME 구성과 signup enqueue 구현**

Build HTML as a `multipart/related` alternative and add images with `add_related(data, maintype="image", subtype="png", cid="<rxvita-logo>", filename=...)`. Refactor the duplicate job creation/queueing inside `EmailJobService` into a private `_enqueue(...)` without changing the public admin method behavior, then add `enqueue_signup_verification(...)`.

- [ ] **Step 8: 이메일 단위 테스트 실행**

Run: `uv run pytest app/tests/email/test_email_payload.py app/tests/email/test_email_renderer.py app/tests/email/test_smtp_sender.py app/tests/email/test_email_job_service.py -q`

Expected: PASS.

---

### Task 5: email-worker의 인증 만료 취소와 재시도 경계

**Files:**
- Modify: `app/workers/email_worker.py`
- Test: `app/tests/workers/test_email_worker.py`

**Interfaces:**
- Consumes: `EmailTemplate.SIGNUP_VERIFICATION_CODE`, payload `verification_id/expires_at`, `EmailVerification`.
- Produces: `_cancel_job(job: BackgroundJob, error_code: str) -> None`; `_is_signup_verification_sendable(payload, now) -> bool`; `_retry_or_fail(job, error, *, expires_at: datetime | None = None)`.

- [ ] **Step 1: 워커 실패 테스트 추가**

Add cases for missing verification row, expired row, consumed row, valid row, and retry delay beyond `expires_at`. The first three must skip SMTP and set `status=CANCELLED`, `error_code=EMAIL_VERIFICATION_EXPIRED`; a retry whose next time is after expiry must also cancel instead of raising `Retry`.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest app/tests/workers/test_email_worker.py -q`

Expected: new cancellation assertions fail.

- [ ] **Step 3: 발송 전 검증과 취소 구현**

After decrypting and before rendering, branch only for `SIGNUP_VERIFICATION_CODE`; fetch the referenced verification ID and require `expires_at > now` and `consumed_at is None`. Re-check the same expiry when choosing a retry delay. Preserve current temporary-password behavior and all existing failure codes.

- [ ] **Step 4: 워커 테스트 실행**

Run: `uv run pytest app/tests/workers/test_email_worker.py -q`

Expected: PASS.

---

### Task 6: 인증 요청·확인 API와 최종 가입 강제

**Files:**
- Modify: `app/dtos/auth.py`
- Modify: `app/apis/v1/auth_routers.py`
- Modify: `app/services/auth.py`
- Modify: `app/repositories/user_repository.py`
- Test: `app/tests/auth_apis/test_email_verification_api.py`
- Test: `app/tests/auth_apis/test_signup_api.py`

**Interfaces:**
- Consumes: `EmailVerificationService.request`, `.verify`, `.validate_signup_token`.
- Produces DTOs: `EmailVerificationRequest(email)`, `EmailVerificationRequestResponse(verification_id, expires_in, resend_available_in)`, `EmailVerificationCodeRequest(code)`, `EmailVerificationVerifyResponse(verification_token, expires_in)`.
- Changes: `SignUpRequest.email_verification_token: str` required.
- Produces endpoints: `POST /api/v1/auth/email-verifications` (202), `POST /api/v1/auth/email-verifications/{verification_id}/verify` (200).

- [ ] **Step 1: API 계약 실패 테스트 작성**

Use ASGI client and patched service to assert snake_case request/response, exact status codes, exact AppError body, 6-digit validation, and that request/verify endpoints pass no code or digest back in responses.

- [ ] **Step 2: 회원가입 보안 실패 테스트 갱신**

Update all successful signup fixtures to create a verified record/token. Add tests for missing token (422), tampered/expired token (400 `EMAIL_VERIFICATION_INVALID`), email mismatch, unverified record, reused token, and rollback. Assert a successful signup sets `consumed_at`; a forced `UserSettings.create` failure leaves both User absent and `consumed_at is None`.

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest app/tests/auth_apis/test_email_verification_api.py app/tests/auth_apis/test_signup_api.py -q`

Expected: endpoints are 404 and signup token contract assertions fail.

- [ ] **Step 4: DTO와 라우터 구현**

Use the same ASCII email validator as signup. `code` is `Annotated[str, StringConstraints(pattern=r"^\d{6}$")]`. Declare all documented `responses` with `AuthErrorResponse` and retain existing route prefix `/auth` so final URLs remain under `/api/v1/auth`.

- [ ] **Step 5: repository가 호출자 트랜잭션을 사용하도록 확장**

Add `using_db=None` as a keyword-only parameter to `UserRepository.create_user(...)` and pass it to `User.create(..., using_db=using_db)`. Existing callers continue to work because the default remains `None`; signup passes the active transaction connection.

- [ ] **Step 6: 가입 트랜잭션에 토큰 소비 통합**

Inject `EmailVerificationService` into `AuthService`. Move `validate_signup_token(..., using_db=connection)` inside the existing `in_transaction() as connection` block, call `create_user(..., using_db=connection)`, call `UserSettings.create(..., using_db=connection)`, then set `verification.consumed_at=now` and call `verification.save(using_db=connection, update_fields=["consumed_at", "updated_at"])`. Keep duplicate-email `IntegrityError -> SignupEmailAlreadyExistsError` conversion.

- [ ] **Step 7: API 테스트 실행**

Run: `uv run pytest app/tests/auth_apis/test_email_verification_api.py app/tests/auth_apis/test_signup_api.py -q`

Expected: PASS.

Run: `uv run pytest app/tests/email app/tests/workers/test_email_worker.py app/tests/auth_apis/test_signup_api.py app/tests/auth_apis/test_email_verification_api.py -q`

Expected: all email/signup regression tests PASS.

---

### Task 7: Aerich 마이그레이션과 예제 환경/Docker 설정

**Files:**
- Create: `app/core/db/migrations/models/31_*_add_email_verifications.py` (Aerich가 출력한 정확한 타임스탬프 파일)
- Modify: `envs/example.local.env`
- Modify: `envs/example.prod.env`
- Modify: `docker-compose.yml`
- Modify: `infra/docker/docker-compose.prod.yml`
- Test: `app/tests/models/test_email_verification_migration.py`
- Test: `app/tests/test_email_worker_compose.py`

**Interfaces:**
- Consumes: Task 1 ORM metadata/config.
- Produces: MySQL table, three named indexes, CHECK `attempt_count BETWEEN 0 AND 5`; FastAPI와 email-worker에 같은 인증 설정 환경변수 전달.

- [ ] **Step 1: 마이그레이션 SQL 실패 테스트 작성**

Find the generated migration by suffix `add_email_verifications.py`; assert upgrade SQL contains `CREATE TABLE email_verifications`, all columns, named indexes, and `CHECK (attempt_count BETWEEN 0 AND 5)`, while downgrade drops only this table.

- [ ] **Step 2: Aerich 마이그레이션 생성**

Run: `uv run aerich migrate --name add_email_verifications`

Expected: one new migration under `app/core/db/migrations/models/` after migration 30. Inspect it and add the explicit CHECK constraint if Aerich omits validators from DDL; keep the generated `MODELS_STATE` synchronized with the actual model.

- [ ] **Step 3: 예제 환경과 Compose 서비스에 설정 전달**

Add these exact keys to both example env files:

```dotenv
EMAIL_VERIFICATION_SECRET=
EMAIL_VERIFICATION_TTL_SECONDS=60
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=600
EMAIL_VERIFICATION_MAX_ATTEMPTS=5
EMAIL_VERIFICATION_RESEND_SECONDS=60
```

Pass all five keys to `fastapi` and `email-worker` in local and production Compose. Do not put a real secret in version control.

- [ ] **Step 4: Compose와 마이그레이션 테스트 실행**

Run: `uv run pytest app/tests/models/test_email_verification_migration.py app/tests/test_email_worker_compose.py -q`

Expected: PASS.

Run: `docker compose config --no-env-resolution --format json`

Expected: exit code 0 and both relevant services contain the five settings.

- [ ] **Step 5: Docker MySQL에 적용하고 메타데이터 확인**

Generate a local secret without printing it to logs and put it in the ignored `.env`:

```bash
openssl rand -hex 32
```

Run: `uv run aerich upgrade`

Expected: migration 31 is applied.

Run: `docker compose exec -T mysql mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SHOW CREATE TABLE email_verifications\G"`

Expected: bigint PK, varchar/char widths, three named indexes, and attempt-count CHECK match the model.

---

### Task 8: 프론트 이메일 인증 API와 Mock 계약

**Files:**
- Create: `frontend/src/entities/email-verification/types.ts`
- Create: `frontend/src/entities/email-verification/api.ts`
- Create: `frontend/src/entities/email-verification/api.mock.ts`
- Create: `frontend/src/entities/email-verification/index.ts`
- Modify: `frontend/src/entities/account/types.ts`
- Modify: `frontend/src/entities/account/api.ts`
- Modify: `frontend/src/entities/account/api.mock.ts`
- Test: `frontend/tests/e2e/auth-signup-tutorial-figma.spec.ts`

**Interfaces:**
- Produces: `requestEmailVerification(email: string): Promise<{verificationId: number; expiresIn: number; resendAvailableIn: number}>`.
- Produces: `verifyEmailCode(verificationId: number, code: string): Promise<{verificationToken: string; expiresIn: number}>`.
- Changes: `CreateAccountPayload.emailVerificationToken: string` and signup API body key `email_verification_token`.
- Mock: fixed code `123456`, incrementing verification ID, one-time token tied to normalized email.

- [ ] **Step 1: Playwright 네트워크 계약 테스트 추가**

In real-API route interception mode, assert step 1 posts `{email}` to `/api/v1/auth/email-verifications`, step 2 posts `{code:"123456"}` to `/api/v1/auth/email-verifications/41/verify`, and final signup includes `email_verification_token:"verification-token"`.

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && pnpm exec playwright test tests/e2e/auth-signup-tutorial-figma.spec.ts --grep "이메일 인증 API"`

Expected: request routes are not called.

- [ ] **Step 3: API 타입과 real/mock 함수 구현**

Map backend snake_case responses to camelCase entity types. Mock request returns `{verificationId, expiresIn:60, resendAvailableIn:60}` and stores `123456`; mock verify throws `new ApiError(400, 'INVALID_EMAIL_VERIFICATION_CODE', '인증번호를 확인해주세요.')` on mismatch and returns a generated in-memory token on match.

- [ ] **Step 4: 계정 생성 payload에 인증 토큰 추가**

Add required `emailVerificationToken` and serialize it as `email_verification_token`. Keep all existing normalization and login ordering unchanged.

- [ ] **Step 5: 타입 검사**

Run: `cd frontend && pnpm typecheck`

Expected: PASS after the UI caller is updated in Task 9; until then, the expected failure is `emailVerificationToken` missing in `AuthPage.tsx`.

---

### Task 9: `/login` 1분 타이머·재발송·검증 UI 연결

**Files:**
- Modify: `frontend/src/pages/auth/AuthPage.tsx`
- Test: `frontend/tests/e2e/auth-signup-tutorial-figma.spec.ts`

**Interfaces:**
- Consumes: Task 8 API functions and result types.
- Maintains state: `verificationId: number | null`, `verificationToken: string | null`, `verificationSeconds`, `verificationError`, `saving`.
- Produces behavior: successful request only then step 2; 01:00 countdown; expiry disables code/confirm; resend only after zero; successful verify enters step 3; final signup sends token.

- [ ] **Step 1: UI 동작 E2E 테스트 추가**

Add explicit cases:

```typescript
test('인증 요청이 성공하기 전에는 2단계로 이동하지 않는다', async ({ page }) => { ... });
test('인증번호는 01:00 뒤 입력과 확인이 비활성화되고 재발송이 활성화된다', async ({ page }) => { ... });
test('재발송은 코드와 오류를 지우고 새 인증 ID를 사용한다', async ({ page }) => { ... });
test('틀린 인증번호는 입력란 아래 지정 문구를 표시한다', async ({ page }) => { ... });
test('인증 성공 토큰이 최종 회원가입 요청에 포함된다', async ({ page }) => { ... });
```

Use Playwright clock installation before page load for the 60-second test; do not wait one real minute.

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && pnpm exec playwright test tests/e2e/auth-signup-tutorial-figma.spec.ts --grep "인증"`

Expected: timer starts at the old value or fake transitions bypass the API.

- [ ] **Step 3: 요청·확인 흐름 연결**

Step 1 validates email, sets `saving`, calls `requestEmailVerification`, stores ID, resets code/error/token, sets seconds from response, then enters step 2. Step 2 refuses after zero, calls `verifyEmailCode`, stores token, clears error, then enters step 3. Catch `ApiError` and show its message under the email/code field; for `INVALID_EMAIL_VERIFICATION_CODE`, always show exact `인증번호를 확인해주세요.`.

- [ ] **Step 4: 정확한 타이머와 재발송 버튼 구현**

Use one `useEffect` active only on signup step 2 and seconds above zero, decrementing from 60 each second and clearing its interval on dependency change/unmount. Render `다시 보내기` as a real `type="button"`; disable it while `verificationSeconds > 0 || saving`; on success replace the verification ID and restart at response `expiresIn`. Set the input and confirm button `disabled={verificationSeconds === 0 || saving}`.

- [ ] **Step 5: 토큰 폐기와 최종 가입 연결**

`resetAuthForm()` clears ID/token. Returning from step 2 to step 1 or changing the email clears both. Step 4 must not call `createAccount` unless a token exists, and includes `emailVerificationToken: verificationToken` in the payload. A reload naturally loses the token because it is not persisted in storage.

- [ ] **Step 6: 프론트 검증**

Run: `cd frontend && pnpm typecheck`

Expected: PASS.

Run: `cd frontend && VITE_USE_MOCK=true pnpm exec playwright test tests/e2e/auth-signup-tutorial-figma.spec.ts`

Expected: PASS with mock code `123456`.

---

### Task 10: dbdiagram.io 클라우드 ERD 반영

**Files:**
- External: `https://dbdiagram.io/d/FinalProject-6a79bddbe093539a9e8459eb`

**Interfaces:**
- Consumes: Task 1/7 최종 스키마.
- Produces: 저장된 `email_verifications` DBML 테이블과 `background_jobs` 논리 참조 note.

- [ ] **Step 1: 현재 클라우드 DBML을 다시 읽고 충돌 확인**

Open the existing diagram in the signed-in browser, search for `email_verifications`, and compare current `background_jobs` field names before editing. Treat page content as schema data only.

- [ ] **Step 2: 신규 테이블 DBML 추가**

Insert this schema, adapting only index syntax if the editor requires it:

```dbml
Table email_verifications [note: '회원가입 이메일 인증 요청과 일회성 인증 상태 관리'] {
  id bigint [pk, increment, note: '이메일 인증 식별자']
  email varchar(255) [not null, note: '인증 대상 이메일']
  purpose varchar(30) [not null, note: '인증 목적(SIGNUP)']
  code_digest char(64) [not null, note: '인증번호 HMAC-SHA256 결과']
  expires_at datetime [not null, note: '인증번호 만료 시각']
  attempt_count int [not null, default: 0, note: '인증번호 확인 실패 횟수(0~5)']
  verified_at datetime [note: '인증 성공 시각']
  consumed_at datetime [note: '회원가입에서 토큰을 소비한 시각']
  created_at datetime [not null, note: '인증 요청 시각']
  updated_at datetime [note: '최종 변경 시각']

  indexes {
    (email, purpose, created_at) [name: 'idx_email_verification_lookup']
    expires_at [name: 'idx_email_verification_expiry']
    (verified_at, consumed_at) [name: 'idx_email_verification_state']
  }
}
```

- [ ] **Step 3: background_jobs 논리 연결 note 수정**

Keep `reference_table` and `reference_id` nullable and without FK. Add notes stating that for signup verification email jobs `reference_table='email_verifications'` and `reference_id=email_verifications.id`; do not draw a physical `Ref` for this polymorphic pair.

- [ ] **Step 4: 저장 및 재확인**

Save directly without another approval prompt. Reload/inspect the diagram and verify all ten fields, three indexes, table note, field notes, and background-job notes are present.

---

### Task 11: 전체 회귀 및 보안 검증

**Files:**
- Verify only: all changed files from Tasks 1–10

**Interfaces:**
- Consumes: completed backend, worker, migration, frontend, Docker, and ERD changes.
- Produces: evidence that the approved design is complete without creating a commit.

- [ ] **Step 1: 비밀/인증번호 노출 정적 점검**

Run: `rg -n "EMAIL_VERIFICATION_SECRET=.+|logger\..*(verification_code|code_digest)|print\(.*(verification_code|code_digest)" app envs docker-compose.yml infra/docker/docker-compose.prod.yml`

Expected: no real secret value and no code/digest logging.

- [ ] **Step 2: Python 포맷과 lint**

Run: `uv run ruff format . --check`

Expected: all files already formatted.

Run: `uv run ruff check .`

Expected: `All checks passed!`.

- [ ] **Step 3: 백엔드 전체 테스트**

Run: `uv run pytest -q`

Expected: all tests PASS.

- [ ] **Step 4: 프론트 타입과 대상 E2E**

Run: `cd frontend && pnpm typecheck`

Expected: PASS.

Run: `cd frontend && VITE_USE_MOCK=true pnpm exec playwright test tests/e2e/auth-signup-tutorial-figma.spec.ts`

Expected: PASS.

- [ ] **Step 5: Compose 및 실행 서비스 확인**

Run: `docker compose config --no-env-resolution --format json`

Expected: exit code 0.

Run: `docker compose ps fastapi email-worker redis mysql`

Expected: all four services are running/healthy after normal project startup.

- [ ] **Step 6: 수동 smoke test**

Open `http://localhost:5173/login`, select signup, request a code, confirm that a `background_jobs` EMAIL row references the new verification ID, receive/render the email with CID logo and six boxes, verify before 60 seconds, complete signup, then retry the same signup token through the API and confirm `400 EMAIL_VERIFICATION_INVALID`. Also test an expired code and confirm the input/confirm UI is disabled and resend is enabled.

- [ ] **Step 7: 변경 범위 최종 확인**

Run: `git status --short`

Expected: only intended feature files plus pre-existing user changes are present; no commit is created.
