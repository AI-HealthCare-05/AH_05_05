# Follow-up Visit User Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `follow_up_visits.care_episode_id` ownership with `user_id`, remove unused location/detail columns, add nullable `hospital` across the model, database, APIs, and ERD, and expose authenticated CRUD APIs for user-owned visits.

**Architecture:** `FollowUpVisit` becomes a user-owned schedule record independent of a care episode. Existing rows derive `user_id` through `care_episodes.user_id` during migration; alarm authorization reads the direct user FK. OCR confirmation may still create a dated visit, but it stores only the authenticated user and leaves `hospital` nullable when the source has no hospital value.

**Tech Stack:** Python 3.13, FastAPI, Tortoise ORM, Aerich, MySQL 8, dbdiagram DBML, pytest.

**Spec:** User request dated 2026-09-01 in the active Codex task.

## Global Constraints

- Delete `doctor_name`, `care_episode_id`, `place`, and `purpose` from `follow_up_visits`.
- Add required `user_id` referencing `user.id` and nullable `hospital varchar(255)`.
- Preserve existing rows by backfilling `user_id` from `care_episodes` before dropping `care_episode_id`.
- Do not change `CareEpisode`, `Medication`, or their `source_ocr_job_id` fields.
- Do not create a Git commit.

---

### Task 1: Model contract and ownership behavior

**Files:**
- Modify: `tests/models/test_model_metadata.py`
- Modify: `app/models/care.py`
- Modify: `app/repositories/alarm_repository.py`
- Modify: `app/services/alarms.py`
- Test: `app/tests/alarm_apis/test_alarm_crud_api.py`

**Interfaces:**
- Produces: `FollowUpVisit.user` as a required `models.User` FK with `CASCADE` deletion.
- Produces: `AlarmRepository.get_owned_follow_up_visit(visit_id, user_id)` using direct `user_id` ownership.

- [ ] **Step 1: Write failing metadata and alarm ownership tests**

```python
assert care.FollowUpVisit._meta.fields_map["user"].model_name == "models.User"
assert "care_episode" not in care.FollowUpVisit._meta.fields_map
assert care.FollowUpVisit._meta.fields_map["hospital"].max_length == 255
```

- [ ] **Step 2: Run tests and confirm the old care-episode model fails them**

Run: `uv run pytest tests/models/test_model_metadata.py::test_care_v4_metadata app/tests/alarm_apis/test_alarm_crud_api.py -q`

- [ ] **Step 3: Replace model fields and direct ownership query**

```python
user = fields.ForeignKeyField("models.User", related_name="follow_up_visits", on_delete=fields.CASCADE)
hospital = fields.CharField(max_length=255, null=True)
```

- [ ] **Step 4: Remove the obsolete care-episode mismatch validation and rerun tests separately**

Run: `uv run pytest tests/models/test_model_metadata.py::test_care_v4_metadata -q`

Run: `uv run pytest app/tests/alarm_apis/test_alarm_crud_api.py -q`

### Task 2: OCR visit creation

**Files:**
- Modify: `app/services/medication_guide_ocr_jobs.py`
- Modify: `app/tests/ocr_apis/test_medication_guide_ocr_job_service.py`

**Interfaces:**
- Consumes: required `FollowUpVisit.user_id`.
- Produces: confirmed OCR visits owned directly by the authenticated user.

- [ ] **Step 1: Change the OCR confirmation assertion to verify `visit.user_id`**

```python
assert visit.user_id == user.id
```

- [ ] **Step 2: Run the test and confirm it fails against the old creation arguments**

Run: `uv run pytest app/tests/ocr_apis/test_medication_guide_ocr_job_service.py -q`

- [ ] **Step 3: Create the visit with `user_id=user.id` and remove `care_episode_id` and `purpose`**

```python
await FollowUpVisit.create(user_id=user.id, visit_date=request.next_visit_date, using_db=connection)
```

- [ ] **Step 4: Rerun the OCR service tests**

Run: `uv run pytest app/tests/ocr_apis/test_medication_guide_ocr_job_service.py -q`

### Task 3: Aerich migration and Docker MySQL

**Files:**
- Create: `app/core/db/migrations/models/19_*_follow_up_visit_user_ownership.py`

**Interfaces:**
- Consumes: current model state from migration 18.
- Produces: required `user_id`, nullable `hospital`, and removal of four legacy columns.

- [ ] **Step 1: Generate migration 19 from the latest offline model state**

Run: `uv run aerich migrate --name follow_up_visit_user_ownership --offline`

- [ ] **Step 2: Stage `user_id` as nullable, backfill through `care_episodes`, then enforce NOT NULL**

```sql
ALTER TABLE follow_up_visits ADD user_id BIGINT NULL;
UPDATE follow_up_visits f JOIN care_episodes c ON c.id=f.care_episode_id SET f.user_id=c.user_id;
ALTER TABLE follow_up_visits MODIFY user_id BIGINT NOT NULL;
```

- [ ] **Step 3: Apply only migration 19 and record its Aerich model state**

Run the selected-migration helper used for migration 18 so unrelated pending migrations remain untouched.

- [ ] **Step 4: Verify columns, FK, row preservation, and Aerich version in Docker MySQL**

```sql
SHOW COLUMNS FROM follow_up_visits;
SELECT id,user_id,hospital FROM follow_up_visits;
```

### Task 4: DBML and dbdiagram synchronization

**Files:**
- Modify: `docs/poke-erd-v1.1.4-full-ai-chat-safety.dbml`

**Interfaces:**
- Produces: local and cloud DBML with the same `follow_up_visits` definition.

- [ ] **Step 1: Replace columns, index, relationship, and obsolete notes in local DBML**

```dbml
user_id bigint [not null]
hospital varchar(255)
Ref: follow_up_visits.user_id > user.id [delete: cascade]
```

- [ ] **Step 2: Remove the dangling quoted `source_ocr_job_id` relation**

```dbml
Ref: "follow_up_visits"."id" ?<? "follow_up_visits"."source_ocr_job_id"
```

- [ ] **Step 3: Prepare the cloud editor change and obtain action-time confirmation before deleting cloud schema fields**

- [ ] **Step 4: Save and verify the cloud editor has no deleted fields or dangling relation**

### Task 5: Follow-up visit CRUD API

**Files:**
- Create: `app/dtos/follow_up_visits.py`
- Create: `app/repositories/follow_up_visit_repository.py`
- Create: `app/services/follow_up_visits.py`
- Create: `app/apis/v1/follow_up_visit_router.py`
- Create: `app/tests/follow_up_visit_apis/test_follow_up_visit_crud_api.py`
- Modify: `app/apis/v1/__init__.py`

**Interfaces:**
- Produces: authenticated CRUD under `/api/v1/user/follow-up-visits`.
- Enforces: every query is scoped to the authenticated user's `user_id`.

- [x] **Step 1: Write CRUD, authentication, ownership, filter, and pagination API tests**

- [x] **Step 2: Implement DTO, repository, service, and router layers**

- [x] **Step 3: Register the router and verify all CRUD API tests**

### Task 6: Final verification

**Files:**
- Verify all files changed in Tasks 1-5.

- [ ] **Step 1: Run isolated model, alarm API, and OCR service tests**

Run each test file in a separate pytest process to avoid Tortoise registry contamination.

- [ ] **Step 2: Run Ruff formatting, lint, and `git diff --check`**

- [ ] **Step 3: Verify Docker MySQL and dbdiagram schema match the requested fields**
