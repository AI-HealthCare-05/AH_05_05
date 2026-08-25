# Interaction and Chat ORM Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 약·영양제·음식 상호작용 규칙과 CHAT 출처 추적을 위한 사용자 담당 Tortoise ORM을 추가하되 팀원 소유 모델과 실제 DB는 변경하지 않는다.

**Architecture:** 기존 `Medication`, `SupplementNutrient`, `UserSupplementNutrient`를 정본으로 유지하고 별도의 `interactions.py`에서 성분 정규화, 사용자 약·영양제 매핑, 승인 규칙, Qdrant 근거 연결을 관리한다. CHAT에는 상호작용 라우트와 출처 FK, P95 측정 필드만 추가하며 모든 신규 모델은 기존 Tortoise 앱에 등록한다.

**Tech Stack:** Python 3.13, Tortoise ORM 0.25+, Aerich, pytest, Ruff

---

## 범위 경계

- 구현: Enum, 9개 상호작용 ORM 모델, CHAT 필드/관계, 모델 등록, 메타데이터 테스트.
- 유지: `medications.py`, `supplement_nutrients.py`, OCR 모델과 서비스 로직.
- 제외: `aerich migrate`, `aerich upgrade`, MySQL 스키마 반영, 데이터 적재.

### Task 1: 상호작용 ORM 계약 테스트

**Files:**
- Create: `tests/models/test_interaction_model_metadata.py`
- Reference: `docs/poke-erd-v6-ai-chat-focus.dbml`

1. 신규 Enum 값, 9개 테이블명, 핵심 FK 삭제 정책, 고유키·인덱스·기본값을 검증하는 테스트를 작성한다.
2. `uv run --group app --group dev python -m pytest tests/models/test_interaction_model_metadata.py -q`를 실행하여 신규 모듈 부재로 실패하는 것을 확인한다.

### Task 2: 상호작용 Enum과 모델 구현

**Files:**
- Modify: `app/models/enums.py`
- Create: `app/models/interactions.py`

1. 성분 종류, 별칭 종류, 매핑 상태·방법, 조합 종류, 위험도, 검수 상태 Enum을 추가한다.
2. 성분 정규화·식별자·약/영양제 매핑·승인 규칙·원문 출처·Qdrant 청크 연결 모델을 구현한다.
3. DBML의 고유키와 인덱스를 ORM `Meta`에 반영하고 수치 필드에 검증자를 적용한다.
4. 대상 메타데이터 테스트를 다시 실행해 통과를 확인한다.

### Task 3: CHAT 상호작용 출처 추적 확장

**Files:**
- Modify: `tests/models/test_interaction_model_metadata.py`
- Modify: `app/models/enums.py`
- Modify: `app/models/chat.py`

1. `INTERACTION` 라우트, `USER_SUPPLEMENT`·`INTERACTION_RULE` 출처, `duration_ms`, 두 출처 FK를 요구하는 실패 테스트를 작성한다.
2. 대상 테스트를 실행해 필드와 Enum 부재로 실패하는 것을 확인한다.
3. Enum과 CHAT 모델을 최소 변경하고 신규 FK 인덱스를 추가한다.
4. 대상 테스트를 다시 실행해 통과를 확인한다.

### Task 4: Tortoise 모델 등록

**Files:**
- Modify: `tests/models/test_interaction_model_metadata.py`
- Modify: `app/core/db/databases.py`
- Modify: `app/models/__init__.py`

1. 등록 테이블 집합에 9개 신규 테이블이 포함되어야 한다는 실패 테스트를 먼저 작성한다.
2. `TORTOISE_APP_MODELS`와 패키지 export에 신규 모듈·모델을 등록한다.
3. 메타데이터 테스트 전체를 실행한다.

### Task 5: 정적·회귀 검증

**Files:**
- Verify only; 마이그레이션 파일은 생성하지 않는다.

1. `uv run --group dev ruff format`을 변경 Python 파일에 적용한다.
2. `uv run --group dev ruff check app/models app/core/db/databases.py tests/models`를 실행한다.
3. `uv run --group app --group dev python -m pytest tests/models -q`를 실행한다.
4. `uv run --group app --group dev python -m pytest tests -q`를 실행한다.
5. `git diff --check`와 `git status --short`로 변경 범위와 사용자 기존 변경 보존을 확인한다.
6. Aerich와 MySQL을 실행하지 않았음을 명시하고, 사용자가 다음 단계에서 수행할 명령을 별도로 안내한다.

## 마이그레이션 전 필수 수동 검토

Aerich는 Tortoise ORM이 표현하지 못하는 조건부 `CHECK`와 기존 수동
`CHECK`의 변경을 자동 생성하지 않는다. 따라서 `aerich migrate` 후
`aerich upgrade` 전에 생성된 마이그레이션을 열어 다음을 직접 반영한다.

- 기존 `chk_chat_public_source`, `chk_chat_patient_source`를 제거하고
  `PATIENT_SAVED_FIELD`, `PUBLIC_RAG_CHUNK`, `USER_SUPPLEMENT`,
  `INTERACTION_RULE` 네 분기를 허용하는 DBML v6 조건으로 재생성한다.
- `supplement_interaction_entities`의 `amount`/`unit` 동시 존재 규칙을 추가한다.
- `interaction_rules.left_entity_id <> right_entity_id`를 추가한다.
- `APPROVED` 규칙만 `approved_at IS NOT NULL`이 되도록 조건을 추가한다.
- `chat_message_sources`의 출처 유형별 FK 배타성과 점수·페이지 범위를
  DBML v6 조건대로 추가한다.
- downgrade에는 기존 CHAT `CHECK` 복원과 신규 `CHECK` 제거를 포함한다.
