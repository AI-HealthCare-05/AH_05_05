# DBDiagram v4 Schema Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최신 dbdiagram v4 스키마를 Tortoise ORM 모델과 Docker MySQL에 기존 데이터 손실 없이 반영한다.

**Architecture:** 모델 메타데이터 테스트를 먼저 실패시킨 뒤 enum/모델을 동기화한다. 적용된 Aerich head 다음 번호로 단일 마이그레이션을 생성하고, 자동 생성 SQL에 안전한 백필·FK 정책·CHECK 변경을 보완하여 실제 MySQL에 적용한다.

**Tech Stack:** Python 3.13, FastAPI, Tortoise ORM, Aerich, MySQL 8, pytest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-08-21-dbdiagram-v4-schema-sync-design.md`

## Global Constraints

- 프로젝트 루트는 `/Users/admin/PycharmProjects/FinalProject`이다.
- 기존 데이터와 기존 사용자의 변경사항을 보존한다.
- DB를 재생성하지 않고 Aerich upgrade로 반영한다.
- 신규 CRUD/API 업무 로직은 추가하지 않는다.
- Git 커밋을 생성하지 않는다.

---

### Task 1: Model metadata regression tests

**Files:**
- Modify: `tests/models/test_model_metadata.py`

**Interfaces:**
- Consumes: 현재 Tortoise 모델 메타데이터
- Produces: v4 스키마 차이를 검증하는 실패 테스트

- [ ] **Step 1: Add enum and model metadata assertions**

다음을 개별 테스트로 추가한다.

```python
def test_user_notification_v4_metadata() -> None:
    assert enums.NotifySettingKey.IS_NOTIFY_MEDICATION == "IS_NOTIFY_MEDICATION"
    assert users.UserSettings._meta.fields_map["terms_agreed_at"].null is True
    assert users.UserSettings._meta.fields_map["notify_consented_at"].null is True
    history = users.UserNotifyHistory
    assert history._meta.db_table == "user_notify_histories"
    assert history._meta.fields_map["user"].on_delete == fields.CASCADE


def test_care_v4_metadata() -> None:
    assert care.CareAdvice._meta.fields_map["category"].null is False
    assert care.FollowUpVisit._meta.fields_map["visit_date"].null is False
    assert care.FollowUpVisit._meta.fields_map["visit_time"].null is True
    assert care.FollowUpVisit._meta.fields_map["source_ocr_job"].on_delete == fields.SET_NULL
    assert "visit_at" not in care.FollowUpVisit._meta.fields_map


def test_chat_and_source_retention_v4_metadata() -> None:
    assert chat.ChatSession._meta.fields_map["user"].null is False
    assert chat.ChatSession._meta.fields_map["care_episode"].null is True
    for model in (chat.ChatMessageSource, recovery.RecoveryGuideSource):
        for name in ("medication", "care_advice", "follow_up_visit"):
            assert model._meta.fields_map[name].on_delete == fields.RESTRICT
```

Medication assertions에는 세 상세 컬럼, `note.max_length == 500`, `days`의 최대 365 validator를 포함한다.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run python -m pytest tests/models/test_model_metadata.py -q
```

Expected: 새 enum/필드/모델이 없거나 기존 delete policy가 CASCADE여서 실패한다.

---

### Task 2: Enums and user notification models

**Files:**
- Modify: `app/models/enums.py`
- Modify: `app/models/users.py`
- Modify: `app/models/__init__.py`

**Interfaces:**
- Produces: `CareAdviceCategory`, `NotifySettingKey`, `UserNotifyHistory`

- [ ] **Step 1: Add enums**

```python
class CareAdviceCategory(StrEnum):
    ACTIVITY = "ACTIVITY"
    HYGIENE = "HYGIENE"
    DIET = "DIET"
    LIFESTYLE = "LIFESTYLE"
    RESTRICTION = "RESTRICTION"
    RED_FLAG = "RED_FLAG"
    OTHER = "OTHER"


class NotifySettingKey(StrEnum):
    IS_NOTIFY_MEDICATION = "IS_NOTIFY_MEDICATION"
    IS_NOTIFY_SCHEDULE = "IS_NOTIFY_SCHEDULE"
    IS_NOTIFY_GUIDE = "IS_NOTIFY_GUIDE"
```

- [ ] **Step 2: Extend UserSettings and create history model**

```python
terms_agreed_at = fields.DatetimeField(null=True)
notify_consented_at = fields.DatetimeField(null=True)
```

`UserNotifyHistory`는 BigInt PK, user CASCADE FK, `NotifySettingKey` CharEnum, boolean `new_value`, auto-add `created_at`을 가지며 ERD의 두 인덱스를 선언한다. `app/models/__init__.py`에서 공개한다.

- [ ] **Step 3: Run focused tests**

```bash
uv run python -m pytest tests/models/test_model_metadata.py -q
```

Expected: 사용자 모델 관련 실패가 해소되고 나머지 v4 테스트만 실패한다.

---

### Task 3: Care, medication, chat, and source models

**Files:**
- Modify: `app/models/care.py`
- Modify: `app/models/medications.py`
- Modify: `app/models/chat.py`
- Modify: `app/models/recovery.py`
- Modify: `app/models/__init__.py`

**Interfaces:**
- Consumes: Task 2의 enums
- Produces: ERD v4와 일치하는 도메인 모델

- [ ] **Step 1: Update CareAdvice and FollowUpVisit**

`CareAdvice.category`를 필수 `CareAdviceCategory` CharEnum으로 추가하고 `(care_episode, category)` 인덱스를 추가한다.

`FollowUpVisit`은 다음 형태로 변경한다.

```python
source_ocr_job = fields.ForeignKeyField(
    "models.OcrJob", related_name="follow_up_visits", null=True, on_delete=fields.SET_NULL
)
visit_date = fields.DateField()
visit_time = fields.TimeField(null=True)
department = fields.CharField(max_length=255, null=True)
doctor_name = fields.CharField(max_length=255, null=True)
```

`visit_at`을 제거하고 `(visit_date, visit_time, id)` 인덱스를 선언한다.

- [ ] **Step 2: Update Medication**

`efficacy`, `administration`, `precautions`를 nullable varchar(500)으로 추가한다. `note`를 500자로 확장하고 `days`에 MinValueValidator(1), MaxValueValidator(365)를 사용한다.

- [ ] **Step 3: Update ChatSession**

```python
user = fields.ForeignKeyField("models.User", related_name="chat_sessions", on_delete=fields.CASCADE)
care_episode = fields.ForeignKeyField(
    "models.CareEpisode", related_name="chat_sessions", null=True, on_delete=fields.CASCADE
)
```

- [ ] **Step 4: Strengthen source retention**

`ChatMessageSource`와 `RecoveryGuideSource`의 medication/care_advice/follow_up_visit 관계를 모두 `fields.RESTRICT`로 변경한다.

- [ ] **Step 5: Run metadata tests and verify GREEN**

```bash
uv run python -m pytest tests/models/test_model_metadata.py -q
```

Expected: 전체 통과.

---

### Task 4: Adapt follow-up visit test fixtures

**Files:**
- Modify: `app/tests/alarm_apis/test_alarm_crud_api.py`

**Interfaces:**
- Consumes: `FollowUpVisit.visit_date`, `visit_time`
- Produces: 변경 후 모델 계약으로 실행되는 알람 회귀 테스트

- [ ] **Step 1: Replace visit_at fixture construction**

```python
first_visit = await FollowUpVisit.create(
    care_episode=care_episode,
    visit_date=date(2026, 8, 25),
    visit_time=time(10, 0),
)
second_visit = await FollowUpVisit.create(
    care_episode=care_episode,
    visit_date=first_visit.visit_date + timedelta(days=7),
    visit_time=first_visit.visit_time,
)
```

나머지 다른 사용자/케어 불일치 fixture도 같은 계약으로 변경한다.

- [ ] **Step 2: Run alarm tests**

```bash
docker compose exec -T fastapi uv run --no-sync pytest app/tests/alarm_apis/test_alarm_crud_api.py -q
```

Expected: 전체 통과.

---

### Task 5: Create and harden the Aerich migration

**Files:**
- Create: `app/core/db/migrations/models/4_<timestamp>_sync_dbdiagram_v4.py`

**Interfaces:**
- Consumes: 적용된 head `3_20260821043505_add_alarm_follow_up_visit.py`
- Produces: 재실행 가능한 단일 v4 upgrade/downgrade

- [ ] **Step 1: Generate migration**

```bash
docker compose exec -T fastapi uv run --no-sync aerich migrate --name sync_dbdiagram_v4
```

Expected: 버전 4 migration 한 개 생성.

- [ ] **Step 2: Harden upgrade SQL**

자동 SQL을 다음 순서로 보완한다.

1. user settings 두 datetime 추가 및 history table 생성.
2. chat session user nullable 추가 → care episode join 백필 → NOT NULL/FK → care episode nullable.
3. care advice category nullable 추가 → `OTHER` 백필 → NOT NULL.
4. medication 상세 컬럼/note 길이 추가 및 `chk_medications_days`를 BETWEEN 1 AND 365로 교체.
5. follow-up의 date/time/source columns 추가 → `visit_at` 백필 → date NOT NULL → 기존 visit_at/index 제거 → 새 FK/index 추가.
6. 두 source table의 여섯 FK를 삭제하고 ON DELETE RESTRICT로 재생성.

- [ ] **Step 3: Harden downgrade SQL**

FK와 인덱스를 역순으로 복원하고 `visit_at`은 `TIMESTAMP(visit_date, COALESCE(visit_time, '00:00:00'))`로 재구성한다. 신규 테이블/컬럼을 제거하고 source FK를 CASCADE로 되돌린다. `chat_sessions.care_episode_id IS NULL` 데이터가 존재하면 손실 없이 다운그레이드할 수 없으므로 NOT NULL 변경에서 명시적으로 실패하도록 둔다.

- [ ] **Step 4: Review SQL without applying**

마이그레이션 파일에서 컬럼/제약 이름 중복, SQL 순서, upgrade/downgrade 대칭성을 검토한다.

---

### Task 6: Apply to Docker MySQL and verify data

**Files:** No source changes.

**Interfaces:**
- Consumes: Task 5 migration
- Produces: v4 Docker MySQL schema

- [ ] **Step 1: Capture pre-upgrade evidence**

`follow_up_visits.id=1`, Aerich version, 영향 테이블 row counts를 다시 조회한다.

- [ ] **Step 2: Apply upgrade**

```bash
docker compose exec -T fastapi uv run --no-sync aerich upgrade
```

Expected: v4 migration 성공.

- [ ] **Step 3: Verify information_schema**

다음을 확인한다.

- user settings의 두 datetime 및 `user_notify_histories`
- chat session user NOT NULL, care episode nullable
- care advice category NOT NULL
- medication 신규 필드/길이/CHECK
- follow-up date/time/source FK/복합 인덱스와 기존 visit_at 제거
- source FK 여섯 개의 DELETE_RULE=RESTRICT
- Aerich version 4 기록

- [ ] **Step 4: Verify preserved test data**

`follow_up_visits.id=1`이 `visit_date=2026-08-28`, `visit_time=10:00:00`, care_episode 1과 기존 텍스트 값을 보존하는지 확인한다.

---

### Task 7: Final regression verification

**Files:** No source changes unless a verification failure identifies an in-scope defect.

**Interfaces:**
- Produces: 완료 주장에 필요한 최신 검증 증거

- [ ] **Step 1: Run model tests**

```bash
uv run python -m pytest tests/models/test_model_metadata.py -q
```

- [ ] **Step 2: Run affected container tests**

```bash
docker compose exec -T fastapi uv run --no-sync pytest app/tests/alarm_apis app/tests/workers app/tests/services -q
```

- [ ] **Step 3: Run Ruff**

```bash
uv run ruff check app/models tests/models/test_model_metadata.py app/tests/alarm_apis/test_alarm_crud_api.py app/core/db/migrations/models
```

- [ ] **Step 4: Verify runtime services**

`docker compose ps`와 최근 `alarm-worker` 로그에서 Redis 연결과 polling cron 성공을 확인한다.

- [ ] **Step 5: Review working tree**

요청 범위 파일만 변경됐는지 확인하고 Git commit을 생성하지 않는다.
