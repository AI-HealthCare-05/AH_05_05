# Tortoise Domain Models and Account Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `accounts` with direct `user`/`admin` account fields, implement all 19 dbdiagram tables as Tortoise models, create a fresh Aerich initial migration, and update the online dbdiagram.

**Architecture:** Keep one Tortoise app label (`models`) and split model modules by domain. Shared `StrEnum` types live in one dependency-free module; relationships use string model references to prevent import cycles. Existing user authentication is minimally adapted to the new `User` shape, while administrator APIs and services remain out of scope.

**Tech Stack:** Python 3.13, Tortoise ORM 0.25.3, Aerich 0.9.2, FastAPI, Pydantic 2, MySQL 8, pytest

**Spec:** `docs/superpowers/specs/2026-08-18-tortoise-models-account-merge-design.md`

## Global Constraints

- Implement exactly 19 database tables after removing `accounts`.
- Remove `account_type`, `account_id`, `gender`, `birthday`, `last_login`, `is_active`, and `is_admin`.
- Do not create administrator Repository, DTO, service, API, login, or JWT flows.
- Preserve dbdiagram FK deletion policies and polymorphic `background_jobs.reference_table/reference_id` behavior.
- Generate a fresh initial migration; existing database data does not need migration or preservation.
- Do not modify the user's unrelated `.DS_Store` change.

## File Structure

- `app/models/enums.py`: all DB-backed `StrEnum` definitions.
- `app/models/users.py`: `User` only.
- `app/models/admins.py`: `Admin` and its creator self-reference.
- `app/models/care.py`: `CareEpisode`, `CareAdvice`, `FollowUpVisit`.
- `app/models/ocr.py`: `OcrJob`, `OcrExtractedField`.
- `app/models/recovery.py`: `RecoveryGuide`, `RecoveryGuideSource`.
- `app/models/chat.py`: `ChatSession`, `ChatMessage`, `ChatMessageSource`.
- `app/models/alarms.py`: `PushSubscription`, `Alarm`, `AlarmEvent`.
- `app/models/background_jobs.py`: `BackgroundJob`.
- `app/models/medications.py`: `Medication`, `MedicationTime`.
- `app/models/consents.py`: `UserConsent`.
- `app/core/db/databases.py`: complete model-module registration.
- `app/tests/models/test_model_metadata.py`: fast metadata tests for tables, fields, enums, indexes, unique constraints, and relationships.
- `app/tests/auth_apis/*.py`, `app/tests/user_apis/*.py`: API contract updates for the reduced user shape.
- `app/core/db/migrations/models/0_*_init.py`: freshly generated Aerich migration.

---

### Task 1: Shared enums and merged account models

**Files:**
- Create: `app/models/enums.py`
- Create: `app/models/admins.py`
- Modify: `app/models/users.py`
- Create: `app/tests/models/__init__.py`
- Create: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Produces: `AccountStatus`, `AdminRole`, `User`, and `Admin` for all later tasks.
- Produces: `MODEL_MODULES: tuple[str, ...]` test constant listing domain modules once they exist.

- [ ] **Step 1: Write failing account-model metadata tests**

```python
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.models.users import User


def test_user_matches_merged_account_schema() -> None:
    assert User._meta.db_table == "user"
    assert User._meta.fields == {
        "id", "email", "hashed_password", "status", "name", "phone",
        "is_alarm", "created_at", "updated_at",
    }
    assert User._meta.fields_map["email"].unique is True
    assert User._meta.fields_map["status"].default == AccountStatus.PENDING


def test_admin_has_nullable_creator_self_reference() -> None:
    assert Admin._meta.db_table == "admin"
    assert Admin._meta.fields_map["role"].default == AdminRole.STAFF
    creator = Admin._meta.fields_map["created_by_admin"]
    assert creator.null is True
    assert creator.model_name == "models.Admin"
```

- [ ] **Step 2: Run the account tests and verify import failures**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: FAIL because `app.models.enums` and `app.models.admins` do not exist and `User` still has legacy fields.

- [ ] **Step 3: Define all shared enums with exact DB values**

Create `app/models/enums.py` with these `StrEnum` classes and values:

```python
class AccountStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    WITHDRAWN = "WITHDRAWN"


class AdminRole(StrEnum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"
```

The same file must also define the exact DBML values for:

```text
OcrJobStatus: QUEUED, PROCESSING, READY_FOR_REVIEW, COMPLETE, FAILED, CANCELLED
AlarmStatus: ACTIVE, PAUSED, COMPLETED, CANCELLED
AlarmEventType: SCHEDULED, SENT, DELIVERED, COMPLETED, SKIPPED, FAILED
AlarmType: MEDICATION, FOLLOW_UP_VISIT, CUSTOM
BackgroundJobType: OCR, LLM, CHAT, ALARM, DATA_DELETION
BackgroundJobStatus: QUEUED, PROCESSING, RETRY_WAITING, COMPLETED, FAILED, CANCELLED
CareEpisodeStatus: ACTIVE, COMPLETED, CANCELLED
OcrDocumentType: DISCHARGE_SUMMARY, DISCHARGE_INSTRUCTION, PRESCRIPTION, MEDICATION_GUIDE, MEDICATION_BAG
OcrMaskingStatus: PENDING, COMPLETED, SUSPECTED, FAILED
OcrReviewStatus: UNREVIEWED, REVIEW_REQUIRED, REVIEWED
RecoveryGuideStatus: COMPLETED, SUPERSEDED
GuideSourceType: PATIENT_SAVED_FIELD, PUBLIC_RAG_CHUNK
ChatSessionStatus: ACTIVE, DELETED
ChatMessageRole: USER, ASSISTANT, SYSTEM
ChatMessageStatus: PENDING, STREAMING, COMPLETED, FAILED
ChatRouteType: PATIENT_DB, PUBLIC_RAG, PATIENT_AND_PUBLIC, GENERAL_LIFESTYLE, SAFETY_RESPONSE, OUT_OF_SCOPE_RESPONSE
ChatSafetyStatus: PENDING, SAFE, RESTRICTED, BLOCKED, VALIDATION_FAILED
ChatVerificationStatus: NOT_REQUIRED, PENDING, VERIFIED, FAILED
ChatConflictStatus: NOT_APPLICABLE, NO_CONFLICT, PATIENT_DATA_PRIORITY, PUBLIC_SOURCE_EXCLUDED, REVIEW_REQUIRED
ChatSourceType: PATIENT_SAVED_FIELD, PUBLIC_RAG_CHUNK
ConsentType: MEDICAL_DATA, AI_USAGE, NOTIFICATION
```

- [ ] **Step 4: Implement the merged `User` and `Admin` models**

Use these public fields and table names:

```python
class User(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True)
    hashed_password = fields.CharField(max_length=255)
    status = fields.CharEnumField(AccountStatus, default=AccountStatus.PENDING)
    name = fields.CharField(max_length=100)
    phone = fields.TextField(null=True)
    is_alarm = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "user"
        indexes = (("status",), ("created_at",))


class Admin(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True)
    hashed_password = fields.CharField(max_length=255)
    status = fields.CharEnumField(AccountStatus, default=AccountStatus.PENDING)
    name = fields.CharField(max_length=100)
    role = fields.CharEnumField(AdminRole, default=AdminRole.STAFF)
    created_by_admin = fields.ForeignKeyField(
        "models.Admin", related_name="created_admins", null=True, on_delete=fields.SET_NULL
    )
    approved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "admin"
        indexes = (("role",), ("status",), ("created_by_admin",), ("created_at",))
```

- [ ] **Step 5: Run account metadata tests**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: PASS for account tests.

- [ ] **Step 6: Commit account models**

```bash
git add app/models/enums.py app/models/users.py app/models/admins.py app/tests/models
git commit -m "feat: merge account fields into user and admin models"
```

---

### Task 2: Care, OCR, and confirmed care-data models

**Files:**
- Create: `app/models/care.py`
- Create: `app/models/ocr.py`
- Modify: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Consumes: enums from `app.models.enums`; string references to `models.User`.
- Produces: `CareEpisode`, `CareAdvice`, `FollowUpVisit`, `OcrJob`, `OcrExtractedField`.

- [ ] **Step 1: Add failing table/relationship tests**

```python
def test_care_and_ocr_tables_and_relations() -> None:
    assert CareEpisode._meta.db_table == "care_episodes"
    assert CareEpisode._meta.fields_map["user"].model_name == "models.User"
    assert OcrJob._meta.fields_map["care_episode"].model_name == "models.CareEpisode"
    assert OcrExtractedField._meta.unique_together == (
        ("ocr_job", "entity_key", "field_type"),
    )
    assert CareAdvice._meta.unique_together == (("care_episode", "display_order"),)
```

- [ ] **Step 2: Run tests and verify missing-model failures**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: FAIL importing the five new classes.

- [ ] **Step 3: Implement care models**

Implement exact DBML field groups:

```text
CareEpisode: id, user FK, title(150), status, started_at, default_end_at,
planned_end_at, completed_at, created_at, updated_at
CareAdvice: id, care_episode FK, text(500), display_order,
source_extracted_field nullable FK, created_at, updated_at
FollowUpVisit: id, care_episode FK, visit_at, department(100), doctor_name(100),
place(255), purpose(255), source_extracted_field nullable FK, created_at, updated_at
```

Use `CASCADE` for `user`/`care_episode`; use `SET_NULL` for source extracted fields. Add `MinValueValidator(1)` to `display_order`. Add DBML indexes and the `(care_episode, display_order)` unique constraint.

- [ ] **Step 4: Implement OCR models**

Implement exact DBML field groups:

```text
OcrJob: id, care_episode FK, document_type, status, masking_status,
idempotency_key(100 unique), content_hash(71), page_count(default 1),
pipeline_version(50), error_code(100), created_at, completed_at
OcrExtractedField: id, ocr_job FK, entity_key(100), field_type(100), raw_value,
normalized_value JSON, reviewed_value JSON, confidence decimal(5,4), review_status,
source_page, created_at, corrected_at, reviewed_at
```

Use validators `page_count >= 1`, `0 <= confidence <= 1`, and `source_page >= 1`. Add the compound unique and all DBML indexes.

- [ ] **Step 5: Initialize model metadata and run tests**

Extend the test setup with:

```python
MODEL_MODULES = (
    "app.models.users", "app.models.admins", "app.models.care", "app.models.ocr"
)
Tortoise.init_models(MODEL_MODULES, "models")
```

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: PASS for Task 1-2 models with resolved relations.

- [ ] **Step 6: Commit care and OCR models**

```bash
git add app/models/care.py app/models/ocr.py app/tests/models/test_model_metadata.py
git commit -m "feat: add care and OCR domain models"
```

---

### Task 3: Recovery-guide and chat models

**Files:**
- Create: `app/models/recovery.py`
- Create: `app/models/chat.py`
- Modify: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Consumes: `CareEpisode` and `OcrExtractedField` through string references.
- Produces: `RecoveryGuide`, `RecoveryGuideSource`, `ChatSession`, `ChatMessage`, `ChatMessageSource`.

- [ ] **Step 1: Add failing relationship and uniqueness tests**

```python
def test_recovery_and_chat_relationships() -> None:
    assert RecoveryGuide._meta.fields_map["care_episode"].model_name == "models.CareEpisode"
    assert RecoveryGuideSource._meta.unique_together == (("recovery_guide", "citation_order"),)
    assert ChatMessage._meta.unique_together == (("chat_session", "sequence_no"),)
    assert ChatMessage._meta.fields_map["reply_to_message"].model_name == "models.ChatMessage"
    assert ChatMessageSource._meta.fields_map["extracted_field"].on_delete == fields.SET_NULL
```

- [ ] **Step 2: Run tests and verify missing-model failures**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: FAIL importing recovery/chat models.

- [ ] **Step 3: Implement recovery models**

Map all DBML columns without dropping provenance fields:

```text
RecoveryGuide: care_episode FK, status, guide_content JSON, patient_context_hash(64),
model_name(100), model_version(100), prompt_version(100), schema_version(50),
langsmith_trace_id(100), safety_status, safety_reason_code(100), error_code(100),
completed_at, superseded_at, created_at, updated_at
RecoveryGuideSource: recovery_guide FK, source_type, extracted_field nullable FK,
public_dataset_key(100), dataset_version(100), vector_chunk_id(255),
source_record_key(100), source_field(100), chunk_type(100), source_title(255),
source_organization(255), source_url text, similarity_score decimal(5,4),
citation_order, created_at
```

Add source indexes and `(recovery_guide, citation_order)` uniqueness. Use `SET_NULL` for `extracted_field`.

- [ ] **Step 4: Implement chat models**

Map these exact field groups:

```text
ChatSession: id, care_episode FK, status, last_message_at, deleted_at, created_at, updated_at
ChatMessage: id, chat_session FK, reply_to_message nullable self FK, guide nullable FK,
request_id(100), sequence_no, role, content text, status, route_type, safety_status,
safety_reason_code(100), verification_status, conflict_status, model_name(100),
model_version(100), prompt_version(100), schema_version(50), patient_context_hash(64),
langsmith_trace_id(100), error_code(100), started_at, completed_at, created_at, updated_at
ChatMessageSource: id, chat_message FK, source_type, extracted_field nullable FK,
public_dataset_key(100), dataset_version(100), vector_chunk_id(255),
source_record_key(100), source_field(100), chunk_type(100), source_title(255),
source_organization(255), source_url text, similarity_score decimal(5,4),
citation_order, created_at
```

Preserve:

- `reply_to_message` nullable self FK with `SET_NULL`.
- `guide` nullable FK to `RecoveryGuide` with `SET_NULL`.
- source `extracted_field` nullable FK with `SET_NULL`.
- `(chat_session, sequence_no)` and `(chat_message, citation_order)` unique constraints.
- request, trace, created-time, public-dataset, record-key, and vector-chunk indexes.

- [ ] **Step 5: Register modules in metadata setup and run tests**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: PASS for account, care, OCR, recovery, and chat models.

- [ ] **Step 6: Commit recovery and chat models**

```bash
git add app/models/recovery.py app/models/chat.py app/tests/models/test_model_metadata.py
git commit -m "feat: add recovery and chat domain models"
```

---

### Task 4: Alarm and background-job models

**Files:**
- Create: `app/models/alarms.py`
- Create: `app/models/background_jobs.py`
- Modify: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Consumes: `User`, `CareEpisode`, `RecoveryGuide` through string references.
- Produces: `PushSubscription`, `Alarm`, `AlarmEvent`, `BackgroundJob`.

- [ ] **Step 1: Add failing alarm/job metadata tests**

```python
def test_alarm_and_background_job_metadata() -> None:
    assert PushSubscription._meta.fields_map["endpoint"].unique is True
    assert Alarm._meta.fields_map["user"].model_name == "models.User"
    assert AlarmEvent._meta.fields_map["push_subscription"].on_delete == fields.SET_NULL
    assert BackgroundJob._meta.fields_map["parent_job"].model_name == "models.BackgroundJob"
    assert "reference_table" in BackgroundJob._meta.db_fields
    assert "reference_id" in BackgroundJob._meta.db_fields
```

- [ ] **Step 2: Run tests and verify missing-model failures**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: FAIL importing alarm/background classes.

- [ ] **Step 3: Implement push subscription, alarm, and event models**

Map these exact field groups:

```text
PushSubscription: id, user FK, endpoint(500 unique), p256dh_key(255), auth_key(255),
platform(50), user_agent(255), is_active(default true), created_at, last_used_at
Alarm: id, user FK, care_episode nullable FK, source_guide nullable FK, alarm_type,
title(255), message(500), scheduled_at, recurrence_rule(100), timezone(50),
next_trigger_at, status, last_triggered_at, completed_at, cancelled_at, created_at, updated_at
AlarmEvent: id, alarm FK, event_type, push_subscription nullable FK, event_at,
payload JSON, error_code(100), created_at
```

Critical declarations are:

```python
user = fields.ForeignKeyField("models.User", related_name="push_subscriptions", on_delete=fields.CASCADE)
care_episode = fields.ForeignKeyField("models.CareEpisode", null=True, on_delete=fields.CASCADE)
source_guide = fields.ForeignKeyField("models.RecoveryGuide", null=True, on_delete=fields.SET_NULL)
push_subscription = fields.ForeignKeyField("models.PushSubscription", null=True, on_delete=fields.SET_NULL)
```

Use a named Tortoise `Index(fields=("status", "next_trigger_at"), name="idx_due_alarms")` for the scheduler index.

- [ ] **Step 4: Implement `BackgroundJob`**

Map all DBML fields. Keep `reference_table` and `reference_id` as nullable scalar fields. Implement `parent_job` as nullable `models.BackgroundJob` self FK with `SET_NULL`. Add `MinValueValidator(0)` to `retry_count`, and create named `idx_queue_stats` for `(status, requested_at)`.

- [ ] **Step 5: Register modules and run metadata tests**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: PASS.

- [ ] **Step 6: Commit alarm and background-job models**

```bash
git add app/models/alarms.py app/models/background_jobs.py app/tests/models/test_model_metadata.py
git commit -m "feat: add alarm and background job models"
```

---

### Task 5: Medication and consent models plus complete registration

**Files:**
- Create: `app/models/medications.py`
- Create: `app/models/consents.py`
- Modify: `app/core/db/databases.py`
- Modify: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Consumes: `CareEpisode`, `OcrJob`, `OcrExtractedField`, `User` through string references.
- Produces: `Medication`, `MedicationTime`, `UserConsent`; complete `TORTOISE_APP_MODELS`.

- [ ] **Step 1: Add failing final-table and registry tests**

```python
EXPECTED_TABLES = {
    "user", "admin", "care_episodes", "ocr_jobs", "ocr_extracted_fields",
    "recovery_guides", "recovery_guide_sources", "chat_sessions", "chat_messages",
    "chat_message_sources", "push_subscriptions", "alarms", "alarm_events",
    "background_jobs", "medications", "medication_times", "care_advices",
    "follow_up_visits", "user_consents",
}


def test_all_19_tables_are_registered() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    tables = {model._meta.db_table for model in Tortoise.apps["models"].values()}
    assert EXPECTED_TABLES <= tables
    assert "accounts" not in tables
```

- [ ] **Step 2: Run tests and verify missing-model/registry failures**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Expected: FAIL because medication/consent models and module registry entries are absent.

- [ ] **Step 3: Implement medication models**

Map these exact field groups:

```text
Medication: id, care_episode FK, name(255), dose(100), times_per_day, note(255),
days, prescribed_at date, source_ocr_job nullable FK, source_extracted_field nullable FK,
created_at, updated_at
MedicationTime: id, medication FK, time_of_day, created_at
```

Use `SET_NULL` for `source_ocr_job` and `source_extracted_field`; add `MinValueValidator(1)`/`MaxValueValidator(6)` to `times_per_day` and `MinValueValidator(1)` to `days`. Add `(medication, time_of_day)` uniqueness for `MedicationTime`.

- [ ] **Step 4: Implement `UserConsent`**

Map `user`, `consent_type`, `agreed`, `agreed_at`, `policy_version(50)`, and `created_at`. Add both `(user, consent_type, agreed_at)` and `(user, consent_type)` indexes; do not add uniqueness because consent history is append-only.

- [ ] **Step 5: Register every domain module**

Set `TORTOISE_APP_MODELS` to:

```python
TORTOISE_APP_MODELS = [
    "aerich.models",
    "app.models.users",
    "app.models.admins",
    "app.models.care",
    "app.models.ocr",
    "app.models.recovery",
    "app.models.chat",
    "app.models.alarms",
    "app.models.background_jobs",
    "app.models.medications",
    "app.models.consents",
]
```

- [ ] **Step 6: Run metadata tests and model-system check**

Run: `uv run pytest app/tests/models/test_model_metadata.py -q`

Run: `uv run python -c 'from app.core.db.databases import TORTOISE_APP_MODELS; from tortoise import Tortoise; Tortoise.init_models(TORTOISE_APP_MODELS, "models"); print(len(Tortoise.apps["models"]))'`

Expected: tests PASS and output includes 20 models total: 19 domain models plus Aerich's bookkeeping model.

- [ ] **Step 7: Commit final domain models and registration**

```bash
git add app/models/medications.py app/models/consents.py app/core/db/databases.py app/tests/models/test_model_metadata.py
git commit -m "feat: complete Tortoise domain model registry"
```

---

### Task 6: Adapt the existing user API to the reduced model

**Files:**
- Modify: `app/dtos/auth.py`
- Modify: `app/dtos/users.py`
- Modify: `app/repositories/user_repository.py`
- Modify: `app/services/auth.py`
- Modify: `app/tests/auth_apis/test_signup_api.py`
- Modify: `app/tests/auth_apis/test_login_api.py`
- Modify: `app/tests/auth_apis/test_token_api.py`
- Modify: `app/tests/user_apis/test_user_me_apis.py`

**Interfaces:**
- Consumes: `User` and `AccountStatus`.
- Produces: unchanged public auth/user routes using the reduced signup/update payload.

- [ ] **Step 1: Update tests first to the approved API contract**

Remove `gender` and `birth_date` from every signup payload. Keep the existing `phone_number` API name even though the database field is `phone`, and change response assertions to the reduced approved fields:

```python
assert response.json()["email"] == email
assert response.json()["name"] == "테스터"
assert response.json()["phone_number"] == "01012345678"
```

Add a suspended-user service test asserting login raises HTTP 423 when `status == AccountStatus.SUSPENDED`.

- [ ] **Step 2: Run focused API tests and verify failures**

Run: `uv run pytest app/tests/auth_apis app/tests/user_apis -q`

Expected: FAIL from DTO requirements and legacy model-field references.

- [ ] **Step 3: Reduce DTOs**

`SignUpRequest` keeps `email`, `password`, `name`, `phone_number`; remove date and gender imports. `UserUpdateRequest` keeps optional `name`, `email`, and `phone_number`. `UserInfoResponse` becomes:

```python
class UserInfoResponse(BaseSerializerModel):
    id: int
    name: str
    email: str
    phone_number: Annotated[str | None, Field(validation_alias="phone")]
    is_alarm: bool
    status: AccountStatus
    created_at: datetime
```

- [ ] **Step 4: Adapt repository and services**

Change `create_user` to:

```python
async def create_user(
    self,
    email: str | EmailStr,
    hashed_password: str,
    name: str,
    phone: str,
    *,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
```

Set status ACTIVE for normal signup, map normalized `phone_number` to model field `phone`, query duplicate phone through `phone`, remove `update_last_login`, and implement:

```python
if user.status != AccountStatus.ACTIVE:
    raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="비활성화된 계정입니다.")
```

Before `update_instance`, translate the API field name without leaking it into the model:

```python
payload = data.model_dump(exclude_none=True)
if "phone_number" in payload:
    payload["phone"] = normalize_phone_number(payload.pop("phone_number"))
await self.repo.update_instance(user=user, data=payload)
```

Keep `login()` limited to issuing the existing JWT pair.

- [ ] **Step 5: Run focused API tests**

Run: `uv run pytest app/tests/auth_apis app/tests/user_apis -q`

Expected: PASS with MySQL test database available.

- [ ] **Step 6: Run Ruff on modified runtime files**

Run: `uv run ruff check app/dtos/auth.py app/dtos/users.py app/repositories/user_repository.py app/services/auth.py`

Expected: PASS.

- [ ] **Step 7: Commit user-flow compatibility changes**

```bash
git add app/dtos app/repositories/user_repository.py app/services/auth.py app/tests/auth_apis app/tests/user_apis
git commit -m "refactor: align user APIs with merged account schema"
```

---

### Task 7: Generate and verify the fresh Aerich initial migration

**Files:**
- Replace: `app/core/db/migrations/models/0_20260204142014_init.py`
- Test: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Consumes: complete `TORTOISE_ORM` and all registered models.
- Produces: one fresh `0_*_init.py` containing `MODELS_STATE`, upgrade SQL, and downgrade SQL.

- [ ] **Step 1: Verify the current migration is stale**

Run: `rg -n 'accounts|CREATE TABLE.*users|gender|birthday|is_admin' app/core/db/migrations/models`

Expected: current migration contains the legacy `users`, `gender`, `birthday`, and `is_admin` schema.

- [ ] **Step 2: Prepare an isolated empty MySQL schema**

Use a dedicated schema named `finalproject_schema_build`; do not drop or reuse `ai_health` or `test`. Start MySQL with `docker compose up -d mysql`, then create/drop only the isolated schema using authorized local credentials. Confirm immediately before dropping that temporary schema.

- [ ] **Step 3: Archive the stale migration outside the migration directory**

Move `0_20260204142014_init.py` to a temporary backup under `/private/tmp/finalproject-migration-backup/` before generation so recovery remains possible during the task.

- [ ] **Step 4: Generate the initial migration with Aerich**

Run Aerich with environment overrides pointing `TORTOISE_ORM` to `finalproject_schema_build`:

```bash
DB_NAME=finalproject_schema_build uv run aerich init-db
```

Expected: one new `app/core/db/migrations/models/0_*_init.py`, 19 domain tables plus `aerich`, and no `accounts` table.

- [ ] **Step 5: Add cross-field checks if Aerich omitted them**

Inspect upgrade SQL and add these MySQL checks only when missing:

```sql
CHECK (`default_end_at` IS NULL OR `default_end_at` >= `started_at`)
CHECK (`planned_end_at` IS NULL OR `planned_end_at` >= `started_at`)
CHECK (`completed_at` IS NULL OR `completed_at` >= `started_at`)
CHECK (`page_count` >= 1)
CHECK (`confidence` IS NULL OR `confidence` BETWEEN 0 AND 1)
CHECK (`source_page` IS NULL OR `source_page` >= 1)
CHECK (`times_per_day` IS NULL OR `times_per_day` BETWEEN 1 AND 6)
CHECK (`days` IS NULL OR `days` >= 1)
CHECK (`display_order` >= 1)
CHECK (`retry_count` >= 0)
```

- [ ] **Step 6: Verify migration contents and schema**

Run: `uv run aerich heads`

Run a schema inspection against `finalproject_schema_build` and assert:

```text
19 domain tables exist
accounts and users do not exist
user and admin exist
admin.created_by_admin_id references admin.id with SET NULL
all specified FK, unique, and named indexes exist
```

- [ ] **Step 7: Run model and API tests**

Run: `uv run pytest app/tests/models app/tests/auth_apis app/tests/user_apis -q`

Expected: PASS.

- [ ] **Step 8: Commit fresh migration**

```bash
git add app/core/db/migrations/models app/tests/models
git commit -m "feat: generate initial migration for full domain schema"
```

---

### Task 8: Update the online dbdiagram and perform final verification

**Files:**
- Modify externally: `https://dbdiagram.io/d/FinalProject-6a79bddbe093539a9e8459eb`
- No local source files unless verification finds a mismatch.

**Interfaces:**
- Consumes: approved spec and implemented model metadata.
- Produces: online DBML matching the 19 Tortoise domain tables.

- [ ] **Step 1: Build the exact DBML account replacement**

Replace the account section with `account_status`, `admin_role`, `user`, and `admin`. Remove `account_type`, `accounts`, `account_id`, and account FKs. Add:

```dbml
Ref: admin.created_by_admin_id > admin.id [delete: set null]
```

Keep every other table and reference unchanged.

- [ ] **Step 2: Validate DBML locally before editing online**

Check that the text contains 19 `Table` declarations, no `Table accounts`, no `Enum account_type`, and all user ownership refs point to `user.id`.

- [ ] **Step 3: Request action-time confirmation and save the online edit**

Immediately before replacing/saving the dbdiagram editor content, tell the user exactly which shared diagram will be changed and request confirmation. After confirmation, replace the editor DBML and save once.

- [ ] **Step 4: Re-read the saved diagram**

Confirm the online editor contains the merged `user`/`admin` definitions, 19 tables, the admin self-FK, and no account artifacts.

- [ ] **Step 5: Run complete project verification**

```bash
uv run pytest -q
uv run ruff check app tests
uv run mypy app
node --test app/tests/static_ui/*.test.mjs
git status --short
```

Expected: all checks pass; only task files and the pre-existing `.DS_Store` change appear in status.

- [ ] **Step 6: Commit any verification-only corrections**

If verification required corrections, review `git diff --name-only` and stage only this task's permitted paths:

```bash
git add app/models app/core/db/databases.py app/core/db/migrations/models \
  app/dtos/auth.py app/dtos/users.py app/repositories/user_repository.py \
  app/services/auth.py app/services/users.py app/tests
git commit -m "fix: align domain schema verification"
```

Do not stage `.DS_Store`.
