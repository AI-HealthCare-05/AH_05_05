# DBDiagram Schema Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최신 온라인 ERD의 18개 테이블과 승인된 `user_settings.user_id` unique index를 소스, Aerich, 로컬 MySQL에 반영한다.

**Architecture:** 기존 초기 마이그레이션은 보존하고 후속 마이그레이션을 추가한다. Tortoise 모델이 표현하는 필드·관계·인덱스를 먼저 테스트하고, 복합 FK와 체크 제약은 생성된 Aerich SQL을 보완해 적용한다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Tortoise ORM, Aerich, MySQL, pytest

**Spec:** `docs/superpowers/specs/2026-08-18-dbdiagram-schema-sync-design.md`

## Global Constraints

- 작업 루트는 `/Users/admin/PycharmProjects/FinalProject`이다.
- 온라인 ERD의 최신 18개 테이블이 기준이다.
- `user_settings.user_id`는 unique index로 사용자당 한 행만 허용한다.
- 기존 초기 Aerich migration은 수정하지 않는다.
- 사용자의 기존 `.DS_Store`, `app/models/__init__.py`, 미추적 계획 문서를 보존한다.
- Git 커밋은 생성하지 않는다.

---

### Task 1: 최신 모델 계약 테스트

**Files:**
- Modify: `tests/models/test_model_metadata.py`
- Modify: `tests/test_user_contract.py`

**Interfaces:**
- Consumes: 현재 Tortoise 모델 메타데이터와 사용자 DTO
- Produces: 최신 enum, 18개 테이블, user settings, OCR, 출처 관계에 대한 실패 테스트

- [ ] **Step 1: 구형 모델 부재와 신규 모델 메타데이터 assertion 작성**

```python
assert not hasattr(ocr, "OcrExtractedField")
assert not hasattr(medications, "MedicationTime")
assert users.UserSettings._meta.db_table == "user_settings"
assert users.UserSettings._meta.unique_together == (("user",),)
assert medications.MedicationSlot._meta.unique_together == (("medication", "slot"),)
```

- [ ] **Step 2: 신규 enum, OCR JSON, 케어 확정 필드, 출처 FK assertion 작성**

```python
assert enums.MealSlot.BEDTIME.value == "BEDTIME"
assert enums.AlarmType.GUIDE_CHECK.value == "GUIDE_CHECK"
assert enums.PatientSourceKind.MEDICATION.value == "MEDICATION"
assert enums.CareEpisodeSourceField.DIAGNOSIS.value == "DIAGNOSIS"
assert ocr.OcrJob._meta.fields_map["input_manifest"].null is False
assert "confirmation_hash" in care.CareEpisode._meta.fields_map
assert "medication" in recovery.RecoveryGuideSource._meta.fields_map
assert "care_advice" in chat.ChatMessageSource._meta.fields_map
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/models/test_model_metadata.py tests/test_user_contract.py -q`

Expected: 구형 모델과 필드 때문에 FAIL

### Task 2: enum, 사용자 설정, 케어·OCR 모델 구현

**Files:**
- Modify: `app/models/enums.py`
- Modify: `app/models/users.py`
- Modify: `app/models/care.py`
- Modify: `app/models/ocr.py`
- Modify: `app/dtos/users.py`
- Modify: `app/repositories/user_repository.py`

**Interfaces:**
- Produces: `MealSlot`, `PatientSourceKind`, `CareEpisodeSourceField`, `UserSettings`, 재설계된 `OcrJob`, 확정 필드를 가진 `CareEpisode`

- [ ] **Step 1: 최신 enum 추가 및 제거**

`MealSlot`, `PatientSourceKind`, `CareEpisodeSourceField`, `GUIDE_CHECK`를 추가하고 `OcrDocumentType`, `OcrMaskingStatus`, `OcrReviewStatus`, `ConsentType`을 제거한다.

- [ ] **Step 2: User에서 is_alarm을 제거하고 UserSettings 구현**

```python
class UserSettings(models.Model):
    user = fields.OneToOneField("models.User", related_name="settings", on_delete=fields.CASCADE)
    is_notify_medication = fields.BooleanField(default=True)
    is_notify_schedule = fields.BooleanField(default=True)
    is_notify_guide = fields.BooleanField(default=True)
    is_terms_agreed = fields.BooleanField(default=False)
    morning_medication_time = fields.TimeField(default=time(8, 0))
    lunch_medication_time = fields.TimeField(default=time(13, 0))
    evening_medication_time = fields.TimeField(default=time(19, 0))
    bedtime_medication_time = fields.TimeField(default=time(22, 0))
```

- [ ] **Step 3: CareEpisode 확정 필드와 OcrJob 최신 필드 구현**

CareEpisode에 `diagnosis`, `surgery`, `discharge_date`, `medication_days`, `source_ocr_job_id`, `confirmation_hash`, `confirmed_at`, 복약 시작 필드를 추가한다. OcrJob은 `input_manifest`, `structured_result`, 모델·prompt·schema 버전과 상태 시각을 구현하고 OcrExtractedField를 제거한다.

- [ ] **Step 4: 사용자 계약에서 is_alarm 제거**

`UserInfoResponse`와 repository 갱신 허용 목록에서 `is_alarm`을 제거한다. 설정은 별도 모델 계약으로 유지한다.

- [ ] **Step 5: 대상 테스트 실행**

Run: `uv run pytest tests/models/test_model_metadata.py tests/test_user_contract.py -q`

Expected: 구현된 영역 PASS, 아직 미구현 출처·알람 영역 FAIL

### Task 3: 출처·알람·백그라운드·복약 모델 구현

**Files:**
- Modify: `app/models/recovery.py`
- Modify: `app/models/chat.py`
- Modify: `app/models/alarms.py`
- Modify: `app/models/background_jobs.py`
- Modify: `app/models/medications.py`
- Modify: `app/models/care.py`
- Modify: `app/models/consents.py`
- Modify: `app/core/db/databases.py`

**Interfaces:**
- Consumes: Task 2의 enum과 케어 모델
- Produces: 환자 확정 데이터 출처 관계, meal slot 알람, idempotent background job, medication slot

- [ ] **Step 1: RecoveryGuideSource와 ChatMessageSource 재설계**

`extracted_field`를 제거하고 nullable `patient_source_kind`, `patient_field`, `medication`, `care_advice`, `follow_up_visit` 관계를 추가한다. 온라인 ERD의 public source 필드와 unique citation order는 유지한다.

- [ ] **Step 2: 구형 source_extracted_field 제거**

Medication, CareAdvice, FollowUpVisit에서 `source_extracted_field` 관계를 제거한다.

- [ ] **Step 3: 알람·백그라운드·복약 슬롯 구현**

Alarm에 nullable `meal_slot`과 `(user, alarm_type, meal_slot)` unique constraint를 추가한다. BackgroundJob에 unique `idempotency_key`를 추가한다. MedicationTime을 제거하고 MedicationSlot을 추가한다.

- [ ] **Step 4: UserConsent 모델 등록 제거**

`app.models.consents`를 Tortoise registry에서 제거한다. 사용자 소유 `app/models/__init__.py`는 수정하지 않는다.

- [ ] **Step 5: 모델 테스트 통과 확인**

Run: `uv run pytest tests/models/test_model_metadata.py -q`

Expected: PASS

### Task 4: 전체 소스 검증

**Files:**
- Modify: 필요한 기존 테스트 파일만

**Interfaces:**
- Consumes: Tasks 1-3의 최종 모델 계약
- Produces: 마이그레이션 생성 가능한 일관된 Tortoise registry

- [ ] **Step 1: 구형 이름 잔존 검사**

Run: `rg -n "is_alarm|OcrExtractedField|MedicationTime|UserConsent|source_extracted_field|user_meal_times|medication_times|user_consents" app tests`

Expected: 초기 migration 이외의 실행 소스에는 결과 없음

- [ ] **Step 2: 전체 테스트 실행**

Run: `uv run pytest -q`

Expected: PASS

### Task 5: Aerich migration 및 DB 반영

**Files:**
- Create: `app/core/db/migrations/models/1_*_sync_latest_dbdiagram.py`

**Interfaces:**
- Consumes: 최종 Tortoise model metadata
- Produces: 최신 18개 테이블 구조가 적용된 로컬 `ai_health`

- [ ] **Step 1: 후속 migration 생성**

Run: `uv run aerich migrate --name sync_latest_dbdiagram`

Expected: version 1 migration 파일 생성

- [ ] **Step 2: 생성 SQL 보완**

의존 FK를 먼저 제거한 뒤 `ocr_extracted_fields`, `medication_times`, `user_consents`를 삭제한다. `user_settings`, `medication_slots`를 생성하고 `user_settings.user_id` unique index를 적용한다. 온라인 ERD의 alarm slot, OCR 상태, confirmation, patient/public source 체크 제약과 care episode/OCR 복합 FK를 추가한다.

- [ ] **Step 3: DB upgrade**

Run: `uv run aerich upgrade`

Expected: migration 적용 성공

- [ ] **Step 4: information_schema 검증**

18개 업무 테이블, 변경 컬럼, unique/index/FK/check constraint를 조회한다. 제거된 네 테이블이 없고 `user_settings.user_id`가 unique인지 확인한다.

- [ ] **Step 5: 최종 검증**

Run: `uv run pytest -q`

Run: `uv run aerich heads`

Expected: 전체 테스트 PASS, version 1이 head
