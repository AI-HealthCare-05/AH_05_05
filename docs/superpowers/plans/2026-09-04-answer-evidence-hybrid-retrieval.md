# Answer Evidence Coverage and Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 질문 항목별 근거 커버리지를 답변 생성 전후에 강제하고 Dense·BM25·RRF 검색을 동일 평가 계약으로 비교한다.

**Architecture:** 현재 Question Resolve, Query Plan, 단계적 Retriever 구조를 유지한다. 답변 경계에는 결정론적 `MedicationEvidenceCoverageEvaluator`를 추가하고, 검색 저장소 경계에는 named dense/BM25 vector를 사용하는 실험 저장소를 추가한다. 기본은 Dense이며 평가 게이트를 통과한 경우에만 Hybrid를 활성 후보로 기록한다.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, Ruff, qdrant-client 1.19+, Qdrant BM25 sparse vectors, OpenAI dense embeddings, LangSmith

**Spec:** `docs/superpowers/specs/2026-09-04-answer-evidence-hybrid-retrieval-design.md`

## Global Constraints

- `medication_knowledge_full_v2`는 수정·삭제하지 않는다.
- 기존 Dense 벡터를 복사하며 OpenAI 임베딩 API에 문서를 재전송하지 않는다.
- 기본 검색 모드는 `DENSE`다.
- 상호작용 근거는 정확 pair가 검증된 경우에만 충족으로 판정한다.
- 검색 정확도와 잘못된 대상 혼입 방지가 지연시간보다 우선한다.
- OCR, Frontend, RDBMS 스키마는 변경하지 않는다.

---

### Task 1: 근거 커버리지 계약 정의

**Files:**
- Create: `ai_worker/domain/medication_evidence_coverage.py`
- Modify: `ai_worker/schemas/medication_chat.py`
- Test: `ai_worker/tests/domain/test_medication_evidence_coverage.py`

**Interfaces:**
- Consumes: `MedicationKnowledgeQueryPlan`, `MedicationGuideLookup`, `InteractionRuleFact`, `RetrievedKnowledgeChunk`
- Produces: `MedicationEvidenceCoverage`, `MedicationEvidenceCoverageEvaluator.evaluate(...)`

- [ ] 효능·복용법·주의사항·상호작용의 요청/충족/누락을 literal fixture로 검증하는 실패 테스트를 작성한다.
- [ ] 정확 pair가 없는 INTERACTION 청크가 상호작용 커버리지로 인정되지 않는 실패 테스트를 작성한다.
- [ ] 테스트가 타입 또는 결과 불일치로 실패하는지 확인한다.
- [ ] 최소 Pydantic 계약과 결정론적 evaluator를 구현한다.
- [ ] 도메인 테스트와 Ruff를 통과시킨다.

### Task 2: 생성 전후 커버리지 강제 및 추적

**Files:**
- Modify: `ai_worker/llm/assemblers/medication_answer_assembler.py`
- Modify: `ai_worker/llm/generators/medication_answer_generator.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/schemas/medication_chat.py`
- Test: `ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py`
- Test: `ai_worker/tests/llm/generators/test_medication_answer_generator.py`
- Test: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Interfaces:**
- Consumes: Task 1의 `MedicationEvidenceCoverage`
- Produces: 근거가 확인된 항목만 포함하는 초안, `answer.evidence_coverage` trace output, unsupported section fallback

- [ ] 누락된 요청 항목이 초안 내용에 포함되지 않는 실패 테스트를 작성한다.
- [ ] LLM이 근거 없는 항목을 추가하면 초안 fallback이 되는 실패 테스트를 작성한다.
- [ ] use case trace에 requested/covered/missing이 기록되는 실패 테스트를 작성한다.
- [ ] 각 실패가 새 계약 부재 때문인지 확인한다.
- [ ] assembler 필터, generator 후검사, use case span을 최소 구현한다.
- [ ] 관련 단위·use case 테스트와 Ruff를 통과시킨다.
- [ ] 경로를 제한해 근거 커버리지 단위를 커밋한다.

### Task 3: named dense/BM25 실험 컬렉션 저장소

**Files:**
- Create: `ai_worker/rag/vectorstores/qdrant_hybrid_knowledge_store.py`
- Modify: `ai_worker/schemas/knowledge.py`
- Test: `ai_worker/tests/rag/vectorstores/test_qdrant_hybrid_knowledge_store.py`

**Interfaces:**
- Produces: `KnowledgeSearchMode`, `QdrantHybridKnowledgeStore.create_release_collection()`, `upsert_chunks_with_dense_vectors(...)`, `search(...)`

- [ ] named `dense`와 `bm25` 스키마 생성 실패 테스트를 작성한다.
- [ ] DENSE, BM25, HYBRID가 각각 올바른 Qdrant query 계약을 만드는 실패 테스트를 작성한다.
- [ ] RRF 점수에 Dense 임계값을 적용하지 않는 실패 테스트를 작성한다.
- [ ] 실제 in-memory Qdrant가 지원하는 범위에서 payload 왕복 통합 테스트를 작성한다.
- [ ] 최소 저장소 구현 후 관련 테스트와 Ruff를 통과시킨다.

### Task 4: 기존 v2를 하이브리드 실험 릴리스로 복제

**Files:**
- Create: `scripts/clone_knowledge_release_with_bm25.py`
- Test: `ai_worker/tests/scripts/test_clone_knowledge_release_with_bm25.py`

**Interfaces:**
- Consumes: 기존 컬렉션의 point id, Dense vector, payload
- Produces: 새 불변 named-vector 컬렉션

- [ ] 원본과 대상 컬렉션 이름이 같으면 거부하는 실패 테스트를 작성한다.
- [ ] 기존 Dense vector와 payload를 보존하고 BM25 Document를 추가하는 실패 테스트를 작성한다.
- [ ] 대상 컬렉션이 있으면 덮어쓰지 않는 실패 테스트를 작성한다.
- [ ] batch scroll/upsert 및 최종 count 검증을 구현한다.
- [ ] 스크립트 테스트와 Ruff를 통과시킨다.

### Task 5: Retriever와 설정에 검색 모드 연결

**Files:**
- Modify: `ai_worker/core/config.py`
- Modify: `.env.example`
- Modify: `ai_worker/rag/retrievers/medication_knowledge_retriever.py`
- Modify: `app/dependencies/chat.py`
- Test: `ai_worker/tests/core/test_core_package.py`
- Test: `ai_worker/tests/rag/retrievers/test_medication_knowledge_retriever.py`

**Interfaces:**
- Consumes: `KNOWLEDGE_SEARCH_MODE`
- Produces: 기존 tier마다 선택한 후보 생성 모드를 적용하되 후단 적격성·boost·diversity는 재사용

- [ ] 기본값 DENSE와 허용 모드 검증 실패 테스트를 작성한다.
- [ ] Retriever가 search query와 모드를 저장소로 전달하는 실패 테스트를 작성한다.
- [ ] 설정과 dependency wiring을 최소 구현한다.
- [ ] 기존 Dense 회귀 테스트를 포함해 관련 테스트와 Ruff를 통과시킨다.
- [ ] 경로를 제한해 하이브리드 검색 단위를 커밋한다.

### Task 6: Dense/BM25/Hybrid A/B 평가와 채택 판단

**Files:**
- Modify: `ai_worker/schemas/medication_search_evaluation.py`
- Modify: `ai_worker/evaluation/medication_search_baseline_evaluator.py`
- Create: `ai_worker/evaluation/hybrid_search_comparator.py`
- Create: `scripts/compare_medication_search_modes.py`
- Test: `ai_worker/tests/evaluation/test_hybrid_search_comparator.py`
- Test: `ai_worker/tests/scripts/test_compare_medication_search_modes.py`
- Create: `docs/experiments/2026-09-04-dense-bm25-hybrid-comparison.md`

**Interfaces:**
- Consumes: 모드별 `MedicationSearchBaselineReport`
- Produces: 세 모드 지표 표와 `HYBRID` 또는 `DENSE` 채택 결정

- [ ] 정확도 개선 없이 지연시간만 개선된 Hybrid를 거부하는 실패 테스트를 작성한다.
- [ ] Hit@5/MRR 개선과 모든 guardrail 충족 시 Hybrid를 채택하는 실패 테스트를 작성한다.
- [ ] 모드별 평가 실행과 결정론적 comparator를 구현한다.
- [ ] 로컬 컬렉션을 사용할 수 있으면 실제 고정 평가를 실행하고, 없으면 명령과 미실행 사유를 보고서에 기록한다.
- [ ] 전체 AI Worker Ruff와 pytest를 실행한다.
- [ ] 평가 결과와 활성화 여부를 문서화하고 경로를 제한해 커밋한다.
