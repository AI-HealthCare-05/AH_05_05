# 기준정보 Aerich Upsert 설계

## 목표

현재 Docker MySQL에 등록된 활성 기준정보를 버전이 고정된 압축 시드로 추출한다. 새 데이터베이스와 기존 데이터베이스 모두 `aerich upgrade` 한 번으로 같은 기준정보를 확보하며, 동일 시드를 다시 실행해도 중복 행을 만들지 않는다.

## 범위

다음 19개 테이블을 대상으로 한다.

1. `medication_product_guides`
2. `supplement_nutrients`
3. `nutrient_standard`
4. `interaction_entities`
5. `interaction_entity_aliases`
6. `interaction_entity_identifiers`
7. `supplement_interaction_entities`
8. `interaction_rules`
9. `interaction_rule_sources`
10. `interaction_rule_evidence_chunks`
11. `medication_safety_rules`
12. `medication_safety_rule_conditions`
13. `medication_safety_rule_sources`
14. `badges`
15. `challenges`
16. `custom_challenge_templates`
17. `common_code_groups`
18. `common_codes`
19. `admin_settings`

사용자 데이터, 참여 이력, 관리자 계정, 작업 이력은 포함하지 않는다.

## 데이터 원본과 버전 관리

- 최초 `v1` 원본은 추출 시점의 로컬 Docker MySQL이다.
- 추출 파일은 `data/reference_seed/v1/` 아래에 테이블별 `jsonl.gz`로 저장한다.
- `manifest.json`에는 스키마 버전, 추출 일시, 테이블별 필터, 행 수, SHA-256, 적재 순서를 기록한다.
- JSONL은 기본키 순서 또는 업무키 순서로 정렬하고 gzip의 `mtime`을 0으로 고정해 같은 데이터에서 같은 파일이 생성되게 한다.
- 이후 기준정보가 바뀌면 `v1`을 수정하지 않는다. `v2` 디렉터리와 별도 Aerich 데이터 마이그레이션을 추가한다.
- 마이그레이션 파일에는 대용량 SQL이나 원본 행을 직접 삽입하지 않는다.

## 활성 데이터 필터

### 활성 플래그가 있는 테이블

- `common_code_groups`: `is_active = true`
- `common_codes`: `is_active = true`이며 연결 그룹도 활성
- `badges`: `is_active = true`
- `custom_challenge_templates`: `is_active = true`
- `challenges`: `is_displayed = true AND is_deleted = false`

### 검토 상태가 있는 테이블

- `interaction_rules`: `review_status = 'APPROVED'`
- `medication_safety_rules`: `review_status = 'APPROVED'`
- 각 source, condition, evidence 테이블은 선택된 승인 부모에 연결된 행만 포함한다.

### 활성 상태 컬럼이 없는 테이블

다음 테이블은 상태로 미사용 여부를 판단할 수 없으므로 전체를 포함한다.

- `medication_product_guides`
- `supplement_nutrients`
- `nutrient_standard`
- `interaction_entities`
- `interaction_entity_aliases`
- `interaction_entity_identifiers`
- `supplement_interaction_entities`

활성 챌린지·템플릿·배지가 비활성 공통코드 또는 비활성 배지를 참조하면 해당 자식 행도 제외한다. 추출기는 제외 건수와 사유를 manifest에 기록하고 FK가 끊긴 행을 시드에 넣지 않는다.

## 보안 및 감사 컬럼

- `admin_settings.smtp_password_enc`는 내보내지 않는다. 대상 DB에 설정 행이 없으면 불완전한 행을
  만들지 않고 삽입을 건너뛰어 기존 `.env` fallback을 사용한다.
- 기존 `admin_settings` 행을 갱신할 때도 `smtp_password_enc`는 변경하지 않는다.
- SMTP 비밀번호가 없으면 기존 서비스 규칙대로 `.env`의 `SMTP_PASSWORD`를 사용한다.
- 관리자 테이블은 시드 범위가 아니므로 `created_by_admin_id`, `updated_by_admin_id`는 모두 `NULL`로 정규화한다.
- 나머지 생성·수정 일시는 원본 값을 보존한다.

## 파일 구조와 책임

- `scripts/export_reference_seed.py`
  - Docker MySQL이 아니라 애플리케이션 DB 설정으로 원본 DB를 읽는다.
  - 활성 필터, FK 폐쇄성, 정렬, JSON 직렬화, gzip 생성, checksum manifest 생성을 담당한다.
- `app/core/db/reference_seed.py`
  - manifest와 checksum을 검증한다.
  - JSONL을 스트리밍으로 읽고 고정 크기 배치로 upsert한다.
  - FK 업무키를 대상 DB의 실제 ID로 해석한다.
  - 허용된 19개 테이블과 명시된 컬럼만 처리한다.
- `data/reference_seed/v1/*.jsonl.gz`
  - 활성 기준정보 스냅샷이다.
- `data/reference_seed/v1/manifest.json`
  - 행 수, checksum, 필터, 적재 순서, 버전을 보관한다.
- 신규 Aerich 마이그레이션
  - `reference_seed.upgrade(db, version='v1')`을 호출하고 모델 스냅샷은 직전 최종 head를 그대로 유지한다.
  - downgrade는 기존 데이터와 참조 관계를 삭제하지 않는 `SELECT 1` no-op으로 처리한다.

## Upsert 식별키

| 테이블 | 식별키 |
| --- | --- |
| `medication_product_guides` | `item_seq` |
| `supplement_nutrients` | `food_code` |
| `nutrient_standard` | `(grp, age)`; `NULL age`도 하나의 논리 키로 비교 |
| `interaction_entities` | `(entity_kind, normalized_name)` |
| `interaction_entity_aliases` | `(interaction entity 업무키, normalized_alias)` |
| `interaction_entity_identifiers` | `(source_id, source_code)` |
| `supplement_interaction_entities` | `(supplement food_code, interaction entity 업무키)` |
| `interaction_rules` | `(pair_key, rule_dataset_version)` |
| `interaction_rule_sources` | `(interaction rule 업무키, source_id, document_id, record_id)` |
| `interaction_rule_evidence_chunks` | `(source 업무키, dataset_version, vector_chunk_id)` |
| `medication_safety_rules` | `(rule_key, rule_dataset_version)` |
| `medication_safety_rule_conditions` | `(safety rule 업무키, condition_group_no, condition_order)` |
| `medication_safety_rule_sources` | `(safety rule 업무키, source_id, document_id, record_id)` |
| `badges` | `name` |
| `challenges` | 원본 `id`; 현재 스키마에 안정적인 자연키가 없음 |
| `custom_challenge_templates` | `name` |
| `common_code_groups` | `group_code` |
| `common_codes` | `(group_code, detail_code)` |
| `admin_settings` | `setting_key` |

DB의 UNIQUE 제약만으로 `NULL` 포함 복합키 중복을 완전히 막을 수 없는 테이블은 배치 적재 전에 기존 키를 조회해 update와 insert를 분리한다. FK는 원본 숫자 ID에 의존하지 않고 위 업무키로 대상 DB의 실제 ID를 찾는다. `challenges`만 기존 스키마 제약 때문에 원본 ID를 안정 키로 사용한다.
대상 DB의 같은 challenge ID가 시드와 다른 이름 또는 모집 시작일을 가지면 기존 챌린지와 연결된 참여·배지 기록을 보존한다. 충돌한 시드 행만 건너뛰고 `skipped`에 포함하며, ID와 건너뛴 이유를 WARNING으로 남긴다(#411). 나머지 기준정보 적재는 계속한다. 충돌 행을 새 ID로 재생성하거나 기존 기록의 FK를 변경하지 않는다. 따라서 해당 DB에는 충돌한 기본 챌린지가 추가되지 않으며, 필요하면 별도 관리 절차로 등록한다.

## 적재 순서

1. `medication_product_guides`
2. `supplement_nutrients`
3. `nutrient_standard`
4. `common_code_groups`
5. `common_codes`
6. `admin_settings`
7. `interaction_entities`
8. `interaction_entity_aliases`
9. `interaction_entity_identifiers`
10. `supplement_interaction_entities`
11. `interaction_rules`
12. `interaction_rule_sources`
13. `interaction_rule_evidence_chunks`
14. `medication_safety_rules`
15. `medication_safety_rule_conditions`
16. `medication_safety_rule_sources`
17. `badges`
18. `custom_challenge_templates`
19. `challenges`

공통코드와 배지는 챌린지보다 먼저 적재하며, 모든 자식 테이블은 부모 ID 해석이 끝난 뒤 적재한다.

## 트랜잭션과 오류 처리

- 마이그레이션이 받은 `BaseDBAsyncClient` 연결을 그대로 사용한다.
- checksum·manifest·파일 존재 여부·행 수 검증은 첫 DB 변경 전에 수행한다.
- 한 파일을 스트리밍하고 최대 500행 단위로 읽어 메모리 사용량을 제한한다.
- 전체 버전 적재를 하나의 Aerich 마이그레이션 트랜잭션에서 수행한다.
- 누락된 FK 업무키, 허용되지 않은 컬럼, 중복 논리 키, 행 수 불일치가 있으면 즉시 실패시키고 Aerich 이력도 남기지 않는다.
- 로그에는 테이블별 생성·갱신·변경없음·제외 건수만 남기며 SMTP 값과 본문 원문은 출력하지 않는다.

## 재실행과 갱신 정책

- 신규 행은 생성하고 동일 식별키 행은 기준 필드를 갱신한다.
- 시드에 없는 기존 행은 삭제하지 않는다.
- `smtp_password_enc`와 대상 DB에서 생성된 PK는 갱신하지 않는다. `admin_settings`는 기존 행만
  일반 SMTP 필드를 갱신한다.
- 동일 버전을 직접 두 번 실행하면 두 번째 실행의 전체 행 수는 동일해야 한다.
- Aerich 자체는 적용 완료 마이그레이션을 다시 실행하지 않으므로, 기준정보 변경은 반드시 다음 버전의 시드와 마이그레이션으로 배포한다.

## 검증

- exporter 단위 테스트: 필터, FK 제외, 결정적 gzip/checksum, 비밀번호 제거를 검증한다.
- loader 단위 테스트: 업무키 upsert, `NULL` 복합키, FK ID 재해석, 허용 컬럼 검증을 확인한다.
- MySQL 통합 테스트:
  1. disposable DB에 현재 모델 스키마를 생성한다.
  2. 일부 업무키 충돌 행을 다른 PK로 선등록한다.
  3. `v1` 시드를 적재해 예상 행 수와 FK 무결성을 확인한다.
  4. 같은 loader를 다시 실행해 행 수 불변과 값 갱신을 확인한다.
  5. 신규 Aerich 마이그레이션 적용 후 head가 비어 있고 최종 모델 스냅샷이 런타임과 같은지 확인한다.
- 변경 파일에 Ruff format/check와 `git diff --check`를 실행한다.

## 운영 절차

1. 기준 DB를 백업한다.
2. exporter를 실행해 `v1` 시드와 manifest를 생성한다.
3. manifest의 필터·행 수·checksum을 검토한다.
4. disposable MySQL에서 신규 DB와 기존 데이터 충돌 DB 두 경우를 검증한다.
5. 애플리케이션 배포 시 `aerich upgrade`를 실행한다.
6. 테이블별 upsert 결과와 Aerich 적용 이력을 확인한다.
