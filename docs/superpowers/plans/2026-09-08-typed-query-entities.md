# Typed Query Entities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카탈로그 기반 타입·출처 엔터티만 Query Plan에 전달해 무관한 제품 혼입을 차단한다.

**Architecture:** Resolver가 typed catalog entry를 이용해 질문에서 확인된 엔터티를 반환한다. LCEL Query Plan chain은 그 엔터티만 사용하며, Qdrant/RDBMS/활성 복용정보 공급원은 공통 카탈로그 인터페이스로 결합한다.

**Tech Stack:** Python 3.13, Pydantic v2, Tortoise ORM, Qdrant Async client, LangChain RunnableLambda, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-typed-query-entities-design.md`

## Global Constraints

- 제품명·성분명·음식명 하드코딩 금지
- RDBMS, Qdrant, 환자 활성 컨텍스트의 타입·출처를 보존
- 점수 기준 완화 금지
- 생산 코드 변경 전 실패 테스트 작성

---

### Task 1: Typed catalog contracts

**Files:**
- Modify: `ai_worker/schemas/medication_search.py`
- Modify: `ai_worker/domain/interfaces.py`
- Test: `ai_worker/tests/schemas/test_medication_search_execution_plan.py`

- [x] Write failing tests for a catalog entry that preserves type, kind, aliases, and source.
- [x] Run the focused test and confirm the new contract is missing.
- [x] Add `MedicationCatalogEntry`, typed catalog lookup, and source enum values for RDBMS/Qdrant/patient context/catalog.
- [x] Re-run focused schema tests.

### Task 2: Catalog suppliers

**Files:**
- Modify: `ai_worker/repositories/medication_expression_catalog_repository.py`
- Modify: `ai_worker/repositories/supplement_ingredient_catalog_repository.py`
- Test: `ai_worker/tests/repositories/test_medication_expression_catalog_repository.py`

- [x] Write failing tests proving product guides, interaction entities/aliases, and supplements yield typed entries.
- [x] Run focused repository tests and confirm the supplier lacks typed results.
- [x] Implement RDBMS and Qdrant typed entry suppliers with TTL cache and partial-failure-safe composite merge.
- [x] Re-run focused repository tests.

### Task 3: Resolver and Query Plan allow-list

**Files:**
- Modify: `ai_worker/domain/medication_question_resolver.py`
- Modify: `ai_worker/chains/medication_query_plan_chain.py`
- Modify: `ai_worker/rag/query_builders/medication_knowledge_query_builder.py`
- Test: `ai_worker/tests/domain/test_medication_question_resolver.py`
- Test: `ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py`

- [x] Write failing tests for the recommendation question, active-list wording, a product name, a supplement ingredient, and a food category.
- [x] Run focused tests and confirm general words currently become `DRUG` entities.
- [x] Implement exact typed-entry matching and pass resolver entities through the LCEL chain.
- [x] Remove the default unknown-token-to-`DRUG` branch for the live Resolver path while preserving legacy standalone-builder compatibility.
- [x] Re-run focused resolver and query builder tests.

### Task 4: UseCase guide lookup guard

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/use_cases/test_answer_medication_question.py`

- [x] Write a failing test proving an in-scope request with zero typed entities does not call product-guide lookup.
- [x] Run it and confirm the current broad fallback invokes lookup.
- [x] Preserve an explicit empty typed-entity set through query planning so product-guide lookup has no arbitrary candidate.
- [x] Re-run focused UseCase tests.

### Task 5: Wiring and regression verification

**Files:**
- Modify: `ai_worker/services/medication_chat_core_service.py`
- Test: `ai_worker/tests/services/test_medication_chat_core_service.py`
- Test: `ai_worker/tests/chains/test_medication_lcel_chains.py`

- [x] Verify factory wiring injects RDBMS, Qdrant, and active-context catalog sources.
- [x] Verify the Chat Core service uses the typed catalog through the existing Resolver wiring.
- [x] Run affected unit tests, Ruff, full AI worker tests, and `git diff --check`.
