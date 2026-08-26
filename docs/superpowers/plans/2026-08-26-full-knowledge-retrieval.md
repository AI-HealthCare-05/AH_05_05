# Full Knowledge Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전체 적격 PDF를 검증 가능한 release 입력으로 만들고 의약품·영양제 복합 질문을 근거 중심으로 검색한다.

**Architecture:** 기존 문서 유형별 전처리기를 전체 코퍼스 서비스로 확장한다. Chat Core는 질문 계획을 만든 뒤 후보 20개를 검색하고 엔티티·섹션 일치로 재정렬하며, 의약품 부분검색의 모호함과 Qdrant 근거를 함께 비교한다.

**Tech Stack:** Python 3.13, Pydantic, Tortoise ORM, Qdrant, OpenAI Embeddings, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-26-full-knowledge-retrieval-design.md`

## Global Constraints

- 기존 `medication_knowledge_baseline_v1` 컬렉션은 수정하거나 삭제하지 않는다.
- `DEMO_RESTRICTED`는 포함하되 내부 데모 전용 표시와 명시적 외부 임베딩 승인 플래그를 유지한다.
- `QDRANT_DISABLED_UNTIL_VERIFIED`, `STRUCTURED_SOURCE`, `OCR_REQUIRED`는 인덱싱하지 않는다.
- 최소 의미 유사도 `0.65`를 낮추지 않는다.
- 사용자의 기존 미커밋 변경을 보존한다.

---

### Task 1: 질문 분석과 검색 계획

**Files:**
- Create: `ai_worker/rag/query_builders/medication_knowledge_query_builder.py`
- Test: `ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py`

**Interfaces:**
- Produces: `MedicationKnowledgeQueryPlan(query: str, entity_names: list[str], section_types: list[KnowledgeSectionType])`
- Produces: `MedicationKnowledgeQueryBuilder.build(question: str) -> MedicationKnowledgeQueryPlan`

- [ ] 기능·섭취량·주의·상호작용 질문과 제품 제형을 구분하는 실패 테스트를 작성한다.
- [ ] 테스트를 실행해 query builder가 없어 실패하는지 확인한다.
- [ ] 원 질문을 보존하면서 결정론적으로 검색 표현을 확장하는 최소 구현을 작성한다.
- [ ] 단위 테스트와 Ruff를 실행한다.

### Task 2: 후보 확대와 재정렬

**Files:**
- Modify: `ai_worker/rag/retrievers/medication_knowledge_retriever.py`
- Modify: `ai_worker/schemas/knowledge.py`
- Test: `ai_worker/tests/rag/retrievers/test_medication_knowledge_retriever.py`

**Interfaces:**
- Consumes: `MedicationKnowledgeQueryPlan`
- Produces: `MedicationKnowledgeRetriever.search(..., limit: int) -> list[RetrievedKnowledgeChunk]`

- [ ] 최종 5건 요청이 Qdrant 후보 20건을 조회하는 실패 테스트를 작성한다.
- [ ] 성분명·약명·section type 일치 후보가 높은 순위가 되는 실패 테스트를 작성한다.
- [ ] 원시 유사도 0.65 미만 후보는 가산점과 관계없이 제외되는 테스트를 작성한다.
- [ ] 후보 수 확대, 중복 제거, 결정론적 재정렬을 구현한다.
- [ ] Retriever와 VectorStore 테스트를 실행한다.

### Task 3: 의약품·영양제 복합 라우팅

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Interfaces:**
- Consumes: 의약품 `MedicationGuideLookup`과 재정렬된 Knowledge 청크
- Produces: 근거 비교 후 `MedicationChatRoute`와 명확화 응답

- [ ] `마그네슘은 왜 먹어?`가 의약품 부분검색 모호함만으로 종료되지 않는 실패 테스트를 작성한다.
- [ ] `마그밀정 500mg`과 `타이레놀` 모호성 동작을 보존하는 테스트를 작성한다.
- [ ] RDBMS와 Qdrant 조회 결과를 모두 얻은 뒤 명확화 여부를 결정하도록 실행 순서를 수정한다.
- [ ] Use case와 Chat Core 서비스 테스트를 실행한다.

### Task 4: 범용 청크 엔티티 메타데이터

**Files:**
- Create: `ai_worker/rag/metadata/knowledge_entity_extractor.py`
- Modify: `ai_worker/rag/splitters/knowledge_splitter.py`
- Modify: `ai_worker/services/knowledge_pilot_preprocessing_service.py`
- Test: `ai_worker/tests/rag/metadata/test_knowledge_entity_extractor.py`
- Test: `ai_worker/tests/rag/splitters/test_knowledge_splitter.py`

**Interfaces:**
- Produces: `KnowledgeEntityExtractor.enrich(chunk: KnowledgeChunk) -> KnowledgeChunk`

- [ ] 공전 성분, 약물백과 제목, 복수 성분 상호작용 청크의 메타데이터 실패 테스트를 작성한다.
- [ ] 청크에 실제 포함된 엔티티만 정규화해 추가하는 구현을 작성한다.
- [ ] embedding text에 정규화된 엔티티가 포함되는지 검증한다.
- [ ] 메타데이터와 원문 불일치를 품질 차단 사유로 추가한다.
- [ ] 전처리 관련 단위 테스트를 실행한다.

### Task 5: 전체 코퍼스 전처리 release 준비

**Files:**
- Create: `ai_worker/services/knowledge_corpus_preprocessing_service.py`
- Create: `scripts/preprocess_knowledge_corpus.py`
- Test: `ai_worker/tests/services/test_knowledge_corpus_preprocessing_service.py`
- Test: `ai_worker/tests/scripts/test_preprocess_knowledge_corpus.py`
- Modify: `data/knowledge/README.md`

**Interfaces:**
- Produces: 전체 적격 문서 JSONL 청크와 `preprocessing-quality.json`

- [ ] QDRANT 출처만 선택하고 OCR·비활성·구조화 자료를 제외하는 실패 테스트를 작성한다.
- [ ] SHA-256 파일 해시로 문서 ID와 중복 제거가 결정적인지 테스트한다.
- [ ] 기존 전처리 구성요소를 재사용해 전체 코퍼스 서비스를 구현한다.
- [ ] PUBLIC과 DEMO_RESTRICTED 건수를 분리한 품질 보고서를 생성한다.
- [ ] 임베딩 없이 전체 전처리를 실행해 문서·청크·차단 건수를 확인한다.

### Task 6: 회귀 검증과 release 인덱싱 준비

**Files:**
- Modify: `data/knowledge/evaluation/knowledge_retrieval_cases.json`
- Create: `data/knowledge/reports/knowledge-full-v1-preindex.json`
- Modify: `data/knowledge/README.md`

**Interfaces:**
- Consumes: Task 5 품질 승인 청크
- Produces: 새 불변 collection을 만들 수 있는 검증 결과

- [ ] 마그네슘 기능·섭취량·주의사항과 임부 질문 평가 사례를 추가한다.
- [ ] 전체 Ruff와 AI Worker 테스트를 실행한다.
- [ ] 전처리 결정론과 차단 문서를 재실행으로 검증한다.
- [ ] 문서·청크·접근범위별 수를 기록하고 OpenAI 전송 대상을 확인한다.
- [ ] 명시적 승인 플래그로만 새 collection 인덱싱 명령을 실행한다.
