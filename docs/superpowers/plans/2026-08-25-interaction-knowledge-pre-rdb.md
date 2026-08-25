# 상호작용 Knowledge RDBMS 직전 단계 구현 계획

> 작업 브랜치: `feature/68`

**목표:** 구조화된 DUR 병용금기 데이터를 검수 가능한 RDBMS 후보로 만들고, Qdrant 근거 청크와 같은 조합 키를 공유할 수 있는 계약을 제공한다.

**범위:** `ai_worker`, `scripts`, `data/knowledge` 문서와 테스트만 수정한다. `app` ORM, migration, MySQL은 수정하지 않는다.

## 1. 상호작용 계약

- [ ] `ai_worker/schemas/interaction.py`에 주체, 조합 유형, 위험도, 검수 상태, 출처, 후보 스키마를 추가한다.
- [ ] `ai_worker/tests/schemas/test_interaction_schema.py`에서 이름 정규화, 입력 순서와 무관한 pair key, PENDING 강제, 출처 검증을 먼저 실패시킨다.
- [ ] 최소 구현 후 해당 테스트를 통과시킨다.
- [ ] 전체 검사 후 중간 커밋한다.

## 2. DUR 병용금기 staging

- [ ] `ai_worker/services/interaction_staging_service.py`의 실패 테스트를 작성한다.
- [ ] UTF-8 BOM CSV, 필수 컬럼, 정상 행, 빈 필드, 중복 방향 조합을 검증한다.
- [ ] 후보 JSONL과 품질 보고서를 원자적으로 생성한다.
- [ ] 모든 자동 후보가 `PENDING`이고 원본 행과 금기 내용을 보존하는지 검증한다.
- [ ] `scripts/build_interaction_staging.py` CLI와 테스트를 추가한다.
- [ ] 대표 실제 CSV를 실행해 행 수와 제외 사유를 확인한다.
- [ ] 전체 검사 후 중간 커밋한다.

## 3. Qdrant 연결 계약

- [ ] `KnowledgeMetadata`와 `KnowledgeSearchQuery`에 `interaction_pair_keys`를 추가하는 실패 테스트를 작성한다.
- [ ] Qdrant payload 보존과 pair key 필터 테스트를 작성한다.
- [ ] embedding text에 검수된 상호작용 조합이 있을 때만 검색 접두어를 추가한다.
- [ ] 기존 청크와 역호환되는지 전체 테스트로 확인한다.

## 4. 문서와 최종 검증

- [ ] `data/knowledge/README.md`와 `processed/README.md`에 staging 산출물과 승인 경계를 기록한다.
- [ ] `ruff check ai_worker scripts`
- [ ] `pytest ai_worker/tests -q`
- [ ] `git diff --check`
- [ ] 변경 범위를 검토하고 최종 중간 커밋한다.

