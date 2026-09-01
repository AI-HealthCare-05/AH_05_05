# 단일 약물 안전 규칙 DB 설계

작성일: 2026-09-01  
기준 ERD: v1.1.3  
대상 브랜치: `feature/162`

## 1. 목표

현재 `interaction_rules`는 두 엔티티의 조합을 표현한다. 이 구조를 유지하면서 다음과 같이 약 하나에 적용되는 구조화 안전자료를 별도 계층으로 추가한다.

- DUR 임부금기
- DUR 특정 연령대 금기
- DUR 노인주의
- DUR 용량주의
- DUR 투여기간주의
- 1일 최대 투여량
- DUR 첨가제주의

구현 결과는 다음을 만족해야 한다.

1. 조합 규칙과 단일 약물 규칙의 의미가 섞이지 않는다.
2. 같은 규칙의 여러 데이터셋 버전을 함께 보존한다.
3. 검수되지 않은 규칙은 챗봇이 조회할 수 없다.
4. 환자 조건이 부족할 때 안전으로 오판하지 않는다.
5. 답변에 사용한 단일 약물 규칙을 `chat_message_sources`에서 추적할 수 있다.
6. 기존 환자·복약·채팅 데이터는 마이그레이션 중 삭제하거나 재작성하지 않는다.

## 2. 범위

### 포함

- 첨부된 v1.1.3 전체 ERD를 기준으로 최신 DBML 생성
- 기존 v1.0.6 DBML 제거
- 안전 규칙 enum 및 ORM 추가
- 안전 규칙 테이블 3개 추가
- 채팅 출처 유형과 nullable FK 확장
- 활성 안전 규칙 데이터셋 버전 설정 추가
- 모델·설정·마이그레이션 테스트
- Aerich 마이그레이션 생성, 검토, 실제 `aerich upgrade`
- 실제 MySQL 테이블·FK·인덱스 검증

### 제외

- 7종 CSV 파서 구현
- 안전 규칙 후보 JSONL 생성
- 실제 안전 규칙 데이터 적재·승인
- 런타임 조건 평가 Repository와 Use Case 연결
- 프론트엔드 변경
- Qdrant 재인덱싱

이번 작업은 이후 데이터 적재와 런타임 평가가 의존할 DB 계약을 먼저 확정하는 단계다.

## 3. 선택한 구조

### 채택: 단일 약물 안전 규칙 전용 3테이블

- `medication_safety_rules`: 규칙 본체
- `medication_safety_rule_conditions`: 적용 조건
- `medication_safety_rule_sources`: 원본 출처

### 채택 이유

`interaction_rules`는 `left_entity_id`와 `right_entity_id`가 모두 필요한 조합 모델이다. 임부금기나 1일 최대 투여량은 대상 약 하나와 환자·복용 조건의 관계이므로 같은 테이블에 넣으면 다음 문제가 생긴다.

- 존재하지 않는 두 번째 엔티티를 표현하기 위해 NULL 또는 가짜 엔티티가 필요하다.
- pair key와 rule key의 의미가 달라진다.
- 조합 검색과 환자 조건 평가가 한 Repository에 섞인다.
- 규칙 유형별 필수값 검증이 어려워진다.

전용 테이블을 사용하면 기존 조합 규칙을 변경하지 않고 단일 규칙을 확장할 수 있다.

### 채택하지 않은 방식

1. `interaction_rules`에 nullable 두 번째 엔티티와 조건 JSON을 추가하는 방식
   - 기존 pair 계약이 깨지고 잘못된 NULL 조합이 만들어질 수 있어 제외한다.
2. 모든 조건을 `raw_effect_text` 한 컬럼에만 저장하는 방식
   - 연령·용량·기간을 결정론적으로 비교할 수 없어 제외한다.
3. 모든 출처를 polymorphic ID 하나로 연결하는 방식
   - DB FK가 사라지고 현재 프로젝트 규모에 비해 복잡해져 제외한다.

## 4. enum 설계

### `MedicationSafetyRuleType`

```text
PREGNANCY_CONTRAINDICATION
AGE_CONTRAINDICATION
ELDERLY_CAUTION
DOSE_CAUTION
DURATION_CAUTION
DAILY_MAX_DOSE
EXCIPIENT_CAUTION
```

### `SafetyConditionKind`

초기 지원값은 다음으로 제한한다.

```text
PREGNANCY_STATUS
AGE_DAYS
AGE_YEARS
DAILY_DOSE
DURATION_DAYS
DOSAGE_FORM
ADMINISTRATION_ROUTE
EXCIPIENT_PRESENT
```

새 조건 종류는 enum 추가와 마이그레이션이 함께 이루어져야 한다.

### `SafetyComparisonOperator`

```text
EQ
LT
LTE
GT
GTE
BETWEEN
PRESENT
```

### 재사용 enum

- 위험도: `InteractionRiskLevel`
- 검수 상태: `InteractionReviewStatus`
- 추출 방식: `InteractionExtractionMethod`

조합 규칙과 단일 규칙이 같은 위험도·승인 정책을 사용하므로 기존 enum을 재사용한다.

## 5. 테이블 설계

## 5.1 `medication_safety_rules`

약 하나에 대한 안전 규칙 본체다.

| 컬럼 | 타입 | NULL | 제약·의미 |
|---|---|---:|---|
| `id` | BIGINT | N | PK, AUTO_INCREMENT |
| `rule_key` | VARCHAR(64) | N | 엔티티·규칙 유형·정규화 조건으로 만든 SHA-256 |
| `interaction_entity_id` | BIGINT | N | `interaction_entities.id`, RESTRICT |
| `rule_type` | VARCHAR enum | N | 단일 약물 안전 규칙 유형 |
| `risk_level` | VARCHAR enum | N | 위험도 |
| `guidance_text` | LONGTEXT | N | 검수된 한국어 안내 문구 |
| `review_status` | VARCHAR enum | N | 기본 `PENDING` |
| `rule_dataset_version` | VARCHAR(100) | N | 불변 규칙 데이터셋 버전 |
| `extraction_method` | VARCHAR enum | N | 추출 방식 |
| `approved_at` | DATETIME(6) | Y | 승인 시각 |
| `created_at` | DATETIME(6) | N | 생성 시각 |
| `updated_at` | DATETIME(6) | Y | 수정 시각 |

제약:

- UNIQUE `(rule_key, rule_dataset_version)`
- INDEX `(interaction_entity_id, rule_type, review_status)`
- INDEX `(rule_dataset_version, review_status)`
- `rule_key`는 64자리 16진수
- `APPROVED`이면 `approved_at IS NOT NULL`
- `APPROVED`가 아니면 `approved_at IS NULL`

`guidance_text`는 원문 복제가 아니다. 검수자가 승인한 사용자용 한국어 안내이며, 원문은 sources 테이블에 그대로 보존한다.

## 5.2 `medication_safety_rule_conditions`

규칙의 적용 조건을 구조화한다.

| 컬럼 | 타입 | NULL | 제약·의미 |
|---|---|---:|---|
| `id` | BIGINT | N | PK, AUTO_INCREMENT |
| `medication_safety_rule_id` | BIGINT | N | 규칙 FK, CASCADE |
| `condition_group_no` | SMALLINT | N | OR 그룹 번호, 1 이상 |
| `condition_order` | SMALLINT | N | 그룹 안 평가 순서, 1 이상 |
| `condition_kind` | VARCHAR enum | N | 조건 종류 |
| `comparison_operator` | VARCHAR enum | N | 비교 연산자 |
| `value_min` | DECIMAL(14,4) | Y | 단일 숫자 또는 하한 |
| `value_max` | DECIMAL(14,4) | Y | BETWEEN 상한 |
| `value_text` | VARCHAR(255) | Y | 임신 상태·제형·경로·첨가제명 |
| `unit` | VARCHAR(30) | Y | mg, mg/day, day, year 등 |
| `created_at` | DATETIME(6) | N | 생성 시각 |

제약:

- UNIQUE `(medication_safety_rule_id, condition_group_no, condition_order)`
- INDEX `(condition_kind, comparison_operator)`
- `condition_group_no >= 1`
- `condition_order >= 1`
- `BETWEEN`은 `value_min`과 `value_max`가 모두 필요하고 `value_min <= value_max`
- 숫자 비교는 `value_min`이 필요
- `EQ`와 `PRESENT`는 조건 종류에 따라 `value_text` 또는 숫자값을 사용

조건 결합:

- 같은 `condition_group_no`: AND
- 서로 다른 `condition_group_no`: OR

런타임 판정 상태 `MATCHED`, `NOT_APPLICABLE`, `INSUFFICIENT_CONTEXT`는 DB enum이나 컬럼으로 저장하지 않고 평가 결과 객체로 계산한다.

## 5.3 `medication_safety_rule_sources`

안전 규칙의 원본 레코드를 보존한다.

| 컬럼 | 타입 | NULL | 제약·의미 |
|---|---|---:|---|
| `id` | BIGINT | N | PK, AUTO_INCREMENT |
| `medication_safety_rule_id` | BIGINT | N | 규칙 FK, CASCADE |
| `source_id` | VARCHAR(100) | N | 원천 데이터 종류 |
| `document_id` | VARCHAR(150) | N | 원본 문서·파일 식별자 |
| `record_id` | VARCHAR(150) | N | 원본 행 ID |
| `raw_effect_text` | LONGTEXT | N | 원문 주의·금기 내용 |
| `source_published_at` | DATE | Y | 공개·기준일 |
| `source_url` | LONGTEXT | Y | 공식 링크 |
| `created_at` | DATETIME(6) | N | 생성 시각 |

제약:

- UNIQUE `(medication_safety_rule_id, source_id, document_id, record_id)`
- INDEX `(source_id, record_id)`

## 6. 채팅 출처 확장

### enum

`ChatSourceType`에 다음 값을 추가한다.

```text
MEDICATION_SAFETY_RULE
```

### FK

`chat_message_sources`에 다음 컬럼을 추가한다.

```text
medication_safety_rule_id BIGINT NULL
```

참조 및 삭제 정책:

```text
medication_safety_rules.id <- chat_message_sources.medication_safety_rule_id
ON DELETE RESTRICT
```

답변 이력이 참조한 규칙은 삭제하지 않는다. 새 버전은 새 행으로 추가하고 과거 규칙은 출처 보존용으로 유지한다.

### 체크 제약 교체

기존 `chk_chat_patient_source`는 새 FK를 알지 못한다. 마이그레이션에서 기존 체크를 제거하고 다음 배타 조건을 포함하도록 다시 만든다.

- `PATIENT_SAVED_FIELD`: 환자 출처 FK만 사용
- `USER_SUPPLEMENT`: `user_suppl_nutrient_id`만 사용
- `INTERACTION_RULE`: `interaction_rule_id`만 사용
- `MEDICATION_SAFETY_RULE`: `medication_safety_rule_id`만 사용
- `PUBLIC_RAG_CHUNK`: Qdrant 출처 필드만 사용

공공 RAG가 아닌 출처에서는 Qdrant 전용 필드를 모두 NULL로 유지한다.

## 7. ORM 설계

### `app/models/enums.py`

- `MedicationSafetyRuleType`
- `SafetyConditionKind`
- `SafetyComparisonOperator`
- `ChatSourceType.MEDICATION_SAFETY_RULE`

### `app/models/interactions.py`

- `MedicationSafetyRule`
- `MedicationSafetyRuleCondition`
- `MedicationSafetyRuleSource`

기존 `InteractionEntity`에는 `related_name="medication_safety_rules"` 관계를 추가한다. 현재 조합 규칙 모델은 변경하지 않는다.

### `app/models/chat.py`

`ChatMessageSource`에 nullable FK를 추가한다.

```python
medication_safety_rule = fields.ForeignKeyField(
    "models.MedicationSafetyRule",
    related_name="chat_message_sources",
    null=True,
    on_delete=fields.RESTRICT,
)
```

### 설정

`ai_worker/core/config.py`와 `.env.example`에 다음을 추가한다.

```dotenv
MEDICATION_SAFETY_RULE_DATASET_VERSION=medication-safety-v1
```

이번 단계에서는 설정을 읽을 수 있게만 하고 Repository 연결은 후속 작업으로 남긴다.

## 8. ERD 파일 정책

- 입력 기준: 사용자가 제공한 v1.1.3 전체 ERD
- 출력: `docs/poke-erd-v1.1.3-full-ai-chat-safety.dbml`
- 제거: `docs/poke-erd-v1.0.6-full-ai-chat-interaction.dbml`
- 팀원 영역은 입력 ERD 그대로 보존한다.
- 수정 위치는 AI enum, AI 안전 규칙 테이블, 채팅 출처 컬럼·제약·Ref에 한정한다.

## 9. 마이그레이션 정책

마이그레이션 이름:

```text
add_medication_safety_rules
```

Upgrade 순서:

1. `medication_safety_rules` 생성
2. `medication_safety_rule_conditions` 생성
3. `medication_safety_rule_sources` 생성
4. `chat_message_sources.medication_safety_rule_id` nullable 컬럼 추가
5. FK와 인덱스 추가
6. 기존 채팅 출처 체크 제약 제거
7. 새 배타 체크 제약 생성
8. `source_type` 메타데이터를 새 enum 값이 포함되도록 갱신

기존 행은 새 FK가 NULL이므로 데이터 변환이 필요 없다.

Downgrade 순서:

1. 개발용 downgrade에서는 `MEDICATION_SAFETY_RULE` 출처 행을 먼저 삭제한다.
2. 새 체크 제약 제거
3. 기존 체크 제약 복원
4. FK·인덱스·컬럼 제거
5. sources → conditions → rules 순서로 테이블 제거

이 downgrade는 답변 감사 이력을 삭제할 수 있으므로 개발 환경에서만 사용한다. 운영 롤백은 downgrade 대신 이전 애플리케이션 버전이 새 nullable 컬럼을 무시하도록 배포한다.

## 10. 테스트 전략

### TDD 모델 테스트

- 새 enum 값 전체 확인
- 각 모델의 실제 DB 테이블명 확인
- FK의 related name과 삭제 정책 확인
- 규칙 키·버전 복합 유일성 확인
- 조건 순서 복합 유일성 확인
- 출처 복합 유일성 확인
- ChatMessageSource의 nullable 안전 규칙 FK 확인
- 설정 기본값 및 환경변수 override 확인

### 마이그레이션 검증

- `ruff check`와 대상 pytest 실행
- `aerich migrate --name add_medication_safety_rules`
- 생성 SQL에서 destructive statement 여부 확인
- `aerich upgrade`
- `aerich heads`가 `No available heads.`인지 확인
- MySQL `SHOW CREATE TABLE`로 FK·인덱스·체크 제약 확인
- 기존 상호작용 규칙 건수와 채팅 메시지 건수가 유지되는지 전후 비교

### 전체 회귀 검증

```bash
uv run --group dev ruff check ai_worker app
uv run --group ai --group app --group dev python -m pytest ai_worker/tests app/tests -q
git diff --check
```

## 11. 실패·안전 정책

- 마이그레이션 SQL에 기존 테이블 또는 컬럼 DROP이 예상 외로 포함되면 upgrade하지 않는다.
- 활성 DB 연결이나 기존 migration head가 불일치하면 새 migration을 만들지 않는다.
- 새 테이블 생성에 실패하면 기존 조합 상호작용 기능은 그대로 유지되어야 한다.
- 환자 조건이 NULL이면 안전 규칙 미해당으로 처리하지 않는다.
- `PENDING`과 `REJECTED` 규칙은 후속 Repository에서도 조회 금지다.
- 규칙이 없다는 사실을 안전하다는 의미로 표현하지 않는다.

## 12. 완료 기준

- 최신 전체 ERD에 선택지 C가 반영되어 있다.
- 현재 ORM과 ERD의 테이블명·컬럼·FK·인덱스가 일치한다.
- 신규 모델 및 설정 테스트가 통과한다.
- Aerich upgrade가 성공한다.
- 추가 migration head가 남지 않는다.
- 기존 DB 레코드 건수가 보존된다.
- 신규 테이블과 채팅 출처 FK를 MySQL에서 직접 확인한다.
