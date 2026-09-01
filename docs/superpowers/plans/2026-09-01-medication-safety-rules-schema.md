# Medication Safety Rules Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 선택지 C의 단일 약물 안전 규칙 테이블을 최신 v1.1.3 ERD, Tortoise ORM, MySQL에 반영하고 기존 데이터 보존을 검증한다.

**Architecture:** 기존 `interaction_rules`는 두 대상 조합 규칙으로 유지한다. 단일 약물 규칙은 `medication_safety_rules`, 조건은 `medication_safety_rule_conditions`, 원문 출처는 `medication_safety_rule_sources`로 분리하며, 답변 출처는 `chat_message_sources.medication_safety_rule_id`로 추적한다.

**Tech Stack:** Python 3.13, Tortoise ORM 0.25+, Aerich 0.9+, MySQL 8.0, pytest, Ruff, DBML

**Spec:** `docs/superpowers/specs/2026-09-01-medication-safety-rules-schema-design.md`

## Global Constraints

- 첨부된 v1.1.3 전체 ERD에서 AI 영역만 수정하고 팀원 테이블은 보존한다.
- 기존 v1.0.6 DBML은 제거하고 최신 v1.1.3 DBML 하나만 남긴다.
- 기존 `interaction_rules`의 컬럼·의미·데이터를 변경하지 않는다.
- 신규 FK는 nullable로 추가하여 기존 `chat_message_sources` 행을 변환하지 않는다.
- `PENDING` 또는 `REJECTED` 규칙은 런타임에서 사용할 수 없다.
- 환자 조건이 없을 때 안전으로 간주하지 않는다.
- Aerich SQL에 예상하지 않은 기존 컬럼·테이블 DROP이 있으면 upgrade하지 않는다.
- 기존 `interaction_rules`, `chat_messages`, `chat_message_sources` 건수는 upgrade 전후 같아야 한다.
- 실제 데이터 적재와 Repository 연결은 이 계획 범위에 포함하지 않는다.

---

## File Structure

### Create

- `docs/poke-erd-v1.1.4-full-ai-chat-safety.dbml`: 첨부 v1.1.3 전체 ERD와 선택지 C를 합친 최신 ERD
- `app/tests/models/test_medication_safety_models.py`: enum·ORM·관계·제약 계약 테스트
- `app/core/db/migrations/models/<next>_add_medication_safety_rules.py`: Aerich 생성 후 안전 체크 제약을 보완한 마이그레이션

### Modify

- `app/models/enums.py`: 안전 규칙 enum 3종과 채팅 출처 enum 값 추가
- `app/models/interactions.py`: 안전 규칙 모델 3종 추가
- `app/models/chat.py`: 답변 출처의 안전 규칙 nullable FK 추가
- `ai_worker/core/config.py`: 활성 안전 규칙 데이터셋 버전 설정 추가
- `ai_worker/tests/core/test_core_package.py`: 설정 기본값·환경변수 테스트
- `.env.example`: 팀 공용 설정 예시 추가
- `docs/ai-worker-database-table-column-guide.md`: 실제 구현 완료 상태와 마이그레이션 결과 반영

### Delete

- `docs/poke-erd-v1.0.6-full-ai-chat-interaction.dbml`: 사용자가 별도로 보관 중인 이전 ERD

---

### Task 1: 최신 v1.1.3 ERD에 선택지 C 반영

**Files:**
- Create: `docs/poke-erd-v1.1.4-full-ai-chat-safety.dbml`
- Delete: `docs/poke-erd-v1.0.6-full-ai-chat-interaction.dbml`
- Reference: `/Users/admin/.codex/attachments/43d19112-bcb9-4c7a-8be6-a4d9b16c699a/pasted-text.txt`

**Interfaces:**
- Consumes: 사용자가 제공한 v1.1.3 전체 DBML
- Produces: ORM과 마이그레이션이 따라야 할 안전 규칙 DB 계약

- [ ] **Step 1: 첨부 v1.1.3을 새 DBML 파일의 기준 내용으로 복사**

팀원 테이블과 Ref를 그대로 유지한다.

- [ ] **Step 2: 안전 규칙 enum 추가**

```dbml
Enum medication_safety_rule_type {
  PREGNANCY_CONTRAINDICATION
  AGE_CONTRAINDICATION
  ELDERLY_CAUTION
  DOSE_CAUTION
  DURATION_CAUTION
  DAILY_MAX_DOSE
  EXCIPIENT_CAUTION
}

Enum safety_condition_kind {
  PREGNANCY_STATUS
  AGE_DAYS
  AGE_YEARS
  DAILY_DOSE
  DURATION_DAYS
  DOSAGE_FORM
  ADMINISTRATION_ROUTE
  EXCIPIENT_PRESENT
}

Enum safety_comparison_operator {
  EQ
  LT
  LTE
  GT
  GTE
  BETWEEN
  PRESENT
}
```

`chat_source_type`에 `MEDICATION_SAFETY_RULE`을 추가한다.

- [ ] **Step 3: 안전 규칙 테이블 3개와 Ref 추가**

설계 문서 5장의 컬럼·인덱스·체크를 그대로 DBML로 표현한다. FK는 다음과 같다.

```dbml
Ref: medication_safety_rules.interaction_entity_id > interaction_entities.id [delete: restrict]
Ref: medication_safety_rule_conditions.medication_safety_rule_id > medication_safety_rules.id [delete: cascade]
Ref: medication_safety_rule_sources.medication_safety_rule_id > medication_safety_rules.id [delete: cascade]
```

- [ ] **Step 4: 채팅 출처 컬럼·체크·Ref 확장**

```dbml
medication_safety_rule_id bigint [note: 'MEDICATION_SAFETY_RULE 출처인 경우 승인된 단일 약물 안전 규칙 ID']

Ref: medication_safety_rules.id < chat_message_sources.medication_safety_rule_id [delete: restrict]
```

`chat_message_sources` 배타 체크에 새 출처 유형을 추가하고 다른 출처 유형에서는 해당 FK가 NULL이 되도록 명시한다.

- [ ] **Step 5: 이전 DBML 제거 및 정적 검증**

Run:

```bash
rg -n "medication_safety|MEDICATION_SAFETY_RULE" docs/poke-erd-v1.1.4-full-ai-chat-safety.dbml
git diff --check -- docs/poke-erd-v1.1.4-full-ai-chat-safety.dbml
```

Expected: enum 3종, 테이블 3개, 채팅 FK와 Ref가 검색되고 공백 오류가 없다.

- [ ] **Step 6: Commit**

```bash
git add docs/poke-erd-v1.1.4-full-ai-chat-safety.dbml \
  docs/poke-erd-v1.0.6-full-ai-chat-interaction.dbml
git commit -m "[feature/162][임경수] 단일 약물 안전 규칙 ERD 반영"
```

---

### Task 2: 실패하는 enum·설정 계약 테스트 작성

**Files:**
- Create: `app/tests/models/test_medication_safety_models.py`
- Modify: `ai_worker/tests/core/test_core_package.py`

**Interfaces:**
- Consumes: 설계 문서의 enum 이름과 기본 데이터셋 버전
- Produces: ORM 구현 전 실패하는 계약 테스트

- [ ] **Step 1: enum 테스트 작성**

```python
from app.models.enums import (
    ChatSourceType,
    MedicationSafetyRuleType,
    SafetyComparisonOperator,
    SafetyConditionKind,
)


def test_medication_safety_enums_define_supported_rules() -> None:
    assert {item.value for item in MedicationSafetyRuleType} == {
        "PREGNANCY_CONTRAINDICATION",
        "AGE_CONTRAINDICATION",
        "ELDERLY_CAUTION",
        "DOSE_CAUTION",
        "DURATION_CAUTION",
        "DAILY_MAX_DOSE",
        "EXCIPIENT_CAUTION",
    }
    assert SafetyConditionKind.DAILY_DOSE.value == "DAILY_DOSE"
    assert SafetyComparisonOperator.BETWEEN.value == "BETWEEN"
    assert ChatSourceType.MEDICATION_SAFETY_RULE.value == (
        "MEDICATION_SAFETY_RULE"
    )
```

- [ ] **Step 2: 설정 테스트 확장**

기본값 테스트에 다음을 추가한다.

```python
assert settings.MEDICATION_SAFETY_RULE_DATASET_VERSION == (
    "medication-safety-v1"
)
```

환경변수 테스트에는 다음을 추가한다.

```python
monkeypatch.setenv(
    "MEDICATION_SAFETY_RULE_DATASET_VERSION",
    "medication-safety-test-v1",
)
assert settings.MEDICATION_SAFETY_RULE_DATASET_VERSION == (
    "medication-safety-test-v1"
)
```

- [ ] **Step 3: 실패 확인**

Run:

```bash
uv run --group ai --group app --group dev python -m pytest \
  app/tests/models/test_medication_safety_models.py \
  ai_worker/tests/core/test_core_package.py -q
```

Expected: 새 enum 또는 Config 필드 import/attribute 오류로 FAIL.

---

### Task 3: enum·설정 최소 구현

**Files:**
- Modify: `app/models/enums.py`
- Modify: `ai_worker/core/config.py`
- Modify: `.env.example`
- Test: `app/tests/models/test_medication_safety_models.py`
- Test: `ai_worker/tests/core/test_core_package.py`

**Interfaces:**
- Produces: `MedicationSafetyRuleType`, `SafetyConditionKind`, `SafetyComparisonOperator`, `ChatSourceType.MEDICATION_SAFETY_RULE`, `Config.MEDICATION_SAFETY_RULE_DATASET_VERSION`

- [ ] **Step 1: enum 구현**

`app/models/enums.py`의 interaction enum 인접 위치에 다음 클래스를 추가한다.

```python
class MedicationSafetyRuleType(StrEnum):
    PREGNANCY_CONTRAINDICATION = "PREGNANCY_CONTRAINDICATION"
    AGE_CONTRAINDICATION = "AGE_CONTRAINDICATION"
    ELDERLY_CAUTION = "ELDERLY_CAUTION"
    DOSE_CAUTION = "DOSE_CAUTION"
    DURATION_CAUTION = "DURATION_CAUTION"
    DAILY_MAX_DOSE = "DAILY_MAX_DOSE"
    EXCIPIENT_CAUTION = "EXCIPIENT_CAUTION"


class SafetyConditionKind(StrEnum):
    PREGNANCY_STATUS = "PREGNANCY_STATUS"
    AGE_DAYS = "AGE_DAYS"
    AGE_YEARS = "AGE_YEARS"
    DAILY_DOSE = "DAILY_DOSE"
    DURATION_DAYS = "DURATION_DAYS"
    DOSAGE_FORM = "DOSAGE_FORM"
    ADMINISTRATION_ROUTE = "ADMINISTRATION_ROUTE"
    EXCIPIENT_PRESENT = "EXCIPIENT_PRESENT"


class SafetyComparisonOperator(StrEnum):
    EQ = "EQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    BETWEEN = "BETWEEN"
    PRESENT = "PRESENT"
```

`ChatSourceType`에는 다음 한 줄을 추가한다.

```python
MEDICATION_SAFETY_RULE = "MEDICATION_SAFETY_RULE"
```

- [ ] **Step 2: Config와 `.env.example` 구현**

`Config`의 상호작용 규칙 버전 바로 다음에 추가한다.

```python
MEDICATION_SAFETY_RULE_DATASET_VERSION: str = "medication-safety-v1"
```

`.env.example`에는 다음을 추가한다.

```dotenv
MEDICATION_SAFETY_RULE_DATASET_VERSION=medication-safety-v1
```

- [ ] **Step 3: 테스트 통과 확인**

Run:

```bash
uv run --group dev ruff check \
  app/models/enums.py \
  ai_worker/core/config.py \
  app/tests/models/test_medication_safety_models.py \
  ai_worker/tests/core/test_core_package.py
uv run --group ai --group app --group dev python -m pytest \
  app/tests/models/test_medication_safety_models.py \
  ai_worker/tests/core/test_core_package.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .env.example app/models/enums.py ai_worker/core/config.py \
  app/tests/models/test_medication_safety_models.py \
  ai_worker/tests/core/test_core_package.py
git commit -m "[feature/162][임경수] 단일 약물 안전 규칙 enum과 설정 추가"
```

---

### Task 4: 실패하는 ORM 관계·제약 테스트 작성

**Files:**
- Modify: `app/tests/models/test_medication_safety_models.py`

**Interfaces:**
- Consumes: Task 3의 enum
- Produces: 모델 3종과 채팅 FK의 ORM 계약 테스트

- [ ] **Step 1: SQLite 메모리 DB fixture 작성**

```python
import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
```

- [ ] **Step 2: 규칙·조건·출처 생성 테스트 작성**

테스트는 `InteractionEntity`를 만든 뒤 다음 값으로 세 모델을 생성한다.

```python
rule = await MedicationSafetyRule.create(
    rule_key="a" * 64,
    interaction_entity=entity,
    rule_type=MedicationSafetyRuleType.AGE_CONTRAINDICATION,
    risk_level=InteractionRiskLevel.CONTRAINDICATED,
    guidance_text="특정 연령에서는 사용하지 않도록 안내된 성분입니다.",
    review_status=InteractionReviewStatus.PENDING,
    rule_dataset_version="medication-safety-v1",
    extraction_method=(
        InteractionExtractionMethod.DETERMINISTIC_STRUCTURED
    ),
)
condition = await MedicationSafetyRuleCondition.create(
    medication_safety_rule=rule,
    condition_group_no=1,
    condition_order=1,
    condition_kind=SafetyConditionKind.AGE_YEARS,
    comparison_operator=SafetyComparisonOperator.LT,
    value_min=12,
    unit="year",
)
source = await MedicationSafetyRuleSource.create(
    medication_safety_rule=rule,
    source_id="MFDS_DUR_AGE",
    document_id="DUR특정연령대금기.csv",
    record_id="row-1",
    raw_effect_text="12세 미만 투여 금기",
)
```

각 FK ID와 enum 값이 보존되는지 확인한다.

- [ ] **Step 3: 복합 유일성 테스트 작성**

같은 버전에 같은 `rule_key`, 같은 규칙의 같은 `(group, order)`, 같은 규칙의 같은 source key를 두 번 생성할 때 `IntegrityError`가 발생해야 한다.

- [ ] **Step 4: 채팅 출처 FK 테스트 작성**

Assistant `ChatMessage`와 `ChatMessageSource`를 생성하고 다음을 확인한다.

```python
assert source.medication_safety_rule_id == rule.id
assert source.source_type == ChatSourceType.MEDICATION_SAFETY_RULE
```

- [ ] **Step 5: 실패 확인**

Run:

```bash
uv run --group ai --group app --group dev python -m pytest \
  app/tests/models/test_medication_safety_models.py -q
```

Expected: 새 ORM 모델 또는 ChatMessageSource FK import/attribute 오류로 FAIL.

---

### Task 5: 안전 규칙 ORM 모델과 채팅 FK 구현

**Files:**
- Modify: `app/models/interactions.py`
- Modify: `app/models/chat.py`
- Test: `app/tests/models/test_medication_safety_models.py`

**Interfaces:**
- Produces: `MedicationSafetyRule`, `MedicationSafetyRuleCondition`, `MedicationSafetyRuleSource`, `ChatMessageSource.medication_safety_rule`

- [ ] **Step 1: 안전 규칙 모델 구현**

`app/models/interactions.py`에 설계된 필드를 Tortoise 모델로 추가한다.

핵심 필드 형식:

```python
rule_key = fields.CharField(max_length=64)
interaction_entity = fields.ForeignKeyField(
    "models.InteractionEntity",
    related_name="medication_safety_rules",
    on_delete=fields.RESTRICT,
)
guidance_text = fields.TextField()
condition_group_no = fields.SmallIntField(
    validators=[MinValueValidator(1)],
)
condition_order = fields.SmallIntField(
    validators=[MinValueValidator(1)],
)
value_min = fields.DecimalField(
    max_digits=14,
    decimal_places=4,
    null=True,
)
value_max = fields.DecimalField(
    max_digits=14,
    decimal_places=4,
    null=True,
)
```

각 `Meta`에 설계 문서의 `table`, `unique_together`, `indexes`를 적용한다.

- [ ] **Step 2: ChatMessageSource FK 구현**

```python
medication_safety_rule = fields.ForeignKeyField(
    "models.MedicationSafetyRule",
    related_name="chat_message_sources",
    null=True,
    on_delete=fields.RESTRICT,
)
```

`Meta.indexes`에 `("medication_safety_rule",)`를 추가한다.

- [ ] **Step 3: 모델 테스트 통과 확인**

Run:

```bash
uv run --group dev ruff check \
  app/models/interactions.py \
  app/models/chat.py \
  app/tests/models/test_medication_safety_models.py
uv run --group ai --group app --group dev python -m pytest \
  app/tests/models/test_medication_safety_models.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/models/interactions.py app/models/chat.py \
  app/tests/models/test_medication_safety_models.py
git commit -m "[feature/162][임경수] 단일 약물 안전 규칙 ORM 추가"
```

---

### Task 6: Aerich 마이그레이션 생성 및 안전 제약 보완

**Files:**
- Create: `app/core/db/migrations/models/<next>_add_medication_safety_rules.py`

**Interfaces:**
- Consumes: Task 5 ORM state, 현재 MySQL migration head
- Produces: 되돌릴 수 있는 신규 스키마 migration

- [ ] **Step 1: 현재 migration 상태와 보존 대상 건수 기록**

Run:

```bash
uv run --group app aerich heads
```

MySQL에서 다음 건수를 기록한다.

```sql
SELECT 'interaction_rules' AS table_name, COUNT(*) AS row_count
FROM interaction_rules
UNION ALL
SELECT 'chat_messages', COUNT(*) FROM chat_messages
UNION ALL
SELECT 'chat_message_sources', COUNT(*) FROM chat_message_sources;
```

- [ ] **Step 2: migration 생성**

Run:

```bash
uv run --group app aerich migrate --name add_medication_safety_rules
```

Expected: 새 migration 파일 한 개 생성.

- [ ] **Step 3: 생성 SQL 검토**

확인 항목:

- 새 테이블 3개 생성
- nullable FK 1개 추가
- 기존 `interaction_rules` 변경 없음
- 기존 데이터 UPDATE 없음
- 예상하지 않은 DROP 없음
- downgrade가 FK와 자식 테이블부터 제거

- [ ] **Step 4: MySQL 체크 제약 수동 보완**

Aerich가 생성하지 않는 다음 체크를 upgrade SQL에 추가한다.

```sql
CONSTRAINT `chk_med_safety_rule_key`
CHECK (CHAR_LENGTH(`rule_key`) = 64
  AND `rule_key` REGEXP '^[0-9A-Fa-f]{64}$')
```

```sql
CONSTRAINT `chk_med_safety_rule_approval`
CHECK ((`review_status` = 'APPROVED' AND `approved_at` IS NOT NULL)
  OR (`review_status` <> 'APPROVED' AND `approved_at` IS NULL))
```

```sql
CONSTRAINT `chk_med_safety_condition_order`
CHECK (`condition_group_no` >= 1 AND `condition_order` >= 1)
```

```sql
CONSTRAINT `chk_med_safety_between`
CHECK (`comparison_operator` <> 'BETWEEN'
  OR (`value_min` IS NOT NULL
    AND `value_max` IS NOT NULL
    AND `value_min` <= `value_max`))
```

기존 `chk_chat_patient_source`와 `chk_chat_public_source`를 새 안전 규칙 FK까지 배타적으로 검사하도록 교체한다. downgrade에는 체크 제거·기존 체크 복원을 대칭으로 작성한다.

- [ ] **Step 5: migration 정적 검사**

Run:

```bash
uv run --group dev ruff check app/core/db/migrations/models
git diff --check -- app/core/db/migrations/models
```

Expected: PASS.

---

### Task 7: 실제 MySQL upgrade 및 스키마 검증

**Files:**
- Uses: Task 6 migration

**Interfaces:**
- Produces: 로컬 MySQL에 적용된 선택지 C 스키마

- [ ] **Step 1: upgrade 실행**

Run:

```bash
uv run --group app aerich upgrade
uv run --group app aerich heads
```

Expected:

```text
Success upgrading to <migration filename>
No available heads.
```

- [ ] **Step 2: 테이블 존재 확인**

```sql
SHOW TABLES LIKE 'medication_safety_rules';
SHOW TABLES LIKE 'medication_safety_rule_conditions';
SHOW TABLES LIKE 'medication_safety_rule_sources';
```

Expected: 각 쿼리 1행.

- [ ] **Step 3: DDL 확인**

```sql
SHOW CREATE TABLE medication_safety_rules;
SHOW CREATE TABLE medication_safety_rule_conditions;
SHOW CREATE TABLE medication_safety_rule_sources;
SHOW CREATE TABLE chat_message_sources;
```

Expected: 설계된 FK·복합 unique·index·check와 nullable `medication_safety_rule_id`가 존재한다.

- [ ] **Step 4: 기존 데이터 건수 비교**

Task 6에서 기록한 쿼리를 다시 실행한다.

Expected: `interaction_rules`, `chat_messages`, `chat_message_sources` 건수가 upgrade 전과 동일.

- [ ] **Step 5: Commit**

```bash
git add app/core/db/migrations/models
git commit -m "[feature/162][임경수] 단일 약물 안전 규칙 마이그레이션 추가"
```

---

### Task 8: 문서 상태 갱신 및 전체 회귀 검증

**Files:**
- Modify: `docs/ai-worker-database-table-column-guide.md`

**Interfaces:**
- Consumes: 실제 upgrade 검증 결과
- Produces: 현재 구현 상태와 DB 계약이 일치하는 운영 설명서

- [ ] **Step 1: 문서의 구현 상태 갱신**

다음 테이블의 상태를 `C 설계 추가 예정`에서 `현재 구현`으로 바꾼다.

```text
medication_safety_rules
medication_safety_rule_conditions
medication_safety_rule_sources
```

체크리스트에서 ORM·migration·설정 항목을 완료로 표시하되 CSV 파서·실제 적재·Repository는 미완료로 유지한다.

- [ ] **Step 2: 대상 테스트 실행**

```bash
uv run --group ai --group app --group dev python -m pytest \
  app/tests/models/test_medication_safety_models.py \
  ai_worker/tests/core/test_core_package.py \
  ai_worker/tests/repositories/test_interaction_rule_repository.py \
  app/tests/chat_apis/test_chat_repository.py -q
```

Expected: PASS.

- [ ] **Step 3: 전체 정적 검사와 테스트 실행**

```bash
uv run --group dev ruff check ai_worker app
uv run --group ai --group app --group dev python -m pytest \
  ai_worker/tests app/tests -q
git diff --check
```

Expected: Ruff와 전체 테스트 PASS, diff whitespace 오류 없음.

- [ ] **Step 4: 최종 변경 범위 확인**

```bash
git status --short
git diff --stat HEAD
```

Expected: 이 계획의 ERD·ORM·설정·테스트·migration·설명서만 변경되고 `.superpowers/`, `.vite/`, `media/`, `output/`, `tmp/`는 포함되지 않는다.

- [ ] **Step 5: Commit**

```bash
git add docs/ai-worker-database-table-column-guide.md
git commit -m "[feature/162][임경수] 안전 규칙 DB 사용설명서 현행화"
```
