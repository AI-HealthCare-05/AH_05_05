# 상호작용 Knowledge RDBMS 직전 단계 구현 계획

> 작업 브랜치: `feature/68`

**목표:** 구조화된 DUR 병용금기 데이터를 검수 가능한 RDBMS 후보로 만들고, Qdrant 근거 청크와 같은 조합 키를 공유할 수 있는 계약을 제공한다.

**범위:** `ai_worker`, `scripts`, `data/knowledge` 문서와 테스트만 수정한다. `app` ORM, migration, MySQL은 수정하지 않는다.

## 1. 상호작용 계약

- [x] `ai_worker/schemas/interaction.py`에 주체, 조합 유형, 위험도, 검수 상태, 출처, 후보 스키마를 추가한다.
- [x] `ai_worker/tests/schemas/test_interaction_schema.py`에서 이름 정규화, 입력 순서와 무관한 pair key, PENDING 강제, 출처 검증을 먼저 실패시킨다.
- [x] 최소 구현 후 해당 테스트를 통과시킨다.
- [x] 전체 검사 후 중간 커밋한다.

## 2. DUR 병용금기 staging

- [x] `ai_worker/services/interaction_staging_service.py`의 실패 테스트를 작성한다.
- [x] UTF-8 BOM CSV, 필수 컬럼, 정상 행, 빈 필드, 중복 방향 조합을 검증한다.
- [x] 후보 JSONL과 품질 보고서를 원자적으로 생성한다.
- [x] 모든 자동 후보가 `PENDING`이고 원본 행과 금기 내용을 보존하는지 검증한다.
- [x] `scripts/build_interaction_staging.py` CLI와 테스트를 추가한다.
- [x] 대표 실제 CSV를 실행해 행 수와 제외 사유를 확인한다.
- [x] 전체 검사 후 중간 커밋한다.

## 3. Qdrant 연결 계약

- [x] `KnowledgeMetadata`와 `KnowledgeSearchQuery`에 `interaction_pair_keys`를 추가하는 실패 테스트를 작성한다.
- [x] Qdrant payload 보존과 pair key 필터 테스트를 작성한다.
- [x] pair key는 의미가 없는 SHA-256이므로 embedding text에 넣지 않고 정확 필터에만 사용한다.
- [x] 기존 청크와 역호환되는지 전체 테스트로 확인한다.

## 4. 문서와 최종 검증

- [x] `data/knowledge/README.md`와 `processed/README.md`에 staging 산출물과 승인 경계를 기록한다.
- [x] `ruff check ai_worker scripts`
- [x] `pytest ai_worker/tests -q`
- [x] `git diff --check`
- [x] 변경 범위를 검토하고 최종 중간 커밋한다.

## 실제 파일럿 결과

- 입력 행: 1,762
- 정상 변환 행: 1,726
- 고유 약-약 조합 후보: 1,211
- 역방향·중복 병합: 515
- 필수값 누락으로 제외: 35
- 닫히지 않은 따옴표로 제외: 1 (`DUR일련번호=1492`, 원본 428행)
- 모든 후보 상태: `PENDING`
- RDBMS 자동 적재 가능 상태: `false`
- 현재 generation: `abde1694460c4c4b`

원본 428행의 닫히지 않은 따옴표 때문에 표준 스트림 CSV 파서는 이후 행을 하나의
필드로 합쳤다. 필드 크기 한도만 늘리면 오류는 사라져도 대부분의 행이 유실되므로,
물리 행별 엄격 파싱으로 비정상 행만 격리하고 이후 행을 계속 처리하도록 보완했다.
정상적인 따옴표 내부 개행은 논리 레코드로 합치고, 다음 DUR 행이 시작될 때까지
따옴표가 닫히지 않으면 이전 행만 격리한다. 원본 금기 문구는 별도 필드에 그대로
보존하며 후보와 품질 보고서는 같은 불변 generation에 게시한다. 레코드 경계는
단순한 `숫자,` 패턴이 아니라 DUR 일련번호·유형·단일/복합 구분·성분코드의 고정
선행 필드를 함께 검증한다. 이 방식은 `2024, 추가 위험` 같은 정상 본문을 새 행으로
오인하지 않으면서, 손상 행 다음의 정상 멀티라인 행도 함께 유실하지 않는다.
