# 구조화 의약품 안전자료 적재 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 식약처 7종 구조화 CSV를 결정론적으로 변환·검증하고 v1.1.4의 단일 약물 안전 규칙 테이블에 PENDING 상태로 반복 안전하게 적재한다.

**Architecture:** 원본 CSV를 직접 DB에 쓰지 않는다. 먼저 공통 Pydantic 후보 스키마로 정규화하고 불변 generation 디렉터리에 JSONL·품질 보고서·current marker를 발행한 뒤, 별도 importer가 SHA-256과 건수를 재검증하고 하나의 DB 트랜잭션으로 엔티티·규칙·조건·출처를 upsert한다. 승인과 런타임 조건 평가는 후속 단계로 남긴다.

**Tech Stack:** Python 3.13, Pydantic v2, Tortoise ORM, MySQL 8, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-01-medication-safety-rules-schema-design.md`

## Global Constraints

- 기존 `interaction_rules` 및 병용금기 파이프라인은 변경하지 않는다.
- 신규 테이블·컬럼·Aerich 마이그레이션은 만들지 않고 v1.1.4 스키마를 사용한다.
- 모든 자동 변환 후보는 `PENDING`; 자동 `APPROVED`는 금지한다.
- 불확실한 연령·용량·기간 표현은 임의 추론하지 않고 품질 보고서에 차단 사유를 기록한다.
- 원본 CSV는 Git 추적 대상에 추가하지 않는다.
- 한 staging generation은 동일 입력과 버전에서 같은 JSONL과 generation ID를 생성해야 한다.
- importer는 candidate SHA-256, dataset version, generation ID, candidate count를 DB 쓰기 전에 검증한다.
- 동일 generation 재실행은 중복 행을 만들지 않아야 한다.

---

### Task 1: 공통 안전 규칙 후보 계약

**Files:**
- Create: `ai_worker/schemas/medication_safety.py`
- Create: `ai_worker/tests/schemas/test_medication_safety.py`

**Interfaces:**
- Produces: `MedicationSafetyRuleCandidate`, `MedicationSafetyConditionCandidate`, `MedicationSafetySourceRecord`, `build_medication_safety_rule_key()`
- Consumes: 기존 `InteractionEntity`, 안전 규칙 enum

- [ ] 후보 스키마가 공백 정규화, 조건 정렬, 출처 중복 제거, PENDING 강제, SHA-256 rule key 생성을 검증하는 실패 테스트를 작성한다.
- [ ] 대상 테스트를 실행해 모듈 부재 또는 계약 부재로 실패하는 것을 확인한다.
- [ ] Pydantic 모델과 안정적인 canonical JSON 기반 rule key 생성을 최소 구현한다.
- [ ] 후보 스키마 테스트를 통과시킨다.

### Task 2: 7종 유형별 결정론적 파서

**Files:**
- Create: `ai_worker/services/medication_safety_staging_service.py`
- Create: `ai_worker/tests/services/test_medication_safety_staging_service.py`

**Interfaces:**
- Produces: `MedicationSafetyStagingService.build()`, `MedicationSafetyStagingResult`, `SkippedMedicationSafetyRow`
- Consumes: Task 1 후보 스키마

- [ ] 다음 literal fixture를 사용하는 실패 테스트를 작성한다: 임부 2등급, 12세 미만, 노인주의, 4,000mg 용량주의, 7일 기간주의, 1일 최대 4정, 유당 첨가제주의.
- [ ] 실패 테스트가 parser 미구현 때문에 실패하는지 확인한다.
- [ ] 공통 DUR 28열 reader와 1일 최대 투여량 reader를 구현한다.
- [ ] 규칙 매핑을 구현한다: 임부→`PREGNANCY_STATUS`, 연령→연/월/주/일 단위 보존, 노인→`AGE_YEARS >= 65`, 용량/최대량→`DAILY_DOSE`, 기간→`DURATION_DAYS`, 첨가제→`EXCIPIENT_PRESENT`.
- [ ] `-`, 비정상 상태, 다른 DUR 유형, 필수값 누락, 지원하지 않는 복합 숫자 표현을 skip reason으로 기록한다.
- [ ] 숫자와 단위를 분리하되 `4|000밀리그램`은 `4000 mg`으로 정규화하고 원문은 source에 그대로 보존한다.
- [ ] 모든 parser 테스트를 통과시킨다.

### Task 3: 불변 staging 발행과 CLI

**Files:**
- Create: `scripts/build_medication_safety_staging.py`
- Create: `ai_worker/tests/scripts/test_build_medication_safety_staging.py`
- Modify: `ai_worker/services/medication_safety_staging_service.py`

**Interfaces:**
- Produces: `processed/staging/<dataset-version>/<generation-id>/medication_safety_rule_candidates.jsonl`, 품질 JSON, `current.json`

- [ ] 동일 입력 재실행 시 후보 파일과 generation ID가 같은 실패 테스트를 작성한다.
- [ ] 7개 기본 입력 경로, 안전한 dataset version, JSON 결과 출력을 검증하는 CLI 실패 테스트를 작성한다.
- [ ] 임시 디렉터리 작성 후 atomic replace로 generation과 current marker를 발행한다.
- [ ] 후보 파일 SHA-256과 유형별 입력·승인·skip 건수를 품질 보고서에 기록한다.
- [ ] staging 및 CLI 테스트를 통과시킨다.

### Task 4: 트랜잭션 기반 PENDING importer

**Files:**
- Create: `scripts/import_medication_safety_staging.py`
- Create: `ai_worker/tests/scripts/test_import_medication_safety_staging.py`

**Interfaces:**
- Produces: `load_medication_safety_staging_dataset()`, `import_medication_safety_staging_dataset()`, `MedicationSafetyImportResult`
- Consumes: current marker와 Task 1 후보 스키마, v1.1.4 ORM

- [ ] marker 경로 탈출, SHA 불일치, 건수 불일치, dataset version 불일치를 거부하는 실패 테스트를 작성한다.
- [ ] 실제 테스트 DB에서 엔티티·source identifier·규칙·조건·출처가 생성되고 상태가 PENDING인지 검증하는 실패 테스트를 작성한다.
- [ ] 같은 dataset을 두 번 적재해 두 번째 생성 건수가 0인 idempotency 실패 테스트를 작성한다.
- [ ] `in_transaction()` 안에서 엔티티 식별자→규칙→조건→출처 순으로 upsert한다.
- [ ] 기존 동일 source code가 있으면 해당 엔티티를 재사용하고 충돌하는 이름은 자동 덮어쓰기하지 않는다.
- [ ] import 후 해당 dataset version의 규칙·조건·출처 건수를 후보와 대조한다.
- [ ] importer 테스트를 통과시킨다.

### Task 5: 실제 7종 자료 검증

**Files:**
- Generated but Git-ignored: `data/knowledge/processed/staging/<dataset-version>/...`
- Modify: `docs/ai-worker-database-table-column-guide.md` only if 실행법이 현재 문서에 없을 때

**Interfaces:**
- Uses: `scripts/build_medication_safety_staging.py`, `scripts/import_medication_safety_staging.py`

- [ ] 실제 7종 CSV로 staging을 생성한다.
- [ ] 유형별 input/accepted/skipped/candidate 건수와 skip reason을 확인한다.
- [ ] 후보 파일의 SHA-256과 동일 입력 재실행 결정성을 확인한다.
- [ ] `--allow-pending`으로 로컬 MySQL에 적재하고 전부 PENDING인지 확인한다.
- [ ] 같은 명령을 재실행해 신규 생성 건수가 0인지 확인한다.

### Task 6: 회귀 검증

**Files:**
- No additional files

- [ ] `uv run --group dev ruff check ai_worker scripts app`를 실행한다.
- [ ] `uv run --group dev ruff format ai_worker scripts app --check`를 실행한다.
- [ ] 안전 규칙 대상 테스트를 실행한다.
- [ ] `uv run --group ai --group app --group dev python -m pytest ai_worker/tests app/tests -q`를 실행한다.
- [ ] `git diff --check`와 `git status --short`로 작업 소유 파일과 기존 미추적 파일을 구분한다.
